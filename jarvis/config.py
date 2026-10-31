import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


@dataclass
class Settings:
    demo: bool = field(default_factory=lambda: flag("DEMO_MODE", True))
    token: str = field(default_factory=lambda: os.getenv("DASHBOARD_TOKEN", ""))
    ha_url: str = field(default_factory=lambda: os.getenv("HOME_ASSISTANT_URL", "").rstrip("/"))
    ha_token: str = field(default_factory=lambda: os.getenv("HOME_ASSISTANT_TOKEN", ""))
    entities: tuple[str, ...] = field(default_factory=lambda: tuple(
        item.strip() for item in os.getenv("HOME_ASSISTANT_ENTITIES", "").split(",") if item.strip()))
    media_player: str = field(default_factory=lambda: os.getenv("MEDIA_PLAYER_ENTITY", "media_player.living_room"))
    music: dict[str, str] = field(default_factory=lambda: json.loads(os.getenv("MUSIC_LIBRARY", "{}")))
    docker_host: str = field(default_factory=lambda: os.getenv("DOCKER_HOST", ""))
    container_control: bool = field(default_factory=lambda: flag("CONTAINER_CONTROL_ENABLED"))
    latitude: str = field(default_factory=lambda: os.getenv("WEATHER_LATITUDE", ""))
    longitude: str = field(default_factory=lambda: os.getenv("WEATHER_LONGITUDE", ""))
    location: str = field(default_factory=lambda: os.getenv("WEATHER_LOCATION", "Home"))
    rss: tuple[str, ...] = field(default_factory=lambda: tuple(
        item.strip() for item in os.getenv(
            "RSS_FEEDS", "https://feeds.bbci.co.uk/news/world/rss.xml").split(",") if item.strip()))
    api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    text_model: str = field(default_factory=lambda: os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash"))
    live_model: str = field(default_factory=lambda: os.getenv(
        "GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025"))
    voice_enabled: bool = field(default_factory=lambda: flag("VOICE_ENABLED"))
    tts_engine: str = field(default_factory=lambda: os.getenv("TTS_ENGINE", "piper"))
    piper_model: str = field(default_factory=lambda: os.getenv("PIPER_MODEL_PATH", "models/en_GB-northern_english_male-medium.onnx"))
    piper_length_scale: float = field(default_factory=lambda: float(os.getenv("PIPER_LENGTH_SCALE", "1.05")))
    in_container: bool = field(default_factory=lambda: flag("JARVIS_CONTAINER"))

    def __post_init__(self):
        if self.tts_engine not in {"piper", "browser"}:
            raise ValueError("TTS_ENGINE must be piper or browser")
        if not 0.5 <= self.piper_length_scale <= 2:
            raise ValueError("PIPER_LENGTH_SCALE must be between 0.5 and 2")
        if self.voice_enabled and self.tts_engine != "piper":
            raise ValueError("Pi voice requires TTS_ENGINE=piper for its local fallback")
        if not self.demo and len(self.token) < 24:
            raise ValueError("Live mode requires DASHBOARD_TOKEN with at least 24 characters")
        if not isinstance(self.music, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in self.music.items()):
            raise ValueError("MUSIC_LIBRARY must be a JSON object mapping genres to media IDs")
        for url in self.rss:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(f"Invalid configured RSS feed: {url}")
        if bool(self.latitude) != bool(self.longitude):
            raise ValueError("Set both WEATHER_LATITUDE and WEATHER_LONGITUDE")
        if self.latitude and not (-90 <= float(self.latitude) <= 90 and -180 <= float(self.longitude) <= 180):
            raise ValueError("Weather coordinates are out of range")
