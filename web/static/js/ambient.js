/**
 * ChaosGate Ambient Background Engine — Interactive Dot Matrix & Signal Field
 * Directly ported from index (4).html
 * Features:
 * - Dynamic dot matrix with slow organic noise wave
 * - Diagonal signal sweep traversing the grid
 * - Interactive cursor ripple rings with decay
 * - Twinkling star-dots
 * - Top violet aura glow
 * - Mouse smoothing and scroll reactivity
 */
(() => {
  const cv = document.getElementById("ambient-canvas");
  if (!cv) return;

  const gl = cv.getContext("webgl", {
    antialias: false,
    preserveDrawingBuffer: false,
    powerPreference: "high-performance"
  });

  if (!gl) {
    document.body.style.background = "#08080b";
    return;
  }

  const vsSource = `
    attribute vec2 a;
    void main() {
      gl_Position = vec4(a, 0.0, 1.0);
    }
  `;

  const fsSource = `
    precision highp float;
    uniform vec2  uRes;
    uniform float uTime;
    uniform vec2  uMouse;
    uniform float uScroll;
    uniform float uDpr;

    float hash(vec2 p) {
      p = fract(p * vec2(123.34, 456.21));
      p += dot(p, p + 45.32);
      return fract(p.x * p.y);
    }

    float noise(vec2 p) {
      vec2 i = floor(p);
      vec2 f = fract(p);
      vec2 u = f * f * (3.0 - 2.0 * f);
      return mix(
        mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
        mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
        u.y
      );
    }

    void main() {
      vec2 frag = gl_FragCoord.xy;
      vec2 uv = frag / uRes;
      float t = uTime;
      float cell = 22.0 * uDpr;
      vec2 g = frag / cell;
      vec2 id = floor(g);
      vec2 f = fract(g) - 0.5;

      // slow organic field + a diagonal signal sweep
      float n = noise(id * 0.09 + vec2(t * 0.05, -t * 0.03));
      float sweep = sin((id.x * 0.12 - id.y * 0.06) - t * 0.9);
      float band = smoothstep(0.92, 1.0, sweep); // thin bright band travelling across

      // mouse ripple
      vec2 m = uMouse / cell;
      float dm = length(id - m);
      float ring = exp(-dm * 0.12) * (0.5 + 0.5 * sin(dm * 0.7 - t * 3.0));

      float b = 0.10 + n * 0.22 + band * 0.55 + ring * 0.35;
      float twinkle = step(0.985, hash(id + floor(t * 0.5))) * 0.5;
      b += twinkle;

      float r = 0.075 + b * 0.06;
      float dot_ = smoothstep(r, r - 0.05, length(f));

      // fade: strongest behind the top hero & navigation, vanishing toward lower page
      vec2 c = uv - vec2(0.5, 0.78 + uScroll * 0.0006);
      float mask = exp(-dot(c * vec2(1.1, 2.2), c * vec2(1.1, 2.2)) * 2.6);
      mask = max(mask, 0.18 * smoothstep(0.0, 1.0, uv.y));

      vec3 dotCol = mix(vec3(0.55, 0.55, 0.62), vec3(0.60, 0.52, 1.0), clamp(band + ring * 0.6, 0.0, 1.0));
      vec3 col = vec3(0.031, 0.031, 0.043);
      col += dotCol * dot_ * b * mask * 1.25;

      // top violet glow
      col += vec3(0.33, 0.26, 0.85) * exp(-pow(length((uv - vec2(0.5, 1.08)) * vec2(1.0, 2.6)), 2.0) * 2.2) * 0.22 * (1.0 - uScroll * 0.0008);
      col += (hash(frag + fract(t)) - 0.5) * 0.008;

      gl_FragColor = vec4(col, 1.0);
    }
  `;

  const sh = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.error(gl.getShaderInfoLog(s));
      return null;
    }
    return s;
  };

  const vs = sh(gl.VERTEX_SHADER, vsSource);
  const fs = sh(gl.FRAGMENT_SHADER, fsSource);
  if (!vs || !fs) return;

  const prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  gl.useProgram(prog);

  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);

  const loc = gl.getAttribLocation(prog, "a");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

  const uRes = gl.getUniformLocation(prog, "uRes");
  const uTime = gl.getUniformLocation(prog, "uTime");
  const uMouse = gl.getUniformLocation(prog, "uMouse");
  const uScroll = gl.getUniformLocation(prog, "uScroll");
  const uDpr = gl.getUniformLocation(prog, "uDpr");

  let dpr = 1;
  let isVisible = true;
  let animId = null;

  const mouse = { x: -9999, y: -9999, tx: -9999, ty: -9999 };

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.floor(window.innerWidth * dpr);
    cv.height = Math.floor(window.innerHeight * dpr);
    cv.style.width = window.innerWidth + "px";
    cv.style.height = window.innerHeight + "px";
    gl.viewport(0, 0, cv.width, cv.height);
  }

  window.addEventListener("resize", resize, { passive: true });
  window.addEventListener("pointermove", (e) => {
    mouse.tx = e.clientX * dpr;
    mouse.ty = (window.innerHeight - e.clientY) * dpr;
    if (mouse.x < -999) {
      mouse.x = mouse.tx;
      mouse.y = mouse.ty;
    }
  }, { passive: true });

  document.addEventListener("visibilitychange", () => {
    isVisible = !document.hidden;
    if (isVisible && !animId) {
      animId = requestAnimationFrame(frame);
    }
  });

  resize();

  const t0 = performance.now();

  function frame(now) {
    if (!isVisible) {
      animId = null;
      return;
    }

    mouse.x += (mouse.tx - mouse.x) * 0.08;
    mouse.y += (mouse.ty - mouse.y) * 0.08;

    gl.uniform2f(uRes, cv.width, cv.height);
    gl.uniform1f(uTime, (now - t0) / 1000);
    gl.uniform2f(uMouse, mouse.x, mouse.y);
    gl.uniform1f(uScroll, window.scrollY || 0);
    gl.uniform1f(uDpr, dpr);

    gl.drawArrays(gl.TRIANGLES, 0, 3);

    animId = requestAnimationFrame(frame);
  }

  animId = requestAnimationFrame(frame);
})();
