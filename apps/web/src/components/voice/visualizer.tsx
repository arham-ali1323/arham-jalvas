"use client";

import { useEffect, useRef } from "react";

import type { VoiceState } from "@/lib/live";

interface VisualizerProps {
  /** Combined 0..1 loudness (microphone + model output). */
  level: number;
  state: VoiceState;
  className?: string;
}

const BAR_COUNT = 48;

const STATE_COLOR: Record<VoiceState, [number, number, number]> = {
  idle: [56, 90, 120],
  connecting: [56, 130, 160],
  listening: [34, 211, 238],
  thinking: [56, 189, 248],
  speaking: [125, 232, 252],
  error: [248, 113, 113],
};

/**
 * A radial spectrum that responds to real audio loudness and the conversation
 * state. Drawn on a canvas so it stays smooth under React re-renders; the level
 * is read from a ref so a 60fps animation never triggers a render.
 */
export function Visualizer({ level, state, className }: VisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const levelRef = useRef(level);
  const stateRef = useRef(state);
  const smoothRef = useRef(0);

  levelRef.current = level;
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let phase = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      const cx = w / 2;
      const cy = h / 2;
      const base = Math.min(w, h) * 0.22;
      const maxBar = Math.min(w, h) * 0.22;

      const target = levelRef.current;
      smoothRef.current += (target - smoothRef.current) * 0.18;
      const level = smoothRef.current;
      const [r, g, b] = STATE_COLOR[stateRef.current] ?? STATE_COLOR.idle;
      const active = stateRef.current !== "idle";

      // Core glow.
      const coreRadius = base * (0.55 + level * 0.2);
      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreRadius * 2.2);
      core.addColorStop(0, `rgba(${r}, ${g}, ${b}, ${active ? 0.35 : 0.15})`);
      core.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(cx, cy, coreRadius * 2.2, 0, Math.PI * 2);
      ctx.fill();

      ctx.lineCap = "round";
      for (let i = 0; i < BAR_COUNT; i++) {
        const angle = (i / BAR_COUNT) * Math.PI * 2 - Math.PI / 2;
        // A travelling wave keeps the ring alive even at low volume.
        const wave = 0.5 + 0.5 * Math.sin(phase + i * 0.5);
        const energy = active ? level * (0.35 + 0.65 * wave) : 0.02;
        const len = base * 0.12 + maxBar * energy;

        const x1 = cx + Math.cos(angle) * base;
        const y1 = cy + Math.sin(angle) * base;
        const x2 = cx + Math.cos(angle) * (base + len);
        const y2 = cy + Math.sin(angle) * (base + len);

        ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${0.35 + 0.6 * energy})`;
        ctx.lineWidth = (dpr * Math.min(w, h)) / 420;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }

      phase += active ? 0.06 : 0.015;
      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden />;
}
