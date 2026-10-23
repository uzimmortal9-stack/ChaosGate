/**
 * ChaosGate Ambient Background Engine
 * Subtle Interactive Fluid Light Wave (GSAP/Canvas Harmonic Flow)
 * A delicate glowing particle wave ribbons at the top hero area that responds gracefully to pointer movement.
 */
(() => {
  const canvas = document.getElementById("ambient-canvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return;

  let width = 0;
  let height = 380;
  let dpr = 1;
  let isVisible = true;
  let animId = null;

  const mouse = {
    x: 0,
    y: 140,
    targetX: 0,
    targetY: 140,
    vx: 0,
    prevX: 0,
    hasMoved: false,
  };

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth || document.documentElement.clientWidth || 1280;
    height = width < 768 ? 280 : 380;

    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);

    if (!mouse.hasMoved) {
      mouse.targetX = width * 0.5;
      mouse.targetY = height * 0.42;
      mouse.x = mouse.targetX;
      mouse.y = mouse.targetY;
      mouse.prevX = mouse.x;
    }
  }

  window.addEventListener("resize", resize, { passive: true });
  window.addEventListener("pointermove", (e) => {
    mouse.hasMoved = true;
    mouse.targetX = e.clientX;
    mouse.targetY = Math.min(height + 40, Math.max(-20, e.clientY));
  }, { passive: true });

  document.addEventListener("visibilitychange", () => {
    isVisible = !document.hidden;
    if (isVisible && !animId) {
      render();
    }
  });

  resize();

  let time = 0;

  // 4 harmonic wave ribbons tuned to ChaosGate brand palette
  const waves = [
    {
      yBaseRatio: 0.32,
      amp: 38,
      freq: 0.0022,
      speed: 0.016,
      color1: "rgba(56, 189, 248, 0.42)",   // Electric Cyan
      color2: "rgba(99, 102, 241, 0.16)",   // Indigo
      lineWidth: 2.2,
      phase: 0,
      dropColor: "rgba(56, 189, 248, 0.85)",
    },
    {
      yBaseRatio: 0.38,
      amp: 46,
      freq: 0.0018,
      speed: 0.012,
      color1: "rgba(129, 140, 248, 0.45)",  // Neon Indigo
      color2: "rgba(168, 85, 247, 0.14)",  // Violet
      lineWidth: 1.8,
      phase: 1.8,
      dropColor: "rgba(192, 132, 252, 0.80)",
    },
    {
      yBaseRatio: 0.28,
      amp: 34,
      freq: 0.0026,
      speed: 0.019,
      color1: "rgba(45, 212, 191, 0.36)",   // Cyber Teal
      color2: "rgba(56, 189, 248, 0.12)",   // Cyan
      lineWidth: 2.0,
      phase: 3.4,
      dropColor: "rgba(45, 212, 191, 0.75)",
    },
    {
      yBaseRatio: 0.44,
      amp: 52,
      freq: 0.0014,
      speed: 0.009,
      color1: "rgba(192, 132, 252, 0.30)",  // Soft Violet
      color2: "rgba(99, 102, 241, 0.10)",   // Deep Indigo
      lineWidth: 1.5,
      phase: 4.8,
      dropColor: null,
    }
  ];

  function render() {
    if (!isVisible) {
      animId = null;
      return;
    }

    time += 1;

    // Smooth cursor interpolation with momentum
    mouse.x += (mouse.targetX - mouse.x) * 0.05;
    mouse.y += (mouse.targetY - mouse.y) * 0.05;
    mouse.vx = mouse.x - mouse.prevX;
    mouse.prevX = mouse.x;

    ctx.clearRect(0, 0, width, height);

    // Draw each fluid wave ribbon
    const step = width < 768 ? 8 : 6;

    waves.forEach((w, idx) => {
      ctx.beginPath();

      const yBase = height * w.yBaseRatio;

      // Dynamic linear gradient across canvas
      const grad = ctx.createLinearGradient(0, 0, width, 0);
      grad.addColorStop(0, "rgba(56, 189, 248, 0)");
      grad.addColorStop(0.18, w.color1);
      grad.addColorStop(0.55, w.color2);
      grad.addColorStop(0.82, w.color1);
      grad.addColorStop(1, "rgba(168, 85, 247, 0)");

      ctx.strokeStyle = grad;
      ctx.lineWidth = w.lineWidth;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      let isFirst = true;

      for (let x = -20; x <= width + 20; x += step) {
        // Harmonic undulating wave
        const t = time * w.speed + w.phase;
        const sin1 = Math.sin(x * w.freq + t);
        const cos1 = Math.cos(x * w.freq * 0.65 - t * 0.8);
        const baseWave = (sin1 * 0.72 + cos1 * 0.28) * w.amp;

        // Interactive mouse wave distortion with Gaussian attenuation
        const dx = x - mouse.x;
        const distSq = dx * dx;
        const influence = Math.exp(-distSq / (2 * 190 * 190));
        const mouseLift = (mouse.y - yBase) * influence * 0.55;
        const mouseRipple = Math.sin(dx * 0.032 - time * 0.075) * influence * 16;

        const y = yBase + baseWave + mouseLift + mouseRipple;

        if (isFirst) {
          ctx.moveTo(x, y);
          isFirst = false;
        } else {
          ctx.lineTo(x, y);
        }
      }

      ctx.stroke();

      // Glowing particle droplets anchored along wave crests
      if (w.dropColor) {
        const dropSpacing = width < 768 ? 160 : 130;
        const dropStart = 70 + (idx * 35);
        for (let px = dropStart; px < width - 60; px += dropSpacing) {
          const pt = time * w.speed + w.phase;
          const pyBase = (Math.sin(px * w.freq + pt) * 0.72 + Math.cos(px * w.freq * 0.65 - pt * 0.8)) * w.amp;
          const pdx = px - mouse.x;
          const pinfluence = Math.exp(-(pdx * pdx) / (2 * 190 * 190));
          const py = yBase + pyBase + (mouse.y - yBase) * pinfluence * 0.55;

          // Twinkling subtle pulse
          const twinkle = 0.55 + 0.45 * Math.sin(time * 0.05 + px * 0.01);
          const radius = (1.4 + twinkle * 0.6);

          ctx.beginPath();
          ctx.arc(px, py, radius, 0, Math.PI * 2);
          ctx.fillStyle = w.dropColor;
          ctx.shadowColor = w.dropColor;
          ctx.shadowBlur = 8;
          ctx.fill();
          ctx.shadowBlur = 0; // reset
        }
      }
    });

    animId = requestAnimationFrame(render);
  }

  render();
})();
