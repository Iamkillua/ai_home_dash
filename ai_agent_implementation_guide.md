# Implementation Guide: Custom Gemini Voice Assistant on Raspberry Pi
**Architecture Version:** Dual-Path (Live API Primary + Cascaded Text Fallback)

## Objective
Build a continuous-listening, voice-activated smart assistant running on a Raspberry Pi. The system must use a custom wake word and attempt to stream audio via the Gemini Multimodal Live API for real-time interaction. If rate limits are exceeded, it must gracefully degrade to a local STT -> Text LLM -> Local TTS fallback pipeline.

## System Architecture
The application is an asynchronous Python-based orchestrator utilizing a dual-path routing system:

*   **Continuous Listening**: Picovoice Porcupine (Offline/Local)
*   **Path A (Primary): Gemini Multimodal Live API**
    *   Streams raw microphone input over WebSockets to Google.
    *   Streams raw audio output back to the local speaker.
*   **Path B (Fallback): Cascaded Pipeline**
    *   **STT**: Google Speech Recognition or local Whisper.
    *   **LLM Brain**: Standard Gemini 1.5 Flash Text API.
    *   **TTS**: Local TTS (`pyttsx3` or `Piper`).

## Prerequisites & Credentials Required
The human user must provide the following to the agent/environment:
*   `GEMINI_API_KEY`: Google AI Studio API key.
*   `PICOVOICE_ACCESS_KEY`: Picovoice console access key.
*   `PORCUPINE_MODEL_PATH`: Absolute path to the custom `.ppn` wake word file.
*   Hardware: USB Microphone and Speaker configured in Raspberry Pi OS ALSA/PulseAudio.

## Environment Setup
Instruct the user to install these dependencies:
```bash
sudo apt-get install portaudio19-dev python3-pyaudio flac
pip install google-genai google-generativeai pvporcupine pvrecorder SpeechRecognition pyttsx3 websockets
```

## Step-by-Step Implementation Plan

### Step 1: Initialize the Fallback Modules (STT & TTS)
*   **TTS Task (`pyttsx3`)**: Create a synchronous function to speak text aloud. Ensure it blocks execution until speech is finished to prevent audio looping.
*   **STT Task (`SpeechRecognition`)**: Create a function to listen to the mic for a short duration. Implement a timeout. Return transcribed text.

### Step 2: Configure Gemini Personas (System Instructions)
*   Define the persona (e.g., "Your name is [Name]. You are a concise, helpful assistant.").
*   You will need to pass this persona to *both* the Live API configuration and the standard `GenerativeModel` initialization to ensure personality consistency across both paths.

### Step 3: Implement the Primary Live API Session (Async)
*   **Task**: Create an `async` function `run_live_api_session()` that opens a WebSocket connection using the Gemini Multimodal Live API.
*   **Logic**:
    1. Connect to the Live API using the user's API key and persona config.
    2. Start two concurrent asynchronous tasks (`asyncio.gather`):
       *   **Sender**: Reads raw audio frames from the microphone and sends them over the WebSocket.
       *   **Receiver**: Listens for incoming audio frames from the WebSocket and plays them through the speaker using `pyaudio`.
    3. Close the session after a period of user silence or a specific exit command.

### Step 4: Implement the Fallback Pipeline (Async/Sync Wrapper)
*   **Task**: Create a function `run_fallback_text_pipeline()`.
*   **Logic**: 
    1. Play a fallback notification chime (optional).
    2. Call STT module to capture user request.
    3. Send text to standard Gemini 1.5 Flash API using `model.start_chat()`.
    4. Send text response to TTS module.

### Step 5: The Main Loop & Orchestration (Wake Word)
*   **Task**: Run a continuous listening loop using Picovoice Porcupine, acting as the primary router.
*   **Logic**:
    1. Initialize `pvporcupine` and start reading audio frames.
    2. When `keyword_index >= 0` (Wake Word detected), immediately stop the wake word recorder to free up the microphone.
    3. **The Circuit Breaker**: Use a `try...except` block.
       *   `try`: `await run_live_api_session()`
       *   `except google.api_core.exceptions.ResourceExhausted` (or HTTP 429):
           *   Log the rate limit error.
           *   `await run_fallback_text_pipeline()`
    4. Once the interaction (Live or Fallback) concludes, restart the wake word recorder and resume the listening loop.

## Code Modularity Guidelines for the AI Agent
*   **Async/Await Architecture**: The primary script must be driven by `asyncio` since the Live API relies on asynchronous WebSockets. Wrap synchronous fallback functions (like `pyttsx3`) using `asyncio.to_thread` if necessary to prevent blocking the event loop.
*   **Resource Management**: The microphone (`PyAudio` or `PvRecorder`) can only be used by one process at a time. Explicitly close or pause the wake word recorder *before* starting the Live API or STT modules, and reopen it afterward.
*   **Error Handling**: Suppress non-critical ALSA/Jack audio warnings typical of Raspberry Pi environments. Ensure graceful shutdown (`KeyboardInterrupt`) releases audio hardware properly.