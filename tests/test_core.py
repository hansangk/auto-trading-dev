from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from autogrid.config import ExecutionConfig, RiskConfig
from autogrid.data import MarketData, generate_demo, load_market_data
from autogrid.engine import run_backtest
from autogrid.events import align_events
from autogrid.features import FeatureCache
from autogrid.strategy import StrategySpec, build_score


class CoreTests(unittest.TestCase):
    def _data(self) -> MarketData:
        timestamps = pd.date_range("2025-01-02 14:30", periods=12, freq="min", tz="UTC").to_numpy()
        a = np.linspace(100, 102, 12); b = np.linspace(100, 98, 12)
        close = np.column_stack([a, b]); open_ = np.vstack([[100, 100], close[:-1]])
        high = np.maximum(open_, close) * 1.0001; low = np.minimum(open_, close) * .9999
        return MarketData(timestamps, ("A", "B"), open_, high, low, close, np.full_like(close, 10_000.0))

    def test_long_short_and_next_bar(self) -> None:
        data = self._data(); score = np.tile([1.0, -1.0], (12, 1))
        spec = StrategySpec("x", ("roc_10",), (1.0,), 1, 1, 1, 500, 2.0, 0)
        result = run_backtest(data, score, spec, ExecutionConfig(0, 0, 0), RiskConfig(max_asset_weight=.5), 100_000)
        self.assertGreater(result.total_return, 0); self.assertGreater(result.long_pnl, 0); self.assertGreater(result.short_pnl, 0)
        self.assertEqual(result.trades, result.rounds * 2)

    def test_entry_volume_not_used_before_bar_closes(self) -> None:
        from dataclasses import replace
        data = self._data()
        score = np.tile([1.0, -1.0], (12, 1))
        spec = StrategySpec("volume_causality", (), (), 1, 1, 1, 500, 2, 0)
        base = run_backtest(data, score, spec, ExecutionConfig(0, 0, 0), RiskConfig(), 100000, 1, 2)
        volume = data.volume.copy()
        volume[1] = 0  # Not available at entry open: must not affect this round.
        current = run_backtest(replace(data, volume=volume), score, spec, ExecutionConfig(0, 0, 0), RiskConfig(), 100000, 1, 2)
        self.assertEqual(base.to_dict(), current.to_dict())
        volume[0] = 0  # Previous completed bar is observable.
        previous = run_backtest(replace(data, volume=volume), score, spec, ExecutionConfig(0, 0, 0), RiskConfig(), 100000, 1, 2)
        self.assertEqual(previous.rounds, 0)

    def test_cost_never_improves_return(self) -> None:
        data = self._data(); score = np.tile([1.0, -1.0], (12, 1)); spec = StrategySpec("x", (), (), 1, 1, 1, 500, 2, 0)
        low = run_backtest(data, score, spec, ExecutionConfig(0, 0, 0), RiskConfig(max_asset_weight=.5), 100_000)
        high = run_backtest(data, score, spec, ExecutionConfig(2, 5, 100), RiskConfig(max_asset_weight=.5), 100_000)
        self.assertLess(high.total_return, low.total_return)

    def test_equal_warmup_values_do_not_create_symbol_order_signal(self) -> None:
        data = self._data()
        spec = StrategySpec("x", ("zclose_60",), (1.0,), 1, 1, 1, 50, 1, 0)
        score = build_score(spec, FeatureCache(data))
        self.assertTrue(np.all(score == 0))
        result = run_backtest(data, score, spec, ExecutionConfig(0, 0, 0), RiskConfig(), 100_000)
        self.assertEqual(result.trades, 0)

    def test_reduced_macro_universe_produces_signal(self) -> None:
        timestamps = pd.date_range("2025-01-02 14:30", periods=25, freq="min", tz="UTC").to_numpy()
        symbols = ("SPY", "QQQ", "GLD", "SLV", "IBIT", "BITI", "BITX")
        slopes = np.array([.001, .0012, -.0002, -.0001, .002, -.0015, .003])
        close = 100 * np.exp(np.arange(25)[:, None] * slopes[None, :])
        data = MarketData(timestamps, symbols, close.copy(), close.copy(), close.copy(), close, np.ones_like(close))
        macro = FeatureCache(data).get("macro_risk")
        self.assertGreater(macro[-1, symbols.index("IBIT")], 0)
        self.assertLess(macro[-1, symbols.index("BITI")], 0)

    def test_demo_includes_bitcoin_etfs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.csv"; generate_demo(path, days=3, seed=1)
            data = load_market_data(path)
            self.assertEqual(data.shape, (1170, 13))
            self.assertTrue({"IBIT", "BITI", "BITX"}.issubset(data.symbols))

    def test_rejects_missing_symbol_bar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            pd.DataFrame([
                {"timestamp": "2025-01-01T00:00:00Z", "symbol": "A", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                {"timestamp": "2025-01-01T00:00:00Z", "symbol": "B", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                {"timestamp": "2025-01-01T00:01:00Z", "symbol": "A", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            ]).to_csv(path, index=False)
            with self.assertRaises(ValueError): load_market_data(path)

    def test_news_uses_available_at_not_published_at(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            pd.DataFrame([{
                "event_id": "1", "source": "telegram", "published_at": "2025-01-01T14:30:05Z",
                "available_at": "2025-01-01T14:31:05Z", "symbol": "A", "topic": "regulation",
                "sentiment": -1, "relevance": 1, "confidence": 1, "novelty": 1, "is_breaking": True,
            }]).to_csv(path, index=False)
            market = pd.Index(pd.to_datetime(["2025-01-01T14:31:00Z", "2025-01-01T14:32:00Z"]))
            sentiment, breaking = align_events(path, market, ["A", "B"])
            self.assertEqual(sentiment[0, 0], 0); self.assertEqual(sentiment[1, 0], -1)
            self.assertEqual(breaking[1, 0], 1); self.assertEqual(sentiment[:, 1].sum(), 0)


if __name__ == "__main__":
    unittest.main()
