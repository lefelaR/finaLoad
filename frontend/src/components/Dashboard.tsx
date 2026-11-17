"use client";

import { useEffect, useMemo, useState } from "react";
import { PriceChart } from "@/components/Chart";
import { ago, api, price, sast, scoreTone, signed, toneClass } from "@/lib/format";
import type {
  AlertItem,
  CalendarEvent,
  CandlePayload,
  DashboardPayload,
  Market,
  PositionResult,
  TimeframeSignal,
} from "@/lib/types";

const TIMEFRAMES = ["H1", "H4", "D1"];

export function Dashboard() {
  const [status, setStatus] = useState("Starting the engine…");
  const [failed, setFailed] = useState(false);
  const [board, setBoard] = useState<DashboardPayload | null>(null);
  const [market, setMarket] = useState<Market | null>(null);
  const [timeframe, setTimeframe] = useState("H4");
  const [candles, setCandles] = useState<CandlePayload | null>(null);
  const [showAllNews, setShowAllNews] = useState(false);
  const [currency, setCurrency] = useState<"ALL" | "EUR" | "USD">("ALL");
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [balance, setBalance] = useState(10000);
  const [risk, setRisk] = useState(1);
  const [stop, setStop] = useState(25);
  const [position, setPosition] = useState<PositionResult | null>(null);
  const [positionError, setPositionError] = useState<string | null>(null);

  useEffect(() => {
    let stopPolling = false;
    const wait = async () => {
      while (!stopPolling) {
        try {
          const health = await api<{ ready: boolean; message: string }>("/api/health");
          setStatus(health.message);
          setFailed(false);
          if (health.ready) return;
        } catch {
          setFailed(true);
          setStatus("Cannot reach the TrendLens engine.");
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    };
    wait();
    return () => {
      stopPolling = true;
    };
  }, []);

  useEffect(() => {
    let live = true;
    const pull = async () => {
      try {
        const payload = await api<DashboardPayload>("/api/dashboard");
        if (!live || !payload.ready) return;
        setBoard(payload);
        setMarket(payload.market);
        setFailed(false);
      } catch {
        if (live) setFailed(true);
      }
    };
    const marketPull = async () => {
      try {
        const payload = await api<Market>("/api/market");
        if (live) setMarket(payload);
      } catch {
        /* the dashboard poll reports a dead engine */
      }
    };
    const alertPull = async () => {
      try {
        const payload = await api<{ alerts: AlertItem[] }>("/api/alerts");
        if (live) setAlerts(payload.alerts.filter((item) => !item.suppressed));
      } catch {
        /* bell stays quiet */
      }
    };
    pull();
    marketPull();
    alertPull();
    const boardTimer = window.setInterval(pull, 5000);
    const marketTimer = window.setInterval(marketPull, 1000);
    const alertTimer = window.setInterval(alertPull, 15000);
    return () => {
      live = false;
      window.clearInterval(boardTimer);
      window.clearInterval(marketTimer);
      window.clearInterval(alertTimer);
    };
  }, []);

  useEffect(() => {
    if (!board?.ready) return;
    let live = true;
    const pull = async () => {
      try {
        const payload = await api<CandlePayload>(`/api/candles?timeframe=${timeframe}`);
        if (live) setCandles(payload);
      } catch {
        /* chart keeps the last good frame */
      }
    };
    pull();
    const timer = window.setInterval(pull, 15000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [board?.ready, timeframe]);

  useEffect(() => {
    if (!board?.ready) return;
    const handle = window.setTimeout(async () => {
      try {
        const result = await api<PositionResult>("/api/risk/position", {
          method: "POST",
          body: JSON.stringify({ balance, risk_pct: risk, stop_pips: stop }),
        });
        setPosition(result);
        setPositionError(null);
      } catch (error) {
        setPositionError(error instanceof Error ? error.message : "Could not size the position");
      }
    }, 250);
    return () => window.clearTimeout(handle);
  }, [board?.ready, balance, risk, stop]);

  const selected = board?.timeframes.find((row) => row.timeframe === timeframe) ?? board?.timeframes[0];
  const quote = market ?? board?.market ?? null;
  const events = useMemo(() => {
    const list = board?.calendar.events ?? [];
    if (currency === "ALL") return list;
    return list.filter((event) => event.currency === currency);
  }, [board, currency]);

  if (!board?.ready || !selected || !quote) {
    return (
      <section className="panel px-6 py-16">
        <p className="text-xs uppercase tracking-[0.18em] text-amber">EUR/USD</p>
        <h1 className="mt-3 font-display text-4xl">{failed ? "Engine offline" : "Loading history"}</h1>
        <p className="mt-4 max-w-xl text-muted">{status}</p>
      </section>
    );
  }

  const headlines = showAllNews ? board.news.headlines : board.news.headlines.slice(0, 5);

  return (
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_390px] lg:items-start">
      <SignalCard
        signal={selected}
        news={board.news}
        disclaimer={board.disclaimer}
        warning={board.calendar.warning}
        className="order-1 lg:order-2"
      />

      <div className="order-2 space-y-4 lg:order-1">
      <PriceBar market={quote} />
      {quote.banner ? (
        <div className="border border-amber/50 bg-amber/10 px-4 py-2 text-sm text-amber">{quote.banner}</div>
      ) : null}
      {board.calendar.warning ? (
        <div className="hidden border border-amber/50 bg-amber/10 px-4 py-2 text-sm text-amber lg:block">
          {board.calendar.warning}
        </div>
      ) : null}

      <section className="space-y-4">
        <div className="panel px-4 py-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className={`text-sm font-medium ${toneClass(board.alignment.tone)}`}>{board.alignment.label}</div>
              <div className="mt-1 text-xs text-muted">
                {selected.accuracy.signals
                  ? `Last 30 days accuracy: ${selected.accuracy.win_rate}% (${selected.timeframe}) — ${selected.accuracy.signals} signals`
                  : `Last 30 days: no resolved ${selected.timeframe} signals`}
              </div>
            </div>
            <div className="flex gap-1">
              {TIMEFRAMES.map((item) => (
                <button
                  key={item}
                  type="button"
                  aria-pressed={item === timeframe}
                  onClick={() => setTimeframe(item)}
                  className={`rounded-full px-3 py-1 text-sm ${item === timeframe ? "bg-white text-[#102018]" : "text-muted"}`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
          <PriceChart data={candles} />
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
            <span className="text-amber">EMA 50</span>
            <span className="text-sea">EMA 200</span>
            <span>Green arrow bullish · red arrow bearish</span>
            <span>{board.candles_loaded.H1?.toLocaleString()} H1 candles loaded</span>
          </div>
        </div>

        <section className="panel px-4 py-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-sm uppercase tracking-[0.16em] text-muted">Headlines</h2>
            {board.news.sample ? (
              <span className="text-xs text-muted">Sample wire — add a Marketaux key for the live feed</span>
            ) : (
              <span className="text-xs text-muted">Marketaux</span>
            )}
          </div>
          <ul className="divide-y divide-line">
            {headlines.map((article) => (
              <li key={article.url + article.headline} className="flex items-start justify-between gap-4 py-3">
                <div>
                  <a href={article.url} target="_blank" rel="noreferrer" className="hover:text-sea">
                    {article.headline}
                  </a>
                  <div className="mt-1 text-xs text-muted">
                    {article.source} · {ago(article.published_at)}
                  </div>
                </div>
                <Score net={article.net_score} />
              </li>
            ))}
          </ul>
          {board.news.headlines.length > 5 ? (
            <button type="button" className="mt-2 text-sm text-sea" onClick={() => setShowAllNews((value) => !value)}>
              {showAllNews ? "Show latest 5" : `Show all ${board.news.headlines.length}`}
            </button>
          ) : null}
        </section>

        <TimeframeTable rows={board.timeframes} selected={timeframe} onSelect={setTimeframe} />
        <CalendarList events={events} currency={currency} onCurrency={setCurrency} source={board.calendar.source} />
        <RiskPanel
          balance={balance}
          risk={risk}
          stop={stop}
          quote={quote}
          result={position}
          error={positionError}
          onBalance={setBalance}
          onRisk={setRisk}
          onStop={setStop}
        />
        <p className="px-1 text-xs leading-5 text-muted">
          {board.model.version} · trained {sast(board.model.trained_at)} · dataset {board.model.dataset_size.toLocaleString()} rows
          {board.model.accuracy != null ? ` · class accuracy ${(board.model.accuracy * 100).toFixed(1)}%` : ""}. {board.model.note}
        </p>
      </section>
      </div>

      <a
        href="/alerts"
        className="fixed bottom-4 right-4 rounded-full border border-line bg-panel px-4 py-2 text-sm shadow-lg"
      >
        Alerts{alerts.length ? ` ${alerts.length}` : ""}
      </a>
    </div>
  );
}

function PriceBar({ market, className }: { market: Market; className?: string }) {
  const up = market.day_change_pct >= 0;
  const dot = market.connection === "green" ? "bg-bull" : market.connection === "red" ? "bg-bear" : "bg-amber";
  return (
    <section className={`panel flex flex-wrap items-end justify-between gap-4 px-4 py-4 ${className ?? ""}`}>
      <div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-muted">EUR/USD</div>
        <div className="mt-1 font-mono text-3xl tracking-tight">
          {price(market.bid)} <span className="text-muted">/</span> {price(market.ask)}
        </div>
        <div className="mt-1 text-xs text-muted">Bid / Ask · tick {market.last_tick_sast ?? "—"}</div>
      </div>
      <div className="grid grid-cols-3 gap-6 text-sm">
        <Stat label="Spread" value={market.spread_pips == null ? "—" : `${market.spread_pips.toFixed(1)} pips`} />
        <Stat label="Day" value={signed(market.day_change_pct) + "%"} className={up ? "text-bull" : "text-bear"} />
        <Stat label="Market" value={market.status === "open" ? "Open" : "Closed"} />
      </div>
      <div className="flex items-center gap-2 text-sm">
        <span className={`size-2.5 rounded-full ${dot}`} />
        <span>{market.connection_label}</span>
      </div>
    </section>
  );
}

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.16em] text-muted">{label}</div>
      <div className={`mt-1 font-mono ${className ?? ""}`}>{value}</div>
    </div>
  );
}

function SignalCard({
  signal,
  news,
  disclaimer,
  warning,
  className,
}: {
  signal: TimeframeSignal;
  news: DashboardPayload["news"];
  disclaimer: string;
  warning: string | null;
  className?: string;
}) {
  return (
    <aside className={`panel h-fit p-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-auto ${className ?? ""}`}>
      {warning ? <p className="mb-3 text-sm text-amber">{warning}</p> : null}
      <div className="text-[11px] uppercase tracking-[0.18em] text-muted">{signal.timeframe} · next bar</div>
      <h1 className={`mt-2 font-display text-5xl leading-none ${toneClass(signal.tone)}`}>{signal.direction_label}</h1>
      <div className="mt-3 font-mono text-3xl">{signal.confidence.toFixed(0)}%</div>
      <p className="mt-2 text-sm text-muted">
        {signal.timeframe}: {signal.direction_label} {signal.confidence.toFixed(0)}%
        {signal.target != null ? ` — Target ${price(signal.target)} (${signed(signal.target_pips ?? 0, 1)} pips)` : ""}
        {signal.invalidation_text ? ` — Invalidation: ${signal.invalidation_text}` : ""}
      </p>
      {signal.warning ? <p className="mt-3 text-sm text-amber">{signal.warning}</p> : null}
      {signal.penalty ? (
        <p className="mt-2 text-sm text-amber">Technical confidence reduced 20% — strong bearish news and a high-impact event inside an hour.</p>
      ) : null}
      {signal.withheld && !signal.conflict ? (
        <p className="mt-2 text-sm text-amber">
          Technical lean is {signal.tech_lean}, but confidence is under 55%, so the call stays neutral.
        </p>
      ) : null}

      <div className="mt-5 space-y-3">
        <Gauge label="Technical" value={signal.tech_score} />
        <Gauge label="News" value={signal.news_score} />
        <Gauge label="Combined" value={signal.combined_score} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <span className="rounded-full border border-line px-2 py-1">News {news.label}</span>
        {news.conflict ? <span className="rounded-full border border-amber/60 px-2 py-1 text-amber">Sentiment conflict</span> : null}
      </div>
      <p className="mt-2 text-xs text-muted">
        FXNewsBias previous cycle EUR {news.fxnewsbias_eur} / USD {news.fxnewsbias_usd}. Our 3h net {signed(news.net, 0)}.
      </p>
      {news.flip ? <p className="mt-2 text-sm">{news.flip}</p> : null}

      <h2 className="mt-5 text-[11px] uppercase tracking-[0.16em] text-muted">Why</h2>
      <ol className="mt-2 space-y-2 text-sm">
        {signal.reasons.map((reason, index) => (
          <li key={reason} className="flex gap-2">
            <span className="font-mono text-muted">{index + 1}</span>
            <span>{reason}</span>
          </li>
        ))}
      </ol>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-sea">Feature values</summary>
        <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-xs">
          {Object.entries(signal.features).map(([name, value]) => (
            <div key={name} className="contents">
              <dt className="text-muted">{name}</dt>
              <dd>{value == null ? "—" : value.toFixed(4)}</dd>
            </div>
          ))}
          <div className="contents">
            <dt className="text-muted">P(bear / bull)</dt>
            <dd>
              {signal.probs.bearish}/{signal.probs.bullish}
            </dd>
          </div>
        </dl>
      </details>

      <h2 className="mt-5 text-[11px] uppercase tracking-[0.16em] text-muted">Headlines behind the gauge</h2>
      <ul className="mt-2 space-y-2">
        {news.drivers.map((article) => (
          <li key={article.headline} className="text-sm">
            <a href={article.url} target="_blank" rel="noreferrer" className="hover:text-sea">
              {article.headline}
            </a>
            <div className="mt-1">
              <Score net={article.net_score} />
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-5 text-xs text-muted">{disclaimer}</p>
    </aside>
  );
}

function Gauge({ label, value }: { label: string; value: number }) {
  const clamped = Math.max(-100, Math.min(100, value));
  return (
    <div>
      <div className="mb-1 flex justify-between text-[11px] uppercase tracking-[0.14em] text-muted">
        <span>{label}</span>
        <span className="font-mono text-ink">{clamped}</span>
      </div>
      <div className="relative h-1.5 rounded-full bg-[linear-gradient(90deg,#ff5d73,#f0b429_50%,#3ddc97)]">
        <span
          className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#07111a] bg-white"
          style={{ left: `${(clamped + 100) / 2}%` }}
        />
      </div>
    </div>
  );
}

function Score({ net }: { net: number }) {
  const tone = scoreTone(net);
  const label = tone === "bull" ? "Bullish" : tone === "bear" ? "Bearish" : "Neutral";
  return (
    <span className={`shrink-0 rounded-full border border-line px-2 py-0.5 font-mono text-xs ${toneClass(tone)}`}>
      {label} {net > 0 ? `+${net}` : net}
    </span>
  );
}

function TimeframeTable({
  rows,
  selected,
  onSelect,
}: {
  rows: TimeframeSignal[];
  selected: string;
  onSelect: (timeframe: string) => void;
}) {
  return (
    <section className="panel overflow-x-auto px-4 py-4">
      <h2 className="mb-3 text-sm uppercase tracking-[0.16em] text-muted">Timeframes</h2>
      <table className="w-full text-left text-sm">
        <thead className="text-[11px] uppercase tracking-[0.14em] text-muted">
          <tr>
            <th className="py-2 font-medium">Timeframe</th>
            <th className="py-2 font-medium">Direction</th>
            <th className="py-2 font-medium">Confidence</th>
            <th className="py-2 font-medium">Price</th>
            <th className="py-2 font-medium">Target</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.timeframe}
              onClick={() => onSelect(row.timeframe)}
              className={`cursor-pointer border-t border-line ${row.timeframe === selected ? "bg-white/5" : ""}`}
            >
              <td className="py-3 font-mono">{row.timeframe}</td>
              <td className={`py-3 ${toneClass(row.tone)}`}>{row.direction_label}</td>
              <td className="py-3 font-mono">{row.confidence.toFixed(0)}%</td>
              <td className="py-3 font-mono">{price(row.price)}</td>
              <td className="py-3 font-mono">{price(row.target)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function CalendarList({
  events,
  currency,
  onCurrency,
  source,
}: {
  events: CalendarEvent[];
  currency: "ALL" | "EUR" | "USD";
  onCurrency: (value: "ALL" | "EUR" | "USD") => void;
  source: string;
}) {
  return (
    <section className="panel px-4 py-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm uppercase tracking-[0.16em] text-muted">Economic calendar</h2>
          <p className="mt-1 text-xs text-muted">{source} — not a live ForexFactory feed</p>
        </div>
        <div className="flex gap-1">
          {(["ALL", "EUR", "USD"] as const).map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={item === currency}
              onClick={() => onCurrency(item)}
              className={`rounded-full px-3 py-1 text-sm ${item === currency ? "bg-white text-[#102018]" : "text-muted"}`}
            >
              {item === "ALL" ? "All" : item}
            </button>
          ))}
        </div>
      </div>
      <ul className="divide-y divide-line">
        {events.map((event) => (
          <li key={event.event + event.time} className="grid gap-2 py-3 sm:grid-cols-[1.2fr_1.4fr_auto_auto] sm:items-center">
            <div className="font-mono text-xs text-muted">{sast(event.time)}</div>
            <div>
              {event.event}
              <span className="ml-2 text-xs text-muted">{event.currency}</span>
            </div>
            <div className="font-mono text-xs text-muted">
              Fcst {event.forecast} · Prev {event.previous}
            </div>
            <Impact impact={event.impact} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function Impact({ impact }: { impact: string }) {
  const tone = impact === "High" ? "text-bear" : impact === "Medium" ? "text-amber" : "text-muted";
  return <span className={`text-xs uppercase tracking-[0.14em] ${tone}`}>{impact}</span>;
}

function RiskPanel({
  balance,
  risk,
  stop,
  quote,
  result,
  error,
  onBalance,
  onRisk,
  onStop,
}: {
  balance: number;
  risk: number;
  stop: number;
  quote: Market;
  result: PositionResult | null;
  error: string | null;
  onBalance: (value: number) => void;
  onRisk: (value: number) => void;
  onStop: (value: number) => void;
}) {
  return (
    <section className="panel px-4 py-4">
      <h2 className="text-sm uppercase tracking-[0.16em] text-muted">Position size · ZAR account</h2>
      <p className="mt-2 text-xs text-muted">
        One standard lot of EUR/USD is $10 a pip. Rand value uses {quote.usdzar_source} ({quote.usdzar.toFixed(2)}). Live
        EUR/USD {price(quote.mid)}.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Field label="Balance (ZAR)" value={balance} onChange={onBalance} />
        <Field label="Risk %" value={risk} step={0.1} onChange={onRisk} />
        <Field label="Stop (pips)" value={stop} onChange={onStop} />
      </div>
      {error ? <p className="mt-3 text-sm text-bear">{error}</p> : null}
      {result ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <Stat label="Lot size" value={result.lots.toFixed(2)} />
          <Stat label="Rand risk" value={`R${result.rand_risk.toLocaleString()}`} />
          <Stat label="Pip value" value={`R${result.pip_value_zar.toFixed(2)}`} />
        </div>
      ) : null}
      {result?.warning ? <p className="mt-3 text-sm text-bear">{result.warning}</p> : null}
    </section>
  );
}

function Field({
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
    <label className="block text-xs text-muted">
      {label}
      <input
        type="number"
        min={step}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-1 w-full rounded-lg border border-line bg-[#0b1720] px-3 py-2 font-mono text-sm text-ink outline-none focus:border-sea"
      />
    </label>
  );
}
