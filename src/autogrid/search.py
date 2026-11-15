from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .config import SearchConfig
from .data import MarketData
from .engine import run_backtest
from .features import FeatureCache
from .strategy import StrategySpec, build_score, generate_specs

_DATA: MarketData | None = None
_CONFIG: SearchConfig | None = None
_FOLDS: list[tuple[int, int]] = []
_HOLDOUT: tuple[int, int] = (0, 0)
_FEATURES: FeatureCache | None = None
NEWS_FEATURES = {"sentiment", "breaking_sentiment", "news_momentum"}


def make_splits(data: MarketData, cfg: SearchConfig) -> tuple[list[tuple[int, int]], tuple[int, int]]:
    dates = pd.to_datetime(data.timestamps, utc=True).date
    days, starts = np.unique(dates, return_index=True)
    total_days = len(days)
    if total_days < 3:
        raise ValueError("검증/홀드아웃 분리를 위해 최소 3거래일이 필요합니다.")
    holdout_day = max(
        cfg.validation.min_train_days + cfg.validation.validation_days,
        int(total_days * (1 - cfg.validation.final_holdout_fraction)),
    )
    holdout_day = min(holdout_day, total_days - 1)
    holdout_start = int(starts[holdout_day])
    folds: list[tuple[int, int]] = []
    validation_start_day = min(cfg.validation.min_train_days, max(1, holdout_day // 2))
    while validation_start_day + cfg.validation.validation_days <= holdout_day:
        start = int(starts[validation_start_day]) + cfg.validation.purge_bars
        end_day = validation_start_day + cfg.validation.validation_days
        end = int(starts[end_day]) if end_day < total_days else len(data.timestamps)
        if start < end:
            folds.append((start, end))
        validation_start_day += cfg.validation.step_days
    if not folds:
        folds = [(max(1, holdout_start // 2 + cfg.validation.purge_bars), holdout_start)]
    return folds, (holdout_start, len(data.timestamps))


def _init_worker(data: MarketData, config: SearchConfig, folds: list[tuple[int, int]], holdout: tuple[int, int]) -> None:
    global _DATA, _CONFIG, _FOLDS, _HOLDOUT, _FEATURES
    _DATA, _CONFIG, _FOLDS, _HOLDOUT = data, config, folds, holdout
    _FEATURES = FeatureCache(data)


def _aggregate(spec: StrategySpec, phase: str, stress: float = 1.0, delay: int = 0) -> dict:
    assert _DATA is not None and _CONFIG is not None and _FEATURES is not None
    score = build_score(spec, _FEATURES)
    slices = _FOLDS if phase == "validation" else [_HOLDOUT]
    rows = [
        run_backtest(
            _DATA, score, spec, _CONFIG.execution, _CONFIG.risk, _CONFIG.capital,
            start, stop, stress, delay,
        ).to_dict()
        for start, stop in slices
    ]
    numeric = {
        key: float(np.mean([float(row[key]) for row in rows]))
        for key in rows[0]
        if isinstance(rows[0][key], (int, float, bool))
    }
    numeric["fold_positive_rate"] = float(np.mean([row["total_return"] > 0 for row in rows]))
    numeric["worst_fold_return"] = float(np.min([row["total_return"] for row in rows]))
    numeric.update(spec.to_dict())
    numeric.update({"phase": phase, "stress": stress, "signal_delay_bars": delay})
    return numeric


def _robust_score(frame: pd.DataFrame) -> pd.Series:
    def percentile(column: str, higher: bool = True) -> pd.Series:
        values = frame[column].replace([np.inf, -np.inf], np.nan)
        values = values.fillna(values.median() if values.notna().any() else 0.0)
        rank = values.rank(pct=True, method="average")
        return rank if higher else 1 - rank
    return (
        .22 * percentile("sharpe") + .15 * percentile("sortino") + .15 * percentile("calmar")
        + .12 * percentile("profit_factor") + .08 * percentile("win_rate")
        + .10 * percentile("fold_positive_rate") + .08 * percentile("worst_fold_return")
        + .10 * percentile("max_drawdown", higher=False)
    )


def _read_checkpoint(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _append_checkpoint(path: Path, rows: Iterable[dict]) -> None:
    with path.open("a", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, allow_nan=True) + "\n")
        file.flush(); os.fsync(file.fileno())


def _run_parallel(
    specs: list[StrategySpec], phase: str, cfg: SearchConfig,
    checkpoint: Path | None = None, stress: float = 1.0, delay: int = 0,
) -> list[dict]:
    workers = cfg.workers if cfg.workers > 0 else max(1, (os.cpu_count() or 2) - 1)
    rows: list[dict] = []
    if workers == 1:
        for spec in specs:
            row = _aggregate(spec, phase, stress, delay); rows.append(row)
            if checkpoint: _append_checkpoint(checkpoint, [row])
        return rows
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init_worker,
        initargs=(_DATA, _CONFIG, _FOLDS, _HOLDOUT),
    ) as pool:
        futures = {pool.submit(_aggregate, spec, phase, stress, delay): spec for spec in specs}
        buffer: list[dict] = []
        for future in as_completed(futures):
            row = future.result(); rows.append(row); buffer.append(row)
            if checkpoint and len(buffer) >= cfg.checkpoint_every:
                _append_checkpoint(checkpoint, buffer); buffer.clear()
        if checkpoint and buffer: _append_checkpoint(checkpoint, buffer)
    return rows


def _news_ablation_specs(specs: list[StrategySpec]) -> list[StrategySpec]:
    output = []
    for spec in specs:
        kept = [(name, weight) for name, weight in zip(spec.indicators, spec.weights) if name not in NEWS_FEATURES]
        if kept:
            total = sum(weight for _, weight in kept)
            indicators = tuple(name for name, _ in kept)
            weights = tuple(weight / total for _, weight in kept)
        else:
            indicators, weights = (), ()
        output.append(replace(spec, indicators=indicators, weights=weights))
    return output


def run_search(data: MarketData, cfg: SearchConfig, output: str | Path, resume: bool = False) -> pd.DataFrame:
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    checkpoint = out / "checkpoint.jsonl"
    folds, holdout = make_splits(data, cfg)
    _init_worker(data, cfg, folds, holdout)
    # A missing event file means news is unavailable, not neutral. Excluding the
    # news group prevents zero-filled placeholders from entering a strategy.
    specs = generate_specs(cfg.grid, cfg.max_candidates, cfg.seed, include_news=data.sentiment is not None)
    old_rows = _read_checkpoint(checkpoint) if resume else []
    if not resume and checkpoint.exists(): checkpoint.unlink()
    done = {row.get("strategy_id") for row in old_rows}
    pending = [spec for spec in specs if spec.strategy_id not in done]
    rows = old_rows + _run_parallel(pending, "validation", cfg, checkpoint)
    validation = pd.DataFrame(rows).drop_duplicates("strategy_id", keep="last")
    validation["validation_score"] = _robust_score(validation)
    validation = validation.sort_values(
        ["validation_score", "sharpe", "max_drawdown", "strategy_id"],
        ascending=[False, False, True, True],
    )
    validation.to_csv(out / "all_validation.csv", index=False)
    by_id = {spec.strategy_id: spec for spec in specs}
    shortlist = [by_id[sid] for sid in validation.head(cfg.shortlist)["strategy_id"]]
    final = pd.DataFrame(_run_parallel(shortlist, "holdout", cfg))
    final["score"] = _robust_score(final)

    for multiplier in cfg.execution.cost_stress_multipliers:
        if multiplier == 1.0: continue
        stressed = _run_parallel(shortlist, "holdout", cfg, stress=float(multiplier))
        final[f"return_cost_x{multiplier:g}"] = final["strategy_id"].map({row["strategy_id"]: row["total_return"] for row in stressed})
    for delay in cfg.execution.signal_delay_stress_bars:
        delayed = _run_parallel(shortlist, "holdout", cfg, delay=int(delay))
        final[f"return_delay_{delay}bar"] = final["strategy_id"].map({row["strategy_id"]: row["total_return"] for row in delayed})

    news_specs = [
        spec for spec in shortlist
        if data.sentiment is not None and set(spec.indicators) & NEWS_FEATURES
    ]
    final["uses_point_in_time_news"] = final["strategy_id"].isin({spec.strategy_id for spec in news_specs})
    if news_specs:
        ablated = _run_parallel(_news_ablation_specs(news_specs), "holdout", cfg)
        ablation_map = {row["strategy_id"]: row["total_return"] for row in ablated}
        final["return_without_news"] = final["strategy_id"].map(ablation_map)
        final["news_incremental_return"] = final["total_return"] - final["return_without_news"]
    else:
        final["return_without_news"] = np.nan; final["news_incremental_return"] = np.nan
    delay_columns = [f"return_delay_{delay}bar" for delay in cfg.execution.signal_delay_stress_bars]
    if delay_columns:
        final["timing_fragility"] = (final[delay_columns].min(axis=1) - final["total_return"]).abs()

    final = final.merge(
        validation[["strategy_id", "validation_score", "fold_positive_rate", "worst_fold_return"]],
        on="strategy_id", suffixes=("", "_validation"),
    )
    cost_columns = [column for column in final if column.startswith("return_cost_x")]
    stress_col = cost_columns[-1] if cost_columns else "total_return"
    final["worst_delay_return"] = final[delay_columns].min(axis=1) if delay_columns else final["total_return"]
    cost_rank = final[stress_col].rank(pct=True, method="average")
    delay_rank = final["worst_delay_return"].rank(pct=True, method="average")
    final["stress_score"] = .6 * cost_rank + .4 * delay_rank
    final["score"] = .5 * final["score"] + .2 * final["validation_score"] + .3 * final["stress_score"]
    final["eligible"] = (
        (final["trades"] >= 300) & (final["max_drawdown"] <= cfg.risk.max_drawdown)
        & (final["fold_positive_rate_validation"] >= .6) & (final[stress_col] > 0)
        & (final["worst_delay_return"] > 0) & (final["profit_factor"] > 1)
        & (final["long_pnl"] > 0) & (final["short_pnl"] > 0)
    )
    final = final.sort_values(
        ["eligible", "score", "sharpe", "max_drawdown", "strategy_id"],
        ascending=[False, False, False, True, True],
    ).reset_index(drop=True)
    final.insert(0, "rank", np.arange(1, len(final) + 1))
    top = final.head(cfg.top_n)
    top.to_csv(out / "top30.csv", index=False)
    manifest = {
        "data_hash": hashlib.sha256(data.close.tobytes()).hexdigest(),
        "config": cfg.to_dict(), "folds": folds, "holdout": holdout,
        "candidate_count": len(specs), "symbols": list(data.symbols),
        "bar_minutes": data.bar_minutes,
        "news_data_attached": data.sentiment is not None,
    }
    (out / "run.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return top

