/**
 * ChaosGate Ambient Background Engine — Dark Twilight Procedural Cloud Sky
 * Ported directly from index (3).html WebGL GLSL Shader
 * Deep midnight cosmic purple, domain-warped clouds, twilight horizon glow, and floating starlight motes.
 */
(() => {
  const canvas = document.getElementById("ambient-canvas");
  if (!canvas) return;

  const gl = canvas.getContext("webgl", {
    antialias: false,
    preserveDrawingBuffer: false,
    powerPreference: "high-performance"
  });

  if (!gl) {
    document.body.style.background = "linear-gradient(#0c0617,#1e0b35 55%,#3d1246)";
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

    // ---------- noise ----------
    float hash(vec2 p) {
      p = fract(p * vec2(123.34, 456.21));
      p += dot(p, p + 45.32);
      return fract(p.x * p.y);
    }
    float noise(vec2 p) {
      vec2 i = floor(p), f = fract(p);
      vec2 u = f * f * (3.0 - 2.0 * f);
      float a = hash(i), b = hash(i + vec2(1,0)), c = hash(i + vec2(0,1)), d = hash(i + vec2(1,1));
      return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
    }
    const mat2 ROT = mat2(0.80, 0.60, -0.60, 0.80);
    float fbm(vec2 p) {
      float v = 0.0, a = 0.5;
      for (int i = 0; i < 5; i++) {
        v += a * noise(p);
        p = ROT * p * 2.03 + 1.7;
        a *= 0.5;
      }
      return v;
    }
    // domain-warped fbm -> soft, billowy, painterly cloud shapes
    float clouds(vec2 p, float t) {
      vec2 q = vec2(fbm(p + vec2(0.0, t * 0.05)), fbm(p + vec2(5.2, 1.3) - t * 0.03));
      vec2 r = vec2(fbm(p + 1.4 * q + vec2(1.7, 9.2) + t * 0.04), fbm(p + 1.4 * q + vec2(8.3, 2.8)));
      return fbm(p + 1.1 * r);
    }

    // ---------- grass blades ----------
    float blade(vec2 uv, float x0, float h, float bend, float w, float t, float seed) {
      float y = uv.y;
      if (y > h) return 0.0;
      float k = y / h;
      float sway = sin(t * 0.9 + seed * 6.0) * 0.012 + sin(t * 2.1 + seed * 13.0) * 0.004;
      float cx = x0 + (bend + sway) * k * k;
      float width = w * (1.0 - k);
      float d = abs(uv.x - cx);
      return smoothstep(width + 0.004, width - 0.001, d) * (0.55 + 0.45 * hash(vec2(seed, 1.0)));
    }

    void main() {
      vec2 frag = gl_FragCoord.xy;
      vec2 uv = frag / uRes;                       // 0..1, y up
      float aspect = uRes.x / uRes.y;
      vec2 mOffset = (uMouse / uRes - 0.5) * 0.035;
      vec2 p = vec2(uv.x * aspect, uv.y) + mOffset;
      float t = uTime;

      // ---------- base dark purple twilight gradient ----------
      vec3 top     = vec3(0.040, 0.018, 0.090); // deep midnight cosmic purple
      vec3 mid     = vec3(0.120, 0.050, 0.230); // deep royal violet
      vec3 low     = vec3(0.240, 0.090, 0.380); // dark amethyst twilight
      vec3 horizon = vec3(0.540, 0.170, 0.500); // glowing magenta-violet twilight horizon
      vec3 col = mix(low, mid, smoothstep(0.05, 0.55, uv.y));
      col = mix(col, top, smoothstep(0.55, 1.05, uv.y));

      // warm deep purple glow from lower-left (where the sun has set)
      vec2 sunPos = vec2(-0.05 * aspect, 0.18);
      float sunD = length((p - sunPos) * vec2(0.8, 1.4));
      float glow = exp(-sunD * 1.6);
      col = mix(col, horizon, glow * 0.75);
      // a second, softer purple-magenta band low on the right
      col = mix(col, vec3(0.42, 0.12, 0.44), exp(-length((p - vec2(aspect * 1.05, 0.05)) * vec2(0.9, 2.4)) * 1.8) * 0.45);

      // ---------- cloud layers ----------
      // 1) high wispy streaks (stretched horizontally)
      vec2 wp = vec2(p.x * 0.9 + t * 0.010, p.y * 3.2);
      float wisps = clouds(wp * 0.9, t);
      wisps = smoothstep(0.40, 0.68, wisps) * smoothstep(0.40, 0.95, uv.y);

      // 2) main mid-level billows
      vec2 cp = vec2(p.x * 1.1 + t * 0.018, p.y * 1.9 - 0.3);
      float c = clouds(cp * 0.75, t);
      float lowMask = smoothstep(0.85, 0.15, uv.y);          // denser near the bottom
      float density = smoothstep(0.34, 0.62, c + lowMask * 0.18 - smoothstep(0.6, 1.0, uv.y) * 0.08);

      // 3) big soft foreground clouds sweeping in from the bottom-left
      vec2 bp = vec2(p.x * 0.7 + t * 0.026, p.y * 1.3);
      float big = clouds(bp * 0.6 + 10.0, t * 0.7);
      float bigMask = smoothstep(0.6, 0.0, uv.y) * (0.65 + 0.35 * smoothstep(0.8 * aspect, 0.0, p.x));
      float bigD = smoothstep(0.30, 0.56, big) * bigMask;

      // lighting: fake self-shadow by sampling the field toward the light
      vec2 lightDir = normalize(sunPos - p) * 0.06;
      float cs = clouds((cp + lightDir) * 0.75, t);
      float shade = clamp((c - cs) * 7.0 + 0.45 + density * 0.25, 0.0, 1.0);    // >0.5 means lit edge

      vec3 cloudShadow = vec3(0.080, 0.040, 0.160); // deep dark purple-indigo shadow
      vec3 cloudLit    = vec3(0.740, 0.540, 0.940); // luminous lavender-violet crests
      vec3 cloudPink   = vec3(0.840, 0.300, 0.720); // neon violet-magenta rim
      float warm = clamp(glow * 1.6, 0.0, 1.0);
      vec3 cloudCol = mix(cloudShadow, mix(cloudLit, cloudPink, warm), shade);

      col = mix(col, mix(vec3(0.26, 0.12, 0.44), cloudLit, 0.35), wisps * 0.45);
      col = mix(col, cloudCol, density * 0.85);

      float bs = clouds((bp + lightDir) * 0.6 + 10.0, t * 0.7);
      float bshade = clamp((big - bs) * 7.0 + 0.5 + bigD * 0.3, 0.0, 1.0);
      vec3 bigCol = mix(vec3(0.06, 0.030, 0.13), mix(vec3(0.66, 0.28, 0.70), cloudPink, warm), bshade);
      col = mix(col, bigCol, bigD * 0.9);

      // ---------- tiny floating light motes ----------
      for (int i = 0; i < 5; i++) {
        float fi = float(i);
        vec2 m = vec2(0.210, 0.867);
        if (i == 1) m = vec2(0.2035, 0.848);
        if (i == 2) m = vec2(0.186, 0.833);
        if (i == 3) m = vec2(0.1655, 0.812);
        if (i == 4) m = vec2(0.197, 0.789);
        m.y += sin(t * 0.6 + fi) * 0.006;
        m.x *= aspect;
        float d = length(p - m);
        float r = 0.0045 + 0.002 * hash(vec2(fi, 3.0));
        col += vec3(0.92, 0.78, 1.00) * smoothstep(r, r * 0.3, d) * 0.9;
        col += vec3(0.95, 0.55, 0.92) * exp(-d * 180.0) * 0.15;
      }

      // ---------- out-of-focus grass in the corners ----------
      float g = 0.0;
      for (int i = 0; i < 26; i++) {
        float fi = float(i);
        float s = hash(vec2(fi, 7.1));
        g = max(g, blade(vec2(uv.x, uv.y), 0.01 + s * 0.13, 0.10 + hash(vec2(fi, 2.0)) * 0.22,
                         (hash(vec2(fi, 4.0)) - 0.3) * 0.12, 0.0025 + s * 0.004, t, s));
        g = max(g, blade(vec2(uv.x, uv.y), 0.86 + s * 0.14, 0.12 + hash(vec2(fi, 9.0)) * 0.28,
                         (hash(vec2(fi, 5.0)) - 0.6) * 0.14, 0.0025 + s * 0.0045, t, s + 1.0));
      }
      vec3 grassCol = mix(vec3(0.035, 0.015, 0.065), vec3(0.15, 0.05, 0.17), smoothstep(0.0, 0.3, uv.y));
      col = mix(col, grassCol, g * 0.75);

      // ---------- atmosphere & finishing ----------
      col = mix(col, vec3(0.20, 0.07, 0.26), smoothstep(0.30, 0.0, uv.y) * 0.15);
      vec2 v = uv - 0.5;
      col *= 1.0 - dot(v, v) * 0.55;
      col = pow(col, vec3(0.95));
      col += (hash(frag + fract(t) * 100.0) - 0.5) * 0.018;

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

  const SCALE = 0.75;
  let isVisible = true;
  let animId = null;

  const mouse = {
    x: window.innerWidth * 0.5,
    y: window.innerHeight * 0.5,
    targetX: window.innerWidth * 0.5,
    targetY: window.innerHeight * 0.5
  };

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2) * SCALE;
    canvas.width = Math.floor(window.innerWidth * dpr);
    canvas.height = Math.floor(window.innerHeight * dpr);
    canvas.style.width = window.innerWidth + "px";
    canvas.style.height = window.innerHeight + "px";
    gl.viewport(0, 0, canvas.width, canvas.height);
  }

  window.addEventListener("resize", resize, { passive: true });
  window.addEventListener("pointermove", (e) => {
    mouse.targetX = e.clientX;
    mouse.targetY = e.clientY;
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

    mouse.x += (mouse.targetX - mouse.x) * 0.04;
    mouse.y += (mouse.targetY - mouse.y) * 0.04;

    gl.uniform2f(uRes, canvas.width, canvas.height);
    gl.uniform1f(uTime, (now - t0) / 1000);
    gl.uniform2f(uMouse, mouse.x * (canvas.width / window.innerWidth), (window.innerHeight - mouse.y) * (canvas.height / window.innerHeight));

    gl.drawArrays(gl.TRIANGLES, 0, 3);

    animId = requestAnimationFrame(frame);
  }

  animId = requestAnimationFrame(frame);
})();
