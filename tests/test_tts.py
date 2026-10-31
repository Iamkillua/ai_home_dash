import asyncio
import io
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from jarvis.app import app, settings, speech
from jarvis.config import Settings
from jarvis.services import IntegrationError, Services
from jarvis.tts import PiperSpeech
from jarvis.brain import Brain
from jarvis.voice import VoiceAgent, VoiceState


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(b"\x10\x00" * 2205)
    return buffer.getvalue()


class PiperTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_model_has_actionable_error(self):
        tts = PiperSpeech(Settings(demo=True, token="", piper_model="missing-voice.onnx"))
        self.assertFalse(tts.status()["ready"])
        with self.assertRaisesRegex(IntegrationError, "voice files are missing"):
            await tts.render("Hello")

    async def test_voice_load_is_reused_and_wav_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "voice.onnx"
            model.touch()
            Path(str(model) + ".json").write_text("{}")
            tts = PiperSpeech(Settings(demo=True, token="", piper_model=str(model)))
            voice = MagicMock()
            def generate(text, wav, **kwargs):
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(22050)
                wav.writeframes(b"\x10\x00" * 100)
            voice.synthesize_wav.side_effect = generate
            with patch("piper.PiperVoice.load", return_value=voice) as load:
                first = await tts.render("At your service.")
                await tts.render("Another request.")
            load.assert_called_once_with(str(model), use_cuda=False)
            with wave.open(io.BytesIO(first), "rb") as wav:
                self.assertEqual(wav.getframerate(), 22050)
                self.assertEqual(wav.getnframes(), 100)

    async def test_busy_synthesis_is_rejected_without_queuing(self):
        tts = PiperSpeech(Settings(demo=True, token=""))
        async with tts._busy:
            with self.assertRaisesRegex(IntegrationError, "already speaking"):
                await tts.render("Hello")

    async def test_runtime_failure_is_not_silent_browser_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "broken.onnx"
            model.touch()
            Path(str(model) + ".json").write_text("{}")
            tts = PiperSpeech(Settings(demo=True, token="", piper_model=str(model)))
            with patch("piper.PiperVoice.load", side_effect=ValueError("Invalid model")):
                with self.assertRaisesRegex(IntegrationError, "Piper synthesis failed"):
                    await tts.render("Hello")

    async def test_container_metric_scope_is_explicit(self):
        services = Services(Settings(demo=True, token="", in_container=True))
        try:
            metrics = await asyncio.to_thread(services.system)
            self.assertEqual(metrics["source"], "container-visible")
        finally:
            await services.close()

    async def test_pi_fallback_plays_piper_pcm_and_releases_speaker(self):
        import sys
        services = Services(Settings(demo=True, token=""))
        try:
            brain = Brain(services)
            brain.respond = AsyncMock(return_value={"text": "At your service."})
            piper = MagicMock()
            piper.render = AsyncMock(return_value=wav_bytes())
            state = VoiceState()
            state.update = MagicMock(wraps=state.update)
            agent = VoiceAgent(brain, state, piper)
            recognition = MagicMock()
            recognition.Recognizer.return_value.recognize_google.return_value = "Hello Jarvis"
            audio_module = MagicMock()
            audio = audio_module.PyAudio.return_value
            speaker = audio.open.return_value
            with patch.dict(sys.modules, {"speech_recognition": recognition, "pyaudio": audio_module}):
                await agent.fallback()
            piper.render.assert_awaited_once_with("At your service.")
            self.assertEqual(audio.open.call_args.kwargs["rate"], 22050)
            self.assertGreater(speaker.write.call_count, 0)
            speaker.close.assert_called_once()
            audio.terminate.assert_called_once()
            self.assertEqual(state.snapshot()["state"], "listening")
            self.assertTrue(any(call.kwargs.get("state") == "speaking" and call.kwargs.get("level", 0) > 0
                                for call in state.update.call_args_list))
        finally:
            await services.close()


class SpeechApiTests(unittest.TestCase):
    def test_tts_authentication_and_wav_response(self):
        client = TestClient(app)
        with patch.object(settings, "token", "x" * 32), patch.object(speech, "render", new=AsyncMock(return_value=wav_bytes())) as render:
            self.assertEqual(client.post("/api/tts", json={"text": "Hello"}).status_code, 401)
            result = client.post("/api/tts", json={"text": "At your service."},
                                 headers={"Authorization": "Bearer " + "x" * 32})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.headers["content-type"], "audio/wav")
            self.assertEqual(result.headers["cache-control"], "no-store")
            self.assertTrue(result.content.startswith(b"RIFF"))
            render.assert_awaited_once_with("At your service.")

    def test_tts_invalid_input_and_explicit_error(self):
        client = TestClient(app)
        self.assertEqual(client.post("/api/tts", json={"text": ""}).status_code, 422)
        self.assertEqual(client.post("/api/tts", json={"text": "x" * 4001}).status_code, 422)
        with patch.object(speech, "render", new=AsyncMock(side_effect=IntegrationError("Missing voice model"))):
            result = client.post("/api/tts", json={"text": "Hello"})
            self.assertEqual(result.status_code, 503)
            self.assertIn("Missing voice", result.json()["detail"])

    def test_health_and_nonsecret_tts_configuration(self):
        client = TestClient(app)
        self.assertEqual(client.get("/health").json(), {"status": "ok"})
        config = client.get("/api/config").json()
        self.assertEqual(config["tts"]["engine"], "piper")
        self.assertNotIn("piper_model", config)
