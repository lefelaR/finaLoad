"""Out-of-sample backtest. One position at a time, ATR target and invalidation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.logic import HORIZON_BARS, PIP, position_size

# Historical pip conversion. The live calculator uses the live USD/ZAR rate.
BACKTEST_USDZAR = 18.20


def run_backtest(
    frame: pd.DataFrame,
    timeframe: str,
    oos_start: pd.Timestamp,
    start: pd.Timestamp,
    end: pd.Timestamp,
    capital: float,
    risk_pct: float,
) -> dict:
    if oos_start.tzinfo is None:
        oos_start = oos_start.tz_localize("UTC")
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    if end.tzinfo is None:
        end = end.tz_localize("UTC")
    if start.date() < oos_start.date():
        raise ValueError(
            f"That range includes data the model trained on. Start on or after {oos_start.date().isoformat()}."
        )
    if start < oos_start:
        start = oos_start

    window = frame[(frame.index >= start) & (frame.index <= end)].copy()
    if window.empty:
        raise ValueError("No candles in that range.")

    horizon = HORIZON_BARS[timeframe]
    equity = capital
    peak = capital
    max_dd = 0.0
    curve = [{"time": window.index[0].isoformat(), "equity": round(equity, 2)}]
    trades = []
    highs = window["high"].to_numpy()
    lows = window["low"].to_numpy()
    closes = window["close"].to_numpy()
    times = window.index
    directions = window["direction"].tolist()
    confidence = window["confidence"].to_numpy()
    atr = window["atr_14"].to_numpy()
    i = 0
    n = len(window)
    while i < n - 1:
        direction = directions[i]
        if direction not in {"bullish", "bearish"} or not np.isfinite(atr[i]) or atr[i] <= 0:
            i += 1
            continue
        entry = float(closes[i])
        reach = 1.5 * float(atr[i])
        guard = 1.0 * float(atr[i])
        if direction == "bullish":
            target = entry + reach
            stop = entry - guard
        else:
            target = entry - reach
            stop = entry + guard
        stop_pips = abs(entry - stop) / PIP
        sizing = position_size(equity, risk_pct, max(stop_pips, 0.1), BACKTEST_USDZAR)
        lots = sizing["lots"]
        pip_value = sizing["pip_value_zar"]
        last = min(n - 1, i + horizon)
        exit_price = float(closes[last])
        outcome = "loss"
        hit = last
        for j in range(i + 1, last + 1):
            if direction == "bullish":
                if lows[j] <= stop:
                    exit_price = stop
                    outcome = "loss"
                    hit = j
                    break
                if highs[j] >= target:
                    exit_price = target
                    outcome = "win"
                    hit = j
                    break
            else:
                if highs[j] >= stop:
                    exit_price = stop
                    outcome = "loss"
                    hit = j
                    break
                if lows[j] <= target:
                    exit_price = target
                    outcome = "win"
                    hit = j
                    break
        else:
            outcome = "win" if (
                (direction == "bullish" and exit_price > entry)
                or (direction == "bearish" and exit_price < entry)
            ) else "loss"
        pips = (exit_price - entry) / PIP
        if direction == "bearish":
            pips = -pips
        pnl = pips * pip_value * lots
        equity = max(0.0, equity + pnl)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100)
        trades.append(
            {
                "time": times[i].isoformat(),
                "exit": times[hit].isoformat(),
                "direction": direction,
                "confidence": round(float(confidence[i]), 1),
                "outcome": outcome,
                "pips": round(float(pips), 1),
                "pnl": round(float(pnl), 2),
                "equity": round(equity, 2),
            }
        )
        curve.append({"time": times[hit].isoformat(), "equity": round(equity, 2)})
        if equity <= 0:
            break
        i = hit + 1

    wins = [trade for trade in trades if trade["outcome"] == "win"]
    losses = [trade for trade in trades if trade["outcome"] == "loss"]
    gross_win = sum(trade["pnl"] for trade in wins)
    gross_loss = abs(sum(trade["pnl"] for trade in losses))
    profit_factor = None if gross_loss == 0 else gross_win / gross_loss
    decided = len(wins) + len(losses)
    win_rate = None if decided == 0 else len(wins) / decided * 100
    return {
        "timeframe": timeframe,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "capital": capital,
        "risk_pct": risk_pct,
        "usdzar": BACKTEST_USDZAR,
        "trades": len(trades),
        "win_rate": None if win_rate is None else round(win_rate, 1),
        "avg_win": None if not wins else round(sum(t["pnl"] for t in wins) / len(wins), 2),
        "avg_loss": None if not losses else round(sum(t["pnl"] for t in losses) / len(losses), 2),
        "avg_win_pips": None if not wins else round(sum(t["pips"] for t in wins) / len(wins), 1),
        "avg_loss_pips": None if not losses else round(sum(t["pips"] for t in losses) / len(losses), 1),
        "max_drawdown": round(max_dd, 2),
        "profit_factor": None if profit_factor is None else round(profit_factor, 2),
        "ending_equity": round(equity, 2),
        "equity_curve": curve,
        "sample": trades[-12:],
        "disclaimer": "Past performance does not guarantee future results.",
        "note": "Ran only on the held-out year the model never trained on. Pip value uses USD/ZAR 18.20 for history.",
    }


def history_rows(frame: pd.DataFrame, timeframe: str, limit: int = 400) -> list[dict]:
    tail = frame.tail(limit)
    closes = tail["close"].to_numpy()
    directions = tail["direction"].tolist()
    rows = []
    n = len(tail)
    for i, (stamp, row) in enumerate(tail.iterrows()):
        direction = directions[i]
        if direction == "neutral":
            outcome = "skipped"
            pips = 0.0
        elif i + 1 >= n:
            outcome = "pending"
            pips = 0.0
        else:
            future = float(closes[i + 1])
            move = (future - float(row["close"])) / PIP
            if direction == "bearish":
                move = -move
            pips = move
            outcome = "win" if move > 0 else "loss"
        rows.append(
            {
                "time": stamp.isoformat(),
                "timeframe": timeframe,
                "prediction": direction.upper() if direction != "neutral" else "NEUTRAL",
                "confidence": round(float(row["confidence"]), 1),
                "outcome": outcome,
                "pips": round(float(pips), 1),
                "price": round(float(row["close"]), 5),
            }
        )
    rows.reverse()
    return rows


def accuracy_30d(rows: list[dict], now: pd.Timestamp) -> dict:
    cutoff = now - pd.Timedelta(days=30)
    chosen = []
    for row in rows:
        stamp = pd.Timestamp(row["time"])
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        if stamp >= cutoff and row["outcome"] in {"win", "loss"}:
            chosen.append(row)
    if not chosen:
        return {"win_rate": None, "signals": 0}
    wins = sum(1 for row in chosen if row["outcome"] == "win")
    return {"win_rate": round(wins / len(chosen) * 100, 1), "signals": len(chosen)}
