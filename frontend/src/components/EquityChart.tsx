"use client";

import { useEffect, useRef } from "react";

export function EquityChart({ points }: { points: { time: string; equity: number }[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || points.length < 2) return;
    let chart: { remove: () => void } | null = null;
    let cancelled = false;
    const series = dedupe(points);

    (async () => {
      const { createChart, ColorType } = await import("lightweight-charts");
      if (cancelled || !ref.current || series.length < 2) return;
      const instance = createChart(ref.current, {
        width: ref.current.clientWidth,
        height: ref.current.clientHeight,
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: "#8ea3b5",
          fontFamily: "IBM Plex Mono, ui-monospace, monospace",
        },
        grid: {
          vertLines: { color: "rgba(29, 53, 72, 0.65)" },
          horzLines: { color: "rgba(29, 53, 72, 0.65)" },
        },
        rightPriceScale: { borderColor: "#1d3548" },
        timeScale: { borderColor: "#1d3548" },
      });
      const line = instance.addLineSeries({ color: "#f0b429", lineWidth: 2 });
      line.setData(series);
      instance.timeScale().fitContent();
      const observer = new ResizeObserver(() => {
        if (!ref.current) return;
        instance.applyOptions({ width: ref.current.clientWidth, height: ref.current.clientHeight });
      });
      observer.observe(ref.current);
      chart = {
        remove: () => {
          observer.disconnect();
          instance.remove();
        },
      };
    })();

    return () => {
      cancelled = true;
      chart?.remove();
    };
  }, [points]);

  if (points.length < 2) {
    return <p className="text-sm text-muted">Not enough trades to draw an equity curve.</p>;
  }
  return <div ref={ref} className="h-64 w-full" />;
}

function dedupe(points: { time: string; equity: number }[]) {
  const rows: { time: number; value: number }[] = [];
  for (const point of points) {
    const time = Math.floor(new Date(point.time).getTime() / 1000);
    if (!Number.isFinite(time)) continue;
    const last = rows[rows.length - 1];
    if (last && last.time === time) last.value = point.equity;
    else if (!last || time > last.time) rows.push({ time, value: point.equity });
  }
  return rows;
}
