"use client";

import { useEffect, useRef } from "react";
import type { CandlePayload } from "@/lib/types";

export function PriceChart({ data }: { data: CandlePayload | null }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || !data || data.candles.length === 0) return;
    let chart: { remove: () => void } | null = null;
    let cancelled = false;

    (async () => {
      const { createChart, ColorType, CrosshairMode } = await import("lightweight-charts");
      if (cancelled || !ref.current) return;
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
        timeScale: { borderColor: "#1d3548", timeVisible: true, secondsVisible: false },
        crosshair: { mode: CrosshairMode.Normal },
      });
      const candles = instance.addCandlestickSeries({
        upColor: "#3ddc97",
        downColor: "#ff5d73",
        borderVisible: false,
        wickUpColor: "#3ddc97",
        wickDownColor: "#ff5d73",
      });
      candles.setData(data.candles);
      const ema50 = instance.addLineSeries({
        color: "#f0b429",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      ema50.setData(data.ema50);
      const ema200 = instance.addLineSeries({
        color: "#7eb6ff",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      ema200.setData(data.ema200);
      candles.setMarkers(
        data.markers.map((marker) => ({
          time: marker.time as never,
          position: marker.direction === "bullish" ? "belowBar" : "aboveBar",
          color: marker.direction === "bullish" ? "#3ddc97" : "#ff5d73",
          shape: marker.direction === "bullish" ? "arrowUp" : "arrowDown",
        })),
      );
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
  }, [data]);

  return <div ref={ref} className="h-72 w-full lg:h-[440px]" />;
}
