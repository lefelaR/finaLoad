-- TrendLens V1 starter schema. TimescaleDB (Postgres).
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS candles_eurusd (
  time TIMESTAMPTZ NOT NULL,
  granularity TEXT NOT NULL,
  open DOUBLE PRECISION NOT NULL,
  high DOUBLE PRECISION NOT NULL,
  low DOUBLE PRECISION NOT NULL,
  close DOUBLE PRECISION NOT NULL,
  volume DOUBLE PRECISION,
  bid DOUBLE PRECISION,
  ask DOUBLE PRECISION,
  spread_pips DOUBLE PRECISION,
  PRIMARY KEY (time, granularity)
);
SELECT create_hypertable('candles_eurusd', 'time', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS ingestion_errors (
  id BIGSERIAL PRIMARY KEY,
  time TIMESTAMPTZ,
  granularity TEXT,
  reason TEXT NOT NULL,
  payload JSONB,
  logged_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS features_eurusd (
  time TIMESTAMPTZ NOT NULL,
  granularity TEXT NOT NULL,
  model_version TEXT NOT NULL,
  features JSONB NOT NULL,
  PRIMARY KEY (time, granularity, model_version)
);

CREATE TABLE IF NOT EXISTS news_articles (
  id BIGSERIAL PRIMARY KEY,
  headline TEXT NOT NULL,
  source TEXT,
  published_at TIMESTAMPTZ NOT NULL,
  url TEXT NOT NULL,
  entities JSONB,
  raw_text TEXT,
  eur_score INT,
  usd_score INT,
  net_score INT,
  UNIQUE (url, headline)
);

CREATE TABLE IF NOT EXISTS signals (
  id BIGSERIAL PRIMARY KEY,
  timeframe TEXT NOT NULL,
  direction TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  price DOUBLE PRECISION,
  target DOUBLE PRECISION,
  invalidation DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  outcome TEXT,
  pips_moved DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS backtests (
  id BIGSERIAL PRIMARY KEY,
  date_range TEXT,
  timeframe TEXT,
  win_rate DOUBLE PRECISION,
  profit_factor DOUBLE PRECISION,
  max_drawdown DOUBLE PRECISION,
  equity_curve JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS failover_events (
  id BIGSERIAL PRIMARY KEY,
  logged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  from_source TEXT,
  to_source TEXT,
  reason TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  message TEXT NOT NULL,
  channel TEXT,
  suppressed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS retrain_log (
  id BIGSERIAL PRIMARY KEY,
  trained_at TIMESTAMPTZ NOT NULL,
  accuracy DOUBLE PRECISION,
  dataset_size INT,
  model_version TEXT
);
