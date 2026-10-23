/**
 * ChaosGate Ambient Background Engine — Real-Time Procedural Cloudy Sky
 * High-performance WebGL GLSL shader rendering organic volumetric clouds
 * drifting across a luminous daylight atmosphere (Hark Pro light-mode aesthetic).
 */
(() => {
  const canvas = document.getElementById("ambient-canvas");
  if (!canvas) return;

  const gl = canvas.getContext("webgl", {
    alpha: false,
    depth: false,
    antialias: false,
    powerPreference: "high-performance"
  });

  if (!gl) {
    // Graceful 2D canvas fallback
    render2DFallback(canvas);
    return;
  }

  const vsSource = `
    attribute vec2 position;
    void main() {
      gl_Position = vec4(position, 0.0, 1.0);
    }
  `;

  const fsSource = `
    precision highp float;
    uniform vec2 uRes;
    uniform float uTime;
    uniform vec2 uMouse;

    float hash21(vec2 p) {
      vec3 p3 = fract(vec3(p.xyx) * 0.1031);
      p3 += dot(p3, p3.yzx + 33.33);
      return fract((p3.x + p3.y) * p3.z);
    }

    // Quintic smoothed value noise for silky cloud transitions
    float vnoise(vec2 p) {
      vec2 i = floor(p);
      vec2 f = fract(p);
      vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
      float a = hash21(i);
      float b = hash21(i + vec2(1.0, 0.0));
      float c = hash21(i + vec2(0.0, 1.0));
      float d = hash21(i + vec2(1.0, 1.0));
      return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
    }

    // 4-octave rotating Fractional Brownian Motion
    float fbm(vec2 p) {
      float v = 0.0;
      float a = 0.52;
      mat2 rot = mat2(0.8, 0.6, -0.6, 0.8);
      for (int i = 0; i < 4; i++) {
        v += a * vnoise(p);
        p = rot * p * 2.02;
        a *= 0.48;
      }
      return v;
    }

    void main() {
      vec2 uv = gl_FragCoord.xy / uRes;
      float aspect = uRes.x / uRes.y;
      vec2 p = vec2(uv.x * aspect, uv.y);

      // Slow cinematic atmospheric wind drift
      float t = uTime * 0.032;
      vec2 drift = vec2(t * 0.42, t * 0.10);

      // Subtle interactive mouse parallax
      vec2 mOffset = (uMouse / uRes - 0.5) * 0.06;
      p += mOffset;

      // Domain warping for natural billowing cumulus clouds
      vec2 q = vec2(
        fbm(p * 1.15 + drift),
        fbm(p * 1.15 + vec2(5.2, 1.3) - drift * 0.65)
      );
      vec2 r = vec2(
        fbm(p * 1.45 + 1.2 * q + vec2(1.7, 9.2) + t * 0.04),
        fbm(p * 1.45 + 1.2 * q + vec2(8.3, 2.8) - t * 0.035)
      );
      float cloudDensity = fbm(p * 1.05 + 0.9 * r);

      // Daytime Sky Rayleigh Scattering Gradient
      vec3 skyZenith  = vec3(0.72, 0.85, 0.98); // Soft sky azure
      vec3 skyMid     = vec3(0.88, 0.93, 0.99); // Crisp daylight
      vec3 skyHorizon = vec3(0.96, 0.97, 0.99); // Warm ivory horizon

      vec3 sky = mix(skyHorizon, skyMid, smoothstep(0.0, 0.45, uv.y));
      sky = mix(sky, skyZenith, smoothstep(0.40, 1.0, uv.y));

      // Atmospheric Sun Glow
      vec2 sunPos = vec2(0.68 * aspect, 0.82) + mOffset * 0.5;
      float sunDist = length(p - sunPos);
      float sunGlow = exp(-sunDist * 1.5) * 0.32;
      vec3 sunColor = vec3(1.0, 0.97, 0.92);
      sky += sunGlow * sunColor;

      // Volumetric Cloud Shading: Sunlit tops vs soft ambient underside shadows
      float cloudCut = smoothstep(0.38, 0.78, cloudDensity);
      vec3 cloudBase = vec3(0.93, 0.95, 0.98); // Ambient underside shadow
      vec3 cloudLit  = vec3(1.0, 1.0, 1.0);     // Pure sunlit cloud white

      float sunLighting = smoothstep(0.40, 0.76, fbm(p * 1.28 + q - sunPos * 0.2));
      vec3 cloudCol = mix(cloudBase, cloudLit, sunLighting * 0.85 + 0.15);

      // Atmospheric haze blending
      vec3 finalColor = mix(sky, cloudCol, cloudCut * 0.72);

      // High-frequency subtle dithering to prevent display banding
      float grain = (hash21(gl_FragCoord.xy + fract(uTime)) - 0.5) * (1.0 / 255.0);
      finalColor += grain;

      gl_FragColor = vec4(finalColor, 1.0);
    }
  `;

  function createShader(gl, type, source) {
    const s = gl.createShader(type);
    gl.shaderSource(s, source);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.error(gl.getShaderInfoLog(s));
      gl.deleteShader(s);
      return null;
    }
    return s;
  }

  const vs = createShader(gl, gl.VERTEX_SHADER, vsSource);
  const fs = createShader(gl, gl.FRAGMENT_SHADER, fsSource);
  if (!vs || !fs) return;

  const program = gl.createProgram();
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);

  const posLoc = gl.getAttribLocation(program, "position");
  const resLoc = gl.getUniformLocation(program, "uRes");
  const timeLoc = gl.getUniformLocation(program, "uTime");
  const mouseLoc = gl.getUniformLocation(program, "uMouse");

  const posBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
    -1, -1,
     1, -1,
    -1,  1,
    -1,  1,
     1, -1,
     1,  1
  ]), gl.STATIC_DRAW);

  let width = 0;
  let height = 0;
  let isVisible = true;
  let animId = null;

  const mouse = {
    x: 720,
    y: 360,
    targetX: 720,
    targetY: 360
  };

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    gl.viewport(0, 0, canvas.width, canvas.height);

    if (!mouse.hasMoved) {
      mouse.targetX = width * 0.5;
      mouse.targetY = height * 0.4;
      mouse.x = mouse.targetX;
      mouse.y = mouse.targetY;
    }
  }

  window.addEventListener("resize", resize, { passive: true });
  window.addEventListener("pointermove", (e) => {
    mouse.hasMoved = true;
    mouse.targetX = e.clientX;
    mouse.targetY = e.clientY;
  }, { passive: true });

  document.addEventListener("visibilitychange", () => {
    isVisible = !document.hidden;
    if (isVisible && !animId) {
      animId = requestAnimationFrame(render);
    }
  });

  resize();

  const startTime = performance.now();

  function render(now) {
    if (!isVisible) {
      animId = null;
      return;
    }

    const elapsed = (now - startTime) * 0.001;

    mouse.x += (mouse.targetX - mouse.x) * 0.04;
    mouse.y += (mouse.targetY - mouse.y) * 0.04;

    gl.useProgram(program);

    gl.enableVertexAttribArray(posLoc);
    gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
    gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

    gl.uniform2f(resLoc, canvas.width, canvas.height);
    gl.uniform1f(timeLoc, elapsed);
    gl.uniform2f(mouseLoc, mouse.x * (canvas.width / width), (height - mouse.y) * (canvas.height / height));

    gl.drawArrays(gl.TRIANGLES, 0, 6);

    animId = requestAnimationFrame(render);
  }

  animId = requestAnimationFrame(render);

  function render2DFallback(cvs) {
    const ctx = cvs.getContext("2d");
    if (!ctx) return;
    function draw() {
      cvs.width = window.innerWidth;
      cvs.height = window.innerHeight;
      const grad = ctx.createLinearGradient(0, 0, 0, cvs.height);
      grad.addColorStop(0, "#b8d8fa");
      grad.addColorStop(0.5, "#e0edfc");
      grad.addColorStop(1, "#f5f7fc");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, cvs.width, cvs.height);
    }
    window.addEventListener("resize", draw);
    draw();
  }
})();
