import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from google.genai import errors
from pydantic import BaseModel, Field
from typing import Literal

from .brain import Brain
from .config import Settings
from .services import IntegrationError, Services
from .voice import VoiceAgent, VoiceState
from .tts import PiperSpeech

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
settings = Settings()
services = Services(settings)
brain = Brain(services)
voice_state = VoiceState()
speech = PiperSpeech(settings)
agent = VoiceAgent(brain, voice_state, speech)
bearer = HTTPBearer(auto_error=False)


async def auth(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if settings.token:
        if not credentials or not secrets.compare_digest(credentials.credentials, settings.token):
            raise HTTPException(401, "Enter the dashboard access token in Connections.")
    elif not settings.demo:
        raise HTTPException(503, "Dashboard authentication is not configured.")


async def voice_worker():
    try:
        await agent.run()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.exception("Pi voice agent stopped")
        voice_state.update(state="error", level=0,
                           error=f"Pi voice stopped ({type(exc).__name__}). Check the server log and audio configuration.")


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(voice_worker()) if settings.voice_enabled else None
    try:
        yield
    finally:
        agent.stopping = True
        if agent.recorder:
            agent.recorder.stop()
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if brain.client:
            await brain.client.aio.aclose()
        await services.close()


app = FastAPI(title="Jarvis Home Console", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


class DeviceAction(BaseModel):
    device_name: str = Field(min_length=1, max_length=200)
    turn_on: bool


class MusicAction(BaseModel):
    genre: str = Field(min_length=1, max_length=80)


class ContainerAction(BaseModel):
    action: Literal["start", "stop", "restart"]


class HistoryItem(BaseModel):
    role: Literal["user", "model"]
    text: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[HistoryItem] = Field(default_factory=list, max_length=12)
    speak_on_pi: bool = False


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


async def section(call):
    try:
        return {"data": await call(), "error": None}
    except IntegrationError as exc:
        return {"data": None, "error": str(exc)}


@app.get("/api/config")
async def config():
    return {"demo": settings.demo, "auth_required": bool(settings.token),
            "container_control": settings.container_control, "voice_enabled": settings.voice_enabled,
            "gemini_configured": bool(settings.api_key), "location": settings.location,
            "tts": speech.status()}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/tts", dependencies=[Depends(auth)])
async def tts(request: SpeechRequest):
    try:
        data = await speech.render(request.text)
        return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store"})
    except IntegrationError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/dashboard", dependencies=[Depends(auth)])
async def dashboard():
    devices, applications, weather, news = await asyncio.gather(
        section(services.devices), section(services.applications), section(services.weather), section(services.news))
    return {"demo": settings.demo, "system": await asyncio.to_thread(services.system), "devices": devices,
            "applications": applications, "weather": weather, "news": news, "voice": voice_state.snapshot()}


@app.get("/api/voice", dependencies=[Depends(auth)])
async def voice():
    return voice_state.snapshot()


@app.post("/api/devices/toggle", dependencies=[Depends(auth)])
async def toggle(action: DeviceAction):
    try:
        return await services.toggle_device(action.device_name, action.turn_on)
    except IntegrationError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/music", dependencies=[Depends(auth)])
async def music(action: MusicAction):
    try:
        return await services.play_music(action.genre)
    except IntegrationError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/containers/{container_id}/action", dependencies=[Depends(auth)])
async def container(container_id: str, action: ContainerAction):
    try:
        return await services.container_action(container_id, action.action)
    except IntegrationError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/chat", dependencies=[Depends(auth)])
async def chat(request: ChatRequest):
    if request.speak_on_pi:
        raise HTTPException(400, "Use the Pi wake word for Pi audio, or enable browser speech in the dashboard.")
    try:
        return await brain.respond(request.message, [item.model_dump() for item in request.history])
    except IntegrationError as exc:
        raise HTTPException(502, str(exc)) from exc
    except errors.APIError as exc:
        log.warning("Gemini text API failed: %s", exc.code)
        raise HTTPException(429 if exc.code == 429 else 502,
                            "Gemini rate limit reached. Try again shortly." if exc.code == 429
                            else "Gemini rejected the request. Check the API key and configured model in the server log.") from exc
    except Exception as exc:
        log.exception("Chat provider failed")
        raise HTTPException(502, "The AI provider connection failed. Check the server log and try again.") from exc


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "web", html=True), name="web")
