# Jarvis Home Command

A browser command console backed by an asynchronous Python service. Includes Home Assistant devices, actual host CPU/RAM/storage/uptime, Open-Meteo weather, RSS headlines, Docker monitoring, conversation and a canvas voice instrument.

**It starts in demo mode.** Devices, weather, containers and headlines are labeled examples; system metrics are real measurements visible to the Python process. Demo chat is a deterministic local simulator, not Gemini, and never operates your actual home. Piper speech works in demo mode without Gemini.

## Quick start on Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m piper.download_voices en_GB-northern_english_male-medium --download-dir models
.\.venv\Scripts\python.exe -m uvicorn jarvis.app:app --host 127.0.0.1 --port 8000
```

Open <http://localhost:8000>. Python 3.11+ is recommended (also tested on 3.14). No Node build or external fonts are needed.
The checked-in `web/visualizer.js` is a self-contained Three.js bundle, so normal Python startup does not need Node or Internet for graphics. To change the visualization source (`frontend/core.js`), install Node.js 22+ and run `npm ci` then `npm run build`. `npm run check` checks renderer and application syntax. The Docker build runs the Node build in a separate stage; the running image contains no Node toolchain.

Click the particle spheres to show only the visualization and full reply text. The live spheres expand smoothly from their dashboard position into the full-screen focus view, then return with a shorter transition when clicked again or **Esc** is pressed. Reduced-motion users switch instantly. Existing voice sessions continue; entering this view does not enable microphone listening. The spheres are also a keyboard-accessible focus control, with no lettering over the particles.

## Monochrome particle visualization

The black-and-white dashboard uses five concentric Three.js particle spheres of different radii, sharing one center with no overlaid J or logo. Low, middle and high audio frequency bands deform the particles on the GPU, with real amplitude controlling expansion and brightness. Browser Piper playback, microphone input and Pi voice amplitude all use the existing audio path; idle/thinking motion is state motion, not invented speech.

The renderer is limited to 30 FPS, capped pixel density and 11,200 mobile / 20,200 desktop particles, without postprocessing. It pauses when hidden or offscreen and disposes its GPU resources on navigation. Reduced-motion users get static geometry with amplitude-based brightness, not rotating or expanding spheres. WebGL failure shows an explicit notice and a lightweight 2D particle projection with 4,500 particles; context loss pauses graphics until recovery without stopping audio or controls. A Pi hosts the service, but the browser device renders the graphics—Pi browser performance still needs to be measured on the target hardware.

## Piper natural speech

Piper 1.8.0 is installed by `requirements.txt`. The default is a CPU-only, medium-quality British-English male voice suitable as a starting point for the Pi 4B. Download the model once with `python -m piper.download_voices en_GB-northern_english_male-medium --download-dir models`. This downloads the `.onnx` and matching `.onnx.json`; both are required. The model is loaded lazily and reused, with one synthesis at a time to bound Pi memory usage.

`TTS_ENGINE=piper` generates browser replies through the authenticated `/api/tts` endpoint and plays WAV audio in the browser. The animated circle reads actual playback amplitude through Web Audio. It also replaces `pyttsx3` in the Pi's cascaded voice fallback. Gemini Live remains the primary Pi voice path. Missing models, synthesis errors and playback permission problems are visible; the service does not silently switch back to the robotic browser voice. `TTS_ENGINE=browser` explicitly selects the old browser speech engine, but cannot be used with Pi voice enabled.

Set `PIPER_MODEL_PATH` to the model file and `PIPER_LENGTH_SCALE` (default `1.05`) to adjust pace; larger values slow speech. The browser sends at most 4,000 characters per spoken reply; longer text stays available in the conversation/focus view. First synthesis includes model-load time. Speed on this Windows preview is not a Pi performance guarantee; measure it alongside your containers and use short replies.

Piper is GPL-3.0; the default voice model card identifies a CC BY-SA 4.0 dataset. See `VOICE-LICENSES.md` for attribution and sources. Review replacement voice licensing before downloading or distributing models.

## Docker on a Raspberry Pi 4B

Use **64-bit Raspberry Pi OS** and Docker with the Compose plugin. The image uses Python 3.11 and CPU inference, and is intended for native ARM64 on the Pi or AMD64 on a PC; no `platform` setting forces emulation.

From this project directory, copy `.env.example` to `.env` **only if you do not already have a configured `.env`**, then edit it. Create `models` and `wake` directories. Build the image with `docker compose build`. Download the voice using the image rather than installing Python on the Pi host:

```
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" -v "$PWD/models:/models:rw" jarvis python -m piper.download_voices en_GB-northern_english_male-medium --download-dir /models
docker compose up -d
```

These commands run in the Pi's Linux shell. The base configuration works with `VOICE_ENABLED=false` and leaves audio devices inaccessible. `docker compose logs -f jarvis` shows failures. `docker compose down` stops the stack. Downloading voices requires Internet, but Piper synthesis is offline afterward. Models are mounted read-only during normal service operation, not baked into the image. If selecting another voice, set `PIPER_VOICE` to its filename stem; Compose sets `PIPER_MODEL_PATH=/models/<voice>.onnx`.

The dashboard binds to **127.0.0.1:8000** on the host. Use a host reverse proxy for trusted HTTPS LAN access. For temporary access from a trusted isolated LAN only, set `JARVIS_BIND_ADDRESS=0.0.0.0` in `.env` and recreate the service; set `DASHBOARD_TOKEN` even in demo mode before exposing it. Do not publish this service or its Docker API to the Internet. A container's `homeassistant.local` may not resolve: use your Home Assistant LAN IP or a resolvable DNS name.

### Pi microphone and speaker

Configure the ALSA default USB microphone/speaker on the Pi first. Copy the Pi-compatible Jarvis Porcupine `.ppn` file to `wake/jarvis.ppn`, set `DEMO_MODE=false`, Gemini/Picovoice credentials and a strong dashboard token in `.env`. Add `AUDIO_GID` using the numeric group ID printed by `getent group audio` on the Pi. Start with:

```
docker compose -f compose.yaml -f compose.pi-voice.yaml up -d --build
```

The override enables Pi voice, maps only `/dev/snd`, and adds the host audio group. The image runs as non-root UID 10001, without privileged mode, with a read-only root filesystem and writable temporary storage. If your USB audio needs a custom ALSA configuration, mount a known host `asound.conf` to `/etc/asound.conf:ro` through your own override. PulseAudio-only setups need explicit socket/auth configuration and are not covered by the ALSA override. One worker owns the microphone; do not scale replicas when using Pi voice.

### Docker monitoring and metric scope

Compose uses a **read-only API proxy**, on an internal network with no published port, rather than mounting the Docker socket into Jarvis. Container GET requests (including stats/inspection) are allowed; POST is disabled. This still exposes container metadata through Docker inventory: use it only in a trusted deployment. The proxy itself has Docker socket access and must be trusted; a `:ro` socket mount alone is not an API permission boundary.

Compose intentionally forces `CONTAINER_CONTROL_ENABLED=false`; this stack monitors existing applications, it cannot start/stop them. Container control outside this stack remains an explicit opt-in. Do not loosen proxy permissions merely to hide a dashboard error.

Under Docker, telemetry is labeled **container-visible**. psutil CPU/RAM report kernel-visible values, storage reports the mounted container filesystem, and uptime is kernel boot uptime—not cgroup memory/CPU usage, all Pi disks, or container uptime. Actual per-application CPU/memory comes from Docker's stats API. No privileged host mount is needed or implied. For complete Pi storage/hardware telemetry, use a dedicated host exporter rather than treating these values as full host telemetry.

## Raspberry Pi deployment

On Raspberry Pi OS, create a virtual environment, install `requirements.txt`, copy `.env.example` to `.env`, and run `python -m uvicorn jarvis.app:app --host 127.0.0.1 --port 8000` from this directory. A single Uvicorn worker is required when voice is enabled, because one process owns the microphone.

For LAN access, use a HTTPS reverse proxy such as Caddy, with this service bound to localhost. Binding directly to `0.0.0.0` without HTTPS is suitable only for a trusted, isolated LAN: tokens and chat would travel unencrypted. Do not expose it to the Internet. Browser microphones require HTTPS or localhost; the Pi audio path does not have this browser restriction.

Run the service as an unprivileged user with read/write access only to the required audio devices and configuration. Keep `.env` private. Add your process manager or systemd unit with this project as its working directory and the virtual-environment Python as the executable. Do not use Uvicorn reload for unattended voice operation.

## Connect your home

Set these values in `.env` and restart the service:

| Setting | Purpose |
|---|---|
| `DEMO_MODE=false` | Enables actual integrations and Gemini conversation |
| `DASHBOARD_TOKEN` | Required in live mode; generate a random token of at least 24 characters |
| `HOME_ASSISTANT_URL` | Your Home Assistant base URL |
| `HOME_ASSISTANT_TOKEN` | A long-lived access token from your Home Assistant profile |
| `HOME_ASSISTANT_ENTITIES` | Optional comma-separated allowlist of entity IDs |
| `MEDIA_PLAYER_ENTITY` | Speaker used by `play_music` |
| `MUSIC_LIBRARY` | JSON mapping of genres to actual playable media-source IDs or URLs |
| `WEATHER_LATITUDE`, `WEATHER_LONGITUDE` | Home weather coordinates |
| `WEATHER_LOCATION` | Display name, e.g. `Home` |
| `RSS_FEEDS` | Comma-separated, administrator-trusted HTTP(S) RSS/Atom feeds |
| `GEMINI_API_KEY` | Server-side Google AI Studio key |
| `GEMINI_TEXT_MODEL`, `GEMINI_LIVE_MODEL` | Models currently available to your account |

Generate a token locally with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Enter it in **Connections** in the dashboard. It is held in the current tab's session storage and sent as a bearer token. Do not put API keys or Home Assistant tokens in the browser. The static dashboard and non-secret configuration are public; all telemetry and action routes are protected when a token is set. Demo mode binds to localhost by default and can also be protected by setting a token.

Home Assistant lights, switches, fans and input booleans have explicit on/off controls. Climate, media players and sensors are displayed read-only. The media-player tool uses `play_media`; it does not invent playlist URLs. Configure your real media library. Home Assistant service responses acknowledge the request; the subsequent dashboard poll reads actual state. Names come from entity `friendly_name`; room falls back to `Home` when `area_name` is absent in the entity attributes.

## Applications and containers

Docker monitoring lists existing running and stopped containers with image, health check state, CPU, memory and exposed port keys. Ports are informational, not automatically exposed browser links. Ask Jarvis about your applications through the dashboard or voice; the same inventory tool is available to both Gemini paths.

The service uses the local Docker engine or `DOCKER_HOST`. **Docker socket access is effectively host-administrator access**, even when the UI is read-only. Prefer a properly configured socket proxy for read-only monitoring, or a dedicated host with restricted access; never publish an unauthenticated Docker TCP socket.

To start or stop **existing** containers, explicitly set `CONTAINER_CONTROL_ENABLED=true`. The UI asks for confirmation. The API also supports `restart`. Container operations are not AI tools: conversational requests cannot start, stop, create or delete containers. This is a monitor and an existing-container control surface, not a container deployment editor.

## RSS-only news and information

The default example configuration includes BBC, NASA and Google News RSS. Feeds are cached for five minutes and read concurrently; failures are visible, including partial feed failures. Results include original source links. Gemini's `get_news(topic)` filters configured headlines and summaries. Requests involving Google or news use this tool rather than Google Search grounding. If the configured feeds cannot answer a question, Jarvis must say so.

Feeds are set by the server administrator, not accepted from chat or request URLs. RSS text is untrusted and displayed as text, never injected as HTML. Configure a range of feeds appropriate to your interests. General web search, full article scraping and fabricated answers are deliberately not provided.

## Voice: primary Live audio and rate-limit fallback

`ai_agent_implementation_guide.md` is the source architecture. The implementation uses the maintained `google-genai` SDK for both paths rather than the guide's older `google-generativeai`/Gemini 1.5 interface. Model availability changes: replace the example model names with supported models in your account rather than relying on a preview identifier indefinitely.

For non-Docker deployment, install the Pi system dependencies (`portaudio19-dev`, `python3-pyaudio`, and `flac`) using Raspberry Pi OS's package manager, then install `requirements-voice.txt` in your virtual environment and download the Piper model. The Docker image includes these libraries. Supply:

```dotenv
VOICE_ENABLED=true
PICOVOICE_ACCESS_KEY=your-key
PORCUPINE_MODEL_PATH=/absolute/path/to/raspberry-pi-jarvis.ppn
AUDIO_DEVICE_INDEX=-1
VOICE_STT=google
VOICE_SESSION_SECONDS=60
```

`DEMO_MODE` must be false for Pi voice. Obtain a **custom Jarvis Porcupine model for the target Pi platform**; arbitrary `.ppn` files are not portable between operating systems or architectures. Configure the USB microphone and speaker with ALSA/PulseAudio first.

The voice worker:

1. Listens offline with Porcupine for Jarvis, then stops its recorder before another path acquires the microphone.
2. Streams microphone PCM (16 kHz mono) to Gemini Live and plays returned PCM (24 kHz mono). Input is not forwarded during playback to reduce speaker feedback. One request/response completes the session, or it closes after the configured maximum duration.
3. On Live HTTP 429/resource-exhaustion, logs the failure and captures a new utterance with SpeechRecognition, calls Gemini text with the same persona/tools, then synthesizes Piper speech and plays it through the local speaker. **Repeat your request when entering the fallback path**; the failed Live microphone stream cannot be retrospectively transcribed.
4. Releases streams and resumes Porcupine. Non-rate-limit provider/hardware failures are not silently retried or disguised as fallback: they stop the worker and appear on the dashboard; fix the configuration and restart the service.

Use `VOICE_STT=whisper` for local fallback recognition; separately install `SpeechRecognition[whisper-local]` and its model/runtime dependencies (and `ffmpeg`). Google recognition requires Internet and sends audio to its speech service. Local wake-word detection does not mean Gemini audio stays local: the Live path streams it to Google.

Both AI paths have `list_devices`, `toggle_device`, `play_music`, `list_applications`, `get_system`, `get_weather` and `get_news`. Tools validate names, domains and argument types; no arbitrary shell execution or generic Home Assistant service tool is exposed.

The dashboard circle reacts to actual microphone amplitude, browser Piper playback, returned Pi Gemini Live PCM, and Pi Piper fallback PCM. The optional old browser speech engine exposes no PCM, so it changes speaking state without pretending to measure amplitude. No fake equalizer is used.

Browser speech is a separate convenience text/STT/TTS path. Enable **browser wake listening** explicitly to listen for "Jarvis"; it may use the browser's cloud recognizer, is not an offline Porcupine substitute, and stops when the tab is hidden. Permissions and browser support vary. Text interaction always remains available.

## Checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check web\app.js
```

The tests cover demo tools/actions, allowlists, authentication, RSS isolation/filtering, errors, Gemini multi-turn function dispatch, container gating and primary/fallback voice routing. Real Pi audio, external accounts, Home Assistant and Docker cannot be verified without the corresponding hardware and credentials.

With Docker installed, `docker compose config --quiet` validates the stack without starting it. Actual image builds and Pi audio/device permissions require a running Docker engine and target hardware.

For browser interaction checks, install `requirements-dev.txt` and run `python -m playwright install chromium`. With a demo server running on localhost:8000, run `python tests/browser_smoke.py`; it exercises desktop and mobile controls and writes screenshots to `JARVIS_SCREENSHOTS` (or `screenshots` if unset).
Run `python tests/visualizer_smoke.py` against the same demo server for Three.js rendering, real Piper audio reactivity, idle rotation, WebGL context recovery and fallback behavior.
