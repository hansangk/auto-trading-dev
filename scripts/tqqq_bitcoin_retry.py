"""TQQQ and Bitcoin-ETF-only hourly search using free Yahoo chart bars.

This is a research downloader/backtest. Yahoo's chart endpoint is not an
execution-quality feed. The script trades long and short legs simultaneously.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import hashlib
import json
import random
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.features import FeatureCache
from autogrid.strategy import StrategySpec


OUT = Path("runs/tqqq_bitcoin_retry")
DATA = OUT / "yahoo_1h.csv"
CFG = load_config("configs/win60_search.yaml")
UNIVERSES = {
    "spot_proxy": ("TQQQ", "IBIT"),
    "leveraged_set": ("TQQQ", "IBIT", "BITI", "BITX"),
}
INDICATORS = (
    "ema_3_15", "ema_5_20", "ema_8_30", "roc_10", "roc_30",
    "momentum_20", "slope_20", "macd_5_20_7", "rsi_7", "rsi_14",
    "bollinger_20", "stoch_14", "stochrsi_14", "vwapdev_20",
    "donchian_10", "donchian_20", "donchian_60", "atrbreak_14",
    "rangepos_20", "volumez_20", "obv_20", "cmf_20", "realvol_20",
)
CACHE: dict[str, tuple] = {}


def download() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for symbol in sorted({s for values in UNIVERSES.values() for s in values}):
        params = urllib.parse.urlencode({
            "range": "2y", "interval": "1h", "includePrePost": "false",
            "events": "div,splits",
        })
        request = urllib.request.Request(
            f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?{params}",
            headers={"User-Agent": "Mozilla/5.0 AutoGrid-Research/0.3"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        frame = pd.DataFrame({
            "timestamp": pd.to_datetime(result["timestamp"], unit="s", utc=True),
            "symbol": symbol, "open": quote["open"], "high": quote["high"],
            "low": quote["low"], "close": quote["close"], "volume": quote["volume"],
        }).dropna()
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    counts = combined.groupby("timestamp")["symbol"].nunique()
    common = counts[counts == len(frames)].index
    combined = combined[combined.timestamp.isin(common)].sort_values(["timestamp", "symbol"])
    combined.to_csv(DATA, index=False)


def context(universe: str):
    if universe in CACHE:
        return CACHE[universe]
    data = load_market_data(DATA, list(UNIVERSES[universe]))
    times = pd.to_datetime(data.timestamps, utc=True)
    cache = FeatureCache(data)
    ranks = {name: cache.cross_sectional_rank(name) for name in INDICATORS}
    CACHE[universe] = data, times, ranks
    return CACHE[universe]


def evaluate(task: tuple[dict, str, str, float, int]) -> dict:
    candidate, universe, period, cost, delay = task
    data, times, ranks = context(universe)
    score = np.zeros(data.shape, dtype=np.float32)
    for indicator, weight in zip(candidate["indicators"], candidate["weights"]):
        score += weight * ranks[indicator]
    # Avoid warm-up ties and weak mixed-indicator conviction.
    score[np.ptp(score, axis=1) < candidate["gap"]] = 0
    spec = StrategySpec(
        candidate["id"], tuple(candidate["indicators"]), tuple(candidate["weights"]),
        1, 1, candidate["hold"], candidate["stop"], candidate["tp"], 2,
    )
    bounds = {
        "train": ("2024-11-14", "2025-07-01"),
        "validation": ("2025-07-01", "2026-01-01"),
        "diagnostic": ("2026-01-01", "2026-11-14"),
    }
    start, end = [
        int(np.searchsorted(times.asi8, pd.Timestamp(value, tz="UTC").value))
        for value in bounds[period]
    ]
    result = run_backtest(
        data, score, spec, CFG.execution, CFG.risk, CFG.capital,
        start, end, cost, delay,
    )
    return {
        **candidate, "indicators": "+".join(candidate["indicators"]),
        "weights": "+".join(f"{value:.2f}" for value in candidate["weights"]),
        "universe": universe, "period": period, "cost": cost, "delay": delay,
        **result.to_dict(),
    }


def candidates(count: int = 1200) -> list[dict]:
    rng = random.Random(20261116)
    result: dict[str, dict] = {}
    while len(result) < count:
        size = rng.choice((1, 2, 3))
        indicators = tuple(sorted(rng.sample(INDICATORS, size)))
        raw = np.asarray([rng.choice((.5, 1., 1.5)) for _ in indicators])
        weights = tuple(np.round(raw / raw.sum(), 6))
        payload = {
            "indicators": indicators, "weights": weights,
            "gap": rng.choice((0., .5, 1.0)),
            "hold": rng.choice((1, 2, 4, 6)),
            "stop": rng.choice((30., 60., 100., 150.)),
            "tp": rng.choice((1.5, 3., 6.)),
        }
        sid = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        payload["id"] = sid
        result[sid] = payload
    return sorted(result.values(), key=lambda item: item["id"])


def rank_results(frame: pd.DataFrame) -> pd.DataFrame:
    base = frame[(frame.cost == 1) & (frame.delay == 0)].pivot(
        index=["universe", "id"], columns="period"
    )
    cost = frame[(frame.period == "validation") & (frame.cost == 2)].set_index(["universe", "id"])
    delay = frame[(frame.period == "validation") & (frame.delay == 1)].set_index(["universe", "id"])
    out = pd.DataFrame(index=base.index)
    for metric in ("total_return", "max_drawdown", "win_rate", "profit_factor", "rounds"):
        out[f"{metric}_train"] = base[metric]["train"]
        out[f"{metric}_validation"] = base[metric]["validation"]
    out["return_cost2"] = cost.total_return
    out["return_delay1"] = delay.total_return
    returns = ["total_return_train", "total_return_validation", "return_cost2", "return_delay1"]
    out["positive_scenarios"] = (out[returns] > 0).sum(axis=1)
    out["worst_return"] = out[returns].min(axis=1)
    out["score"] = out.worst_return + .15 * out[returns].mean(axis=1)
    return out.reset_index().sort_values(
        ["positive_scenarios", "score", "id"], ascending=[False, False, True]
    )


if __name__ == "__main__":
    download()
    grid = candidates()
    manifest = {
        "source": "Yahoo chart 1h free endpoint", "downloaded_utc": pd.Timestamp.utcnow().isoformat(),
        "symbols": sorted({s for values in UNIVERSES.values() for s in values}),
        "universes": UNIVERSES, "candidate_count": len(grid),
        "warning": "Not execution-quality; 2026 is diagnostic, not pristine holdout",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tasks = [
        (candidate, universe, period, cost, delay)
        for universe in UNIVERSES for candidate in grid
        for period, cost, delay in (
            ("train", 1., 0), ("validation", 1., 0),
            ("validation", 2., 0), ("validation", 1., 1),
        )
    ]
    with ProcessPoolExecutor(max_workers=6) as pool:
        development = list(pool.map(evaluate, tasks, chunksize=20))
    frame = pd.DataFrame(development)
    frame.to_csv(OUT / "development_stress.csv", index=False)
    ranking = rank_results(frame)
    ranking.to_csv(OUT / "ranking.csv", index=False)
    selected = set(zip(ranking.head(30).universe, ranking.head(30).id))
    chosen = [(candidate, universe) for universe in UNIVERSES for candidate in grid
              if (universe, candidate["id"]) in selected]
    with ProcessPoolExecutor(max_workers=6) as pool:
        diagnostic = list(pool.map(
            evaluate,
            [(candidate, universe, "diagnostic", cost, delay)
             for candidate, universe in chosen
             for cost, delay in ((1., 0), (2., 0), (1., 1))],
            chunksize=3,
        ))
    pd.DataFrame(diagnostic).to_csv(OUT / "diagnostic.csv", index=False)
    print(f"complete development={len(development)} diagnostic={len(diagnostic)}", flush=True)
