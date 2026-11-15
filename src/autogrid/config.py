from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ExecutionConfig:
    commission_bps: float = 0.3
    slippage_bps: float = 2.0
    short_borrow_bps_per_year: float = 50.0
    cost_stress_multipliers: tuple[float, ...] = (1.0, 1.5, 2.0)
    signal_delay_stress_bars: tuple[int, ...] = (1, 2)


@dataclass(frozen=True)
class RiskConfig:
    gross_exposure: float = 1.0
    max_asset_weight: float = 0.15
    risk_per_trade: float = 0.001
    daily_soft_loss: float = 0.005
    daily_hard_loss: float = 0.0075
    max_drawdown: float = 0.05
    max_loss_streak: int = 4


@dataclass(frozen=True)
class ValidationConfig:
    final_holdout_fraction: float = 0.20
    min_train_days: int = 10
    validation_days: int = 5
    step_days: int = 5
    purge_bars: int = 60


@dataclass(frozen=True)
class SearchConfig:
    capital: float = 100_000_000.0
    workers: int = 0
    seed: int = 20261114
    max_candidates: int = 5000
    shortlist: int = 150
    top_n: int = 30
    checkpoint_every: int = 25
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    grid: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_config(path: str | Path) -> SearchConfig:
    with Path(path).open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    execution = raw.get("execution", {})
    return SearchConfig(
        capital=float(raw.get("capital", 100_000_000)),
        workers=int(raw.get("workers", 0)),
        seed=int(raw.get("seed", 20261114)),
        max_candidates=int(raw.get("max_candidates", 5000)),
        shortlist=int(raw.get("shortlist", 150)),
        top_n=int(raw.get("top_n", 30)),
        checkpoint_every=int(raw.get("checkpoint_every", 25)),
        validation=ValidationConfig(**raw.get("validation", {})),
        execution=ExecutionConfig(
            commission_bps=float(execution.get("commission_bps", 0.3)),
            slippage_bps=float(execution.get("slippage_bps", 2.0)),
            short_borrow_bps_per_year=float(execution.get("short_borrow_bps_per_year", 50.0)),
            cost_stress_multipliers=tuple(map(float, execution.get("cost_stress_multipliers", (1.0, 1.5, 2.0)))),
            signal_delay_stress_bars=tuple(map(int, execution.get("signal_delay_stress_bars", (1, 2)))),
        ),
        risk=RiskConfig(**raw.get("risk", {})),
        grid=raw.get("grid", {}),
    )

