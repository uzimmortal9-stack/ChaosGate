/**
 * ChaosGate Ambient Background Engine
 * Interactive 3D Halftone Dither Sphere with Real-Time Fluid Chaos Distortion
 * Inspired by Cre8tera & modern high-end creative computing aesthetics.
 */
(() => {
  const canvas = document.getElementById("ambient-canvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return;

  let width = 0;
  let height = 0;
  let dpr = 1;

  const mouse = {
    x: 0,
    y: 0,
    targetX: 0,
    targetY: 0,
    hasMoved: false,
  };

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    width = window.innerWidth;
    height = window.innerHeight;

    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.scale(dpr, dpr);

    if (!mouse.hasMoved) {
      mouse.targetX = width * 0.5;
      mouse.targetY = height * 0.5;
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

  resize();

  let time = 0;
  let animId = null;

  // Optimized dot spacing for high performance (60fps)
  const spacing = 8.5;

  function render() {
    time += 0.015;

    // Smooth cursor inertia
    mouse.x += (mouse.targetX - mouse.x) * 0.045;
    mouse.y += (mouse.targetY - mouse.y) * 0.045;

    // Clear canvas frame for transparent compositing over aurora
    ctx.clearRect(0, 0, width, height);

    // Responsive Sphere Placement
    const isDesktop = width >= 1100;
    const cx = isDesktop ? width * 0.64 : width * 0.5;
    const cy = isDesktop ? height * 0.48 : height * 0.44;
    const R = Math.min(width, height) * (isDesktop ? 0.40 : 0.44);
    const Rsq = R * R;

    // Cybernetic Directional Lighting (top-left, projecting forward)
    const lx = -0.52;
    const ly = -0.48;
    const lz = 0.70;

    // Interactive 3D Rotations (Time rotation + Mouse tilt)
    const rotY = (mouse.x - width * 0.5) * 0.0014 + time * 0.28;
    const rotX = (mouse.y - height * 0.5) * 0.0014 + Math.sin(time * 0.18) * 0.18;

    const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
    const cosX = Math.cos(rotX), sinX = Math.sin(rotX);

    // Bounding Box to minimize loops
    const margin = R * 1.45;
    const startX = Math.max(0, Math.floor((cx - margin) / spacing) * spacing);
    const endX = Math.min(width, Math.ceil((cx + margin) / spacing) * spacing);
    const startY = Math.max(0, Math.floor((cy - margin) / spacing) * spacing);
    const endY = Math.min(height, Math.ceil((cy + margin) / spacing) * spacing);

    for (let y = startY; y <= endY; y += spacing) {
      const dy = y - cy;
      const dySq = dy * dy;

      for (let x = startX; x <= endX; x += spacing) {
        const dx = x - cx;
        const distSq = dx * dx + dySq;

        if (distSq <= Rsq) {
          // Inside 3D Halftone Sphere
          const z = Math.sqrt(Rsq - distSq);
          const nx = dx / R;
          const ny = dy / R;
          const nz = z / R;

          // 3D Sphere Surface Rotation (Yaw then Pitch)
          const x1 = nx * cosY + nz * sinY;
          const z1 = -nx * sinY + nz * cosY;
          const y2 = ny * cosX - z1 * sinX;
          const z2 = ny * sinX + z1 * cosX;
          const x2 = x1;

          // 3D Diffuse Lighting + Rim Fresnel Glow
          const diffuse = Math.max(0, nx * lx + ny * ly + nz * lz);
          const fresnel = Math.pow(1 - nz, 2.4) * 0.42;

          // Multi-harmonic Fluid Chaos Wave on Sphere Surface
          const u = x2 * 2.8 + time * 0.85;
          const v = y2 * 2.8 - time * 0.65;
          const w = z2 * 2.4;

          const wave1 = Math.sin(u + Math.cos(v * 1.3)) * Math.cos(v + w);
          const wave2 = Math.sin(x2 * 4.2 - y2 * 2.4 + time * 1.15);
          const plasma = Math.abs(wave1 * 0.68 + wave2 * 0.32);

          // Energy Ribbon threshold (dynamic chaos stream)
          const isWave = plasma > 0.40 && z2 > -0.32;
          const waveIntensity = isWave ? Math.min(1, (plasma - 0.40) * 3.6) : 0;

          let dotRadius;
          let fillStyle;

          if (waveIntensity > 0.08) {
            // ChaosGate Electric Fluid Stream (Cyan -> Indigo -> Violet)
            const colorTone = Math.sin(x2 * 2.2 + time * 1.2) * 0.5 + 0.5;
            dotRadius = 1.3 + waveIntensity * 2.7;

            if (colorTone > 0.66) {
              // Radiant Electric Cyan (#38bdf8)
              fillStyle = `rgba(56, 189, 248, ${0.72 + waveIntensity * 0.28})`;
            } else if (colorTone > 0.32) {
              // Neon Indigo (#818cf8)
              fillStyle = `rgba(129, 140, 248, ${0.72 + waveIntensity * 0.28})`;
            } else {
              // Cyber Teal / Emerald (#2dd4bf)
              fillStyle = `rgba(45, 212, 191, ${0.72 + waveIntensity * 0.28})`;
            }
          } else {
            // Monochromatic Halftone Shading with 3D Depth
            const brightness = Math.min(1, Math.max(0.06, diffuse * 0.86 + fresnel));
            dotRadius = 0.75 + brightness * 2.25;

            const alpha = 0.12 + brightness * 0.78;
            const rgb = Math.round(175 + brightness * 80);
            fillStyle = `rgba(${rgb}, ${rgb + 2}, ${rgb + 12}, ${alpha})`;
          }

          ctx.beginPath();
          ctx.arc(x, y, dotRadius, 0, Math.PI * 2);
          ctx.fillStyle = fillStyle;
          ctx.fill();

        } else {
          // Outside the sphere: Coordinate Dot Matrix Grid
          const dist = Math.sqrt(distSq);
          const maxDist = R * 1.48;
          if (dist < maxDist) {
            const alpha = Math.max(0, (1 - (dist - R) / (maxDist - R)) * 0.11);
            if (alpha > 0.015) {
              ctx.beginPath();
              ctx.arc(x, y, 0.85, 0, Math.PI * 2);
              ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
              ctx.fill();
            }
          }
        }
      }
    }

    animId = requestAnimationFrame(render);
  }

  // Handle visibility to save battery / CPU when tab is hidden
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (animId) cancelAnimationFrame(animId);
    } else {
      animId = requestAnimationFrame(render);
    }
  });

  animId = requestAnimationFrame(render);
})();
