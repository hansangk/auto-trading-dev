from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import SearchConfig
from .data import MarketData
from .engine import run_backtest
from .features import FeatureCache
from .strategy import StrategySpec, build_score


def _parse_specs(path: str | Path) -> list[StrategySpec]:
    frame = pd.read_csv(path, dtype={"strategy_id": str})
    specs: list[StrategySpec] = []
    for row in frame.to_dict("records"):
        specs.append(StrategySpec(
            str(row["strategy_id"]), tuple(ast.literal_eval(str(row["indicators"]))),
            tuple(map(float, ast.literal_eval(str(row["weights"])))),
            int(row["long_k"]), int(row["short_k"]), int(row["hold_bars"]),
            float(row["stop_loss_bps"]), float(row["take_profit_multiple"]),
            int(row["cooldown_bars"]),
        ))
    return specs


def _evaluation_days(data: MarketData, evaluation_start: str) -> tuple[np.ndarray, np.ndarray, int]:
    timestamps = pd.to_datetime(data.timestamps, utc=True)
    dates = np.asarray(timestamps.date)
    unique, starts = np.unique(dates, return_index=True)
    cutoff = pd.Timestamp(evaluation_start).date()
    day_position = int(np.searchsorted(unique, cutoff, side="left"))
    if day_position >= len(unique):
        raise ValueError("evaluation_start 이후 거래일이 없습니다.")
    return unique[day_position:], starts[day_position:], int(starts[day_position])


def _sample_windows(
    day_starts: np.ndarray, data_stop: int, window_days: tuple[int, ...],
    samples_per_size: int, seed: int,
) -> list[dict]:
    rng = np.random.default_rng(seed)
    output: list[dict] = []
    total_days = len(day_starts)
    for length in window_days:
        possible = total_days - length + 1
        if possible <= 0:
            continue
        count = min(samples_per_size, possible)
        choices = rng.choice(possible, size=count, replace=False)
        for start_day in sorted(map(int, choices)):
            stop_day = start_day + length
            start = int(day_starts[start_day])
            stop = int(day_starts[stop_day]) if stop_day < total_days else data_stop
            output.append({"window_days": length, "start_day": start_day, "start": start, "stop": stop})
    if not output:
        raise ValueError("평가 구간보다 랜덤 window가 깁니다.")
    return output


def run_random_validation(
    data: MarketData,
    cfg: SearchConfig,
    top_path: str | Path,
    output: str | Path,
    evaluation_start: str,
    window_days: tuple[int, ...] = (5, 10, 20, 40),
    samples_per_size: int = 25,
    seed: int = 20261115,
) -> pd.DataFrame:
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    specs = _parse_specs(top_path)
    eval_days, starts, eval_start_index = _evaluation_days(data, evaluation_start)
    windows = _sample_windows(starts, len(data.timestamps), window_days, samples_per_size, seed)
    cache = FeatureCache(data)
    rows: list[dict] = []
    detail_rows: list[dict] = []

    for spec in specs:
        score = build_score(spec, cache)
        full = run_backtest(data, score, spec, cfg.execution, cfg.risk, cfg.capital, eval_start_index, len(data.timestamps))
        full_cost2 = run_backtest(data, score, spec, cfg.execution, cfg.risk, cfg.capital, eval_start_index, len(data.timestamps), 2.0, 0)
        full_delay1 = run_backtest(data, score, spec, cfg.execution, cfg.risk, cfg.capital, eval_start_index, len(data.timestamps), 1.0, 1)
        full_delay2 = run_backtest(data, score, spec, cfg.execution, cfg.risk, cfg.capital, eval_start_index, len(data.timestamps), 1.0, 2)
        base_returns: list[float] = []
        cost2_returns: list[float] = []
        delay_returns: list[float] = []
        max_mdds: list[float] = []
        win_rates: list[float] = []
        for number, window in enumerate(windows):
            base = run_backtest(data, score, spec, cfg.execution, cfg.risk, cfg.capital, window["start"], window["stop"])
            cost2 = run_backtest(data, score, spec, cfg.execution, cfg.risk, cfg.capital, window["start"], window["stop"], 2.0, 0)
            delayed = run_backtest(data, score, spec, cfg.execution, cfg.risk, cfg.capital, window["start"], window["stop"], 1.0, 1)
            base_returns.append(base.total_return); cost2_returns.append(cost2.total_return)
            delay_returns.append(delayed.total_return); max_mdds.append(base.max_drawdown); win_rates.append(base.win_rate)
            detail_rows.append({
                "strategy_id": spec.strategy_id, "window_number": number,
                "window_days": window["window_days"], "start_index": window["start"], "stop_index": window["stop"],
                "return": base.total_return, "return_cost_x2": cost2.total_return,
                "return_delay_1bar": delayed.total_return, "max_drawdown": base.max_drawdown,
                "win_rate": base.win_rate, "trades": base.trades,
            })
        base_arr = np.asarray(base_returns); cost_arr = np.asarray(cost2_returns); delay_arr = np.asarray(delay_returns)
        random_score = (
            .35 * np.mean(base_arr > 0) + .25 * np.mean(cost_arr > 0) + .15 * np.mean(delay_arr > 0)
            + .15 * np.clip(np.median(base_arr) * 100, -1, 1)
            - .10 * np.clip(np.max(max_mdds) / max(cfg.risk.max_drawdown, 1e-9), 0, 2)
        )
        eligible = bool(
            full.trades >= 300 and full.total_return > 0 and full_cost2.total_return > 0
            and full_delay1.total_return > 0 and full_delay2.total_return > 0
            and full.long_pnl > 0 and full.short_pnl > 0
            and np.mean(base_arr > 0) >= .65 and np.mean(cost_arr > 0) >= .55
            and np.quantile(base_arr, .10) > -.02 and max(max_mdds) <= cfg.risk.max_drawdown
        )
        rows.append({
            "strategy_id": spec.strategy_id, "indicators": list(spec.indicators), "weights": list(spec.weights),
            "long_k": spec.long_k, "short_k": spec.short_k, "hold_bars": spec.hold_bars,
            "stop_loss_bps": spec.stop_loss_bps, "take_profit_multiple": spec.take_profit_multiple,
            "cooldown_bars": spec.cooldown_bars, "evaluation_days": len(eval_days),
            "full_return": full.total_return, "full_cost_x2_return": full_cost2.total_return,
            "full_delay_1bar_return": full_delay1.total_return, "full_delay_2bar_return": full_delay2.total_return,
            "full_trades": full.trades, "full_win_rate": full.win_rate, "full_profit_factor": full.profit_factor,
            "full_max_drawdown": full.max_drawdown, "full_long_pnl": full.long_pnl,
            "full_short_pnl": full.short_pnl, "full_bitcoin_etf_pnl": full.bitcoin_etf_pnl,
            "random_windows": len(windows), "random_positive_rate": float(np.mean(base_arr > 0)),
            "random_cost_x2_positive_rate": float(np.mean(cost_arr > 0)),
            "random_delay_positive_rate": float(np.mean(delay_arr > 0)),
            "random_median_return": float(np.median(base_arr)),
            "random_q10_return": float(np.quantile(base_arr, .10)),
            "random_worst_return": float(np.min(base_arr)),
            "random_mean_win_rate": float(np.mean(win_rates)),
            "random_max_drawdown": float(np.max(max_mdds)),
            "random_score": float(random_score), "eligible": eligible,
        })

    summary = pd.DataFrame(rows).sort_values(
        ["eligible", "random_score", "full_return", "strategy_id"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    summary.insert(0, "rank", np.arange(1, len(summary) + 1))
    summary.to_csv(out / "random_validation.csv", index=False)
    pd.DataFrame(detail_rows).to_csv(out / "random_windows_detail.csv", index=False)
    (out / "random_windows.json").write_text(json.dumps({
        "evaluation_start": evaluation_start, "evaluation_days": list(map(str, eval_days)),
        "window_days": list(window_days), "samples_per_size": samples_per_size,
        "seed": seed, "windows": windows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
