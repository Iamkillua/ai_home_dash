import asyncio
import copy
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import docker
import feedparser
import httpx
import psutil

from .config import Settings

log = logging.getLogger(__name__)
SUPPORTED_DOMAINS = {"light", "switch", "fan", "input_boolean", "media_player", "climate", "sensor", "binary_sensor"}
TOGGLE_DOMAINS = {"light", "switch", "fan", "input_boolean"}


class IntegrationError(RuntimeError):
    pass


class Services:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=12, follow_redirects=True)
        self._docker = None
        self._news_cache = None
        self._news_time = 0
        self._weather_cache = None
        self._weather_time = 0
        self.demo_devices = [
            {"id": "light.living_room", "name": "Living room lights", "room": "Living room", "domain": "light", "state": "on", "detail": "Warm white"},
            {"id": "light.bedroom", "name": "Bedside lamps", "room": "Bedroom", "domain": "light", "state": "off", "detail": "Ready for a quiet evening"},
            {"id": "climate.hallway", "name": "Climate control", "room": "Hallway", "domain": "climate", "state": "heat", "detail": "22 °C"},
            {"id": "switch.desk", "name": "Desk power", "room": "Study", "domain": "switch", "state": "on", "detail": "Smart outlet"},
            {"id": "media_player.living_room", "name": "Living room speaker", "room": "Living room", "domain": "media_player", "state": "idle", "detail": "Nothing playing"},
            {"id": "binary_sensor.front_door", "name": "Front door", "room": "Entrance", "domain": "binary_sensor", "state": "off", "detail": "Closed"},
        ]
        self.demo_apps = [
            {"id": "demo-homeassistant", "name": "home-assistant", "image": "homeassistant/home-assistant:stable", "status": "running", "health": "healthy", "cpu": 2.4, "memory_mb": 384, "ports": ["8123/tcp"], "description": "Home automation and device orchestration"},
            {"id": "demo-jellyfin", "name": "jellyfin", "image": "jellyfin/jellyfin:latest", "status": "running", "health": "healthy", "cpu": 0.8, "memory_mb": 218, "ports": ["8096/tcp"], "description": "Your personal media library"},
            {"id": "demo-mosquitto", "name": "mosquitto", "image": "eclipse-mosquitto:2", "status": "running", "health": "not configured", "cpu": 0.1, "memory_mb": 24, "ports": ["1883/tcp"], "description": "MQTT messaging for connected devices"},
            {"id": "demo-nodered", "name": "node-red", "image": "nodered/node-red:latest", "status": "exited", "health": "not configured", "cpu": 0, "memory_mb": 0, "ports": ["1880/tcp"], "description": "Visual automation workflows"},
        ]

    async def close(self):
        await self.http.aclose()
        if self._docker:
            await asyncio.to_thread(self._docker.close)

    async def ha(self, method: str, route: str, body=None):
        if not self.settings.ha_url or not self.settings.ha_token:
            raise IntegrationError("Home Assistant is not configured. Set its URL and token in .env.")
        try:
            response = await self.http.request(method, self.settings.ha_url + "/api/" + route,
                                               headers={"Authorization": f"Bearer {self.settings.ha_token}"}, json=body)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Home Assistant request failed: %s", type(exc).__name__)
            raise IntegrationError("Home Assistant could not be reached or rejected the request. Check its URL and token.") from exc

    async def devices(self):
        if self.settings.demo:
            return copy.deepcopy(self.demo_devices)
        states = await self.ha("GET", "states")
        result = []
        for entity in states:
            entity_id = entity["entity_id"]
            domain = entity_id.split(".")[0]
            if domain not in SUPPORTED_DOMAINS or (self.settings.entities and entity_id not in self.settings.entities):
                continue
            attrs = entity.get("attributes", {})
            detail = attrs.get("media_title") or (
                f'{attrs["current_temperature"]} °C' if "current_temperature" in attrs else
                f'{entity["state"]} {attrs.get("unit_of_measurement", "")}'.strip())
            result.append({"id": entity_id, "name": attrs.get("friendly_name", entity_id),
                           "room": attrs.get("area_name", "Home"), "domain": domain,
                           "state": entity["state"], "detail": detail})
        return result

    async def toggle_device(self, device_name: str, turn_on: bool):
        devices = await self.devices()
        matches = [d for d in devices if device_name.casefold() in {d["id"].casefold(), d["name"].casefold()}]
        if len(matches) != 1:
            raise IntegrationError("Use the exact device name or entity ID from the device list.")
        device = matches[0]
        if device["domain"] not in TOGGLE_DOMAINS:
            raise IntegrationError("Only lights, switches, fans and input booleans support this action.")
        if device["state"] in {"unavailable", "unknown"}:
            raise IntegrationError("This device is unavailable. Check its Home Assistant connection.")
        if self.settings.demo:
            next(d for d in self.demo_devices if d["id"] == device["id"])["state"] = "on" if turn_on else "off"
        else:
            await self.ha("POST", f'services/{device["domain"]}/turn_{"on" if turn_on else "off"}',
                          {"entity_id": device["id"]})
        return {"device": device["name"], "requested_state": "on" if turn_on else "off",
                "demo": self.settings.demo}

    async def play_music(self, genre: str):
        key = next((k for k in self.settings.music if k.casefold() == genre.casefold()), None)
        if self.settings.demo:
            speaker = next(d for d in self.demo_devices if d["domain"] == "media_player")
            speaker.update(state="playing", detail=f"{genre.title()} selection (demo)")
            return {"genre": genre, "demo": True}
        if key is None:
            raise IntegrationError("That genre is not configured in MUSIC_LIBRARY.")
        if not any(d["id"] == self.settings.media_player for d in await self.devices()):
            raise IntegrationError("The configured media player is not in the allowed device list.")
        await self.ha("POST", "services/media_player/play_media",
                      {"entity_id": self.settings.media_player, "media_content_id": self.settings.music[key],
                       "media_content_type": "music"})
        return {"genre": key, "player": self.settings.media_player, "requested": True}

    def system(self):
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path.cwd().anchor))
        return {"cpu": psutil.cpu_percent(interval=0.1), "ram_percent": memory.percent,
                "ram_used_gb": round(memory.used / 1024**3, 1), "ram_total_gb": round(memory.total / 1024**3, 1),
                "disk_percent": disk.percent, "disk_used_gb": round(disk.used / 1024**3, 1),
                "disk_total_gb": round(disk.total / 1024**3, 1), "uptime_seconds": int(time.time() - psutil.boot_time()),
                "hostname": __import__("socket").gethostname(),
                "source": "container-visible" if self.settings.in_container else "host"}

    def _application_snapshot(self):
        try:
            if self._docker is None:
                self._docker = docker.DockerClient(base_url=self.settings.docker_host) if self.settings.docker_host else docker.from_env()
            result = []
            for container in self._docker.containers.list(all=True):
                attrs = container.attrs
                state = attrs.get("State", {})
                cpu, memory = 0.0, 0.0
                if container.status == "running":
                    stats = container.stats(stream=False)
                    current = stats.get("cpu_stats", {})
                    previous = stats.get("precpu_stats", {})
                    delta = current.get("cpu_usage", {}).get("total_usage", 0) - previous.get("cpu_usage", {}).get("total_usage", 0)
                    system_delta = current.get("system_cpu_usage", 0) - previous.get("system_cpu_usage", 0)
                    cpus = current.get("online_cpus") or len(current.get("cpu_usage", {}).get("percpu_usage", [])) or 1
                    cpu = round(delta / system_delta * cpus * 100, 1) if system_delta > 0 else 0.0
                    mem = stats.get("memory_stats", {})
                    cache = mem.get("stats", {}).get("inactive_file", mem.get("stats", {}).get("cache", 0))
                    memory = round(max(0, mem.get("usage", 0) - cache) / 1024**2, 1)
                result.append({"id": container.id, "name": container.name, "image": attrs.get("Config", {}).get("Image", ""),
                               "status": container.status, "health": state.get("Health", {}).get("Status", "not configured"),
                               "cpu": cpu, "memory_mb": memory, "ports": list((attrs.get("NetworkSettings", {}).get("Ports") or {}).keys()),
                               "description": (attrs.get("Config", {}).get("Labels") or {}).get("org.opencontainers.image.description", "")})
            return result
        except docker.errors.DockerException as exc:
            log.warning("Docker connection failed: %s", type(exc).__name__)
            raise IntegrationError("Docker is unavailable. Check the daemon, socket permissions and DOCKER_HOST.") from exc

    async def applications(self):
        return copy.deepcopy(self.demo_apps) if self.settings.demo else await asyncio.to_thread(self._application_snapshot)

    async def container_action(self, container_id: str, action: str):
        if not self.settings.container_control:
            raise IntegrationError("Container control is disabled. Enable CONTAINER_CONTROL_ENABLED explicitly.")
        if action not in {"start", "stop", "restart"}:
            raise IntegrationError("Unsupported container action.")
        apps = await self.applications()
        if not any(app["id"] == container_id for app in apps):
            raise IntegrationError("Container not found in the monitored inventory.")
        if self.settings.demo:
            next(a for a in self.demo_apps if a["id"] == container_id)["status"] = "exited" if action == "stop" else "running"
        else:
            def execute():
                try:
                    container = self._docker.containers.get(container_id)
                    getattr(container, action)()
                except docker.errors.DockerException as exc:
                    log.warning("Container %s failed: %s", action, type(exc).__name__)
                    raise IntegrationError(f"Docker rejected the {action} operation.") from exc
            await asyncio.to_thread(execute)
        return {"action": action, "requested": True, "demo": self.settings.demo}

    async def weather(self):
        if self.settings.demo:
            return {"temperature": 24, "feels_like": 25, "humidity": 58, "wind": 11, "code": 2,
                    "location": "Home · demo", "demo": True}
        if not self.settings.latitude:
            raise IntegrationError("Set WEATHER_LATITUDE and WEATHER_LONGITUDE in .env.")
        if self._weather_cache and time.monotonic() - self._weather_time < 600:
            return copy.deepcopy(self._weather_cache)
        try:
            response = await self.http.get("https://api.open-meteo.com/v1/forecast",
                                          params={"latitude": self.settings.latitude, "longitude": self.settings.longitude,
                                                  "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code"})
            response.raise_for_status()
            c = response.json()["current"]
            data = {"temperature": c["temperature_2m"], "feels_like": c["apparent_temperature"],
                    "humidity": c["relative_humidity_2m"], "wind": c["wind_speed_10m"],
                    "code": c["weather_code"], "location": self.settings.location, "demo": False}
            self._weather_cache, self._weather_time = data, time.monotonic()
            return copy.deepcopy(data)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("Weather retrieval failed: %s", type(exc).__name__)
            raise IntegrationError("Weather provider is unavailable. Check the configured coordinates.") from exc

    async def news(self, topic: str = ""):
        if self.settings.demo:
            articles = [
                {"title": "Your morning briefing, without the endless scrolling", "source": "Demo briefing", "url": "", "summary": "Live mode reads your configured RSS feeds, including Google News RSS.", "published": "Illustrative content"},
                {"title": "A quieter home starts with thoughtful automations", "source": "Demo technology", "url": "", "summary": "This is an example entry, not a published news story.", "published": "Illustrative content"},
                {"title": "The next frontier is a little closer to home", "source": "Demo science", "url": "", "summary": "Connect NASA, BBC or your preferred RSS source for real headlines.", "published": "Illustrative content"},
            ]
            return {"articles": articles, "errors": [], "demo": True}
        if not self._news_cache or time.monotonic() - self._news_time >= 300:
            async def fetch(url):
                try:
                    response = await self.http.get(url)
                    response.raise_for_status()
                    if len(response.content) > 2_000_000:
                        raise ValueError("RSS feed exceeds 2 MB")
                    parsed = await asyncio.to_thread(feedparser.parse, response.content)
                    if parsed.bozo and not parsed.entries:
                        raise ValueError("Invalid RSS feed")
                    source = parsed.feed.get("title", urlparse(url).hostname)
                    articles = []
                    for entry in parsed.entries[:12]:
                        link = entry.get("link", "")
                        if urlparse(link).scheme not in {"http", "https"}:
                            continue
                        summary = re.sub("<[^>]+>", "", entry.get("summary", ""))[:600]
                        articles.append({"title": entry.get("title", "Untitled"), "url": link, "source": source,
                                         "summary": summary, "published": entry.get("published", "")})
                    return articles, None
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("RSS feed %s failed: %s", urlparse(url).hostname, type(exc).__name__)
                    return [], f"Could not read {urlparse(url).hostname}. Check the configured RSS feed."
            feeds = await asyncio.gather(*(fetch(url) for url in self.settings.rss))
            seen, articles = set(), []
            for items, _ in feeds:
                for item in items:
                    if item["url"] not in seen:
                        seen.add(item["url"])
                        articles.append(item)
            self._news_cache = {"articles": articles, "errors": [error for _, error in feeds if error], "demo": False}
            self._news_time = time.monotonic()
        data = copy.deepcopy(self._news_cache)
        if topic:
            terms = topic.casefold().split()
            data["articles"] = [a for a in data["articles"] if any(
                term in (a["title"] + " " + a["summary"]).casefold() for term in terms)]
        data["articles"] = data["articles"][:18]
        return data
