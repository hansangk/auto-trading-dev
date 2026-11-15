from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import random

import numpy as np

from .features import FeatureCache, INDICATOR_GROUPS


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    indicators: tuple[str, ...]
    weights: tuple[float, ...]
    long_k: int
    short_k: int
    hold_bars: int
    stop_loss_bps: float
    take_profit_multiple: float
    cooldown_bars: int

    def to_dict(self) -> dict:
        out = asdict(self); out["indicators"] = list(self.indicators); out["weights"] = list(self.weights)
        return out


def _strategy_id(payload: dict) -> str:
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def generate_specs(
    grid: dict, max_candidates: int, seed: int, include_news: bool = True,
) -> list[StrategySpec]:
    """Discrete grid를 고정 seed로 넓게 샘플링한다.

    수십억 개 직교곱을 메모리에 만들지 않고 서로 다른 지표군을 우선 선택한다.
    max_candidates를 크게 잡으면 하루짜리 탐색으로 자연스럽게 확장된다.
    """
    rng = random.Random(seed)
    groups = [
        group for group in INDICATOR_GROUPS
        if include_news or group != "point_in_time_news"
    ]
    counts = list(map(int, grid.get("components_per_strategy", [1, 2, 3])))
    weight_grid = list(map(float, grid.get("component_weights", [.5, 1, 1.5])))
    choices = {
        "long_k": list(map(int, grid.get("long_k", [1, 2]))),
        "short_k": list(map(int, grid.get("short_k", [1, 2]))),
        "hold_bars": list(map(int, grid.get("hold_bars", [1, 3, 5]))),
        "stop_loss_bps": list(map(float, grid.get("stop_loss_bps", [15, 25, 40]))),
        "take_profit_multiple": list(map(float, grid.get("take_profit_multiple", [1, 1.5, 2]))),
        "cooldown_bars": list(map(int, grid.get("cooldown_bars", [0, 15]))),
    }
    specs: dict[str, StrategySpec] = {}
    attempts = 0
    while len(specs) < max_candidates and attempts < max_candidates * 100:
        attempts += 1
        count = rng.choice(counts)
        selected_groups = rng.sample(groups, count)
        indicators = tuple(rng.choice(INDICATOR_GROUPS[group]) for group in selected_groups)
        raw_weights = [rng.choice(weight_grid) for _ in indicators]
        weights = tuple(round(w / sum(raw_weights), 6) for w in raw_weights)
        params = {name: rng.choice(values) for name, values in choices.items()}
        payload = {"indicators": indicators, "weights": weights, **params}
        sid = _strategy_id(payload)
        specs[sid] = StrategySpec(sid, indicators, weights, **params)
    return sorted(specs.values(), key=lambda spec: spec.strategy_id)


def build_score(spec: StrategySpec, cache: FeatureCache) -> np.ndarray:
    score = np.zeros(cache.data.shape, dtype=np.float32)
    for name, weight in zip(spec.indicators, spec.weights):
        score += float(weight) * cache.cross_sectional_rank(name)
    return score
