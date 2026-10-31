import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from google.genai import types

from jarvis.brain import Brain
from jarvis.config import Settings
from jarvis.services import IntegrationError, Services
from jarvis.voice import VoiceAgent, VoiceState, hardware


class ServicesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.services = Services(Settings(demo=True, token=""))
        self.brain = Brain(self.services)

    async def asyncTearDown(self):
        await self.services.close()

    async def test_demo_toggle_is_explicit_and_persistent(self):
        result = await self.services.toggle_device("light.living_room", False)
        self.assertEqual(result["requested_state"], "off")
        self.assertEqual((await self.services.devices())[0]["state"], "off")
        self.assertTrue(result["demo"])

    async def test_non_toggle_entities_and_unknown_names_rejected(self):
        for name in ["climate.hallway", "light.unknown", "Living room"]:
            with self.assertRaises(IntegrationError):
                await self.services.toggle_device(name, True)

    async def test_tool_types_and_unknown_tools_rejected(self):
        result = await self.brain.execute("toggle_device", {"device_name": "light.living_room", "turn_on": "false"})
        self.assertIn("error", result)
        self.assertIn("error", await self.brain.execute("shell", {"command": "anything"}))

    async def test_music_demo_and_application_conversation(self):
        await self.services.play_music("jazz")
        self.assertEqual((await self.services.devices())[4]["state"], "playing")
        result = await self.brain.respond("Jarvis, tell me about my applications")
        self.assertIn("3 of 4", result["text"])
        self.assertEqual(result["tools"][0]["name"], "list_applications")

    async def test_news_demo_cannot_claim_live_news(self):
        result = await self.brain.respond("Google, give me news")
        self.assertTrue(result["demo"])
        self.assertEqual(result["tools"][0]["name"], "get_news")
        self.assertIn("illustrative", result["text"])

    async def test_container_control_disabled_by_default(self):
        with self.assertRaises(IntegrationError):
            await self.services.container_action("demo-jellyfin", "stop")
        self.services.settings.container_control = True
        await self.services.container_action("demo-jellyfin", "stop")
        self.assertEqual((await self.services.applications())[1]["status"], "exited")

    async def test_live_allowlist_and_action_request(self):
        self.services.settings.demo = False
        self.services.settings.entities = ("light.office",)
        states = [
            {"entity_id": "light.office", "state": "off", "attributes": {"friendly_name": "Office light"}},
            {"entity_id": "lock.door", "state": "locked", "attributes": {}},
            {"entity_id": "light.bedroom", "state": "on", "attributes": {}},
        ]
        self.services.ha = AsyncMock(return_value=states)
        devices = await self.services.devices()
        self.assertEqual([d["id"] for d in devices], ["light.office"])
        await self.services.toggle_device("Office light", True)
        self.services.ha.assert_awaited_with("POST", "services/light/turn_on", {"entity_id": "light.office"})

    async def test_live_music_must_use_configured_library_and_allowed_player(self):
        self.services.settings.demo = False
        self.services.settings.music = {"jazz": "media-source://media_source/local/jazz.mp3"}
        self.services.devices = AsyncMock(return_value=[{"id": self.services.settings.media_player}])
        self.services.ha = AsyncMock(return_value=[])
        await self.services.play_music("Jazz")
        self.services.ha.assert_awaited_once()
        with self.assertRaises(IntegrationError):
            await self.services.play_music("arbitrary-genre")

    async def test_rss_fetch_filter_and_partial_error(self):
        self.services.settings.demo = False
        self.services.settings.rss = ("https://example.org/rss", "https://example.org/broken")
        feed = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Science</title>
        <item><title>Moon mission launches</title><link>https://example.org/moon</link><description>Science news</description></item>
        <item><title>Other news</title><link>https://example.org/other</link></item></channel></rss>"""
        def handler(request):
            return httpx.Response(200 if request.url.path == "/rss" else 500, content=feed)
        await self.services.http.aclose()
        self.services.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await self.services.news("moon")
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(result["articles"][0]["source"], "Science")
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual((await self.services.news("unmatched"))["articles"], [])

    async def test_text_gemini_tool_result_roundtrip(self):
        self.services.settings.demo = False
        fake = MagicMock()
        call = types.FunctionCall(name="list_applications", args={})
        responses = [
            MagicMock(candidates=[MagicMock(content=types.Content(role="model", parts=[types.Part(function_call=call)]))], function_calls=[call]),
            MagicMock(candidates=[MagicMock(content=types.Content(role="model", parts=[types.Part(text="Your apps are running.")]))], function_calls=[], text="Your apps are running."),
        ]
        fake.aio.models.generate_content = AsyncMock(side_effect=responses)
        self.brain.client = fake
        self.services.applications = AsyncMock(return_value=[{"name": "jellyfin", "status": "running"}])
        result = await self.brain.respond("How are my applications?")
        self.assertEqual(result["text"], "Your apps are running.")
        self.assertEqual(result["tools"][0]["result"]["applications"][0]["name"], "jellyfin")
        self.assertEqual(fake.aio.models.generate_content.await_count, 2)

    async def test_voice_state_and_hardware_cancellation_cleanup(self):
        voice = VoiceState()
        voice.update(state="speaking", level=0.5)
        self.assertEqual(voice.snapshot()["sequence"], 1)
        completed = []
        import time
        def io():
            time.sleep(0.03)
            completed.append(True)
        task = asyncio.create_task(hardware(io))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(completed, [True])

    async def test_voice_live_is_primary_and_rate_limit_routes_fallback(self):
        import sys
        from google.genai import errors
        fake_porcupine = MagicMock()
        recorder = MagicMock()
        porcupine = MagicMock(frame_length=512)
        porcupine.process.return_value = 0
        fake_porcupine.create.return_value = porcupine
        recorder_module = MagicMock()
        recorder_module.PvRecorder.return_value = recorder
        self.brain.client = MagicMock()
        self.services.settings.demo = False
        agent = VoiceAgent(self.brain, VoiceState())
        agent.live = AsyncMock(side_effect=errors.APIError(429, {"error": {"message": "Quota exceeded"}}))
        async def fallback():
            agent.stopping = True
        agent.fallback = AsyncMock(side_effect=fallback)
        with patch.dict(sys.modules, {"pvporcupine": fake_porcupine, "pvrecorder": recorder_module}), \
                patch.dict(os.environ, {"PICOVOICE_ACCESS_KEY": "test", "PORCUPINE_MODEL_PATH": "test.ppn"}), \
                patch("jarvis.voice.os.path.isfile", return_value=True):
            await agent.run()
        agent.live.assert_awaited_once()
        agent.fallback.assert_awaited_once()
        recorder.stop.assert_called()
        recorder.delete.assert_called_once()
        porcupine.delete.assert_called_once()

    async def test_live_stream_audio_tools_and_cleanup(self):
        import struct
        import sys
        audio_module = MagicMock()
        microphone, speaker = MagicMock(), MagicMock()
        microphone.read.return_value = b"\0" * 2048
        audio = MagicMock()
        audio.open.side_effect = [microphone, speaker]
        audio_module.PyAudio.return_value = audio
        session = MagicMock()
        session.send_realtime_input = AsyncMock()
        session.send_tool_response = AsyncMock()
        tool = MagicMock(data=None, server_content=None,
                         tool_call=MagicMock(function_calls=[types.FunctionCall(id="call-1", name="list_applications", args={})]))
        content = MagicMock(input_transcription=None, output_transcription=MagicMock(text="At your service."),
                            interrupted=False, turn_complete=True)
        pcm = struct.pack("<4h", 6000, -6000, 6000, -6000)
        output = MagicMock(data=pcm, server_content=content, tool_call=None)
        async def receive():
            yield tool
            yield output
        session.receive = receive
        connection = MagicMock()
        connection.__aenter__ = AsyncMock(return_value=session)
        connection.__aexit__ = AsyncMock(return_value=False)
        self.brain.client = MagicMock()
        self.brain.client.aio.live.connect.return_value = connection
        voice = VoiceState()
        voice.update = MagicMock(wraps=voice.update)
        agent = VoiceAgent(self.brain, voice)
        with patch.dict(sys.modules, {"pyaudio": audio_module}):
            await agent.live()
        speaker.write.assert_called_once_with(pcm)
        session.send_tool_response.assert_awaited_once()
        self.assertEqual(session.send_tool_response.call_args.kwargs["function_responses"][0].id, "call-1")
        self.assertTrue(any(call.kwargs.get("state") == "speaking" and call.kwargs.get("level", 0) > 0
                            for call in voice.update.call_args_list))
        self.assertEqual(voice.snapshot()["state"], "listening")
        self.assertEqual([call.kwargs["rate"] for call in audio.open.call_args_list], [16000, 24000])
        microphone.close.assert_called_once()
        speaker.close.assert_called_once()
        audio.terminate.assert_called_once()


class ConfigurationTests(unittest.TestCase):
    def test_live_mode_requires_strong_token(self):
        with self.assertRaises(ValueError):
            Settings(demo=False, token="")
        self.assertFalse(Settings(demo=False, token="x" * 32).demo)

    def test_invalid_coordinates_rejected(self):
        with self.assertRaises(ValueError):
            Settings(demo=True, latitude="91", longitude="0")
