"""Turn feature values and SHAP contributions into the five plain-English reasons."""

from __future__ import annotations

def describe_feature(name: str, value: float) -> str:
    if name == "ema200_dist":
        side = "above" if value > 0 else "below"
        bias = "Bullish" if value > 0 else "Bearish"
        return f"Price {side} EMA 200 ({bias})"
    if name == "ema50_dist":
        side = "above" if value > 0 else "below"
        return f"Price {side} EMA 50"
    if name == "ema20_dist":
        side = "above" if value > 0 else "below"
        return f"Price {side} EMA 20"
    if name == "ema20_50":
        if value > 0:
            return "EMA 20 is above EMA 50 — short-term trend is up"
        return "EMA 20 is below EMA 50 — short-term trend is down"
    if name == "rsi_14":
        if value >= 70:
            mood = "stretched, momentum fading"
        elif value >= 60:
            mood = "firm momentum"
        elif value <= 30:
            mood = "washed out"
        elif value < 40:
            mood = "weak momentum"
        else:
            mood = "mid-range momentum"
        return f"RSI {value:.0f} — {mood}"
    if name == "macd_hist_n":
        if value > 0:
            return "MACD histogram is positive"
        return "MACD histogram is negative"
    if name == "adx_14":
        if value >= 25:
            return f"ADX {value:.0f} — the trend has strength"
        return f"ADX {value:.0f} — the trend is soft"
    if name == "atr_pct":
        return f"ATR is {value * 100:.2f}% of price"
    if name == "bb_pct":
        if value > 0.8:
            return "Price is near the upper Bollinger band"
        if value < 0.2:
            return "Price is near the lower Bollinger band"
        return "Price is inside the Bollinger bands"
    if name == "vwap_dist":
        side = "above" if value > 0 else "below"
        return f"Price {side} session VWAP"
    if name == "structure":
        if value > 0:
            return "Structure is higher highs and higher lows"
        if value < 0:
            return "Structure is lower highs and lower lows"
        return "Structure is mixed"
    if name == "ret_1":
        return f"Last bar {value * 100:+.2f}%"
    if name == "ret_4":
        return f"Last four bars {value * 100:+.2f}%"
    if name == "ret_12":
        return f"Last twelve bars {value * 100:+.2f}%"
    return name


def top_reasons(shap_pairs: list[tuple[str, float, float]], news_lines: list[str], limit: int = 5) -> list[str]:
    """shap_pairs is (feature, shap_value, raw_value), already sorted by |shap|."""
    reasons = []
    for name, shap_value, raw in shap_pairs:
        if raw is None:
            continue
        text = describe_feature(name, raw)
        influence = "supports the call" if shap_value >= 0 else "pushes the other way"
        reasons.append(f"{text} — {influence}")
        if len(reasons) == max(0, limit - len(news_lines)):
            break
    return (reasons + news_lines)[:limit]
