"use client";

import { useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { api, price, sast, toneClass } from "@/lib/format";
import type { HistoryRow } from "@/lib/types";

export default function HistoryPage() {
  return (
    <Shell>
      <History />
    </Shell>
  );
}

function History() {
  const [timeframe, setTimeframe] = useState("ALL");
  const [outcome, setOutcome] = useState("ALL");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const pull = async () => {
      const params = new URLSearchParams({ timeframe, outcome });
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      try {
        const payload = await api<{ rows: HistoryRow[] }>(`/api/signals/history?${params.toString()}`);
        if (live) {
          setRows(payload.rows);
          setError(null);
        }
      } catch (err) {
        if (live) setError(err instanceof Error ? err.message : "Could not load history");
      }
    };
    pull();
    return () => {
      live = false;
    };
  }, [timeframe, outcome, start, end]);

  return (
    <section className="panel px-4 py-5 sm:px-6">
      <h1 className="font-display text-4xl">Signal history</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted">
        Technical model calls on the held-out year. Outcome is the next bar in the direction of the call. Neutral calls are skipped.
      </p>
      <div className="mt-5 grid gap-3 sm:grid-cols-4">
        <Select label="Timeframe" value={timeframe} onChange={setTimeframe} options={["ALL", "H1", "H4", "D1"]} />
        <Select label="Outcome" value={outcome} onChange={setOutcome} options={["ALL", "win", "loss", "pending", "skipped"]} />
        <DateField label="From" value={start} onChange={setStart} />
        <DateField label="To" value={end} onChange={setEnd} />
      </div>
      {error ? <p className="mt-4 text-sm text-bear">{error}</p> : null}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-[11px] uppercase tracking-[0.14em] text-muted">
            <tr>
              <th className="py-2 font-medium">Timestamp</th>
              <th className="py-2 font-medium">Timeframe</th>
              <th className="py-2 font-medium">Prediction</th>
              <th className="py-2 font-medium">Confidence</th>
              <th className="py-2 font-medium">Outcome</th>
              <th className="py-2 font-medium">Pips moved</th>
              <th className="py-2 font-medium">Price</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.time + row.timeframe} className="border-t border-line">
                <td className="py-2 font-mono text-xs">{sast(row.time)}</td>
                <td className="py-2 font-mono">{row.timeframe}</td>
                <td className={`py-2 ${toneClass(row.prediction.includes("BULL") ? "bull" : row.prediction.includes("BEAR") ? "bear" : "neutral")}`}>
                  {row.prediction}
                </td>
                <td className="py-2 font-mono">{row.confidence.toFixed(0)}%</td>
                <td className="py-2 capitalize">{row.outcome}</td>
                <td className="py-2 font-mono">{row.pips.toFixed(1)}</td>
                <td className="py-2 font-mono">{price(row.price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && !error ? <p className="py-6 text-sm text-muted">No signals in this filter.</p> : null}
      </div>
    </section>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <label className="text-xs text-muted">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-lg border border-line bg-[#0b1720] px-3 py-2 text-sm text-ink"
      >
        {options.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
    </label>
  );
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="text-xs text-muted">
      {label}
      <input
        type="date"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-lg border border-line bg-[#0b1720] px-3 py-2 text-sm text-ink"
      />
    </label>
  );
}
