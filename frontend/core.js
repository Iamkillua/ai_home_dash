import * as THREE from "three";

const vertexShader = `
  uniform float uTime;
  uniform float uLevel;
  uniform float uDensity;
  uniform vec3 uBands;
  attribute float aSeed;
  varying float vShade;
  void main() {
    vec3 direction = normalize(position);
    float low = sin(direction.y * 6.0 + uTime * 2.0 + aSeed) * uBands.x;
    float mid = sin(direction.x * 11.0 - uTime * 1.4) * uBands.y;
    float high = sin(direction.z * 18.0 + uTime * 2.4) * uBands.z;
    float ripple = (low * .13 + mid * .07 + high * .035) * uLevel;
    vec3 p = position * (1.0 + uLevel * .14 + ripple);
    vec4 view = modelViewMatrix * vec4(p, 1.0);
    vShade = .35 + .65 * (direction.z * .5 + .5);
    gl_PointSize = clamp((2.5 + aSeed * 1.2 + uLevel * 1.1) * uDensity / -view.z, 1.0, 5.0);
    gl_Position = projectionMatrix * view;
  }
`;
const fragmentShader = `
  uniform float uOpacity;
  uniform float uBrightness;
  varying float vShade;
  void main() {
    float d = length(gl_PointCoord - vec2(.5));
    if (d > .5) discard;
    float alpha = smoothstep(.5, .15, d) * uOpacity;
    gl_FragColor = vec4(vec3(vShade * uBrightness), alpha);
  }
`;

function sphereGeometry(count, radius) {
  const positions = new Float32Array(count * 3);
  const seeds = new Float32Array(count);
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - 2 * (i + .5) / count;
    const r = Math.sqrt(1 - y * y);
    const angle = i * goldenAngle;
    positions.set([Math.cos(angle) * r * radius, y * radius, Math.sin(angle) * r * radius], i * 3);
    seeds[i] = ((i * 73) % 101) / 101;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 1));
  return geometry;
}

export function createCore(canvas, getAudioFrame, notify) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false, powerPreference: "low-power" });
  } catch (error) {
    console.warn("Three.js WebGL unavailable; using particle projection", error);
    notify("3D graphics unavailable. Using a lightweight particle view.");
    return createFallback(canvas, getAudioFrame);
  }
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, .1, 30);
  camera.position.z = 6.8;
  const group = new THREE.Group();
  scene.add(group);
  const compact = matchMedia("(max-width: 800px)").matches;
  const definitions = [
    { radius: 1.4, count: compact ? 3600 : 6800, opacity: .45 },
    { radius: 1.15, count: compact ? 2600 : 5000, opacity: .58 },
    { radius: .9, count: compact ? 2000 : 3200, opacity: .7 },
    { radius: .65, count: compact ? 1500 : 2600, opacity: .85 },
    { radius: .42, count: compact ? 1500 : 2600, opacity: .9 },
  ];
  const meshes = definitions.map((definition, index) => {
    const material = new THREE.ShaderMaterial({
      vertexShader, fragmentShader, transparent: true, depthWrite: false,
      uniforms: {
        uTime: { value: 0 }, uLevel: { value: 0 }, uBands: { value: new THREE.Vector3() },
        uOpacity: { value: definition.opacity }, uDensity: { value: 4 },
        uBrightness: { value: 1 },
      },
    });
    const mesh = new THREE.Points(sphereGeometry(definition.count, definition.radius), material);
    mesh.rotation.set(index * .4, index * .7, index * .25);
    group.add(mesh);
    return mesh;
  });
  canvas.dataset.renderer = "three";
  canvas.dataset.spheres = String(meshes.length);
  canvas.dataset.particles = String(definitions.reduce((total, sphere) => total + sphere.count, 0));
  canvas.dataset.layout = "concentric";
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let visible = true, stopped = false, frameId = 0, previous = 0, time = 0, level = 0, lost = false;
  let width = 0, height = 0;
  function resize() {
    // CSS transforms must not feed back into the renderer's size or projection.
    width = canvas.clientWidth; height = canvas.clientHeight;
    if (width < 1 || height < 1) return;
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, compact ? 1.25 : 1.5));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.position.z = camera.aspect < 1.15 ? 8.5 : 6.8;
    camera.updateProjectionMatrix();
    const density = Math.min(devicePixelRatio || 1, 1.5) * height / 100;
    meshes.forEach(mesh => { mesh.material.uniforms.uDensity.value = density; });
    if (!lost) renderer.render(scene, camera);
  }
  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  function request() {
    if (!stopped && !lost && !document.hidden && visible && !frameId) frameId = requestAnimationFrame(draw);
  }
  function draw(now) {
    frameId = 0;
    if (stopped || lost || document.hidden || !visible) return;
    if (now - previous < (reduced.matches ? 100 : 1000 / 30)) { request(); return; }
    const delta = Math.min((now - previous) / 1000, .1);
    previous = now;
    const audio = getAudioFrame();
    level += (audio.level - level) * (1 - Math.exp(-delta * 12));
    if (!reduced.matches) time += delta;
    canvas.dataset.audioLevel = level.toFixed(3);
    canvas.dataset.motion = reduced.matches ? "reduced" : "animated";
    meshes.forEach((mesh, index) => {
      const uniforms = mesh.material.uniforms;
      uniforms.uTime.value = reduced.matches ? 0 : time;
      uniforms.uLevel.value = reduced.matches ? 0 : level;
      uniforms.uBands.value.set(...audio.bands);
      uniforms.uBrightness.value = audio.state === "error" ? .65 : 1 + level * .5;
      if (!reduced.matches) {
        const speed = audio.state === "thinking" ? .22 : .065;
        mesh.rotation.y += delta * speed * (index % 2 ? -1 : 1);
        mesh.rotation.z += delta * .018 * (index % 2 ? 1 : -1);
      }
    });
    if (width > 0 && height > 0) renderer.render(scene, camera);
    request();
  }
  const intersection = new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting;
    if (!visible) { cancelAnimationFrame(frameId); frameId = 0; }
    else request();
  });
  intersection.observe(canvas);
  function visibility() {
    if (document.hidden) { cancelAnimationFrame(frameId); frameId = 0; }
    else { previous = performance.now(); request(); }
  }
  function contextLost(event) {
    event.preventDefault(); lost = true;
    cancelAnimationFrame(frameId); frameId = 0;
    canvas.dataset.renderer = "context-lost";
    notify("3D graphics paused. Waiting for WebGL to recover; audio and controls remain available.");
  }
  function contextRestored() {
    lost = false; canvas.dataset.renderer = "three";
    notify(""); resize(); request();
  }
  canvas.addEventListener("webglcontextlost", contextLost);
  canvas.addEventListener("webglcontextrestored", contextRestored);
  document.addEventListener("visibilitychange", visibility);
  function dispose() {
    stopped = true; cancelAnimationFrame(frameId);
    observer.disconnect(); intersection.disconnect();
    document.removeEventListener("visibilitychange", visibility);
    canvas.removeEventListener("webglcontextlost", contextLost);
    canvas.removeEventListener("webglcontextrestored", contextRestored);
    meshes.forEach(mesh => { mesh.geometry.dispose(); mesh.material.dispose(); });
    renderer.dispose();
    window.removeEventListener("pagehide", pagehide);
    window.removeEventListener("pageshow", pageshow);
  }
  function pagehide(event) {
    if (!event.persisted) dispose();
    else { stopped = true; cancelAnimationFrame(frameId); frameId = 0; }
  }
  function pageshow() { stopped = false; request(); }
  window.addEventListener("pagehide", pagehide);
  window.addEventListener("pageshow", pageshow);
  resize(); request();
  return { dispose };
}

function createFallback(oldCanvas, getAudioFrame) {
  // A canvas that has attempted WebGL cannot reliably acquire a 2D context.
  const canvas = oldCanvas.cloneNode(false);
  oldCanvas.replaceWith(canvas);
  canvas.dataset.renderer = "fallback";
  canvas.dataset.spheres = "5";
  canvas.dataset.particles = "4500";
  canvas.dataset.layout = "concentric";
  const ctx = canvas.getContext("2d");
  if (!ctx) return { dispose() {} };
  const points = sphereGeometry(900, 1).getAttribute("position").array;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let frameId = 0, stopped = false, previous = 0, time = 0, visible = true, width = 0, height = 0;
  const resize = new ResizeObserver(() => {
    width = canvas.clientWidth; height = canvas.clientHeight;
    canvas.width = width; canvas.height = height;
  });
  resize.observe(canvas);
  function request() { if (!stopped && visible && !document.hidden && !frameId) frameId = requestAnimationFrame(draw); }
  function draw(now) {
    frameId = 0;
    if (stopped || !visible || document.hidden) return;
    if (now - previous < (reduced.matches ? 100 : 1000 / 24)) { request(); return; }
    const delta = Math.min((now - previous) / 1000, .1); previous = now;
    if (!reduced.matches) time += delta;
    const audio = getAudioFrame();
    canvas.dataset.audioLevel = audio.level.toFixed(3);
    canvas.dataset.motion = reduced.matches ? "reduced" : "animated";
    ctx.clearRect(0, 0, width, height);
    const radius = Math.min(height * .32, width * .25) * (1 + (reduced.matches ? 0 : audio.level * .1));
    for (const scale of [1, .82, .64, .46, .3]) {
      for (let i = 0; i < points.length; i += 3) {
        const x = points[i] * Math.cos(time * .07) + points[i + 2] * Math.sin(time * .07);
        const z = -points[i] * Math.sin(time * .07) + points[i + 2] * Math.cos(time * .07);
        ctx.fillStyle = `rgba(255,255,255,${.12 + (z + 1) * .25})`;
        ctx.beginPath();
        ctx.arc(width / 2 + x * scale * radius, height / 2 + points[i + 1] * radius * scale, .8, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    request();
  }
  const intersection = new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting;
    if (visible) request(); else { cancelAnimationFrame(frameId); frameId = 0; }
  });
  intersection.observe(canvas);
  function visibility() { if (document.hidden) { cancelAnimationFrame(frameId); frameId = 0; } else request(); }
  document.addEventListener("visibilitychange", visibility);
  function dispose() {
    stopped = true; cancelAnimationFrame(frameId); resize.disconnect(); intersection.disconnect();
    document.removeEventListener("visibilitychange", visibility);
    window.removeEventListener("pagehide", pagehide);
    window.removeEventListener("pageshow", pageshow);
  }
  function pagehide(event) { if (!event.persisted) dispose(); else { stopped = true; cancelAnimationFrame(frameId); frameId = 0; } }
  function pageshow() { stopped = false; request(); }
  window.addEventListener("pagehide", pagehide); window.addEventListener("pageshow", pageshow);
  request();
  return { dispose };
}
