export type Tone = "bull" | "bear" | "neutral" | "mixed";

export type Market = {
  bid: number | null;
  ask: number | null;
  mid: number | null;
  spread_pips: number | null;
  day_change_pct: number;
  status: "open" | "closed";
  last_tick_sast: string | null;
  connection: "green" | "amber" | "red";
  connection_label: string;
  source: string;
  usdzar: number;
  usdzar_source: string;
  banner: string | null;
};

export type TimeframeSignal = {
  timeframe: string;
  direction: string;
  direction_label: string;
  tone: Exclude<Tone, "mixed">;
  confidence: number;
  price: number | null;
  signal_price: number;
  target: number | null;
  target_pips: number | null;
  invalidation: number | null;
  invalidation_text: string;
  reasons: string[];
  features: Record<string, number | null>;
  tech_score: number;
  news_score: number;
  combined_score: number;
  conflict: boolean;
  warning: string | null;
  withheld: boolean;
  news_label: string;
  probs: { bearish: number; bullish: number; neutral: number };
  penalty: boolean;
  accuracy: { win_rate: number | null; signals: number };
};

export type Article = {
  headline: string;
  source: string;
  published_at: string;
  url: string;
  entities: string[];
  eur_score: number;
  usd_score: number;
  net_score: number;
};

export type CalendarEvent = {
  time: string;
  event: string;
  currency: "EUR" | "USD";
  forecast: string;
  previous: string;
  impact: "High" | "Medium" | "Low";
};

export type DashboardPayload = {
  ready: boolean;
  message: string;
  disclaimer: string;
  market: Market;
  timeframes: TimeframeSignal[];
  alignment: { label: string; tone: Tone };
  news: {
    net: number;
    label: string;
    eur_score: number;
    usd_score: number;
    fxnewsbias_eur: number;
    fxnewsbias_usd: number;
    fxnewsbias_net: number;
    method: string;
    source: string;
    conflict: boolean;
    headlines: Article[];
    drivers: Article[];
    flip: string | null;
    sample: boolean;
    window_count: number;
  };
  calendar: {
    source: string;
    events: CalendarEvent[];
    warning: string | null;
  };
  model: {
    version: string;
    trained_at: string;
    accuracy: number | null;
    dataset_size: number;
    oos_start: string;
    note: string;
  };
  candles_loaded: Record<string, number>;
};

export type CandlePayload = {
  timeframe: string;
  candles: { time: number; open: number; high: number; low: number; close: number }[];
  ema50: { time: number; value: number }[];
  ema200: { time: number; value: number }[];
  markers: { time: number; direction: "bullish" | "bearish" }[];
};

export type PositionResult = {
  lots: number;
  rand_risk: number;
  pip_value_zar: number;
  risk_at_lots: number;
  warning: string | null;
  usdzar: number;
  usdzar_source: string;
  eurusd: number | null;
  disclaimer: string;
};

export type BacktestResult = {
  timeframe: string;
  trades: number;
  win_rate: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  avg_win_pips: number | null;
  avg_loss_pips: number | null;
  max_drawdown: number;
  profit_factor: number | null;
  ending_equity: number;
  capital: number;
  equity_curve: { time: string; equity: number }[];
  disclaimer: string;
  note: string;
};

export type HistoryRow = {
  time: string;
  timeframe: string;
  prediction: string;
  confidence: number;
  outcome: string;
  pips: number;
  price: number;
};

export type AlertSettings = {
  on_flip: boolean;
  on_confidence: boolean;
  on_news: boolean;
  quiet_hours: boolean;
  quiet_start: string;
  quiet_end: string;
  email: string;
};

export type AlertItem = {
  id: number;
  at: string;
  text: string;
  channel: string;
  suppressed: boolean;
  email: string;
};
