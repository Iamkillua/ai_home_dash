FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY frontend ./frontend
COPY web ./web
RUN npm run build

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libportaudio2 portaudio19-dev gcc alsa-utils flac \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-voice.txt ./
RUN pip install -r requirements-voice.txt \
    && apt-get purge -y --auto-remove gcc portaudio19-dev \
    && groupadd --gid 10001 jarvis \
    && useradd --uid 10001 --gid jarvis --create-home jarvis \
    && mkdir /models /wake \
    && chown jarvis:jarvis /models /wake

COPY --chown=jarvis:jarvis jarvis ./jarvis
COPY --from=frontend --chown=jarvis:jarvis /build/web ./web
USER jarvis
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "jarvis.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
