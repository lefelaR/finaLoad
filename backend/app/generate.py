"""Deterministic EUR/USD history for the demo feed.

The path has multi-week drifts so a tree model can learn trend features.
It is not a recording of the real market. The UI says so.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.logic import validate_candle


def forex_index(start: str, end: datetime | None = None) -> pd.DatetimeIndex:
    if end is None:
        end = datetime.now(timezone.utc)
    idx = pd.date_range(start, end, freq="h", tz="UTC")
    # Mon 00:00 SAST = Sun 22:00 UTC. Fri 23:00 SAST = Fri 21:00 UTC.
    sunday_open = (idx.dayofweek == 6) & (idx.hour >= 22)
    weekday = idx.dayofweek < 4
    friday = (idx.dayofweek == 4) & (idx.hour <= 21)
    return idx[sunday_open | weekday | friday]


def generate_h1(start: str = "2016-01-01", seed: int = 42) -> tuple[pd.DataFrame, list[dict]]:
    index = forex_index(start)
    rng = np.random.default_rng(seed)
    n = len(index)
    regime = np.zeros(n)
    cursor = 0
    while cursor < n:
        length = int(rng.integers(180, 520))
        drift = float(rng.normal(0, 0.00012))
        regime[cursor : cursor + length] = drift
        cursor += length

    price = 1.1050
    closes = np.empty(n)
    vols = rng.uniform(0.00025, 0.00055, n)
    shocks = rng.normal(0, 1, n)
    for i in range(n):
        pull = -0.015 * (price - 1.12)
        ret = regime[i] + shocks[i] * vols[i] + pull * 0.001
        price = max(0.9, min(1.4, price * (1 + ret)))
        closes[i] = price

    opens = np.empty(n)
    opens[0] = closes[0]
    opens[1:] = closes[:-1]
    wick = np.abs(rng.normal(0.00018, 0.00006, n))
    high = np.maximum(opens, closes) + wick
    low = np.minimum(opens, closes) - wick
    volume = rng.integers(800, 12000, n).astype(float)
    spread_pips = rng.uniform(0.6, 1.6, n)
    spread_px = spread_pips * 0.0001

    frame = pd.DataFrame(
        {
            "open": opens,
            "high": high,
            "low": low,
            "close": closes,
            "volume": volume,
            "bid": closes - spread_px / 2,
            "ask": closes + spread_px / 2,
            "spread_pips": spread_pips,
            "granularity": "H1",
        },
        index=index,
    )
    frame.index.name = "time"

    errors: list[dict] = []
    keep = []
    for stamp, row in frame.iterrows():
        payload = row.to_dict()
        reason = validate_candle(payload)
        if reason:
            errors.append(
                {
                    "time": stamp.to_pydatetime(),
                    "granularity": "H1",
                    "reason": reason,
                    "payload": {k: float(payload[k]) for k in ("open", "high", "low", "close")},
                }
            )
            continue
        keep.append(stamp)
    clean = frame.loc[keep]
    clean = clean[~clean.index.duplicated(keep="last")]
    return clean, errors


def resample_candles(h1: pd.DataFrame, rule: str, granularity: str) -> pd.DataFrame:
    grouped = h1.resample(rule, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "bid": "last",
            "ask": "last",
            "spread_pips": "mean",
        }
    )
    grouped = grouped.dropna(subset=["open", "high", "low", "close"])
    grouped["granularity"] = granularity
    grouped.index.name = "time"
    grouped = grouped[~grouped.index.duplicated(keep="last")]
    return grouped
