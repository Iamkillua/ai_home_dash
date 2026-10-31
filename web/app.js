"use strict";
const $ = (selector) => document.querySelector(selector);
const state = {
  config: null, data: null, room: "All", view: "overview", history: [],
  busy: false, loading: false, core: "idle", level: 0, recognition: null,
  wake: false, listening: false, spoken: false, voiceSequence: -1,
  token: sessionStorage.getItem("jarvis-token") || "", toastTimer: null,
  audio: null, analyser: null, stream: null, recognitionTimer: null, utterance: null,
  focused: false, coreMessage: "", focusInert: [], focusAnimations: [],
  playback: null, playbackAnalyser: null, speechController: null, speechSession: null,
};
const icon = (name) => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  svg.setAttribute("aria-hidden", "true");
  return svg;
};
const node = (tag, className, text) => {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
};
function toast(message, error = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = `toast${error ? " error" : ""}`;
  el.hidden = false;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => { el.hidden = true; }, error ? 8000 : 4500);
}
async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), path === "/api/chat" ? 90000 : 45000);
  try {
    const response = await fetch(path, {
      ...options, signal: controller.signal, cache: "no-store",
      headers: { "Content-Type": "application/json", ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}) },
    });
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401) openConnections();
      throw new Error(typeof data.detail === "string" ? data.detail : `Request rejected (${response.status}). Check your input.`);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The request timed out. Check the service connection and retry.");
    throw error;
  } finally { clearTimeout(timer); }
}
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });
function setCore(next, message) {
  state.core = next;
  $("#reactor").dataset.state = next;
  $("#core-state").textContent = ({ idle: "STANDBY", wake: "WAKE LISTENING", listening: "LISTENING", thinking: "PROCESSING", speaking: "SPEAKING", fallback: "FALLBACK", error: "OFFLINE" })[next] || next.toUpperCase();
  $("#core-caption").textContent = next === "listening" ? "LISTENING" : next === "thinking" ? "THINKING" : "J.A.R.V.I.S.";
  if (message) setCoreMessage(message);
}
function setCoreMessage(message) {
  state.coreMessage = message;
  $("#core-message").textContent = !state.focused && message.length > 210 ? `${message.slice(0, 207)}…` : message;
}
function stopFocusMotion() {
  state.focusAnimations.splice(0).forEach(animation => { animation.cancel(); });
  $(".jarvis-panel").classList.remove("focus-transition");
}
function toggleJarvisFocus() {
  const reactor = $("#reactor");
  const before = reactor.getBoundingClientRect();
  const beforeDistance = reactor.clientWidth / reactor.clientHeight < 1.15 ? 8.5 : 6.8;
  stopFocusMotion();
  state.focused = !state.focused;
  document.body.classList.toggle("jarvis-focus", state.focused);
  const button = $("#focus-jarvis");
  button.setAttribute("aria-pressed", String(state.focused));
  button.setAttribute("aria-label", state.focused ? "Return to dashboard" : "Show only J.A.R.V.I.S. and reply text");
  if (state.focused) {
    state.focusInert = [...document.querySelectorAll(".rail, .topbar, #main > :not(.deck), .home-panel, .right-stack, .jarvis-panel > :not(.reactor):not(.core-copy), #voice-description, .skip-link")];
    state.focusInert.forEach(el => { el.inert = true; });
  } else {
    state.focusInert.forEach(el => { el.inert = false; });
    state.focusInert = [];
  }
  setCoreMessage(state.coreMessage);
  button.focus({ preventScroll: true });
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || !reactor.animate) return;
  const after = reactor.getBoundingClientRect();
  if (!before.width || !before.height || !after.width || !after.height) return;
  // Match projected sphere size, not the rectangular canvas's aspect ratio.
  const afterDistance = reactor.clientWidth / reactor.clientHeight < 1.15 ? 8.5 : 6.8;
  const scale = before.height / after.height * afterDistance / beforeDistance;
  const x = before.left + before.width / 2 - after.left - after.width / 2;
  const y = before.top + before.height / 2 - after.top - after.height / 2;
  const transform = `translate(${x}px, ${y}px) scale(${scale})`;
  $(".jarvis-panel").classList.add("focus-transition");
  const expansion = reactor.animate([
    { transform, transformOrigin: "50% 50%" },
    { transform: "none", transformOrigin: "50% 50%" },
  ], { duration: state.focused ? 420 : 280, easing: "cubic-bezier(0.16, 1, 0.3, 1)" });
  state.focusAnimations.push(expansion);
  if (state.focused) {
    state.focusAnimations.push($(".core-copy").animate(
      [{ opacity: 0 }, { opacity: 1 }],
      { duration: 180, delay: 120, fill: "backwards" },
    ));
  }
  expansion.onfinish = stopFocusMotion;
}
function sectionError(container, message) {
  container.replaceChildren(node("p", "notice error", message));
}
function renderDevices() {
  const section = state.data.devices;
  if (section.error) {
    sectionError($("#device-list"), section.error);
    $("#device-count").textContent = "Offline";
    $("#home-footer").textContent = "Home Assistant disconnected";
    $("#room-filters").replaceChildren();
    return;
  }
  const devices = section.data;
  $("#device-count").textContent = `${devices.length} devices`;
  const rooms = ["All", ...new Set(devices.map(d => d.room))];
  if (!rooms.includes(state.room)) state.room = "All";
  $("#room-filters").replaceChildren(...rooms.map(room => {
    const button = node("button", state.room === room ? "selected" : "", room);
    button.type = "button";
    button.setAttribute("aria-pressed", String(state.room === room));
    button.addEventListener("click", () => { state.room = room; renderDevices(); });
    return button;
  }));
  const visible = devices.filter(d => state.room === "All" || d.room === state.room);
  $("#device-list").replaceChildren(...visible.map(device => {
    const row = node("div", "device");
    const active = ["on", "heat", "cool", "playing"].includes(device.state);
    const symbol = node("div", `device-icon${active ? " on" : ""}`);
    symbol.append(icon(({ light: "bulb", switch: "power", fan: "power", input_boolean: "power", climate: "temp", media_player: "music", binary_sensor: "door" })[device.domain] || "chip"));
    const info = node("div", "device-info");
    info.append(node("h3", "", device.name), node("p", "", `${device.room} · ${device.detail}`));
    row.append(symbol, info);
    if (["light", "switch", "fan", "input_boolean"].includes(device.domain)) {
      const button = node("button", "toggle");
      button.setAttribute("role", "switch");
      button.setAttribute("aria-checked", String(device.state === "on"));
      button.setAttribute("aria-label", `Turn ${device.name} ${device.state === "on" ? "off" : "on"}`);
      button.disabled = ["unknown", "unavailable"].includes(device.state);
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const result = await post("/api/devices/toggle", { device_name: device.id, turn_on: device.state !== "on" });
          toast(`${result.demo ? "Demo · " : ""}${result.device}: ${result.requested_state} requested`);
          await refresh();
        } catch (error) { toast(error.message, true); }
        finally { if (button.isConnected) button.disabled = false; }
      });
      row.append(button);
    } else row.append(node("span", `device-state${active ? " active" : ""}`, device.state));
    return row;
  }));
  if (!visible.length) $("#device-list").append(node("p", "muted", "No devices in this view. Configure Home Assistant entities to add devices."));
  $("#home-footer").textContent = `${state.data.demo ? "Demo home" : "Home Assistant"} · ${devices.filter(d => !["unavailable", "unknown"].includes(d.state)).length} devices available`;
}
function weatherLabel(code) {
  if (code === 0) return "Clear skies";
  if (code <= 3) return "Partly cloudy";
  if (code <= 48) return "Misty outside";
  if (code <= 67) return "Rainy";
  if (code <= 77) return "Snowy";
  if (code <= 82) return "Rain showers";
  if (code <= 86) return "Snow showers";
  return "Thunderstorms";
}
function renderWeather() {
  const section = state.data.weather;
  $(".weather-icon").hidden = Boolean(section.error);
  if (section.error) return sectionError($("#weather-content"), section.error);
  const w = section.data, main = node("div", "weather-main");
  const symbol = w.code === 0 ? "sun" : w.code <= 3 ? "cloud-sun" : w.code <= 48 ? "cloud"
    : w.code <= 67 ? "rain" : w.code <= 77 ? "snow" : w.code <= 82 ? "rain" : w.code <= 86 ? "snow" : "storm";
  $("#weather-symbol").setAttribute("href", `#i-${symbol}`);
  const temperature = node("div", "temperature", String(Math.round(w.temperature)));
  temperature.append(node("sup", "", "°"));
  const desc = node("div", "weather-description");
  desc.append(node("p", "", weatherLabel(w.code)), node("p", "muted", w.location));
  main.append(temperature, desc);
  const meta = node("div", "weather-meta");
  [["Feels", `${w.feels_like}°`], ["Humidity", `${w.humidity}%`], ["Wind", `${w.wind} km/h`]].forEach(([label, value]) => {
    const item = node("span", "", label); item.append(node("strong", "", value)); meta.append(item);
  });
  $("#weather-content").replaceChildren(main, meta);
}
function safeLink(url) {
  try { const parsed = new URL(url); return ["https:", "http:"].includes(parsed.protocol) ? parsed.href : null; }
  catch { return null; }
}
function renderNews() {
  const section = state.data.news;
  if (section.error) return sectionError($("#news-list"), section.error);
  const news = section.data, items = news.articles.slice(0, state.view === "briefing" ? 18 : 3);
  const children = items.map(article => {
    const url = safeLink(article.url);
    const item = node(url ? "a" : "div", "news-item");
    if (url) { item.href = url; item.target = "_blank"; item.rel = "noopener noreferrer"; }
    const source = node("div", "source", article.source);
    source.append(node("span", "", url ? " ↗" : " · DEMO"));
    item.append(source, node("h3", "", article.title));
    return item;
  });
  if (!children.length) children.push(node("p", "muted news-empty", "No headlines available from your configured feeds."));
  news.errors.forEach(error => children.push(node("p", "news-warning", error)));
  $("#news-list").replaceChildren(...children);
}
function renderSystem() {
  const s = state.data.system;
  $("#host-label").textContent = `${s.hostname} · ${s.source === "host" ? "live host metrics" : "container-visible metrics"}`;
  const uptimeHours = Math.floor(s.uptime_seconds / 3600);
  const metrics = [
    ["Processor", s.cpu, "%", s.source === "host" ? "Current CPU utilization" : "Kernel-visible CPU · not cgroup usage", s.cpu],
    ["Memory", s.ram_percent, "%", `${s.ram_used_gb} / ${s.ram_total_gb} GB used${s.source === "host" ? "" : " · kernel-visible RAM"}`, s.ram_percent],
    ["Storage", s.disk_percent, "%", `${s.disk_used_gb} / ${s.disk_total_gb} GB used · ${s.source === "host" ? "host volume" : "container filesystem"}`, s.disk_percent],
    ["Uptime", uptimeHours >= 24 ? Math.floor(uptimeHours / 24) : uptimeHours, uptimeHours >= 24 ? "days" : "hrs", s.source === "host" ? "Since the host last restarted" : "Kernel boot uptime · not container uptime", null],
  ];
  $("#system-content").replaceChildren(...metrics.map(([title, value, unit, detail, percent]) => {
    const item = node("div", "system-item"), top = node("div", "system-item-top");
    const metric = node("span", "metric", String(value)); metric.append(node("small", "", unit));
    top.append(node("h3", "", title), metric);
    const meter = node("div", percent === null ? "uptime-decoration" : "meter");
    if (percent !== null) {
      meter.setAttribute("role", "meter"); meter.setAttribute("aria-label", title);
      meter.setAttribute("aria-valuenow", String(percent)); meter.setAttribute("aria-valuemin", "0"); meter.setAttribute("aria-valuemax", "100");
      const fill = node("span", percent > 85 ? "warning" : "");
      fill.style.transform = `scaleX(${Math.max(0, Math.min(100, percent)) / 100})`;
      meter.append(fill);
    }
    item.append(top, meter, node("p", "", detail)); return item;
  }));
}
function renderApplications() {
  const section = state.data.applications;
  $("#app-error").hidden = !section.error;
  if (section.error) {
    $("#app-error").textContent = section.error;
    $("#app-list").replaceChildren();
    $("#app-count").textContent = "Offline";
    return;
  }
  const apps = section.data, filter = $("#app-filter").value;
  $("#app-count").textContent = `${apps.filter(a => a.status === "running").length} running`;
  const visible = apps.filter(a => filter === "all" || (filter === "running" ? a.status === "running" : a.status !== "running"));
  $("#app-list").replaceChildren(...visible.map(app => {
    const row = node("tr"), nameCell = node("td"), name = node("div", "app-name");
    const symbol = node("div", "app-symbol", app.name.slice(0, 1).toUpperCase());
    const info = node("div"); info.append(node("strong", "", app.name), node("small", "", app.image));
    name.append(symbol, info); nameCell.append(name);
    const statusCell = node("td"), status = node("span", `app-status${app.status !== "running" ? " stopped" : app.health === "unhealthy" ? " unhealthy" : ""}`);
    status.append(node("span", "status-dot"), document.createTextNode(app.status));
    statusCell.append(status, node("small", "app-health", app.health));
    const ports = node("td", "port", app.ports.join(", ") || "—");
    const actionsCell = node("td"), actions = node("div", "app-actions");
    const ask = node("button", "", "Ask");
    ask.setAttribute("aria-label", `Ask Jarvis about ${app.name}`);
    ask.addEventListener("click", () => sendMessage(`Jarvis, tell me about the ${app.name} application, its health and resource usage.`));
    actions.append(ask);
    if (state.config.container_control) {
      const action = app.status === "running" ? "stop" : "start";
      const control = node("button", "", action[0].toUpperCase() + action.slice(1));
      control.setAttribute("aria-label", `${action} ${app.name}`);
      control.addEventListener("click", async () => {
        if (!window.confirm(`${state.data.demo ? "Simulate" : "Confirm"} ${action} for ${app.name}? ${action === "stop" ? "This will interrupt its service." : "This starts the existing container; it does not create one."}`)) return;
        control.disabled = true;
        try { await post(`/api/containers/${encodeURIComponent(app.id)}/action`, { action }); toast(`${app.name}: ${action} requested`); await refresh(); }
        catch (error) { toast(error.message, true); }
        finally { if (control.isConnected) control.disabled = false; }
      });
      actions.append(control);
    }
    actionsCell.append(actions);
    row.append(nameCell, statusCell, node("td", "", `${app.cpu}%`), node("td", "", `${app.memory_mb} MB`), ports, actionsCell);
    return row;
  }));
  if (!visible.length) { const row = node("tr"), cell = node("td", "muted", "No applications match this view."); cell.colSpan = 6; row.append(cell); $("#app-list").append(row); }
  $("#fleet-footer").textContent = `${state.data.demo ? "Demo Docker inventory" : "Docker engine"} · ${apps.length} applications monitored`;
}
function renderConnections() {
  if (!state.data) return;
  const sections = [["Home Assistant", state.data.devices], ["Docker", state.data.applications], ["Weather", state.data.weather], ["RSS feeds", state.data.news]];
  $("#connection-status").replaceChildren(...sections.map(([name, section]) => {
    const item = node("div", "connection-item", name);
    item.append(node("small", "", section.error || (state.data.demo ? "Illustrative demo data" : "Connected")));
    return item;
  }));
}
async function refresh() {
  if (state.loading) return;
  state.loading = true; $("#refresh").disabled = true;
  try {
    state.data = await api("/api/dashboard");
    $("#global-error").hidden = true;
    $("#demo-notice").hidden = !state.data.demo;
    $("#demo-notice > span:nth-child(2)").replaceChildren(
      node("strong", "", "Demo environment"),
      document.createTextNode(` · Home, weather, applications and news are illustrative. System metrics are ${state.data.system.source === "host" ? "from this host" : "container-visible, not full Pi telemetry"}.`));
    $("#mode-badge").textContent = state.data.demo ? "DEMO MODE" : "HOME CONNECTED";
    $("#mode-badge").classList.toggle("demo", state.data.demo);
    $("#rail-status").textContent = "Online";
    $("#updated").textContent = "Just updated";
    renderDevices(); renderWeather(); renderNews(); renderSystem(); renderApplications(); renderConnections();
    updateVoice(state.data.voice);
  } catch (error) {
    $("#global-error").textContent = `${error.message} Displayed values may be stale.`;
    $("#global-error").hidden = false;
    $("#rail-status").textContent = "Offline";
    $("#updated").textContent = "Unavailable";
    $("#mode-badge").textContent = "DISCONNECTED";
  } finally { state.loading = false; $("#refresh").disabled = false; }
}
function appendChat(role, text, tools = []) {
  const entry = node("div", "chat-entry");
  entry.append(node("strong", "", role === "user" ? "YOU" : "J.A.R.V.I.S."));
  const p = node("p");
  // Plain-text rendering prevents tool output or RSS content from injecting markup.
  const urlPattern = /https?:\/\/[^\s<>"\])]+/g;
  let last = 0, match;
  while ((match = urlPattern.exec(text))) {
    p.append(document.createTextNode(text.slice(last, match.index)));
    const url = safeLink(match[0]);
    if (url) {
      const link = node("a", "", match[0]); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; p.append(link);
    } else p.append(document.createTextNode(match[0]));
    last = match.index + match[0].length;
  }
  p.append(document.createTextNode(text.slice(last))); entry.append(p);
  if (tools.length) entry.append(node("div", "tool-chips", tools.map(t => `${t.name}${t.result.error ? " · failed" : ""}`).join(" / ")));
  $("#chat-log").append(entry);
  while ($("#chat-log").children.length > 30) $("#chat-log").firstElementChild.remove();
  $("#conversation-count").textContent = String($("#chat-log").children.length);
  $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
}
async function sendMessage(message) {
  message = message.trim();
  if (!message || state.busy) return;
  state.busy = true; $("#send-command").disabled = true;
  stopSpeech();
  stopRecognition(false);
  setCore("thinking", "One moment. Putting the pieces together.");
  appendChat("user", message);
  $("#command").value = "";
  try {
    const result = await post("/api/chat", { message, history: state.history.slice(-12) });
    state.history.push({ role: "user", text: message }, { role: "model", text: result.text });
    state.history = state.history.slice(-12);
    appendChat("model", result.text, result.tools);
    setCoreMessage(result.text);
    $(".conversation").open = true;
    await refresh();
    if ($("#speech-enabled").checked) speak(result.text);
    else setCore(state.wake ? "wake" : "idle");
  } catch (error) {
    setCore("error", error.message); appendChat("model", error.message); toast(error.message, true);
  } finally {
    state.busy = false; $("#send-command").disabled = false;
    if (state.wake && !state.spoken) scheduleWake();
  }
}
async function speak(text) {
  if (state.config?.tts?.engine !== "piper") return speakBrowser(text);
  stopRecognition(false);
  const session = {};
  state.speechSession = session;
  state.spoken = true;
  $("#stop-speaking").hidden = false;
  setCore("thinking");
  const controller = new AbortController();
  state.speechController = controller;
  const timeout = setTimeout(() => controller.abort(), 90000);
  let audio;
  try {
    audio = new AudioContext();
    state.playback = audio;
    await audio.resume();
    if (audio.state !== "running") throw new Error("Audio playback is blocked. Allow sound for this site and retry.");
    const response = await fetch("/api/tts", {
      method: "POST", headers: { "Content-Type": "application/json",
        ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}) },
      body: JSON.stringify({ text: text.slice(0, 4000) }), signal: controller.signal,
    });
    if (!response.ok) {
      const result = await response.json();
      throw new Error(typeof result.detail === "string" ? result.detail : "Piper rejected the speech request.");
    }
    const buffer = await audio.decodeAudioData(await response.arrayBuffer());
    if (state.speechSession !== session) return;
    const source = audio.createBufferSource();
    source.buffer = buffer;
    const analyser = audio.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser); analyser.connect(audio.destination);
    state.playbackAnalyser = analyser;
    const complete = () => {
      if (state.speechSession !== session) return;
      stopSpeech();
      setCore(state.wake ? "wake" : "idle");
      if (state.wake) scheduleWake();
    };
    source.onended = complete;
    setCore("speaking");
    source.start();
  } catch (error) {
    if (state.speechSession !== session) return;
    stopSpeech();
    setCore("error");
    toast(error.name === "AbortError" ? "Piper speech timed out. Check the server and model." : error.message, true);
    // Do not silently switch to the robotic browser voice.
    if (state.wake) scheduleWake();
  } finally {
    clearTimeout(timeout);
    if (state.speechSession !== session && audio && audio.state !== "closed") {
      audio.close().catch(error => console.warn("Speech cleanup failed", error));
    }
  }
}
function speakBrowser(text) {
  if (!("speechSynthesis" in window)) {
    toast("Browser speech is unavailable. Pi voice is configured separately.", true);
    return setCore(state.wake ? "wake" : "idle");
  }
  stopRecognition(false);
  const utterance = new SpeechSynthesisUtterance(text);
  state.utterance = utterance;
  const voices = speechSynthesis.getVoices();
  const voice = voices.find(v => v.lang === "en-GB") || voices.find(v => v.lang.startsWith("en"));
  if (voice) utterance.voice = voice;
  utterance.rate = 1; utterance.pitch = 0.9;
  utterance.onstart = () => {
    if (state.utterance !== utterance) return;
    state.spoken = true; setCore("speaking"); $("#stop-speaking").hidden = false;
  };
  const complete = () => {
    if (state.utterance !== utterance) return;
    state.utterance = null;
    state.spoken = false; $("#stop-speaking").hidden = true; state.level = 0;
    setCore(state.wake ? "wake" : "idle");
    if (state.wake) scheduleWake();
  };
  utterance.onend = complete;
  utterance.onerror = (event) => {
    if (state.utterance !== utterance) return;
    if (!["interrupted", "canceled"].includes(event.error)) toast(`Browser speech failed: ${event.error}. Use text or the Pi voice assistant.`, true);
    complete();
  };
  speechSynthesis.speak(utterance);
}
function stopSpeech() {
  state.speechSession = null;
  state.speechController?.abort();
  state.speechController = null;
  state.playbackAnalyser = null;
  state.playback?.close().catch(error => console.warn("Piper audio cleanup failed", error));
  state.playback = null;
  state.utterance = null;
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  state.spoken = false; $("#stop-speaking").hidden = true; state.level = 0;
}
async function connectMicrophone() {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone requires localhost or HTTPS and a supported browser.");
  state.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  state.audio = new AudioContext();
  await state.audio.resume();
  state.analyser = state.audio.createAnalyser(); state.analyser.fftSize = 256;
  state.audio.createMediaStreamSource(state.stream).connect(state.analyser);
}
function releaseMicrophone() {
  state.stream?.getTracks().forEach(track => track.stop());
  state.stream = null; state.analyser = null;
  state.audio?.close().catch(error => console.warn("Microphone audio context cleanup failed", error));
  state.audio = null; state.level = 0;
}
function stopRecognition(disableWake = true) {
  clearTimeout(state.recognitionTimer);
  if (disableWake) { state.wake = false; updateWakeButton(); }
  const recognition = state.recognition;
  state.recognition = null; state.listening = false;
  if (recognition) recognition.abort();
  releaseMicrophone();
  $("#microphone").classList.remove("listening");
}
function scheduleWake() {
  clearTimeout(state.recognitionTimer);
  state.recognitionTimer = setTimeout(() => {
    if (state.wake && !state.busy && !state.spoken && !state.recognition) startRecognition(true);
  }, 700);
}
function updateWakeButton() {
  $("#wake-toggle").setAttribute("aria-pressed", String(state.wake));
  $("#wake-toggle").textContent = state.wake ? "Disable browser wake listening" : "Enable browser wake listening";
}
async function startRecognition(wake = false) {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) { state.wake = false; updateWakeButton(); return toast("Speech recognition is not supported here. Type a request or use Pi wake-word audio.", true); }
  if (state.recognition || state.busy || state.spoken) return;
  try {
    await connectMicrophone();
    const recognition = new Recognition();
    state.recognition = recognition;
    recognition.lang = "en-US"; recognition.interimResults = true; recognition.continuous = false;
    state.listening = true; setCore(wake ? "wake" : "listening");
    $("#microphone").classList.add("listening");
    $("#voice-description").textContent = wake ? "Say “Jarvis” followed by your request. Browser recognition may use a cloud service." : "Listening. Say your request.";
    let submitted = false;
    recognition.onresult = event => {
      const transcript = Array.from(event.results).map(result => result[0].transcript).join(" ");
      if (!wake) $("#command").value = transcript;
      if (!event.results[event.results.length - 1].isFinal || submitted) return;
      if (wake && !/\bjarvis\b/i.test(transcript)) return;
      const request = wake ? transcript.replace(/^.*?\bjarvis\b[,.\s]*/i, "").trim() : transcript.trim();
      if (request) { submitted = true; sendMessage(`Jarvis, ${request}`); }
      else {
        // Hearing just the wake word switches to one-shot command capture.
        stopRecognition(false);
        state.recognitionTimer = setTimeout(() => startRecognition(false), 300);
      }
    };
    recognition.onerror = event => {
      if (event.error === "aborted" || event.error === "no-speech") return;
      state.wake = false; updateWakeButton();
      toast(`Microphone recognition failed (${event.error}). Check browser permissions or use text.`, true);
    };
    recognition.onend = () => {
      if (state.recognition !== recognition) return;
      state.recognition = null; state.listening = false; releaseMicrophone();
      $("#microphone").classList.remove("listening");
      if (!state.busy && !state.spoken) setCore(state.wake ? "wake" : "idle");
      if (state.wake && !state.busy && !state.spoken) scheduleWake();
    };
    recognition.start();
  } catch (error) {
    stopRecognition(); setCore("error"); toast(`Cannot start microphone: ${error.message}`, true);
  }
}
function updateVoice(voice) {
  $("#voice-footer").textContent = state.config?.voice_enabled ? `Pi voice · ${voice.state}` : "Pi wake-word voice · not enabled";
  if (!state.config?.voice_enabled || voice.sequence === state.voiceSequence) return;
  state.voiceSequence = voice.sequence;
  if (!state.busy && !state.spoken && !state.listening) {
    setCore(voice.state === "disabled" ? "idle" : voice.state, voice.transcript || undefined);
    state.level = voice.level;
  }
  if (voice.error) $("#voice-description").textContent = voice.error;
  else $("#voice-description").textContent = "Pi voice connected. Say Jarvis to begin.";
}
async function pollVoice() {
  if (!state.config?.voice_enabled || document.hidden) return;
  try { updateVoice(await api("/api/voice")); }
  catch (error) { $("#voice-footer").textContent = `Pi voice connection failed: ${error.message}`; }
}
function openConnections() { $("#connections").hidden = false; $("#token").value = state.token; $("#connections").scrollIntoView({ behavior: "smooth", block: "start" }); }
function applyView() {
  const selected = location.hash.slice(1) || "overview";
  state.view = ["overview", "devices", "applications", "system", "briefing"].includes(selected) ? selected : "overview";
  $("#main").classList.toggle("focused-view", ["devices", "briefing"].includes(state.view));
  $("#main").dataset.view = state.view;
  document.querySelectorAll(".nav-link[data-view]").forEach(link => {
    const active = link.dataset.view === state.view;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  });
  $("#page-title").hidden = state.view === "overview";
  $("#page-title").textContent = ({ overview: "", devices: "Home, thoughtfully orchestrated.", applications: "Every application. Accounted for.", system: "The machinery behind the magic.", briefing: "The world, without the noise." })[state.view];
  if (state.data) renderNews();
  if (state.view !== "overview") setTimeout(() => document.getElementById(state.view)?.scrollIntoView({ behavior: "smooth", block: "start" }), 30);
}
async function animateCore() {
  const samples = new Uint8Array(256), frequency = new Uint8Array(128);
  const getAudioFrame = () => {
    let level = state.level, bands = [level, level, level];
    const analyser = state.spoken ? state.playbackAnalyser : state.listening ? state.analyser : null;
    if (analyser) {
      analyser.getByteTimeDomainData(samples);
      level = Math.min(1, Math.sqrt(samples.reduce((sum, sample) => sum + ((sample - 128) / 128) ** 2, 0) / samples.length) * 5);
      analyser.getByteFrequencyData(frequency);
      const average = (start, end) => {
        let sum = 0;
        for (let i = start; i < end; i++) sum += frequency[i];
        return sum / (end - start) / 255;
      };
      bands = [average(0, 8), average(8, 32), average(32, 128)];
    }
    return { level, bands, state: state.core };
  };
  const notify = message => {
    $("#graphics-notice").textContent = message;
    $("#graphics-notice").hidden = !message;
  };
  try {
    const { createCore } = await import("./visualizer.js");
    createCore($("#core-canvas"), getAudioFrame, notify);
  } catch (error) {
    console.error("Particle visualization could not load", error);
    notify("Particle graphics could not load. Run npm run build and refresh. Audio and controls remain available.");
  }
}
$("#command-form").addEventListener("submit", event => { event.preventDefault(); sendMessage($("#command").value); });
document.querySelectorAll("[data-prompt]").forEach(button => button.addEventListener("click", () => sendMessage(button.dataset.prompt)));
$("#refresh").addEventListener("click", refresh);
$("#app-filter").addEventListener("change", () => { if (state.data) renderApplications(); });
$("#open-connections").addEventListener("click", openConnections);
$("#demo-connections").addEventListener("click", openConnections);
$("#close-connections").addEventListener("click", () => { $("#connections").hidden = true; $("#open-connections").focus(); });
$("#token-form").addEventListener("submit", async event => {
  event.preventDefault(); state.token = $("#token").value.trim();
  if (state.token) sessionStorage.setItem("jarvis-token", state.token); else sessionStorage.removeItem("jarvis-token");
  await refresh();
});
$("#microphone").addEventListener("click", () => {
  if (state.listening) { stopRecognition(); setCore("idle"); }
  else { stopSpeech(); startRecognition(false); }
});
$("#wake-toggle").addEventListener("click", () => {
  if (state.wake) { stopRecognition(); setCore("idle"); }
  else {
    if (!window.confirm("Browser wake listening uses browser speech recognition, which may send microphone audio to its speech provider. For offline wake-word detection, configure Porcupine on the Pi. Enable browser listening?")) return;
    state.wake = true; updateWakeButton(); startRecognition(true);
  }
});
$("#stop-speaking").addEventListener("click", () => { stopSpeech(); setCore(state.wake ? "wake" : "idle"); if (state.wake) scheduleWake(); });
$("#speech-enabled").addEventListener("change", () => { if (!$("#speech-enabled").checked) { stopSpeech(); setCore("idle"); } });
$("#focus-jarvis").addEventListener("click", toggleJarvisFocus);
window.addEventListener("resize", stopFocusMotion);
matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", stopFocusMotion);
window.addEventListener("keydown", event => {
  if (event.key === "Escape" && state.focused) { event.preventDefault(); toggleJarvisFocus(); }
});
window.addEventListener("hashchange", applyView);
window.addEventListener("pagehide", () => { stopRecognition(); stopSpeech(); });
document.addEventListener("visibilitychange", () => { if (document.hidden) { stopRecognition(); stopSpeech(); } else refresh(); });
function tick() { $("#clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }); }
async function init() {
  state.coreMessage = $("#core-message").textContent;
  tick(); setInterval(tick, 1000); animateCore(); applyView();
  try {
    state.config = await api("/api/config");
    $("#speech-enabled").parentElement.lastChild.textContent = state.config.tts?.engine === "piper"
      ? " Spoken replies · Piper" : " Spoken replies · browser";
    if (state.config.tts?.engine === "piper" && !state.config.tts.ready) {
      $("#voice-description").textContent = "Piper voice not installed. Download the voice model; see README.md.";
    }
    if (state.config.auth_required && !state.token) openConnections();
    await refresh();
    setInterval(() => { if (!document.hidden) refresh(); }, 30000);
    let voicePolling = false;
    setInterval(async () => { if (voicePolling) return; voicePolling = true; try { await pollVoice(); } finally { voicePolling = false; } }, 300);
  } catch (error) { $("#global-error").textContent = `Cannot connect to the Jarvis service: ${error.message}`; $("#global-error").hidden = false; setCore("error"); }
}
init();
