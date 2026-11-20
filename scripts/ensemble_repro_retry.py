"""Multi-timeframe ensemble search ranked by reproducibility, not win rate.

The search uses 2024 and 2025 as model-development folds. 2026 is reported
only as a retrospective diagnostic because that period has already been
inspected repeatedly in this project.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from itertools import combinations, product
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.features import FeatureCache
from autogrid.strategy import StrategySpec


ROOT = Path("runs/multiframe_pilot")
OUT = Path("runs/ensemble_repro_retry")
OUT.mkdir(parents=True, exist_ok=True)
CFG = load_config("configs/win60_search.yaml")
CACHE: dict[str, object] = {}

FAST = (
    "donchian_10", "donchian_20", "atrbreak_14", "rangepos_20",
    "macd_5_20_7", "ema_5_20", "roc_10", "momentum_20",
    "stoch_14", "stochrsi_14", "obv_20", "cmf_20",
)
SLOW = (
    "ema_3_15", "ema_5_20", "roc_10", "donchian_20",
    "macd_5_20_7", "atrbreak_14", "volratio_60", "stochrsi_14",
)


def context():
    if CACHE:
        return CACHE["x"]
    fast_data = load_market_data(ROOT / "market_15m.csv")
    slow_data = load_market_data(ROOT / "market_60m.csv")
    fast_time = pd.to_datetime(fast_data.timestamps, utc=True)
    slow_time = pd.to_datetime(slow_data.timestamps, utc=True)
    # A 60-minute bar is usable only once it has fully closed.
    slow_index = np.searchsorted(
        (slow_time + pd.Timedelta(minutes=60)).asi8,
        (fast_time + pd.Timedelta(minutes=15)).asi8,
        side="right",
    ) - 1
    valid = slow_index >= 0
    local = fast_time.tz_convert("America/New_York")
    minutes = np.asarray(local.hour * 60 + local.minute)
    # Retain the two liquid windows used by the prior successful candidates.
    valid &= ((minutes >= 600) & (minutes < 690)) | ((minutes >= 840) & (minutes < 930))
    fast_cache = FeatureCache(fast_data)
    slow_cache = FeatureCache(slow_data)
    for name in FAST:
        fast_cache.cross_sectional_rank(name)
    for name in SLOW:
        slow_cache.cross_sectional_rank(name)
    CACHE["x"] = fast_data, fast_time, fast_cache, slow_cache, slow_index, valid
    return CACHE["x"]


def build_score(candidate: dict) -> np.ndarray:
    data, _, fast_cache, slow_cache, slow_index, valid = context()
    fast_parts = [fast_cache.cross_sectional_rank(name) for name in candidate["fast"]]
    slow_part = np.zeros(data.shape, dtype=np.float32)
    slow_part[valid] = slow_cache.cross_sectional_rank(candidate["slow"])[slow_index[valid]]
    fast_score = np.mean(fast_parts, axis=0)
    score = candidate["fast_weight"] * fast_score + (1 - candidate["fast_weight"]) * slow_part

    components = fast_parts + [slow_part]
    long_symbol = np.argmax(score, axis=1)
    short_symbol = np.argmin(score, axis=1)
    long_votes = np.zeros(len(score), dtype=np.int8)
    short_votes = np.zeros(len(score), dtype=np.int8)
    rows = np.arange(len(score))
    for part in components:
        long_votes += np.argmax(part, axis=1) == long_symbol
        short_votes += np.argmin(part, axis=1) == short_symbol
    ordered = np.sort(score, axis=1)
    separated = (
        (ordered[:, -1] - ordered[:, -2] >= candidate["gap"])
        & (ordered[:, 1] - ordered[:, 0] >= candidate["gap"])
    )
    enabled = (
        valid & separated
        & (long_votes >= candidate["votes"])
        & (short_votes >= candidate["votes"])
        & (np.ptp(score, axis=1) > 0)
    )
    score[~enabled] = 0
    return score


def evaluate(task: tuple[dict, str, float, int]) -> dict:
    candidate, period, cost, delay = task
    data, times, *_ = context()
    score = build_score(candidate)
    spec = StrategySpec(
        candidate["id"], tuple(candidate["fast"]) + (candidate["slow"],),
        (candidate["fast_weight"] / 2, candidate["fast_weight"] / 2,
         1 - candidate["fast_weight"]),
        1, 1, candidate["hold"], candidate["stop"], candidate["tp"], 3,
    )
    bounds = {
        "2024": ("2024-01-01", "2025-01-01"),
        "2025": ("2025-01-01", "2026-01-01"),
        "recent": ("2026-01-01", "2026-11-14"),
    }
    if period not in bounds and "Q" in period:
        quarter = pd.Period(period, freq="Q")
        bounds[period] = (
            quarter.start_time.strftime("%Y-%m-%d"),
            (quarter.end_time + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        )
    start, end = [
        int(np.searchsorted(times.asi8, pd.Timestamp(value, tz="UTC").value))
        for value in bounds[period]
    ]
    result = run_backtest(
        data, score, spec, CFG.execution, CFG.risk, CFG.capital,
        start, end, cost, delay,
    )
    return {**candidate, "fast": "+".join(candidate["fast"]),
            "period": period, "cost": cost, "delay": delay, **result.to_dict()}


def stable_rank(frame: pd.DataFrame) -> pd.DataFrame:
    key = ["id"]
    base = frame[(frame.cost == 1) & (frame.delay == 0)].pivot(index=key, columns="period")
    cost = frame[(frame.period == "2025") & (frame.cost == 2)].set_index("id")
    delay = frame[(frame.period == "2025") & (frame.delay == 1)].set_index("id")
    summary = pd.DataFrame(index=base.index)
    for metric in ("total_return", "max_drawdown", "win_rate", "profit_factor", "rounds"):
        summary[f"{metric}_2024"] = base[metric]["2024"]
        summary[f"{metric}_2025"] = base[metric]["2025"]
    summary["return_2025_cost2"] = cost.total_return
    summary["return_2025_delay1"] = delay.total_return
    summary["worst_return"] = summary[[
        "total_return_2024", "total_return_2025",
        "return_2025_cost2", "return_2025_delay1",
    ]].min(axis=1)
    summary["positive_scenarios"] = (summary[[
        "total_return_2024", "total_return_2025",
        "return_2025_cost2", "return_2025_delay1",
    ]] > 0).sum(axis=1)
    summary["score"] = (
        summary["worst_return"]
        + .20 * summary[["total_return_2024", "total_return_2025"]].mean(axis=1)
        - .10 * summary[["max_drawdown_2024", "max_drawdown_2025"]].max(axis=1)
    )
    return summary.reset_index().sort_values(
        ["positive_scenarios", "score", "id"], ascending=[False, False, True]
    )


if __name__ == "__main__":
    # Diverse pairs prevent a nominal ensemble made from near-identical signals.
    fast_pairs = [
        pair for pair in combinations(FAST, 2)
        if not (pair[0].split("_")[0] == pair[1].split("_")[0])
    ]
    signal_grid = list(product(fast_pairs, SLOW, (.50, .67), (2, 3), (0., .15)))
    # Deterministic broad sample, then an exit grid. No result-driven randomness.
    signal_grid = signal_grid[::2][:640]
    candidates = []
    for (fast, slow, fast_weight, votes, gap), (stop, tp, hold) in product(
        signal_grid, ((30., 6., 12), (40., 6., 12), (60., 4., 8), (60., 6., 12))
    ):
        payload = dict(fast=fast, slow=slow, fast_weight=fast_weight,
                       votes=votes, gap=gap, stop=stop, tp=tp, hold=hold)
        payload["id"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:12]
        candidates.append(payload)
    manifest = {
        "grid_count": len(candidates),
        "selection": "rank by worst 2024/2025/cost2/delay1 return; no win-rate target",
        "data_warning": "2026 has already been inspected and is diagnostic only",
        "candidate_hashes": [candidate["id"] for candidate in candidates],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tasks = [
        (candidate, period, cost, delay)
        for candidate in candidates
        for period, cost, delay in (
            ("2024", 1., 0), ("2025", 1., 0),
            ("2025", 2., 0), ("2025", 1., 1),
        )
    ]
    with ProcessPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(evaluate, tasks, chunksize=16))
    development = pd.DataFrame(results)
    development.to_csv(OUT / "development_stress.csv", index=False)
    ranking = stable_rank(development)
    ranking.to_csv(OUT / "ranking.csv", index=False)
    selected = set(ranking.head(30).id)
    chosen = [candidate for candidate in candidates if candidate["id"] in selected]
    with ProcessPoolExecutor(max_workers=6) as pool:
        recent = list(pool.map(
            evaluate,
            [(candidate, "recent", cost, delay) for candidate in chosen
             for cost, delay in ((1., 0), (2., 0), (1., 1))],
            chunksize=3,
        ))
    pd.DataFrame(recent).to_csv(OUT / "recent_diagnostic.csv", index=False)
    quarters = [f"{year}Q{quarter}" for year in (2024, 2025, 2026) for quarter in range(1, 5)]
    with ProcessPoolExecutor(max_workers=6) as pool:
        quarterly = list(pool.map(
            evaluate,
            [(candidate, period, 1., 0) for candidate in chosen for period in quarters],
            chunksize=6,
        ))
    pd.DataFrame(quarterly).to_csv(OUT / "quarterly_diagnostic.csv", index=False)
    print(
        f"complete development={len(results)} recent={len(recent)} quarterly={len(quarterly)}",
        flush=True,
    )
