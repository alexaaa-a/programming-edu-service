import { useEffect } from "react";

const COLORS = ["#e4b48a", "#f6f1e8", "#cbb992", "#9bb8aa", "#c3b0cc"];

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  color: string;
  rot: number;
  vr: number;
  life: number;
};

export function burstConfetti() {
  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  canvas.style.cssText =
    "position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:80";
  document.body.appendChild(canvas);
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    canvas.remove();
    return;
  }

  const resize = () => {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  };
  resize();
  window.addEventListener("resize", resize);

  const originX = canvas.width / 2;
  const originY = canvas.height * 0.28;
  const particles: Particle[] = Array.from({ length: 48 }, () => {
    const angle = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 0.9;
    const speed = 6 + Math.random() * 9;
    return {
      x: originX,
      y: originY,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      size: 4 + Math.random() * 5,
      color: COLORS[Math.floor(Math.random() * COLORS.length)] ?? "#e4b48a",
      rot: Math.random() * Math.PI,
      vr: (Math.random() - 0.5) * 0.3,
      life: 1,
    };
  });

  let frame = 0;
  let raf = 0;
  const tick = () => {
    frame += 1;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const p of particles) {
      p.vy += 0.22;
      p.vx *= 0.99;
      p.x += p.vx;
      p.y += p.vy;
      p.rot += p.vr;
      p.life -= 0.012;
      if (p.life <= 0) continue;
      ctx.save();
      ctx.globalAlpha = Math.max(0, p.life);
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
      ctx.restore();
    }
    if (frame < 90) {
      raf = requestAnimationFrame(tick);
    } else {
      window.removeEventListener("resize", resize);
      canvas.remove();
    }
  };
  raf = requestAnimationFrame(tick);
  window.setTimeout(() => {
    cancelAnimationFrame(raf);
    window.removeEventListener("resize", resize);
    canvas.remove();
  }, 2500);
}

export function ConfettiBurst({ fire }: { fire: boolean }) {
  useEffect(() => {
    if (fire) burstConfetti();
  }, [fire]);
  return null;
}
