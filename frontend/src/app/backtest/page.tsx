"use client";

import { useEffect, useRef, useState } from "react";
import { Shell } from "@/components/Shell";
import { api } from "@/lib/format";
import type { BacktestResult } from "@/lib/types";
import { EquityChart } from "@/components/EquityChart";

type Health = { ready: boolean; message: string; oos_start: string | null };

export default function BacktestPage() {
  return (
    <Shell>
      <Backtest />
    </Shell>
  );
}

function Backtest() {
  const [health, setHealth] = useState<Health | null>(null);
  const [timeframe, setTimeframe] = useState("H4");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [capital, setCapital] = useState(10000);
  const [risk, setRisk] = useState(1);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const seeded = useRef(false);

  useEffect(() => {
    let live = true;
    const pull = async () => {
      try {
        const payload = await api<Health>("/api/health");
        if (!live) return;
        setHealth(payload);
        if (payload.oos_start && !seeded.current) {
          seeded.current = true;
          setStart(payload.oos_start.slice(0, 10));
          setEnd(new Date().toISOString().slice(0, 10));
        }
      } catch {
        if (live) setHealth({ ready: false, message: "Cannot reach the TrendLens engine.", oos_start: null });
      }
    };
    pull();
    const timer = window.setInterval(pull, 2000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, []);

  async function run(event: React.FormEvent) {
    event.preventDefault();
    setRunning(true);
    setError(null);
    try {
      const payload = await api<BacktestResult>("/api/backtest", {
        method: "POST",
        body: JSON.stringify({ timeframe, start, end, capital, risk_pct: risk }),
      });
      setResult(payload);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="panel px-4 py-5 sm:px-6">
      <h1 className="font-display text-4xl">Backtest</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted">
        Technical model only, on the held-out year it never trained on. The live card also folds in news.
      </p>
      {health && !health.ready ? <p className="mt-4 text-sm text-amber">{health.message}</p> : null}
      <form onSubmit={run} className="mt-6 grid gap-3 sm:grid-cols-5">
        <label className="text-xs text-muted">
          Timeframe
          <select
            value={timeframe}
            onChange={(event) => setTimeframe(event.target.value)}
            className="mt-1 w-full rounded-lg border border-line bg-[#0b1720] px-3 py-2 text-sm text-ink"
          >
            <option>H1</option>
            <option>H4</option>
            <option>D1</option>
          </select>
        </label>
        <Field label="Start" type="date" value={start} onChange={setStart} />
        <Field label="End" type="date" value={end} onChange={setEnd} />
        <NumberField label="Capital (ZAR)" value={capital} onChange={setCapital} />
        <NumberField label="Risk %" value={risk} step={0.1} onChange={setRisk} />
        <button
          type="submit"
          disabled={!health?.ready || running}
          className="sm:col-span-5 mt-2 rounded-full bg-amber px-4 py-2 text-sm font-medium text-[#1a1203] disabled:opacity-50"
        >
          {running ? "Running…" : "Run backtest"}
        </button>
      </form>
      {error ? <p className="mt-4 text-sm text-bear">{error}</p> : null}
      {result ? (
        <div className="mt-6">
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Tile label="Win rate" value={result.win_rate == null ? "—" : `${result.win_rate}%`} />
            <Tile label="Trades" value={String(result.trades)} />
            <Tile label="Avg win" value={money(result.avg_win)} />
            <Tile label="Avg loss" value={money(result.avg_loss)} />
            <Tile label="Max drawdown" value={`${result.max_drawdown}%`} />
            <Tile label="Profit factor" value={result.profit_factor == null ? "No losses" : String(result.profit_factor)} />
          </div>
          <p className="mt-3 font-mono text-sm">
            R{result.capital.toLocaleString()} → R{result.ending_equity.toLocaleString()}
          </p>
          <div className="mt-4">
            <EquityChart points={result.equity_curve} />
          </div>
          <p className="mt-4 text-sm text-amber">{result.disclaimer}</p>
          <p className="mt-2 text-xs text-muted">{result.note}</p>
        </div>
      ) : null}
    </section>
  );
}

function money(value: number | null): string {
  if (value == null) return "—";
  return `R${value.toLocaleString()}`;
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line px-3 py-3">
      <div className="text-[11px] uppercase tracking-[0.14em] text-muted">{label}</div>
      <div className="mt-1 font-mono text-lg">{value}</div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type: string;
}) {
  return (
    <label className="text-xs text-muted">
      {label}
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-lg border border-line bg-[#0b1720] px-3 py-2 text-sm text-ink"
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
}) {
  return (
    <label className="text-xs text-muted">
      {label}
      <input
        type="number"
        min={step}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-1 w-full rounded-lg border border-line bg-[#0b1720] px-3 py-2 font-mono text-sm text-ink"
      />
    </label>
  );
}
