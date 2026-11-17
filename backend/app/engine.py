"""Holds candles, the model, live ticks, news and the dashboard snapshot."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from app.backtest import accuracy_30d, history_rows, run_backtest
from app.calendar_feed import filter_events, upcoming_events
from app.generate import generate_h1, resample_candles
from app.logic import (
    DISCLAIMER,
    MODEL_VERSION,
    alignment_badge,
    apply_confidence_gate,
    combine_signal,
    direction_tone,
    display_direction,
    event_within,
    flip_message,
    format_sast,
    high_impact_warning,
    in_quiet_hours,
    market_is_open,
    news_side,
    sentiment_conflict,
    target_and_invalidation,
)
from app.model import latest_from_row, predict_frame, train_all
from app.news import aggregate, load_news
from app.oanda import fetch_history, headers, pricing_stream_url, twelve_data_price

log = logging.getLogger("trendlens")
CACHE = Path(__file__).resolve().parent.parent / ".cache"
SETTINGS_PATH = CACHE / "alert_settings.json"
ORDER = ("H1", "H4", "D1")


def _json_ready(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, float) and value != value:
        return None
    return value


class Engine:
    def __init__(self) -> None:
        self.ready = False
        self.message = "Starting"
        self.frames: dict[str, pd.DataFrame] = {}
        self.model: dict | None = None
        self.predictions: dict[str, pd.DataFrame] = {}
        self.signals: dict[str, dict] = {}
        self.history: dict[str, list] = {}
        self.accuracy: dict[str, dict] = {}
        self.news: list[dict] = []
        self.news_source = "sample"
        self.news_agg: dict = {}
        self.sentiment_label: str | None = None
        self.sentiment_event: str | None = None
        self.ticks: deque = deque(maxlen=1000)
        self.mid: float | None = None
        self.bid: float | None = None
        self.ask: float | None = None
        self.spread_pips = 1.1
        self.last_tick: datetime | None = None
        self.usdzar = 18.40
        self.usdzar_source = "reference 18.40"
        self.source = "demo"
        self.connection = "amber"
        self.connection_label = "Starting"
        self.failover_events: list[dict] = []
        self.ingestion_errors: list[dict] = []
        self.alerts: list[dict] = []
        self.alert_settings = self._load_settings()
        self.last_directions: dict[str, str] = {}
        self.alerted_keys: set[str] = set()
        self.alerts_armed = False
        self.failover_active = False
        self.redis = None
        self._alert_seq = 0

    def _load_settings(self) -> dict:
        default = {
            "on_flip": True,
            "on_confidence": False,
            "on_news": True,
            "quiet_hours": True,
            "quiet_start": "22:00",
            "quiet_end": "06:00",
            "email": "",
        }
        if SETTINGS_PATH.exists():
            try:
                stored = json.loads(SETTINGS_PATH.read_text())
                default.update(stored)
            except (OSError, json.JSONDecodeError):
                pass
        return default

    def save_settings(self, updates: dict) -> dict:
        allowed = {
            "on_flip",
            "on_confidence",
            "on_news",
            "quiet_hours",
            "quiet_start",
            "quiet_end",
            "email",
        }
        for key, value in updates.items():
            if key in allowed:
                self.alert_settings[key] = value
        CACHE.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(self.alert_settings))
        return self.alert_settings

    async def bootstrap(self) -> None:
        try:
            await self._bootstrap()
        except Exception as exc:
            self.message = f"Engine failed: {exc}"
            log.exception("bootstrap failed")

    async def _bootstrap(self) -> None:
        await asyncio.to_thread(self._connect_redis)
        await self._load_usdzar()
        token = os.environ.get("OANDA_API_TOKEN", "").strip()
        frames = None
        errors: list[dict] = []
        if token:
            self.message = "Loading EUR/USD history from OANDA"
            try:
                frames, errors = await asyncio.to_thread(self._load_oanda)
                self.source = "oanda"
            except Exception:
                log.exception("OANDA history failed, using the demo path")
                self.message = "OANDA history failed — loading the demo path"
                frames = None
        if frames is None:
            self.message = "Loading demo EUR/USD history"
            frames, errors = await asyncio.to_thread(self._load_demo)
            self.source = "demo"
        self.frames = frames
        self.ingestion_errors = errors
        h1 = len(frames["H1"])
        self.message = f"Loaded {h1:,} H1 candles — training {MODEL_VERSION}"
        self.model = await asyncio.to_thread(train_all, frames)
        for timeframe in ORDER:
            self.predictions[timeframe] = predict_frame(self.model["bundles"][timeframe])
        self.refresh_news()
        self.compose(arm_alerts=False)
        self._seed_price()
        self.ready = True
        self.connection = "green"
        self.connection_label = "OANDA" if self.source == "oanda" else "Demo feed"
        self.message = f"Loaded {h1:,} H1 candles"
        log.info(self.message)

    def _load_demo(self) -> tuple[dict, list]:
        h1, errors = generate_h1()
        frames = {
            "H1": h1,
            "H4": resample_candles(h1, "4h", "H4"),
            "D1": resample_candles(h1, "1D", "D1"),
        }
        return frames, errors

    def _load_oanda(self) -> tuple[dict, list]:
        start = datetime(2015, 1, 1, tzinfo=timezone.utc)
        frames = {}
        errors: list[dict] = []
        for timeframe in ORDER:
            frame, frame_errors = fetch_history(timeframe, start)
            frames[timeframe] = frame.drop(columns=["granularity"], errors="ignore")
            errors.extend(frame_errors)
        return frames, errors

    def _connect_redis(self) -> None:
        url = os.environ.get("REDIS_URL", "").strip()
        if not url:
            return
        try:
            import redis

            client = redis.Redis.from_url(url, socket_connect_timeout=0.4)
            client.ping()
            self.redis = client
        except Exception:
            log.info("Redis not reachable, ticks stay in memory")
            self.redis = None

    async def _load_usdzar(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=4) as client:
                response = await client.get("https://api.frankfurter.app/latest?from=USD&to=ZAR")
                response.raise_for_status()
                rate = float(response.json()["rates"]["ZAR"])
            self.usdzar = rate
            self.usdzar_source = "Frankfurter USD/ZAR"
        except (httpx.HTTPError, ValueError, KeyError):
            self.usdzar = 18.40
            self.usdzar_source = "reference 18.40 — live rate unavailable"

    def _seed_price(self) -> None:
        last = self.frames["H1"].iloc[-1]
        self.mid = float(last["close"])
        spread = 0.00011
        self.bid = self.mid - spread / 2
        self.ask = self.mid + spread / 2
        self.spread_pips = spread / 0.0001
        self.last_tick = datetime.now(timezone.utc)
        self._remember_tick()

    def _remember_tick(self) -> None:
        if self.bid is None or self.ask is None or self.last_tick is None:
            return
        tick = {"time": self.last_tick.isoformat(), "bid": self.bid, "ask": self.ask}
        self.ticks.append(tick)
        if self.redis is not None:
            try:
                self.redis.lpush("eurusd:ticks", json.dumps(tick))
                self.redis.ltrim("eurusd:ticks", 0, 999)
            except Exception:
                self.redis = None

    def apply_bid_ask(self, bid: float, ask: float, when: datetime | None = None) -> None:
        self.bid = bid
        self.ask = ask
        self.mid = (bid + ask) / 2
        self.spread_pips = (ask - bid) / 0.0001
        self.last_tick = when or datetime.now(timezone.utc)
        self._remember_tick()

    def refresh_news(self) -> None:
        now = datetime.now(timezone.utc)
        articles, source = load_news(now)
        self.news = sorted(articles, key=lambda article: article["published_at"], reverse=True)
        self.news_source = source
        agg = aggregate(self.news, now)
        label = agg["label"]
        if self.sentiment_label and label != self.sentiment_label:
            cause = agg["drivers"][0]["headline"] if agg["drivers"] else "updated headlines"
            self.sentiment_event = flip_message(label.upper(), now, cause)
            log.info(self.sentiment_event)
        self.sentiment_label = label
        self.news_agg = agg

    def compose(self, arm_alerts: bool = True) -> None:
        news_lines = []
        drivers = self.news_agg.get("drivers") or []
        if drivers:
            top = drivers[0]
            if top["net_score"] > 20:
                bias = "Bullish EUR/USD"
            elif top["net_score"] < -20:
                bias = "Bearish EUR/USD"
            else:
                bias = "Neutral for EUR/USD"
            news_lines = [f"{top['headline']} — {bias}"]
        now = datetime.now(timezone.utc)
        events = upcoming_events(now)
        penalty = self.news_agg.get("net", 0) < -70 and event_within(events, now, 1)
        built = {}
        for timeframe in ORDER:
            bundle = self.model["bundles"][timeframe]
            row = self.predictions[timeframe].iloc[-1]
            base = latest_from_row(bundle, row, news_lines)
            confidence = base["tech_confidence"] - (20 if penalty else 0)
            direction, confidence, withheld = apply_confidence_gate(base["tech_direction"], confidence)
            combined = combine_signal(direction, news_side(self.news_agg.get("net", 0)))
            if "bear" in combined["direction"]:
                trade_side = "bearish"
            elif "bull" in combined["direction"]:
                trade_side = "bullish"
            else:
                trade_side = "neutral"
            levels = target_and_invalidation(trade_side, base["price"], base["atr"])
            tech_score = base["tech_score"]
            news_score = int(self.news_agg.get("net", 0))
            if combined["conflict"]:
                combined_score = round((tech_score + news_score) / 2)
            else:
                combined_score = round(0.6 * tech_score + 0.4 * news_score)
            built[timeframe] = {
                **base,
                "direction": combined["direction"],
                "direction_label": display_direction(combined["direction"]),
                "tone": direction_tone(combined["direction"]),
                "confidence": round(confidence, 1),
                "withheld": withheld or combined["conflict"] or base["withheld"],
                "conflict": combined["conflict"],
                "warning": combined["warning"],
                "news_score": news_score,
                "news_label": self.news_agg.get("label", "Neutral"),
                "combined_score": max(-100, min(100, combined_score)),
                "target": levels["target"],
                "target_pips": levels["target_pips"],
                "invalidation": levels["invalidation"],
                "invalidation_text": levels["invalidation_text"],
                "penalty": penalty,
            }
        self.signals = built
        now_ts = pd.Timestamp(now)
        for timeframe in ORDER:
            self.history[timeframe] = history_rows(self.predictions[timeframe], timeframe, limit=900)
            self.accuracy[timeframe] = accuracy_30d(self.history[timeframe], now_ts)
        if arm_alerts and self.alerts_armed:
            self._check_alerts(events, now)
        elif not self.alerts_armed:
            self.last_directions = {tf: sig["direction"] for tf, sig in built.items()}
            self.alerts_armed = True
        log.info(
            "Signal %s",
            ", ".join(f"{tf} {sig['direction_label']} {sig['confidence']}" for tf, sig in built.items()),
        )

    def _check_alerts(self, events: list[dict], now: datetime) -> None:
        settings = self.alert_settings
        quiet = settings["quiet_hours"] and in_quiet_hours(now, settings["quiet_start"], settings["quiet_end"])
        for timeframe, signal in self.signals.items():
            previous = self.last_directions.get(timeframe)
            if settings["on_flip"] and previous and previous != signal["direction"]:
                reason = "; ".join(signal["reasons"][:2]) or "model update"
                self._push_alert(
                    f"EUR/USD {timeframe} flipped to {signal['direction_label']} "
                    f"{signal['confidence']:.0f}% at {signal['price']:.5f} — Reason: {reason}",
                    quiet,
                )
            if (
                settings["on_confidence"]
                and signal["confidence"] > 70
                and "neutral" not in signal["direction"]
            ):
                key = f"conf-{timeframe}-{signal['direction']}"
                if key not in self.alerted_keys:
                    self.alerted_keys.add(key)
                    self._push_alert(
                        f"EUR/USD {timeframe} confidence {signal['confidence']:.0f}% {signal['direction_label']}",
                        quiet,
                    )
            self.last_directions[timeframe] = signal["direction"]
        if settings["on_news"]:
            for event in events:
                if event.get("impact") != "High":
                    continue
                minutes = (event["time"] - now).total_seconds() / 60
                if not 0 <= minutes <= 30:
                    continue
                key = f"news-{event['event']}-{event['time'].isoformat()}"
                if key in self.alerted_keys:
                    continue
                self.alerted_keys.add(key)
                self._push_alert(
                    f"High impact in {int(round(minutes))}m — {event['event']} ({event['currency']})",
                    quiet,
                )

    def _push_alert(self, text: str, quiet: bool) -> None:
        self._alert_seq += 1
        record = {
            "id": self._alert_seq,
            "at": datetime.now(timezone.utc).isoformat(),
            "text": text,
            "channel": "in-app",
            "suppressed": quiet,
            "email": "not-configured",
        }
        if quiet:
            record["text"] = text
            log.info("Alert suppressed for quiet hours: %s", text)
        else:
            log.info("Alert: %s", text)
        if self.alert_settings.get("email") and os.environ.get("SMTP_HOST"):
            record["email"] = "queued"
        self.alerts.insert(0, record)
        del self.alerts[50:]

    def nudge_demo_price(self) -> None:
        if not self.ready or self.source != "demo" or self.mid is None:
            return
        # Small step so the top bar moves without pretending a real tick feed.
        step = ((self._alert_seq + len(self.ticks)) % 7 - 3) * 0.00001
        self.mid = max(0.9, min(1.4, self.mid + step))
        spread = 0.00011
        self.bid = self.mid - spread / 2
        self.ask = self.mid + spread / 2
        self.spread_pips = spread / 0.0001
        self.last_tick = datetime.now(timezone.utc)
        self._remember_tick()

    def market(self) -> dict:
        now = datetime.now(timezone.utc)
        previous = self.mid or 0
        if self.ready and len(self.frames.get("D1", [])) > 2:
            previous = float(self.frames["D1"]["close"].iloc[-2])
        change = 0.0 if not self.mid or not previous else (self.mid - previous) / previous * 100
        banner = None
        if self.connection_label == "Reconnecting...":
            banner = "Reconnecting..."
        return {
            "bid": None if self.bid is None else round(self.bid, 5),
            "ask": None if self.ask is None else round(self.ask, 5),
            "mid": None if self.mid is None else round(self.mid, 5),
            "spread_pips": None if self.spread_pips is None else round(self.spread_pips, 1),
            "day_change_pct": round(change, 2),
            "status": "open" if market_is_open(now) else "closed",
            "last_tick": None if self.last_tick is None else self.last_tick.isoformat(),
            "last_tick_sast": None if self.last_tick is None else format_sast(self.last_tick, with_date=False),
            "connection": self.connection,
            "connection_label": self.connection_label,
            "source": self.source,
            "usdzar": round(self.usdzar, 4),
            "usdzar_source": self.usdzar_source,
            "banner": banner,
        }

    def dashboard(self) -> dict:
        if not self.ready:
            return {"ready": False, "message": self.message, "disclaimer": DISCLAIMER}
        now = datetime.now(timezone.utc)
        events = upcoming_events(now)
        rows = []
        for timeframe in ORDER:
            signal = self.signals[timeframe]
            rows.append(
                {
                    "timeframe": timeframe,
                    "direction": signal["direction"],
                    "direction_label": signal["direction_label"],
                    "tone": signal["tone"],
                    "confidence": signal["confidence"],
                    "price": self.mid,
                    "signal_price": signal["price"],
                    "target": signal["target"],
                    "target_pips": signal["target_pips"],
                    "invalidation": signal["invalidation"],
                    "invalidation_text": signal["invalidation_text"],
                    "reasons": signal["reasons"],
                    "features": signal["features"],
                    "tech_score": signal["tech_score"],
                    "news_score": signal["news_score"],
                    "combined_score": signal["combined_score"],
                    "conflict": signal["conflict"],
                    "warning": signal["warning"],
                    "withheld": signal["withheld"],
                    "news_label": signal["news_label"],
                    "probs": signal["probs"],
                    "penalty": signal["penalty"],
                    "accuracy": self.accuracy.get(timeframe, {}),
                }
            )
        articles = [_public_article(article) for article in self.news[:20]]
        drivers = [_public_article(article) for article in self.news_agg.get("drivers", [])]
        bundle = self.model["bundles"]["H4"]
        return _json_ready(
            {
                "ready": True,
                "message": self.message,
                "disclaimer": DISCLAIMER,
                "market": self.market(),
                "timeframes": rows,
                "alignment": alignment_badge(rows),
                "news": {
                    **self.news_agg,
                    "source": self.news_source,
                    "conflict": sentiment_conflict(
                        self.news_agg.get("net", 0), self.news_agg.get("fxnewsbias_net", 0)
                    ),
                    "headlines": articles,
                    "drivers": drivers,
                    "flip": self.sentiment_event,
                    "sample": self.news_source != "marketaux",
                },
                "calendar": {
                    "source": "sample schedule",
                    "events": events,
                    "warning": high_impact_warning(events, now, 30),
                },
                "model": {
                    "version": MODEL_VERSION,
                    "trained_at": self.model["trained_at"],
                    "accuracy": self.model["accuracy"],
                    "dataset_size": self.model["dataset_size"],
                    "oos_start": bundle["oos_start"],
                    "note": (
                        "Demo history is a synthetic EUR/USD path. "
                        "Accuracy is the held-out year of that path, not a live track record."
                        if self.source == "demo"
                        else "Trained on OANDA history. The last year is held out."
                    ),
                },
                "candles_loaded": {tf: int(len(frame)) for tf, frame in self.frames.items()},
            }
        )

    def candle_payload(self, timeframe: str, count: int = 280) -> dict:
        frame = self.frames[timeframe].tail(count).copy()
        featured = self.model["bundles"][timeframe]["featured"]
        if self.mid is not None and len(frame):
            last = frame.index[-1]
            frame.loc[last, "high"] = max(float(frame.loc[last, "high"]), self.mid)
            frame.loc[last, "low"] = min(float(frame.loc[last, "low"]), self.mid)
            frame.loc[last, "close"] = self.mid
        candles = []
        ema50 = []
        ema200 = []
        for stamp, row in frame.iterrows():
            t = int(stamp.timestamp())
            candles.append(
                {
                    "time": t,
                    "open": round(float(row["open"]), 5),
                    "high": round(float(row["high"]), 5),
                    "low": round(float(row["low"]), 5),
                    "close": round(float(row["close"]), 5),
                }
            )
            if stamp in featured.index:
                feature = featured.loc[stamp]
                if feature["ema50"] == feature["ema50"]:
                    ema50.append({"time": t, "value": round(float(feature["ema50"]), 5)})
                if feature["ema200"] == feature["ema200"]:
                    ema200.append({"time": t, "value": round(float(feature["ema200"]), 5)})
        preds = self.predictions[timeframe]
        markers = []
        recent = preds[preds.index.isin(frame.index)]
        directional = recent[recent["direction"].isin(["bullish", "bearish"])].tail(12)
        for stamp, row in directional.iterrows():
            markers.append({"time": int(stamp.timestamp()), "direction": row["direction"]})
        return {"timeframe": timeframe, "candles": candles, "ema50": ema50, "ema200": ema200, "markers": markers}

    def backtest(self, timeframe: str, start: str, end: str, capital: float, risk_pct: float) -> dict:
        bundle = self.model["bundles"][timeframe]
        result = run_backtest(
            self.predictions[timeframe],
            timeframe,
            pd.Timestamp(bundle["oos_start"]),
            pd.Timestamp(start),
            pd.Timestamp(end),
            capital,
            risk_pct,
        )
        if self.source == "demo":
            result["note"] += " Prices are the synthetic demo path, not OANDA history."
        return result

    def signal_history(self, timeframe: str | None, outcome: str | None, start: str | None, end: str | None) -> list:
        rows: list[dict] = []
        chosen = ORDER if not timeframe or timeframe == "ALL" else (timeframe,)
        for name in chosen:
            rows.extend(self.history.get(name, []))
        if outcome and outcome != "ALL":
            rows = [row for row in rows if row["outcome"] == outcome]
        if start:
            rows = [row for row in rows if row["time"] >= start]
        if end:
            rows = [row for row in rows if row["time"] <= end + "T23:59:59"]
        rows.sort(key=lambda row: row["time"], reverse=True)
        return rows[:300]

    async def tick_loop(self) -> None:
        while True:
            await asyncio.sleep(1)
            if self.ready and self.source == "demo":
                self.nudge_demo_price()

    async def news_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            if not self.ready:
                continue
            self.refresh_news()
            self.compose()

    async def oanda_stream(self) -> None:
        if not os.environ.get("OANDA_API_TOKEN") or not os.environ.get("OANDA_ACCOUNT_ID"):
            return
        import json as jsonlib

        while True:
            self.connection = "amber"
            self.connection_label = "Reconnecting..."
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", pricing_stream_url(), headers=headers()) as response:
                        response.raise_for_status()
                        self.connection = "green"
                        self.connection_label = "OANDA stream"
                        self.failover_active = False
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            message = jsonlib.loads(line)
                            if message.get("type") != "PRICE":
                                continue
                            bids = message.get("bids") or []
                            asks = message.get("asks") or []
                            if not bids or not asks:
                                continue
                            when = datetime.fromisoformat(message["time"].replace("Z", "+00:00"))
                            self.apply_bid_ask(float(bids[0]["price"]), float(asks[0]["price"]), when)
                            self.source = "oanda"
            except Exception:
                log.exception("OANDA stream dropped")
            await asyncio.sleep(3)

    async def failover_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            if not self.ready or not os.environ.get("OANDA_API_TOKEN"):
                continue
            if self.last_tick is None:
                continue
            silent = (datetime.now(timezone.utc) - self.last_tick).total_seconds()
            if silent < 60 or self.failover_active:
                continue
            quote = twelve_data_price()
            self.failover_active = True
            event = {
                "at": datetime.now(timezone.utc).isoformat(),
                "from": "oanda",
                "to": "twelvedata",
                "reason": "OANDA stream silent for 60s",
            }
            self.failover_events.append(event)
            log.warning("failover_event %s", event)
            if quote:
                self.apply_bid_ask(quote[0], quote[1])
                self.source = "twelvedata"
                self.connection = "amber"
                self.connection_label = "Twelve Data fallback"
            else:
                self.connection = "red"
                self.connection_label = "Price feed down"


def _public_article(article: dict) -> dict:
    return {
        "headline": article["headline"],
        "source": article["source"],
        "published_at": article["published_at"],
        "url": article["url"],
        "entities": article["entities"],
        "eur_score": article["eur_score"],
        "usd_score": article["usd_score"],
        "net_score": article["net_score"],
    }


def calendar_view(currency: str) -> dict:
    now = datetime.now(timezone.utc)
    events = upcoming_events(now)
    return _json_ready(
        {
            "source": "sample schedule",
            "events": filter_events(events, currency),
            "warning": high_impact_warning(events, now, 30),
        }
    )


engine = Engine()


def filtered_calendar(currency: str) -> dict:
    return calendar_view(currency)
