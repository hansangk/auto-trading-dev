from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_EVENT_COLUMNS = {
    "event_id", "source", "published_at", "available_at", "symbol", "topic",
    "sentiment", "relevance", "confidence", "novelty", "is_breaking",
}


def align_events(
    path: str | Path, market_timestamps: pd.Index, symbols: list[str], ttl_minutes: int = 30,
) -> tuple[np.ndarray, np.ndarray]:
    events = pd.read_csv(path)
    missing = REQUIRED_EVENT_COLUMNS - set(events.columns)
    if missing:
        raise ValueError(f"뉴스 이벤트 필수 열 누락: {sorted(missing)}")
    events = events.copy()
    events["published_at"] = pd.to_datetime(events["published_at"], utc=True, errors="raise")
    events["available_at"] = pd.to_datetime(events["available_at"], utc=True, errors="raise")
    if (events["available_at"] < events["published_at"]).any():
        raise ValueError("available_at은 published_at보다 빠를 수 없습니다.")
    events["symbol"] = events["symbol"].astype(str).str.upper()
    events = events[events["symbol"].isin([*symbols, "ALL"])].drop_duplicates(["source", "event_id", "symbol"], keep="first")
    for col in ("sentiment", "relevance", "confidence", "novelty"):
        events[col] = pd.to_numeric(events[col], errors="raise")
    if (~events["sentiment"].between(-1, 1)).any():
        raise ValueError("sentiment는 -1~1 범위여야 합니다.")
    if any((~events[c].between(0, 1)).any() for c in ("relevance", "confidence", "novelty")):
        raise ValueError("relevance/confidence/novelty는 0~1 범위여야 합니다.")
    events["weight"] = events["relevance"] * events["confidence"] * events["novelty"]
    events["weighted_sentiment"] = events["sentiment"] * events["weight"]
    events["breaking_score"] = events["is_breaking"].astype(bool).astype(float) * events["weight"]
    t, n = len(market_timestamps), len(symbols)
    sentiment = np.zeros((t, n), dtype=np.float64)
    breaking = np.zeros((t, n), dtype=np.float64)
    left = pd.DataFrame({"timestamp": pd.to_datetime(market_timestamps, utc=True)}).sort_values("timestamp")
    for j, symbol in enumerate(symbols):
        right = events.loc[events["symbol"].isin([symbol, "ALL"]), ["available_at", "weighted_sentiment", "breaking_score"]]
        right = right.groupby("available_at", as_index=False).agg(
            weighted_sentiment=("weighted_sentiment", "sum"),
            breaking_score=("breaking_score", "max"),
        ).sort_values("available_at")
        right["weighted_sentiment"] = right["weighted_sentiment"].clip(-1, 1)
        if right.empty:
            continue
        aligned = pd.merge_asof(
            left, right, left_on="timestamp", right_on="available_at", direction="backward",
            tolerance=pd.Timedelta(minutes=ttl_minutes), allow_exact_matches=True,
        )
        sentiment[:, j] = aligned["weighted_sentiment"].fillna(0).to_numpy()
        breaking[:, j] = aligned["breaking_score"].fillna(0).to_numpy()
    return sentiment, breaking
