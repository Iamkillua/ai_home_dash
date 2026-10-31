import asyncio
import io
import logging
import threading
import wave
from pathlib import Path

from .config import Settings
from .services import IntegrationError

log = logging.getLogger(__name__)


class PiperSpeech:
    """One CPU voice model shared by browser and Pi synthesis, serialized for Pi RAM."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._voice = None
        self._lock = threading.Lock()
        self._busy = asyncio.Lock()

    def status(self):
        model = Path(self.settings.piper_model)
        return {"engine": self.settings.tts_engine, "ready": model.is_file() and Path(str(model) + ".json").is_file(),
                "voice": model.stem}

    def synthesize(self, text: str) -> bytes:
        if self.settings.tts_engine != "piper":
            raise IntegrationError("Piper is disabled. Set TTS_ENGINE=piper to use server speech.")
        with self._lock:
            if not self.status()["ready"]:
                raise IntegrationError("Piper voice files are missing. Download the model and its .onnx.json configuration; see README.md.")
            try:
                from piper import PiperVoice, SynthesisConfig
                if self._voice is None:
                    self._voice = PiperVoice.load(self.settings.piper_model, use_cuda=False)
                output = io.BytesIO()
                with wave.open(output, "wb") as wav:
                    self._voice.synthesize_wav(text, wav, syn_config=SynthesisConfig(
                        length_scale=self.settings.piper_length_scale))
                return output.getvalue()
            except Exception as exc:
                # Provider/runtime errors must reach the caller, not fall back silently.
                log.exception("Piper synthesis failed")
                raise IntegrationError(f"Piper synthesis failed ({type(exc).__name__}). Check the model and server log.") from exc

    async def render(self, text: str) -> bytes:
        if self._busy.locked():
            raise IntegrationError("Piper is already speaking. Wait for the current synthesis to finish.")
        async with self._busy:
            task = asyncio.create_task(asyncio.to_thread(self.synthesize, text))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                # Do not allow a second request to race with an abandoned CPU inference.
                await task
                raise
