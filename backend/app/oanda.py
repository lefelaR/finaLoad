"""OANDA v20 practice/live client. Not the paid Exchange Rates API."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd

from app.logic import validate_candle

PRACTICE = "https://api-fxpractice.oanda.com"
LIVE = "https://api-fxtrade.oanda.com"
GRANULARITY = {"M15": "M15", "H1": "H1", "H4": "H4", "D1": "D"}


def host() -> str:
    if os.environ.get("OANDA_ENV", "practice").lower() == "live":
        return LIVE
    return PRACTICE


def headers() -> dict:
    token = os.environ.get("OANDA_API_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}", "Accept-Datetime-Format": "RFC3339"}


def parse_oanda_time(value: str) -> datetime:
    """OANDA sends nanoseconds. Python 3.9 fromisoformat accepts microseconds."""
    text = value.strip().replace("Z", "+00:00")
    match = re.match(r"^(.*T\d{2}:\d{2}:\d{2})(?:\.(\d+))?([+-]\d{2}:\d{2})$", text)
    if not match:
        return datetime.fromisoformat(text)
    fraction = (match.group(2) or "0")[:6].ljust(6, "0")
    return datetime.fromisoformat(f"{match.group(1)}.{fraction}{match.group(3)}")


def parse_candle(candle: dict, granularity: str) -> tuple[dict | None, str | None]:
    if not candle.get("complete", True) and candle.get("volume", 1) == 0:
        return None, "empty incomplete candle"
    mid = candle.get("mid") or {}
    bid = candle.get("bid") or {}
    ask = candle.get("ask") or {}
    try:
        row = {
            "time": parse_oanda_time(candle["time"]),
            "open": float(mid["o"]),
            "high": float(mid["h"]),
            "low": float(mid["l"]),
            "close": float(mid["c"]),
            "volume": float(candle.get("volume") or 0),
            "bid": float(bid.get("c") or mid["c"]),
            "ask": float(ask.get("c") or mid["c"]),
            "granularity": granularity,
        }
    except (KeyError, TypeError, ValueError):
        return None, "missing or corrupt OHLC"
    row["spread_pips"] = (row["ask"] - row["bid"]) / 0.0001
    reason = validate_candle(row)
    if reason:
        return None, reason
    return row, None


def fetch_history(granularity: str, start: datetime) -> tuple[pd.DataFrame, list[dict]]:
    """Page OANDA candles forward from `start`. Raises if the token is missing or the API fails."""
    token = os.environ.get("OANDA_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("OANDA_API_TOKEN is not set")
    oanda_granularity = GRANULARITY[granularity]
    cursor = start.astimezone(timezone.utc)
    end = datetime.now(timezone.utc)
    rows: list[dict] = []
    errors: list[dict] = []
    with httpx.Client(timeout=30) as client:
        while cursor < end:
            response = client.get(
                f"{host()}/v3/instruments/EUR_USD/candles",
                headers=headers(),
                params={
                    "granularity": oanda_granularity,
                    "price": "MBA",
                    "from": cursor.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
                    "count": 5000,
                },
            )
            response.raise_for_status()
            candles = response.json().get("candles", [])
            if not candles:
                break
            last_time = cursor
            for candle in candles:
                parsed, reason = parse_candle(candle, granularity)
                stamp = candle.get("time")
                if reason or parsed is None:
                    errors.append(
                        {
                            "time": stamp,
                            "granularity": granularity,
                            "reason": reason or "skipped",
                            "payload": candle,
                        }
                    )
                    continue
                rows.append(parsed)
                last_time = parsed["time"]
            if last_time <= cursor or len(candles) < 2:
                break
            cursor = last_time + timedelta(seconds=1)
    if not rows:
        raise RuntimeError(f"OANDA returned no {granularity} candles")
    frame = pd.DataFrame(rows).drop_duplicates(subset=["time"], keep="last")
    frame = frame.set_index("time").sort_index()
    frame.index = pd.DatetimeIndex(frame.index).tz_convert("UTC")
    return frame, errors


def pricing_stream_url() -> str:
    account = os.environ.get("OANDA_ACCOUNT_ID", "").strip()
    if not account:
        raise RuntimeError("OANDA_ACCOUNT_ID is not set")
    return f"{host()}/v3/accounts/{account}/pricing/stream?instruments=EUR_USD"


def twelve_data_price() -> tuple[float, float] | None:
    key = os.environ.get("TWELVE_DATA_API_KEY", "").strip()
    if not key:
        return None
    try:
        response = httpx.get(
            "https://api.twelvedata.com/quote",
            params={"symbol": "EUR/USD", "apikey": key},
            timeout=8,
        )
        response.raise_for_status()
        body = response.json()
        bid = float(body.get("close") or body["price"])
        # Quote endpoint has no bid/ask on the basic plan; keep a 1.1 pip spread.
        return bid, bid + 0.00011
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None
