from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED = ("timestamp", "symbol", "open", "high", "low", "close", "volume")
DEFAULT_UNIVERSE = (
    "AAPL", "MSFT", "NVDA", "AMZN", "SPY", "QQQ", "GLD", "SLV", "TLT", "UUP",
    "IBIT", "BITI", "BITX",
)
BTC_ETFS = ("IBIT", "BITI", "BITX")


@dataclass(frozen=True)
class MarketData:
    timestamps: np.ndarray
    symbols: tuple[str, ...]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    sentiment: np.ndarray | None = None
    breaking: np.ndarray | None = None
    bar_minutes: int = 1

    @property
    def shape(self) -> tuple[int, int]:
        return self.close.shape


def _read_input(path: Path) -> pd.DataFrame:
    if path.is_file():
        return pd.read_csv(path)
    files = sorted(path.glob("*.csv"))
    if not files:
        raise ValueError(f"CSV 파일이 없습니다: {path}")
    frames = []
    for file in files:
        frame = pd.read_csv(file)
        if "symbol" not in frame:
            frame["symbol"] = file.stem.upper()
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def load_market_data(
    path: str | Path, symbols: list[str] | None = None, events_path: str | Path | None = None,
) -> MarketData:
    frame = _read_input(Path(path))
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError(f"필수 열 누락: {sorted(missing)}")
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    wanted = [s.upper() for s in symbols] if symbols else sorted(frame["symbol"].unique().tolist())
    frame = frame[frame["symbol"].isin(wanted)]
    if len(wanted) < 2:
        raise ValueError("롱/숏을 위해 최소 2개 심볼이 필요합니다.")
    if frame.duplicated(["timestamp", "symbol"]).any():
        raise ValueError("timestamp/symbol 중복 행이 있습니다.")
    numeric = ["open", "high", "low", "close", "volume"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(frame[numeric].to_numpy()).all():
        raise ValueError("OHLCV에 NaN 또는 무한대가 있습니다.")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any() or (frame["volume"] < 0).any():
        raise ValueError("가격은 양수, 거래량은 0 이상이어야 합니다.")
    invalid_ohlc = (frame["high"] < frame[["open", "close", "low"]].max(axis=1)) | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    if invalid_ohlc.any():
        raise ValueError("OHLC 범위 관계가 잘못된 행이 있습니다.")
    frame = frame.sort_values(["timestamp", "symbol"])
    counts = frame.groupby("timestamp", sort=True)["symbol"].nunique()
    if (counts != len(wanted)).any():
        bad = int((counts != len(wanted)).sum())
        raise ValueError(f"심볼 간 공통 타임스탬프가 아닙니다 ({bad}개 시점). 결측 봉을 명시적으로 정리하세요.")
    timestamp_index = pd.Index(sorted(frame["timestamp"].unique()))

    def pivot(column: str) -> np.ndarray:
        p = frame.pivot(index="timestamp", columns="symbol", values=column).reindex(index=timestamp_index, columns=wanted)
        return np.ascontiguousarray(p.to_numpy(dtype=np.float64))

    sentiment = breaking = None
    if events_path:
        from .events import align_events
        sentiment, breaking = align_events(events_path, timestamp_index, wanted)
    unique_times = pd.Series(timestamp_index).sort_values()
    deltas = unique_times.diff().dt.total_seconds().div(60)
    intraday = deltas[(deltas > 0) & (deltas <= 390)]
    bar_minutes = max(1, int(round(float(intraday.median())))) if len(intraday) else 1
    return MarketData(
        timestamp_index.to_numpy(), tuple(wanted), pivot("open"), pivot("high"),
        pivot("low"), pivot("close"), pivot("volume"), sentiment, breaking, bar_minutes,
    )


def generate_demo(path: str | Path, days: int = 35, seed: int = 20261114) -> None:
    rng = np.random.default_rng(seed)
    business_days = pd.bdate_range("2025-01-02", periods=days)
    offsets = pd.to_timedelta(np.arange(390), unit="m")
    timestamps = np.concatenate([(day + pd.Timedelta(hours=14, minutes=30) + offsets).to_numpy() for day in business_days])
    symbols = DEFAULT_UNIVERSE
    t, n = len(timestamps), len(symbols)
    market = rng.normal(0.0, 0.00055, size=t)
    btc = rng.normal(0.0, 0.0014, size=t)
    defensive = rng.normal(0.0, 0.00035, size=t)
    betas = np.array([1.05, .95, 1.35, 1.1, 1, 1.15, -.1, .05, -.25, -.15, .15, -.10, .25])
    starts = np.array([190, 420, 140, 220, 600, 510, 185, 24, 92, 28, 42, 30, 35], dtype=float)
    returns = market[:, None] * betas + rng.normal(0.0, 0.00045, size=(t, n))
    returns[:, 6:10] += defensive[:, None] * np.array([.8, .7, 1, .8])
    returns[:, 10] += btc
    returns[:, 11] -= 0.9 * btc
    returns[:, 12] += 2.0 * btc
    returns[1:, :4] += .08 * returns[:-1, :4]
    close = starts[None, :] * np.exp(np.cumsum(returns, axis=0))
    open_ = np.vstack([starts, close[:-1] * np.exp(rng.normal(0, .00008, size=(t - 1, n)))])
    spread = np.abs(rng.normal(.00045, .00018, size=(t, n)))
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    volume = rng.lognormal(mean=11.0, sigma=.55, size=(t, n)).astype(int)
    frames = []
    for j, symbol in enumerate(symbols):
        frames.append(pd.DataFrame({
            "timestamp": pd.to_datetime(timestamps, utc=True), "symbol": symbol,
            "open": open_[:, j], "high": high[:, j], "low": low[:, j],
            "close": close[:, j], "volume": volume[:, j],
        }))
    out = Path(path); out.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_csv(out, index=False)

