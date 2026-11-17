"use client";

import { useEffect, useMemo, useState } from "react";
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

type SortKey = "time" | "timeframe" | "prediction" | "confidence" | "outcome" | "pips" | "price";

const TIMEFRAME_ORDER: Record<string, number> = { M15: 0, H1: 1, H4: 2, D1: 3 };

function History() {
  const [timeframe, setTimeframe] = useState("ALL");
  const [outcome, setOutcome] = useState("ALL");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("time");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((direction) => (direction === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir(key === "time" || key === "confidence" || key === "pips" || key === "price" ? "desc" : "asc");
  }

  const sorted = useMemo(() => {
    const copy = [...rows];
    const factor = sortDir === "asc" ? 1 : -1;
    copy.sort((a, b) => {
      const result = compareRows(a, b, sortKey);
      return result * factor;
    });
    return copy;
  }, [rows, sortKey, sortDir]);

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
              <SortHeader label="Timestamp" column="time" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="Timeframe" column="timeframe" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="Prediction" column="prediction" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="Confidence" column="confidence" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="Outcome" column="outcome" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="Pips moved" column="pips" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="Price" column="price" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
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

function compareRows(a: HistoryRow, b: HistoryRow, key: SortKey): number {
  if (key === "time") return a.time.localeCompare(b.time);
  if (key === "timeframe") return (TIMEFRAME_ORDER[a.timeframe] ?? 9) - (TIMEFRAME_ORDER[b.timeframe] ?? 9);
  if (key === "prediction") return a.prediction.localeCompare(b.prediction);
  if (key === "confidence") return a.confidence - b.confidence;
  if (key === "outcome") return a.outcome.localeCompare(b.outcome);
  if (key === "pips") return a.pips - b.pips;
  return a.price - b.price;
}

function SortHeader({
  label,
  column,
  sortKey,
  sortDir,
  onSort,
}: {
  label: string;
  column: SortKey;
  sortKey: SortKey;
  sortDir: "asc" | "desc";
  onSort: (column: SortKey) => void;
}) {
  const active = sortKey === column;
  const mark = active ? (sortDir === "asc" ? "↑" : "↓") : "";
  return (
    <th className="py-2 font-medium">
      <button
        type="button"
        onClick={() => onSort(column)}
        aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
        className={`inline-flex items-center gap-1 uppercase tracking-[0.14em] ${active ? "text-ink" : "text-muted"}`}
      >
        {label}
        <span className="w-3 text-[10px]" aria-hidden="true">
          {mark}
        </span>
      </button>
    </th>
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
