"""Acceptance checks that do not need a trained model."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

import pandas as pd

from app.auth import mint, verify
from app.backtest import history_rows
from app.logic import (
    alignment_badge,
    apply_confidence_gate,
    combine_signal,
    dedup_articles,
    flip_message,
    high_impact_warning,
    in_quiet_hours,
    market_is_open,
    news_gauge,
    position_size,
    sentiment_conflict,
    validate_candle,
)
from app.news import aggregate, sample_articles, score_text
from app.oanda import parse_candle


class LogicTests(unittest.TestCase):
    def test_confidence_gate_refuses_a_weak_call(self):
        direction, confidence, withheld = apply_confidence_gate("bullish", 54)
        self.assertEqual(direction, "neutral")
        self.assertTrue(withheld)
        self.assertEqual(confidence, 54)

    def test_confidence_gate_keeps_a_clear_call(self):
        direction, confidence, withheld = apply_confidence_gate("bearish", 68)
        self.assertEqual(direction, "bearish")
        self.assertFalse(withheld)
        self.assertEqual(confidence, 68)

    def test_combine_rules(self):
        self.assertEqual(combine_signal("bullish", "bullish")["direction"], "strong_bullish")
        self.assertEqual(combine_signal("bearish", "bearish")["direction"], "strong_bearish")
        conflict = combine_signal("bullish", "bearish")
        self.assertEqual(conflict["direction"], "neutral")
        self.assertTrue(conflict["conflict"])
        self.assertEqual(combine_signal("bearish", "bullish")["direction"], "neutral")
        self.assertEqual(combine_signal("bullish", "neutral")["direction"], "bullish")
        self.assertEqual(combine_signal("neutral", "bearish")["direction"], "neutral")

    def test_news_gauge_bands(self):
        self.assertEqual(news_gauge(-75), "Strong Bearish")
        self.assertEqual(news_gauge(-40), "Bearish")
        self.assertEqual(news_gauge(0), "Neutral")
        self.assertEqual(news_gauge(40), "Bullish")
        self.assertEqual(news_gauge(80), "Strong Bullish")

    def test_ecb_hike_example(self):
        eur, usd = score_text("ECB hints at hike")
        self.assertEqual(eur, 75)
        self.assertEqual(usd, 0)
        self.assertEqual(eur - usd, 75)

    def test_cpi_is_usd_positive(self):
        eur, usd = score_text("US CPI hotter than forecast, dollar firms")
        self.assertEqual(eur, 0)
        self.assertGreater(usd, 0)

    def test_sample_news_is_deduped_and_scored(self):
        now = datetime(2026, 11, 17, 11, 0, tzinfo=timezone.utc)
        rows = sample_articles(now)
        doubled = dedup_articles(rows + rows)
        self.assertEqual(len(doubled), len(rows))
        summary = aggregate(rows, now)
        self.assertLess(summary["net"], -20)
        self.assertTrue(sentiment_conflict(summary["net"], summary["fxnewsbias_net"]))

    def test_high_impact_warning_copy(self):
        now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
        events = [
            {
                "time": datetime(2026, 11, 17, 12, 25, tzinfo=timezone.utc),
                "event": "ECB Rate",
                "currency": "EUR",
                "impact": "High",
            }
        ]
        text = high_impact_warning(events, now)
        self.assertEqual(text, "High Impact in 25m — ECB Rate — Confidence Reduced")

    def test_position_size_uses_zar_pip_value(self):
        sized = position_size(10_000, 1, 20, 16.9)
        self.assertEqual(sized["pip_value_zar"], 169.0)
        self.assertEqual(sized["rand_risk"], 100.0)
        self.assertEqual(sized["lots"], 0.03)
        self.assertIsNone(sized["warning"])
        warned = position_size(10_000, 3, 20, 16.9)
        self.assertIn("High Risk", warned["warning"])

    def test_market_hours_sast(self):
        self.assertTrue(market_is_open(datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)))
        self.assertFalse(market_is_open(datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)))
        self.assertFalse(market_is_open(datetime(2026, 11, 13, 21, 30, tzinfo=timezone.utc)))
        self.assertTrue(market_is_open(datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)))

    def test_quiet_hours_wrap_midnight(self):
        late = datetime(2026, 11, 17, 21, 30, tzinfo=timezone.utc)  # 23:30 SAST
        morning = datetime(2026, 11, 17, 3, 0, tzinfo=timezone.utc)  # 05:00 SAST
        noon = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)  # 12:00 SAST
        self.assertTrue(in_quiet_hours(late))
        self.assertTrue(in_quiet_hours(morning))
        self.assertFalse(in_quiet_hours(noon))

    def test_flip_message(self):
        text = flip_message(
            "BEARISH",
            datetime(2026, 11, 17, 12, 32, tzinfo=timezone.utc),
            "US CPI 0.4% vs 0.3% forecast",
        )
        self.assertIn("Sentiment flipped to BEARISH", text)
        self.assertIn("14:32 SAST", text)
        self.assertIn("US CPI 0.4% vs 0.3% forecast", text)

    def test_corrupt_candle_is_rejected(self):
        self.assertIsNone(validate_candle({"open": 1, "high": 1.1, "low": 0.9, "close": 1.05}))
        self.assertEqual(
            validate_candle({"open": 1, "high": 0.8, "low": 0.9, "close": 1.05}),
            "high below low",
        )

    def test_alignment_badge(self):
        bear = alignment_badge(
            [
                {"timeframe": "H1", "direction": "strong_bearish"},
                {"timeframe": "H4", "direction": "bearish"},
                {"timeframe": "D1", "direction": "bearish"},
            ]
        )
        self.assertEqual(bear["tone"], "bear")
        mixed = alignment_badge(
            [
                {"timeframe": "H1", "direction": "bullish"},
                {"timeframe": "H4", "direction": "bearish"},
            ]
        )
        self.assertEqual(mixed["tone"], "mixed")
        self.assertIn("H1", mixed["label"])

    def test_history_outcomes(self):
        index = pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC")
        frame = pd.DataFrame(
            {
                "close": [1.10, 1.1010, 1.1000],
                "direction": ["bullish", "neutral", "bearish"],
                "confidence": [70, 40, 70],
            },
            index=index,
        )
        rows = history_rows(frame, "H1", limit=10)
        by_time = {row["time"]: row for row in rows}
        first = by_time[index[0].isoformat()]
        second = by_time[index[1].isoformat()]
        third = by_time[index[2].isoformat()]
        self.assertEqual(first["outcome"], "win")
        self.assertEqual(second["outcome"], "skipped")
        self.assertEqual(third["outcome"], "pending")

    def test_oanda_parser_skips_corrupt_rows(self):
        good, reason = parse_candle(
            {
                "complete": True,
                "volume": 10,
                "time": "2024-01-01T00:00:00.000000000Z",
                "mid": {"o": "1.1000", "h": "1.1020", "l": "1.0980", "c": "1.1010"},
                "bid": {"c": "1.1009"},
                "ask": {"c": "1.1011"},
            },
            "H1",
        )
        self.assertIsNone(reason)
        self.assertAlmostEqual(good["spread_pips"], 2.0, places=2)
        bad, why = parse_candle({"complete": True, "time": "2024-01-01T00:00:00Z", "mid": {}}, "H1")
        self.assertIsNone(bad)
        self.assertIsNotNone(why)

    def test_jwt_roundtrip(self):
        token = mint("sipho", ttl_seconds=60)
        self.assertEqual(verify(token)["sub"], "sipho")
        self.assertIsNone(verify(token + "x"))


if __name__ == "__main__":
    unittest.main()
