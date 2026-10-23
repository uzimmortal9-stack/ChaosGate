/**
 * ChaosGate Ambient Background Engine — Hark Pro Architecture
 * Reverse-engineered aesthetic inspired by Hark Pro & modern Apple-grade creative computing:
 * - Deep obsidian foundation (#05070d)
 * - Full-width balanced dual-end kinetic ribbons (active left and active right, zero dead space)
 * - Hark Pro palette: Solar Coral (#ff5938) -> Warm Gold (#ff9e40) -> Luminous Platinum (#fffefa) -> Electric Sapphire (#4f6eff)
 * - Volumetric translucent fills between ribbons for tangible luminous silk depth
 * - Edge-to-edge interactive pointer reactivity with localized ripple propagation
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
    hasMoved: false,
  };

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth || document.documentElement.clientWidth || 1440;
    height = width < 768 ? 290 : 380;

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
    }
  }

  window.addEventListener("resize", resize, { passive: true });
  window.addEventListener("pointermove", (e) => {
    mouse.hasMoved = true;
    mouse.targetX = e.clientX;
    mouse.targetY = Math.min(height + 20, Math.max(0, e.clientY));
  }, { passive: true });

  document.addEventListener("visibilitychange", () => {
    isVisible = !document.hidden;
    if (isVisible && !animId) {
      render();
    }
  });

  resize();

  let time = 0;

  // Hark Pro Reverse-Engineered 5-Ribbon Silk Field
  const ribbons = [
    {
      yBaseRatio: 0.28,
      amp: 42,
      freq: 0.0020,
      speed: 0.015,
      phase: 0,
      lineWidth: 1.8,
    },
    {
      yBaseRatio: 0.33,
      amp: 48,
      freq: 0.0016,
      speed: 0.012,
      phase: 1.6,
      lineWidth: 1.6,
    },
    {
      yBaseRatio: 0.38,
      amp: 38,
      freq: 0.0022,
      speed: 0.018,
      phase: 3.2,
      lineWidth: 1.5,
    },
    {
      yBaseRatio: 0.44,
      amp: 54,
      freq: 0.0013,
      speed: 0.010,
      phase: 4.8,
      lineWidth: 1.3,
    },
    {
      yBaseRatio: 0.49,
      amp: 36,
      freq: 0.0019,
      speed: 0.014,
      phase: 2.4,
      lineWidth: 1.1,
    }
  ];

  function render() {
    if (!isVisible) {
      animId = null;
      return;
    }

    time += 1;

    // Smooth cursor inertia
    mouse.x += (mouse.targetX - mouse.x) * 0.045;
    mouse.y += (mouse.targetY - mouse.y) * 0.045;

    ctx.clearRect(0, 0, width, height);

    const step = width < 768 ? 10 : 8;
    const allCurves = [];

    // Calculate full edge-to-edge curves with balanced dual-end motion
    ribbons.forEach((rb) => {
      const pts = [];
      const yBase = height * rb.yBaseRatio;
      const t = time * rb.speed + rb.phase;

      for (let x = -20; x <= width + 20; x += step) {
        // Edge-to-edge continuous standing wave with dual antiphase peaks
        // Peak 1: Left-center zone
        const wLeft = Math.sin(x * rb.freq + t) * (rb.amp * 0.72);
        // Peak 2: Right-center zone (counter-balanced with offset frequency & phase to prevent empty flank)
        const wRight = Math.cos((x - width * 0.5) * rb.freq * 1.25 - t * 0.85) * (rb.amp * 0.68);
        // High-frequency surface shimmer
        const wDetail = Math.sin(x * 0.005 + t * 1.4) * 6;

        const baseWave = wLeft + wRight + wDetail;

        // Interactive cursor responsiveness across the entire canvas width
        const dx = x - mouse.x;
        const distSq = dx * dx;
        const influence = Math.exp(-distSq / (2 * 210 * 210));
        const mouseLift = (mouse.y - yBase) * influence * 0.52;
        const mouseRipple = Math.sin(dx * 0.035 - time * 0.08) * influence * 15;

        const y = yBase + baseWave + mouseLift + mouseRipple;
        pts.push({ x, y });
      }
      allCurves.push(pts);
    });

    // 1. Draw volumetric gradient fills between layers for deep luminous silk appearance
    for (let r = 0; r < allCurves.length - 1; r++) {
      const topPts = allCurves[r];
      const btmPts = allCurves[r + 1];

      ctx.beginPath();
      ctx.moveTo(topPts[0].x, topPts[0].y);
      for (let i = 1; i < topPts.length; i++) {
        ctx.lineTo(topPts[i].x, topPts[i].y);
      }
      for (let i = btmPts.length - 1; i >= 0; i--) {
        ctx.lineTo(btmPts[i].x, btmPts[i].y);
      }
      ctx.closePath();

      // Hark Pro edge-to-edge rich gradient fill
      const grad = ctx.createLinearGradient(0, 0, width, 0);
      grad.addColorStop(0, "rgba(255, 89, 56, 0.035)");     // Solar Coral glow on left
      grad.addColorStop(0.32, "rgba(255, 158, 64, 0.045)"); // Golden warm crest
      grad.addColorStop(0.62, "rgba(255, 254, 250, 0.040)"); // Platinum sheen center
      grad.addColorStop(1, "rgba(79, 110, 255, 0.050)");    // Electric Sapphire glow on right!
      ctx.fillStyle = grad;
      ctx.fill();
    }

    // 2. Stroke high-definition ribbon contours across the full width
    allCurves.forEach((pts, rIdx) => {
      const rb = ribbons[rIdx];

      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i < pts.length; i++) {
        ctx.lineTo(pts[i].x, pts[i].y);
      }

      // Edge-to-edge balanced stroke gradient (Both ends active!)
      const strokeGrad = ctx.createLinearGradient(0, 0, width, 0);
      strokeGrad.addColorStop(0, "rgba(255, 89, 56, 0.45)");     // Left: active solar coral
      strokeGrad.addColorStop(0.25, "rgba(255, 158, 64, 0.70)"); // Left-center: warm gold
      strokeGrad.addColorStop(0.50, "rgba(255, 254, 250, 0.65)"); // Center: crisp platinum
      strokeGrad.addColorStop(0.75, "rgba(79, 110, 255, 0.70)"); // Right-center: electric sapphire
      strokeGrad.addColorStop(1, "rgba(204, 224, 255, 0.45)");   // Right: celestial mist

      ctx.strokeStyle = strokeGrad;
      ctx.lineWidth = rb.lineWidth;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.stroke();
    });

    // 3. Starlight Corona nodes balanced across BOTH ends (left to right)
    const starNodes = width < 768 ? 10 : 16;
    for (let s = 0; s < starNodes; s++) {
      const sx = 40 + (s / (starNodes - 1)) * (width - 80);
      const curveIdx = s % allCurves.length;
      const pts = allCurves[curveIdx];

      const ptIndex = Math.floor((sx / width) * (pts.length - 1));
      const basePt = pts[Math.min(pts.length - 1, Math.max(0, ptIndex))];

      const pulse = 0.5 + 0.5 * Math.sin(time * 0.05 + s * 0.7);
      const radius = 1.3 + pulse * 0.9;

      ctx.beginPath();
      ctx.arc(sx, basePt.y, radius, 0, Math.PI * 2);

      // Hark Pro color zoning
      if (s < 5) {
        ctx.fillStyle = "rgba(255, 89, 56, 0.85)";
        ctx.shadowColor = "rgba(255, 89, 56, 0.9)";
      } else if (s < 11) {
        ctx.fillStyle = "rgba(255, 254, 250, 0.85)";
        ctx.shadowColor = "rgba(255, 254, 250, 0.8)";
      } else {
        ctx.fillStyle = "rgba(79, 110, 255, 0.90)";
        ctx.shadowColor = "rgba(79, 110, 255, 0.9)";
      }

      ctx.shadowBlur = 8;
      ctx.fill();
      ctx.shadowBlur = 0;
    }

    animId = requestAnimationFrame(render);
  }

  render();
})();
