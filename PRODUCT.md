# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A smart-home owner using a browser to inspect and operate their home, with a Raspberry Pi running the Python service and voice assistant.

## Product Purpose

Jarvis brings Home Assistant devices, host resources, weather, RSS news, and Docker applications into one dashboard and conversational interface.

## Operating Context

The user confirmed a browser dashboard with a Raspberry Pi Python backend, Home Assistant and Docker integrations, and clearly labeled demo mode until credentials are configured.

## Capabilities and Constraints

Voice follows `ai_agent_implementation_guide.md`: local Porcupine wake word, Gemini Live audio, and rate-limit fallback to speech recognition, Gemini text, and local Piper neural speech synthesis. Piper also generates browser audio independently of Gemini. Both AI paths use function calling for device and music operations and application information. News and information retrieval uses configured RSS feeds, not Google Search grounding. Docker packaging targets a 64-bit Pi 4B, with explicit ALSA access and read-only container monitoring.

Credentials and hardware must be supplied by the user. Deployment location, RSS choices, media library mappings, and available devices are configured locally. Container control is opt-in and never exposed as an AI tool.

## Brand Commitments

The assistant is named Jarvis, displayed as J.A.R.V.I.S., responds to Jarvis, and has a concise, witty butler personality. The user approved a modern black-and-white dashboard with five concentric Three.js particle spheres responsive to real speech audio, without a J or lettering over the spheres. Clicking the visualization opens only the spheres and full reply text; clicking again or pressing Escape returns. The overview has no promotional headline or greeting subtitle.

## Evidence on Hand

The supplied implementation guide is the only incumbent project file. No live credentials, home inventory, weather location, or container inventory were supplied. Demonstration data must not be presented as live telemetry.
