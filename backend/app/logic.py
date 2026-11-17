"""Pure decision rules. No I/O, so the acceptance checks stay testable."""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")
PIP = 0.0001
MODEL_VERSION = "model_eurusd_v1.0.pkl"
DISCLAIMER = "For educational purposes only, not financial advice."

# Next-bar move (in pips) treated as noise when labeling the model.
# Moves inside this band are labeled flat. Wider bands made H1/H4 almost all neutral.
FLAT_PIPS = {"H1": 1.0, "H4": 3.0, "D1": 8.0}
# How long a backtest trade may stay open, in bars of that timeframe.
HORIZON_BARS = {"H1": 8, "H4": 6, "D1": 5}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def to_sast(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(SAST)


def format_sast(moment: datetime, with_date: bool = True) -> str:
    local = to_sast(moment)
    if with_date:
        return local.strftime("%d %b %Y, %H:%M SAST")
    return local.strftime("%H:%M SAST")


def market_is_open(moment: datetime) -> bool:
    """Forex hours used by the spec: Mon 00:00 SAST through Fri 23:00 SAST."""
    local = to_sast(moment)
    weekday = local.weekday()  # Monday = 0
    if weekday == 5:
        return False
    if weekday == 6:
        return False
    if weekday == 4 and local.time() >= time(23, 0):
        return False
    return True


def news_gauge(net: float) -> str:
    if net < -60:
        return "Strong Bearish"
    if net < -20:
        return "Bearish"
    if net <= 20:
        return "Neutral"
    if net <= 60:
        return "Bullish"
    return "Strong Bullish"


def news_side(net: float) -> str:
    """Collapse the gauge to the three sides the combine rule uses."""
    label = news_gauge(net)
    if "Bullish" in label:
        return "bullish"
    if "Bearish" in label:
        return "bearish"
    return "neutral"


def apply_confidence_gate(direction: str, confidence: float) -> tuple[str, float, bool]:
    """Below 55% the product must say Neutral, never a forced Buy or Sell."""
    confidence = clamp(confidence, 0.0, 100.0)
    if direction != "neutral" and confidence < 55:
        return "neutral", confidence, True
    return direction, confidence, False


def combine_signal(tech: str, news: str) -> dict:
    """
    Tech Bullish + News Bullish = Strong Bullish
    Tech Bearish + News Bearish = Strong Bearish
    Opposite signs = Neutral, with a conflict warning
    """
    if tech == "bullish" and news == "bullish":
        return {"direction": "strong_bullish", "conflict": False, "warning": None}
    if tech == "bearish" and news == "bearish":
        return {"direction": "strong_bearish", "conflict": False, "warning": None}
    if tech == "bullish" and news == "bearish":
        return {
            "direction": "neutral",
            "conflict": True,
            "warning": "Technical and news disagree — signal withheld",
        }
    if tech == "bearish" and news == "bullish":
        return {
            "direction": "neutral",
            "conflict": True,
            "warning": "Technical and news disagree — signal withheld",
        }
    if tech == "bullish":
        return {"direction": "bullish", "conflict": False, "warning": None}
    if tech == "bearish":
        return {"direction": "bearish", "conflict": False, "warning": None}
    return {"direction": "neutral", "conflict": False, "warning": None}


def display_direction(code: str) -> str:
    return {
        "strong_bullish": "STRONG BULLISH",
        "bullish": "BULLISH",
        "neutral": "NEUTRAL",
        "bearish": "BEARISH",
        "strong_bearish": "STRONG BEARISH",
    }.get(code, "NEUTRAL")


def direction_tone(code: str) -> str:
    if "bull" in code:
        return "bull"
    if "bear" in code:
        return "bear"
    return "neutral"


def alignment_badge(rows: list[dict]) -> dict:
    tones = []
    parts = []
    for row in rows:
        tone = direction_tone(row["direction"])
        tones.append(tone)
        parts.append(f"{row['timeframe']} {display_direction(row['direction']).title()}")
    if tones and all(tone == "bear" for tone in tones):
        return {"label": "All aligned bearish", "tone": "bear"}
    if tones and all(tone == "bull" for tone in tones):
        return {"label": "All aligned bullish", "tone": "bull"}
    if tones and all(tone == "neutral" for tone in tones):
        return {"label": "No directional call — all neutral", "tone": "neutral"}
    return {"label": "Mixed — " + ", ".join(parts), "tone": "mixed"}


def high_impact_warning(events: list[dict], now: datetime, within_minutes: int = 30) -> str | None:
    soonest = None
    soonest_minutes = None
    for event in events:
        if event.get("impact") != "High":
            continue
        if event.get("currency") not in {"EUR", "USD"}:
            continue
        start = event["time"]
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        minutes = (start - now).total_seconds() / 60
        if 0 <= minutes < within_minutes and (soonest_minutes is None or minutes < soonest_minutes):
            soonest = event
            soonest_minutes = minutes
    if soonest is None:
        return None
    remaining = max(1, int(round(soonest_minutes)))
    return f"High Impact in {remaining}m — {soonest['event']} — Confidence Reduced"


def event_within(events: list[dict], now: datetime, hours: float) -> bool:
    for event in events:
        if event.get("impact") != "High":
            continue
        start = event["time"]
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        delta = (start - now).total_seconds() / 3600
        if 0 <= delta < hours:
            return True
    return False


def sentiment_conflict(our_net: float, fx_net: float) -> bool:
    return abs(our_net - fx_net) > 40


def flip_message(direction: str, when: datetime, cause: str) -> str:
    return f"Sentiment flipped to {direction} at {format_sast(when)} due to: {cause}"


def position_size(balance_zar: float, risk_pct: float, stop_pips: float, usdzar: float) -> dict:
    """
    EUR/USD is quoted in USD, so one standard lot is $10 per pip.
    ZAR pip value = that dollar value times the live USD/ZAR rate.
    The EUR/USD price itself does not change the USD pip value.
    """
    if balance_zar <= 0 or risk_pct <= 0 or stop_pips <= 0 or usdzar <= 0:
        raise ValueError("Balance, risk, stop and USD/ZAR must be positive.")
    pip_value_zar = 10.0 * usdzar
    rand_risk = balance_zar * (risk_pct / 100.0)
    lots = rand_risk / (stop_pips * pip_value_zar)
    lots = round(lots, 2)
    if lots < 0.01:
        lots = 0.01
    return {
        "lots": lots,
        "rand_risk": round(rand_risk, 2),
        "pip_value_zar": round(pip_value_zar, 2),
        "risk_at_lots": round(lots * stop_pips * pip_value_zar, 2),
        "warning": "High Risk — Consider reducing lot size" if risk_pct > 2 else None,
    }


def dedup_articles(articles: list[dict]) -> list[dict]:
    seen = set()
    kept = []
    for article in articles:
        key = (article.get("url"), article.get("headline"))
        if key in seen:
            continue
        seen.add(key)
        kept.append(article)
    return kept


def in_quiet_hours(moment: datetime, start: str = "22:00", end: str = "06:00") -> bool:
    local = to_sast(moment).time()
    start_t = time.fromisoformat(start)
    end_t = time.fromisoformat(end)
    if start_t <= end_t:
        return start_t <= local < end_t
    return local >= start_t or local < end_t


def target_and_invalidation(direction: str, price: float, atr: float) -> dict:
    """ATR gives a price target and the level that kills the idea."""
    if direction not in {"bullish", "bearish"} or not atr or atr <= 0:
        return {
            "target": None,
            "target_pips": None,
            "invalidation": None,
            "invalidation_text": "No active invalidation",
        }
    reach = 1.5 * atr
    guard = 1.0 * atr
    if direction == "bullish":
        target = price + reach
        invalidation = price - guard
        text = f"Close below {invalidation:.5f}"
        pips = (target - price) / PIP
    else:
        target = price - reach
        invalidation = price + guard
        text = f"Close above {invalidation:.5f}"
        pips = (target - price) / PIP
    return {
        "target": round(target, 5),
        "target_pips": round(pips, 1),
        "invalidation": round(invalidation, 5),
        "invalidation_text": text,
    }


def validate_candle(row: dict) -> str | None:
    needed = ("open", "high", "low", "close")
    for key in needed:
        value = row.get(key)
        if value is None or value != value:  # NaN
            return f"missing {key}"
    if row["high"] < row["low"]:
        return "high below low"
    if row["high"] < row["open"] or row["high"] < row["close"]:
        return "high does not contain the body"
    if row["low"] > row["open"] or row["low"] > row["close"]:
        return "low does not contain the body"
    if row["close"] <= 0:
        return "non-positive close"
    return None
