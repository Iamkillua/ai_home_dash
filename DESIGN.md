---
name: Jarvis Home Command
description: An instrument-like dashboard for seeing and addressing the state of a connected home.
colors:
  bg: "#080e14"
  surface: "#0d161f"
  surface-raised: "#121f2b"
  line: "#223441"
  line-soft: "#1a2935"
  text: "#e9f1f6"
  muted: "#9badba"
  cyan: "#7be1e8"
  amber: "#f0c17a"
  green: "#8dd6b6"
  red: "#ff9e9e"
  ink-blue: "#0a2028"
typography:
  focused-reply:
    fontFamily: '"Segoe UI", Arial, sans-serif'
    fontSize: "clamp(16px, 2vw, 22px)"
    fontWeight: 400
    lineHeight: 1.7
  display:
    fontFamily: '"Segoe UI", Arial, sans-serif'
    fontSize: "clamp(24px, 2.2vw, 34px)"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "-.025em"
  title:
    fontFamily: '"Segoe UI", Arial, sans-serif'
    fontSize: "15px"
    fontWeight: 500
    letterSpacing: "-.01em"
  body:
    fontFamily: '"Segoe UI", Arial, sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  button:
    fontFamily: '"Segoe UI", Arial, sans-serif'
    fontSize: "12px"
    fontWeight: 600
  control:
    fontFamily: '"Segoe UI", Arial, sans-serif'
    fontSize: "12px"
    fontWeight: 400
rounded:
  tight: "3px"
  control: "4px"
  panel: "5px"
  toggle: "12px"
  circle: "50%"
components:
  button-primary:
    backgroundColor: "{colors.cyan}"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.control}"
    padding: "9px 13px"
    typography: "{typography.button}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "9px 13px"
    typography: "{typography.control}"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
  command-field:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "7px 3px"
    typography: "{typography.control}"
  navigation-active:
    backgroundColor: "#11232d"
    textColor: "{colors.cyan}"
    padding: "13px 4px"
---

# Design System: Jarvis Home Command

## Overview

**Creative North Star: "The Home Command Instrument"**

Jarvis is a home-command instrument, not a wall of anonymous metrics. Ink-blue metal surfaces and fine cyan instrument lines establish a calm, technical field; warm amber marks demo or exception states. Squared panels and readable system type keep the interface operational and legible.

The central custom canvas is an audio instrument. Browser microphone input, browser Piper playback, Pi Piper fallback and Gemini Live audio drive it from real audio amplitude. The optional old browser speech engine exposes no PCM, so its animation communicates state only. Reduced-motion preferences are respected. Demo and disconnected states remain explicit rather than posing as live home data.

**Key Characteristics:**
- Ink-blue metal panels with cyan instrument detail and restrained amber markers.
- A responsive, three-column operational deck centered on the Jarvis audio core.
- Explicit provenance for live, demo, disconnected, and exception states.
- Segoe UI system typography and squared, thin-bordered surfaces.

## Colors

The palette is built from the stylesheet’s dark ink-blue base, cool cyan instrumentation, and warm amber state cues; semantic green and red distinguish status and errors.

### Primary
- **Instrument Cyan** (`#7be1e8`): Core accent for active navigation, focus, live instrument details, and interactive emphasis.
- **Warm Amber** (`#f0c17a`): Demo, listening, weather, and exception markers; it is a status cue rather than a second general-purpose accent.

### Secondary
- **Signal Green** (`#8dd6b6`): Positive connection and healthy-status indication.
- **Alert Red** (`#ff9e9e`): Error and failure messaging.

### Neutral
- **Ink Base** (`#080e14`): Page background.
- **Panel Surface** (`#0d161f`): Standard cards and panels.
- **Raised Surface** (`#121f2b`): Declared surface token for higher tonal separation.
- **Instrument Line** (`#223441`): Structural borders and dividers.
- **Soft Line** (`#1a2935`): Low-emphasis separators.
- **Readout** (`#e9f1f6`): Primary text.
- **Muted Readout** (`#9badba`): Supporting text and labels.
- **Cyan Ink** (`#0a2028`): Text on the cyan primary button.

## Typography

**Display Font:** Segoe UI (with Arial, sans-serif)  
**Body Font:** Segoe UI (with Arial, sans-serif)  
**Label/Mono Font:** Segoe UI for interface labels; Consolas (with Courier New, monospace) for application ports.

**Character:** A familiar system sans keeps operational information direct and readable. The hierarchy is compact, with restrained weights and letter spacing; tabular numerals support changing telemetry.

### Hierarchy
- **Display** (400, `clamp(24px, 2.2vw, 34px)`, 1.2 line-height): Dashboard/page heading, with slightly tightened tracking.
- **Title** (500, 15px): Panel and section headings.
- **Body** (400, 14px, 1.5 line-height): Default page text; most dense dashboard readouts use smaller component-specific sizes.
- **Button** (600, 12px): Primary action text. Compact supporting labels, status values, and table headings use their observed 8–12px component sizes.
- **Ports** (10px, Consolas/Courier New): Monospaced application port values.

## Layout

The main canvas is capped at 1770px and sits beside a fixed navigation rail. On wide desktop (>1200px), the operational deck has three columns: home devices, the central Jarvis core, and a weather/news stack. At widths up to 1200px it becomes two columns, with weather and news together in a row below. At widths up to 800px the deck becomes one column; the core comes first, followed by home devices and the remaining panels. The rail stays fixed and narrows from 94px to 78px at 1200px and 65px at 800px.

The small-screen device list expands rather than imposing a capped scrolling region. The application inventory remains a horizontally scrollable table, with a visible sideways-scroll cue and a sticky first/name column. System readouts move from four columns to two on mobile. Main gutters step from 36px to 24px to 18px across the same desktop, intermediate, and mobile ranges.

## Elevation & Depth

Depth is primarily tonal, with layered ink-blue fills, fine borders, and separators rather than elevated cards. The only explicit box shadow in the stylesheet belongs to the transient toast, giving feedback a small amount of separation from the dashboard.

### Shadow Vocabulary
- **Toast** (`box-shadow: 0 8px 25px #0005`): Transient status feedback above the page.

## Shapes

Panels are squared instrument surfaces with subtle 5px corners, not rounded floating cards. Controls use 3–4px corners; the toggle track is pill-shaped and circular indicators remain round. Thin borders define the panels and controls. The central reactor and brand mark use circular geometry as signature instrument details, not as a general panel shape.

## Components

### Buttons
- **Shape:** Compact, squared corners (4px).
- **Primary:** Cyan fill with ink-blue text; 9px 13px padding and semibold 12px type.
- **Ghost:** Transparent fill with a thin line border; the same base padding, with a tonal background and brighter border on hover.
- **Hover / Focus:** Color, background, and border transitions are 0.18s. Keyboard focus uses a 2px cyan outline with a 4px offset.

### Chips
- **Style:** Room filters and count badges use compact text, dark blue fills or transparent backgrounds, and fine borders.
- **State:** Selected filters use cyan text on a cyan-tinted surface; unselected filters stay muted.

### Cards / Containers
- **Corner Style:** 5px.
- **Background:** Ink-blue panel surface, with deeper variants for the Jarvis core and system grid.
- **Shadow Strategy:** Flat at rest; boundaries come from thin blue-gray borders. See Elevation & Depth for the toast exception.
- **Internal Padding:** Section headers generally use 20px horizontal padding; device and table content use their own compact row spacing.

### Inputs / Fields
- **Style:** The command field sits inside a dark blue, 4px-corner form shell with a fine cyan-blue border; the text input itself is transparent.
- **Focus:** The command shell changes to cyan on focus-within. Other fields and controls use the shared visible cyan focus outline.
- **Error / Disabled:** Errors use red text and a dark red-tinted notice; disabled buttons reduce opacity and show a waiting cursor.

### Navigation
- **Style:** A fixed, narrow rail stacks icon-and-label destinations. The active destination uses cyan on a dark blue highlight with a slim cyan edge; inactive destinations are muted, and hover adds a subtle surface fill. The rail remains fixed at mobile widths.

### Jarvis Audio Core
The central panel pairs a state label, instrument circle, concise response, quick prompts, and command controls. Canvas amplitude is driven only by available audio from browser input, Web Audio analysis of Piper playback, Pi Piper fallback PCM or Gemini Live audio. When a TTS source provides no PCM, show honest state-only motion rather than an invented waveform. Honor reduced-motion preferences.

The central J is a keyboard-accessible focus toggle. Focus mode fills the viewport with only the animated instrument and full reply text; other dashboard content is hidden and inert. Clicking the J again or pressing Escape restores the dashboard without changing voice-listening settings.

### Application Inventory
The fleet is a real horizontally scrollable table with status, resource, port, and action columns. On mobile, keep the application/name column sticky and show the sideways-scroll cue before the table.

## Do's and Don'ts

- **Do** keep the ink-blue metal, cyan instrument lines, warm amber demo/exception markers, and squared panel language.
- **Do** preserve explicit distinctions between demo, disconnected, error, and live states.
- **Do** drive audio amplitude visuals only from real PCM; use state-only animation when the source has no PCM.
- **Do** honor reduced-motion preferences and retain a visible keyboard focus treatment.
- **Do** keep the mobile command core first, allow the device list to expand, and preserve the table’s visible scroll cue and sticky name column.
- **Don't** present illustrative home, weather, application, or news data as live telemetry.
- **Don't** suggest a TTS waveform or measured amplitude when that audio source provides no PCM.
- **Don't** replace the instrument palette with generic bright gradients, soften panels into heavily rounded cards, or remove the fixed navigation rail.
