import asyncio
import logging
import math
import os
import struct
import threading
import io
import wave

from google.genai import errors, types

from .brain import PERSONA, TOOLS, Brain
from .tts import PiperSpeech

log = logging.getLogger(__name__)


async def hardware(call, *args, **kwargs):
    """Finish in-flight hardware I/O before allowing its owning stream to close."""
    task = asyncio.create_task(asyncio.to_thread(call, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class VoiceState:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = {"state": "disabled", "level": 0, "transcript": "", "error": "", "sequence": 0}

    def update(self, **values):
        with self._lock:
            self._state.update(values)
            self._state["sequence"] += 1

    def snapshot(self):
        with self._lock:
            return dict(self._state)


class VoiceAgent:
    def __init__(self, brain: Brain, state: VoiceState, speech: PiperSpeech | None = None):
        self.brain, self.state = brain, state
        self.stopping = False
        self.recorder = self.porcupine = None
        self.history = []
        self.speech = speech or PiperSpeech(brain.services.settings)

    async def run(self):
        # Optional hardware dependencies do not prevent the web console starting.
        import pvporcupine
        from pvrecorder import PvRecorder

        if not self.brain.client:
            raise ValueError("VOICE_ENABLED requires GEMINI_API_KEY")
        if self.brain.services.settings.demo:
            raise ValueError("Pi voice requires DEMO_MODE=false so spoken actions cannot be mistaken for real ones")
        access_key = os.getenv("PICOVOICE_ACCESS_KEY", "")
        model_path = os.getenv("PORCUPINE_MODEL_PATH", "")
        if not access_key or not os.path.isfile(model_path):
            raise ValueError("Configure PICOVOICE_ACCESS_KEY and a Raspberry Pi Jarvis PORCUPINE_MODEL_PATH")
        self.porcupine = pvporcupine.create(access_key=access_key, keyword_paths=[model_path])
        try:
            self.recorder = PvRecorder(device_index=int(os.getenv("AUDIO_DEVICE_INDEX", "-1")),
                                       frame_length=self.porcupine.frame_length)
            self.recorder.start()
            self.state.update(state="wake", error="")
            while not self.stopping:
                frame = await hardware(self.recorder.read)
                if self.porcupine.process(frame) < 0:
                    continue
                self.recorder.stop()
                try:
                    self.state.update(state="listening", error="")
                    await self.live()
                except errors.APIError as exc:
                    if exc.code != 429:
                        raise
                    log.warning("Gemini Live rate limited; entering cascaded STT/text/TTS")
                    self.state.update(state="fallback", error="Live API rate limited; using the cascaded voice path.")
                    await self.fallback()
                except Exception as exc:
                    # A Live WebSocket can signal 429 as a transport close, not APIError.
                    if "429" not in str(exc) and "RESOURCE_EXHAUSTED" not in str(exc):
                        raise
                    log.warning("Gemini Live transport rate limited; entering cascaded path")
                    self.state.update(state="fallback", error="Live API rate limited; using the cascaded voice path.")
                    await self.fallback()
                finally:
                    if not self.stopping:
                        self.recorder.start()
                        self.state.update(state="wake", level=0)
        finally:
            if self.recorder:
                self.recorder.delete()
            if self.porcupine:
                self.porcupine.delete()

    async def live(self):
        import pyaudio

        audio = pyaudio.PyAudio()
        microphone = speaker = None
        try:
            device = int(os.getenv("AUDIO_DEVICE_INDEX", "-1"))
            microphone = audio.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True,
                                    frames_per_buffer=1024, input_device_index=None if device < 0 else device)
            speaker = audio.open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"], system_instruction=PERSONA, tools=[TOOLS],
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig())
            async with self.brain.client.aio.live.connect(
                    model=self.brain.services.settings.live_model, config=config) as session:
                async def sender():
                    while True:
                        data = await hardware(microphone.read, 1024, exception_on_overflow=False)
                        if self.state.snapshot()["state"] != "speaking":
                            await session.send_realtime_input(
                                audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000"))

                async def receiver():
                    transcript = ""
                    async for message in session.receive():
                        if message.tool_call:
                            responses = []
                            for call in message.tool_call.function_calls:
                                result = await self.brain.execute(call.name, call.args or {})
                                responses.append(types.FunctionResponse(id=call.id, name=call.name, response=result))
                            await session.send_tool_response(function_responses=responses)
                        content = message.server_content
                        if content and content.input_transcription:
                            self.state.update(transcript=content.input_transcription.text or "")
                        if content and content.output_transcription:
                            transcript += content.output_transcription.text or ""
                            self.state.update(transcript=transcript)
                        if content and content.interrupted:
                            self.state.update(state="listening", level=0)
                        if message.data:
                            samples = struct.unpack(f"<{len(message.data) // 2}h", message.data)
                            level = min(1, math.sqrt(sum(s*s for s in samples) / max(1, len(samples))) / 12000)
                            self.state.update(state="speaking", level=level)
                            await hardware(speaker.write, message.data)
                        if content and content.turn_complete:
                            self.state.update(state="listening", level=0)
                            return

                tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
                try:
                    done, _ = await asyncio.wait(tasks,
                        timeout=float(os.getenv("VOICE_SESSION_SECONDS", "60")),
                        return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                    if not done:
                        log.info("Live voice session ended after the configured silence/session timeout")
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            if microphone:
                microphone.stop_stream()
                microphone.close()
            if speaker:
                speaker.stop_stream()
                speaker.close()
            audio.terminate()

    async def fallback(self):
        import speech_recognition as sr

        def transcribe():
            recognizer = sr.Recognizer()
            device = int(os.getenv("AUDIO_DEVICE_INDEX", "-1"))
            with sr.Microphone(device_index=None if device < 0 else device) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.3)
                recording = recognizer.listen(source, timeout=7, phrase_time_limit=15)
            stt = os.getenv("VOICE_STT", "google")
            if stt == "whisper":
                return recognizer.recognize_whisper(recording, model=os.getenv("WHISPER_MODEL", "base"))
            if stt != "google":
                raise ValueError("VOICE_STT must be google or whisper")
            return recognizer.recognize_google(recording)

        try:
            message = await hardware(transcribe)
        except (sr.WaitTimeoutError, sr.UnknownValueError):
            log.info("Fallback STT timed out or could not understand speech")
            self.state.update(transcript="I didn't catch that. Say Jarvis to try again.", level=0)
            return
        self.state.update(state="thinking", transcript=message)
        reply = await self.brain.respond(message, self.history)
        self.history.extend([{"role": "user", "text": message}, {"role": "model", "text": reply["text"]}])
        self.history = self.history[-12:]
        self.state.update(state="thinking", transcript=reply["text"], level=0)

        data = await self.speech.render(reply["text"][:4000])

        def speak():
            import pyaudio
            audio = pyaudio.PyAudio()
            speaker = None
            try:
                with wave.open(io.BytesIO(data), "rb") as wav:
                    speaker = audio.open(format=audio.get_format_from_width(wav.getsampwidth()),
                                         channels=wav.getnchannels(), rate=wav.getframerate(), output=True)
                    while frames := wav.readframes(1024):
                        samples = struct.unpack(f"<{len(frames) // 2}h", frames)
                        level = min(1, math.sqrt(sum(s*s for s in samples) / len(samples)) / 12000)
                        self.state.update(state="speaking", level=level)
                        speaker.write(frames)
            finally:
                if speaker:
                    speaker.stop_stream()
                    speaker.close()
                audio.terminate()
        await hardware(speak)
        self.state.update(state="listening", level=0)
