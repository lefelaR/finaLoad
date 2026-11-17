"""Technical features for EUR/USD. Wilder smoothing where the indicator expects it."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "ret_1",
    "ret_4",
    "ret_12",
    "ema20_dist",
    "ema50_dist",
    "ema200_dist",
    "ema20_50",
    "macd_hist_n",
    "rsi_14",
    "adx_14",
    "atr_pct",
    "bb_pct",
    "vwap_dist",
    "structure",
]


def _wilder(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]

    df["ema20"] = close.ewm(span=20, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    df["macd"] = macd
    df["macd_signal"] = macd_signal
    df["macd_hist"] = macd - macd_signal

    delta = close.diff()
    gain = _wilder(delta.clip(lower=0), 14)
    loss = _wilder((-delta).clip(lower=0), 14)
    rs = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    df["atr_14"] = _wilder(tr, 14)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )
    plus_di = 100 * _wilder(plus_dm, 14) / df["atr_14"].replace(0, np.nan)
    minus_di = 100 * _wilder(minus_dm, 14) / df["atr_14"].replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx_14"] = _wilder(dx, 14)

    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    df["bb_mid"] = mid
    df["bb_up"] = mid + 2 * std
    df["bb_lo"] = mid - 2 * std
    width = (df["bb_up"] - df["bb_lo"]).replace(0, np.nan)
    df["bb_pct"] = (close - df["bb_lo"]) / width

    typical = (high + low + close) / 3
    session = df.index.tz_convert("Africa/Johannesburg").date
    grouped_tv = (typical * df["volume"]).groupby(session).cumsum()
    grouped_v = df["volume"].groupby(session).cumsum().replace(0, np.nan)
    df["vwap"] = grouped_tv / grouped_v

    bull_structure = (high > high.shift(5)) & (low > low.shift(5))
    bear_structure = (high < high.shift(5)) & (low < low.shift(5))
    df["structure"] = np.where(bull_structure, 1, np.where(bear_structure, -1, 0)).astype(float)

    df["ret_1"] = close.pct_change(1)
    df["ret_4"] = close.pct_change(4)
    df["ret_12"] = close.pct_change(12)
    df["ema20_dist"] = (close - df["ema20"]) / close
    df["ema50_dist"] = (close - df["ema50"]) / close
    df["ema200_dist"] = (close - df["ema200"]) / close
    df["ema20_50"] = (df["ema20"] - df["ema50"]) / close
    df["macd_hist_n"] = df["macd_hist"] / close
    df["atr_pct"] = df["atr_14"] / close
    df["vwap_dist"] = (close - df["vwap"]) / close
    return df


def feature_snapshot(row: pd.Series) -> dict:
    values = {}
    for name in FEATURE_COLUMNS:
        value = row.get(name)
        if value is None or value != value:
            values[name] = None
        else:
            values[name] = round(float(value), 6)
    values["ema20"] = _round(row.get("ema20"))
    values["ema50"] = _round(row.get("ema50"))
    values["ema200"] = _round(row.get("ema200"))
    values["atr_14"] = _round(row.get("atr_14"), 5)
    values["macd_hist"] = _round(row.get("macd_hist"), 6)
    return values


def _round(value, digits: int = 5):
    if value is None or value != value:
        return None
    return round(float(value), digits)
