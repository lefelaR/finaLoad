USER STORY DOCUMENT - EUR/USD TrendLens
Version: 1.0 - Build Ready
Focus Pair: EUR/USD ONLY
Account Currency for Calculations: ZAR
App Type: Decision-Support Dashboard - NO auto-trading in V1

Product Vision
As a retail forex trader, I want an app that tells me in under 5 seconds whether EUR/USD is likely to go Bullish, Bearish, or Neutral in the next 1H / 4H / 1D, with evidence, so I can trade with a plan instead of guessing.

The app predicts probability, not certainty. It must always show WHY it made a prediction and how confident it is.

Data Source Decision - FINAL
Primary - OANDA v20 API - FREE with Practice Account

Endpoint Practice: https://api-fxpractice.oanda.com
Endpoint Live: https://api-fxtrade.oanda.com
Instrument: EUR_USD
Historical: GET /v3/instruments/EUR_USD/candles - Back to 2005, granularities S5 to M
Live: GET /v3/accounts/{accountID}/pricing/stream - Streaming bid/ask
Cost: R0 - No subscription fee. API is free with a free OANDA Practice demo account. You only pay spreads if you later trade live.
DO NOT USE OANDA Exchange Rates API - That one is $450/month. We are NOT using it.
Fallback - Twelve Data - FREE

Cost: R0 - Basic Plan
Limit: 8 credits/min, 800 requests/day, trial WebSocket
Use only if OANDA stream fails for >60 seconds. Log the failover.
News - Marketaux - FREE

Cost: R0 - 100 requests/day, 3 articles per request
Tags articles with EUR, USD, ECB, Fed + sentiment -1 to +1
Sentiment Check - FXNewsBias - FREE

Cost: R0 - Free key, previous 3-hour cycle
Gives 0-100 score per currency (EUR, USD)
Economic Calendar - ForexFactory / Investing.com

Use for CPI, NFP, ECB Rate, Fed Rate, PMI
Personas
1. Sipho - Retail Trader (Primary)
Trades EUR/USD on 1H/4H. Checks app in morning before London open and before NY open. Needs signal + reason in 5 seconds on phone.

2. Dev / Analyst (Secondary)
Wants to see backtest accuracy, model features, and audit past signals.

3. TrendLens Engine (System)
Runs 24/5, ingests OANDA data, calculates features, scores news, outputs signal every 1 minute.

EPIC 1: Data Ingestion
US-1.1 - Historical EUR/USD Load
As a trader, I want the app to load 10+ years of EUR/USD history, so the model learns from past bull/bear cycles.

Acceptance Criteria:

On first setup, app calls OANDA GET /v3/instruments/EUR_USD/candles?granularity=H1&count=5000 and paginates back to 2015 minimum, ideally 2005
Supports granularities: M15, H1, H4, D1
Stores in TimescaleDB table candles_eurusd: time, open, high, low, close, volume, bid, ask, spread_pips, granularity
Shows progress bar: "Loaded 850,000 H1 candles..."
Missing/corrupt candles are logged to ingestion_errors table, not crashing the load
No duplicate candles - time + granularity is unique key
US-1.2 - Live Price Streaming
As a trader, I want live EUR/USD price every second, so my signal is never stale.

Acceptance Criteria:

App connects to OANDA Pricing Stream for EUR_USD on startup
UI shows: Live Bid/Ask, Spread in pips, Last Tick Timestamp, Connection Status: Green/Amber/Red
If stream drops, auto-reconnect in <5 seconds, show "Reconnecting..." banner
Latency OANDA tick -> UI <1.5 seconds
If OANDA fails for 60s, auto-switch to Twelve Data WebSocket and log failover_event with timestamp
All ticks are saved to Redis cache (last 1000 ticks) for fast UI
US-1.3 - Economic Calendar
As a trader, I want to see upcoming high-impact EUR/USD news, so I am not surprised by a spike.

Acceptance Criteria:

App pulls calendar for EUR and USD events: CPI, NFP, GDP, ECB Rate Decision, Fed Rate Decision, PMI, Retail Sales
Display: Time (SAST), Event, Currency, Forecast vs Previous, Impact: High / Medium / Low
If High Impact event in <30 mins, show amber warning on dashboard: "High Impact in 25m - ECB Rate - Confidence Reduced"
User can filter: EUR Only / USD Only / All
EPIC 2: News & Sentiment Engine
US-2.1 - Realtime News Ingestion
As a trader, I want the app to read realtime news about EUR and USD.

Acceptance Criteria:

Every 60 seconds, app polls Marketaux for EUR, USD, ECB, {{IE_30002}}Federal Reserve{{/IE_30002}}, EUR/USD
Stores: headline, source, published_at, url, entities[], raw_text
News feed shows latest 20 articles, newest first, with "5m ago" timestamp
Clicking headline opens original source in new tab
Deduplication: Same URL + headline = 1 record only
US-2.2 - News Sentiment Scoring
As a trader, I want each story scored Bullish/Bearish for EUR/USD, so I don't read 50 articles.

Acceptance Criteria:

Each article gets eur_score (-100 to +100) and usd_score (-100 to +100) via FinBERT / LLM API
Net Sentiment for EUR/USD = eur_score - usd_score
Example: "ECB hints at hike" = EUR +75, USD 0 = Net +75 Bullish
3H Aggregated Gauge shows: Strong Bearish (<-60) / Bearish (-60 to -20) / Neutral (-20 to +20) / Bullish (+20 to +60) / Strong Bullish (>+60)
App also pulls FXNewsBias 0-100 score as second opinion. If they disagree by >40 points, show "Sentiment Conflict" badge
US-2.3 - News Impact Explanation
As a trader, I want to know WHICH news caused the signal to change.

Acceptance Criteria:

When sentiment flips, app creates event: "Sentiment flipped to BEARISH at 14:32 SAST due to: US CPI 0.4% vs 0.3% forecast"
Each signal card lists Top 3 contributing headlines with their individual scores
EPIC 3: Trend Prediction Model
US-3.1 - Technical Feature Calculation
As a trader, I want indicators calculated automatically.

Acceptance Criteria:

On every closed candle for H1, H4, D1, calculate: EMA 20/50/200, MACD (12,26,9), RSI 14, ADX 14, ATR 14, Bollinger Bands (20,2), VWAP, Structure: HH/HL vs LH/LL
Features stored in features_eurusd table with model version
Calculation must complete in <500ms after candle close
US-3.2 - Bullish / Bearish Prediction
As a trader, I want a clear prediction: Bullish, Bearish, or Neutral + Confidence % for next H1, H4, D1.

Acceptance Criteria:

Model: XGBoost V1 (must ship first - explainable). LSTM is V2 only.
Output per timeframe: direction, confidence (0-100%), target_price, target_pips, invalidation_price, timestamp
Example: "H4: BEARISH 68% - Target 1.0920 (-45 pips) - Invalidation: Close above 1.1025"
If confidence <55%, output MUST be NEUTRAL, not forced Buy/Sell
Model retrains weekly on new OANDA data. Retraining logs: date, accuracy, dataset size
Model file versioned: model_eurusd_v1.2.pkl
US-3.3 - Combined Signal - Tech + News
As a trader, I want ONE final signal combining technicals + news.

Acceptance Criteria:

Logic:
Tech Bullish + News Bullish = Strong Bullish
Tech Bullish + News Bearish = Neutral / Conflict - Show warning
Tech Bearish + News Bearish = Strong Bearish
News Strong Bearish (<-70) + High Impact Event <1H away = Tech confidence -20%
UI shows 3 gauges: Technical Score, News Score, Final Combined Score
US-3.4 - Explainability
As a trader, I want to see WHY it predicted bullish.

Acceptance Criteria:

Each prediction shows Top 5 Reasons in plain English using SHAP values:
"Price below EMA 200 (Bearish)"
"RSI 38 - Weak momentum"
"US CPI beat forecast - USD Bullish"
No black box - user can expand to see feature values
EPIC 4: Dashboard & UX
US-4.1 - Main Dashboard
As a trader, I want one screen with everything I need in the morning.

Acceptance Criteria:

Top Bar: Live EUR/USD Bid/Ask, Spread, Day Change %, Market Status: Open/Closed
Center: Chart (TradingView Lightweight Charts) with EMA 50/200 overlays + signal markers (green up arrow for Bullish, red down for Bearish)
Right Panel: Signal Card (Direction, Confidence, Target, Invalidation), News Gauge, Next Economic Event
Bottom: Latest 5 News Headlines with sentiment badges
Auto-refresh every 5 seconds, no full page reload
Mobile: Signal Card visible without scrolling
US-4.2 - Multi-Timeframe View
As a trader, I want H1, H4, D1 side-by-side to check alignment.

Acceptance Criteria:

Table: Timeframe | Direction | Confidence | Current Price | Target
Alignment Badge: "All Aligned Bearish" (red) or "Mixed - H1 Bullish, H4 Bearish" (amber)
Clicking timeframe changes chart to that timeframe
US-4.3 - Alerts
As a trader, I want an alert when trend flips.

Acceptance Criteria:

User can toggle: Alert on Flip, Alert if Confidence >70%, Alert 30m before High Impact News
Delivery: In-app bell + Email + Push (PWA)
Alert text: "EUR/USD flipped to BEARISH 68% at 1.0985 - Reason: Price broke EMA200 + US CPI hot"
User can set Quiet Hours: 22:00 - 06:00 SAST (default ON)
Alert history stored, user can see last 50 alerts
EPIC 5: Backtesting & Trust
US-5.1 - Backtest Engine
As a trader, I want to see how the model would have done in the past.

Acceptance Criteria:

Inputs: Date Range, Timeframe, Initial Capital (Default R10,000), Risk per Trade (Default 1%)
Runs on OANDA historical data the model has NEVER trained on (out-of-sample)
Outputs: Win Rate %, Total Trades, Avg Win/Loss, Max Drawdown %, Profit Factor, Equity Curve Chart
Backtest for 2 years H1 data completes in <30 seconds
Shows disclaimer: "Past performance does not guarantee future results"
US-5.2 - Signal History Log
As a trader, I want to audit every past signal.

Acceptance Criteria:

Table: Timestamp | Timeframe | Prediction | Confidence | Outcome (Win/Loss/Pending) | Pips Moved
Filter by Date, Timeframe, Win/Loss
Dashboard shows: "Last 30 Days Accuracy: 61% (H4) - 42 signals"
EPIC 6: Risk Management
US-6.1 - Position Size Calculator
As a trader, I want lot size based on my risk, so I don't blow my account.

Acceptance Criteria:

Inputs: Account Balance (ZAR), Risk % (Default 1%), Stop Loss (pips), Account Currency = ZAR
Uses LIVE USD/ZAR rate to convert pip value. At 1.0 lot EUR/USD = $10 per pip = ~R169 per pip (using live rate)
Outputs: Lot Size, Rand Risk, Pip Value in ZAR
If Risk >2%, show red warning: "High Risk - Consider reducing lot size"
Uses live EUR/USD price from OANDA, not static rate
Non-Functional Requirements
Performance: Dashboard loads <2s, Signal update <1.5s after candle close
Availability: 99.5% uptime Mon 00:00 - Fri 23:00 SAST (Forex market hours)
Security: OANDA token, Twelve Data key, Marketaux key in .env / Secrets Manager. NEVER in frontend code. JWT auth for users. Rate limit API calls.
Data Integrity: All OANDA times stored in UTC, displayed in SAST. No duplicate candles.
Compliance: Every signal card shows: "For educational purposes only, not financial advice." No auto-trading in V1.
Logging: Every signal, failover, retraining, and alert is logged with timestamp.
Tech Stack - V1
Frontend: Next.js + Tailwind CSS + TradingView Lightweight Charts
Backend: Python FastAPI - Ingestion, Features, Model Inference
DB: TimescaleDB (Postgres) for candles + Redis for live price cache
ML: XGBoost + SHAP for prediction, FinBERT / LLM API for news sentiment
Infra: Docker, Deploy on Railway / Render
APIs: OANDA v20 Practice (Primary), Twelve Data (Fallback), Marketaux (News), FXNewsBias (Sentiment Check)
Database Schema - Starter
candles_eurusd(time TIMESTAMPTZ, granularity TEXT, open FLOAT, high FLOAT, low FLOAT, close FLOAT, volume FLOAT, spread_pips FLOAT)
news_articles(id, headline, source, published_at, url, eur_score INT, usd_score INT, net_score INT)
signals(id, timeframe, direction, confidence, price, target, invalidation, created_at, outcome)
backtests(id, date_range, timeframe, win_rate, profit_factor, max_drawdown, equity_curve JSON)

Definition of Done - V1
V1 is DONE when a user can:

Open app, see LIVE EUR/USD price from OANDA Practice
See H1/H4/D1 Bullish/Bearish/Neutral + Confidence + Top 5 Reasons
See News Sentiment Gauge + Top 3 headlines driving it
Run a 1-year backtest and see Win Rate + Equity Curve
Get an alert when signal flips
Want me to now turn this into:



