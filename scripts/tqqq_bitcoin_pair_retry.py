"""Selective TQQQ/IBIT long-short pair strategies on hourly bars."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import hashlib
import json
import random

import numpy as np
import pandas as pd

from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec


ROOT = Path("runs/tqqq_bitcoin_retry")
OUT = Path("runs/tqqq_bitcoin_pair_retry")
OUT.mkdir(parents=True, exist_ok=True)
CFG = load_config("configs/win60_search.yaml")
CACHE: dict[str, object] = {}


def context():
    if CACHE:
        return CACHE["x"]
    data = load_market_data(ROOT / "yahoo_1h.csv", ["TQQQ", "IBIT"])
    times = pd.to_datetime(data.timestamps, utc=True)
    ratio = pd.Series(np.log(data.close[:, 0] / data.close[:, 1]))
    CACHE["x"] = data, times, ratio
    return CACHE["x"]


def pair_signal(candidate: dict) -> np.ndarray:
    data, _, ratio = context()
    window = candidate["window"]
    one = ratio.diff()
    scale = one.rolling(max(10, window * 2), min_periods=max(10, window * 2)).std()
    if candidate["mode"] == "momentum":
        raw = ratio.diff(window) / (scale * np.sqrt(window)).replace(0, np.nan)
    elif candidate["mode"] == "mean_reversion":
        raw = -(ratio - ratio.rolling(window).mean()) / ratio.rolling(window).std().replace(0, np.nan)
    elif candidate["mode"] == "dual_momentum":
        short = ratio.diff(max(2, window // 3)) / (scale * np.sqrt(max(2, window // 3))).replace(0, np.nan)
        long = ratio.diff(window) / (scale * np.sqrt(window)).replace(0, np.nan)
        raw = (short + long) / 2
        raw[short * long <= 0] = 0
    elif candidate["mode"] == "breakout":
        prior_high = ratio.shift(1).rolling(window).max()
        prior_low = ratio.shift(1).rolling(window).min()
        raw = (ratio - (prior_high + prior_low) / 2) / (prior_high - prior_low).replace(0, np.nan) * 2
    elif candidate["mode"] == "macd":
        fast = ratio.ewm(span=max(2, window // 3), adjust=False).mean()
        slow = ratio.ewm(span=window, adjust=False).mean()
        raw = (fast - slow) / (scale * np.sqrt(window)).replace(0, np.nan)
    else:
        raise ValueError(candidate["mode"])
    value = raw.to_numpy(dtype=float)
    value[np.abs(value) < candidate["threshold"]] = 0
    value = np.sign(value)
    score = np.column_stack([value, -value]).astype(np.float32)
    score[~np.isfinite(score)] = 0
    return score


def evaluate(task: tuple[dict, str, float, int]) -> dict:
    candidate, period, cost, delay = task
    data, times, _ = context()
    spec = StrategySpec(
        candidate["id"], (candidate["mode"],), (1.,), 1, 1,
        candidate["hold"], candidate["stop"], candidate["tp"], 2,
    )
    bounds = {
        "train": ("2024-11-14", "2025-07-01"),
        "validation": ("2025-07-01", "2026-01-01"),
        "diagnostic": ("2026-01-01", "2026-11-14"),
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
        data, pair_signal(candidate), spec, CFG.execution, CFG.risk, CFG.capital,
        start, end, cost, delay,
    )
    return {**candidate, "period": period, "cost": cost, "delay": delay, **result.to_dict()}


def make_grid(count: int = 1400) -> list[dict]:
    rng = random.Random(2026111602)
    result: dict[str, dict] = {}
    while len(result) < count:
        payload = {
            "mode": rng.choice(("momentum", "mean_reversion", "dual_momentum", "breakout", "macd")),
            "window": rng.choice((6, 10, 16, 24, 40, 60)),
            "threshold": rng.choice((.5, .75, 1., 1.5, 2.)),
            "hold": rng.choice((1, 2, 4, 6)),
            "stop": rng.choice((60., 100., 150., 200.)),
            "tp": rng.choice((1.5, 3., 6.)),
        }
        sid = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        payload["id"] = sid
        result[sid] = payload
    return sorted(result.values(), key=lambda item: item["id"])


def ranking(frame: pd.DataFrame) -> pd.DataFrame:
    base = frame[(frame.cost == 1) & (frame.delay == 0)].pivot(index="id", columns="period")
    cost = frame[(frame.period == "validation") & (frame.cost == 2)].set_index("id")
    delay = frame[(frame.period == "validation") & (frame.delay == 1)].set_index("id")
    out = pd.DataFrame(index=base.index)
    for metric in ("total_return", "max_drawdown", "win_rate", "profit_factor", "rounds"):
        out[f"{metric}_train"] = base[metric]["train"]
        out[f"{metric}_validation"] = base[metric]["validation"]
    out["return_cost2"] = cost.total_return
    out["return_delay1"] = delay.total_return
    cols = ["total_return_train", "total_return_validation", "return_cost2", "return_delay1"]
    out["positive_scenarios"] = (out[cols] > 0).sum(axis=1)
    out["worst_return"] = out[cols].min(axis=1)
    out["score"] = out.worst_return + .15 * out[cols].mean(axis=1)
    return out.reset_index().sort_values(
        ["positive_scenarios", "score", "id"], ascending=[False, False, True]
    )


if __name__ == "__main__":
    grid = make_grid()
    (OUT / "manifest.json").write_text(json.dumps({
        "grid_count": len(grid), "symbols": ["TQQQ", "IBIT"],
        "selection": "worst train/validation/cost2/delay return",
        "warning": "Yahoo hourly research bars; 2026 diagnostic only",
    }, indent=2), encoding="utf-8")
    tasks = [
        (candidate, period, cost, delay) for candidate in grid
        for period, cost, delay in (
            ("train", 1., 0), ("validation", 1., 0),
            ("validation", 2., 0), ("validation", 1., 1),
        )
    ]
    with ProcessPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(evaluate, tasks, chunksize=20))
    frame = pd.DataFrame(results)
    frame.to_csv(OUT / "development_stress.csv", index=False)
    ranked = ranking(frame)
    ranked.to_csv(OUT / "ranking.csv", index=False)
    ids = set(ranked.head(30).id)
    chosen = [candidate for candidate in grid if candidate["id"] in ids]
    with ProcessPoolExecutor(max_workers=6) as pool:
        recent = list(pool.map(
            evaluate,
            [(candidate, "diagnostic", cost, delay) for candidate in chosen
             for cost, delay in ((1., 0), (2., 0), (1., 1))],
            chunksize=3,
        ))
    pd.DataFrame(recent).to_csv(OUT / "diagnostic.csv", index=False)
    survivors = {"ee5c58cca888", "05480af5c1f9", "ddbf529e8040", "1e0916cb4c79"}
    stable = [candidate for candidate in grid if candidate["id"] in survivors]
    quarters = [f"{year}Q{quarter}" for year in (2025, 2026) for quarter in range(1, 5)]
    with ProcessPoolExecutor(max_workers=6) as pool:
        quarterly = list(pool.map(
            evaluate,
            [(candidate, period, 1., 0) for candidate in stable for period in quarters],
            chunksize=4,
        ))
    pd.DataFrame(quarterly).to_csv(OUT / "quarterly_survivors.csv", index=False)
    print(
        f"complete development={len(results)} diagnostic={len(recent)} quarterly={len(quarterly)}",
        flush=True,
    )
