#!/usr/bin/env python3
"""Normalize free FirstRate Data + Yahoo chart samples for an engine smoke test.

This script is intentionally a sample-data adapter, not a production market-data
provider. It creates explicit zero-volume bars when a vendor omits a minute with
no trades and keeps only dates shared by every requested symbol.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


# TLT's currently published free sample is stale (May 2024), so IEF is used as
# the bond proxy for this smoke test. The production/default universe keeps TLT.
FIRST_RATE_SYMBOLS = ("AAPL", "MSFT", "NVDA", "AMZN", "SPY", "QQQ", "GLD", "SLV", "IEF", "UUP")
YAHOO_SYMBOLS = ("IBIT", "BITI", "BITX")
PRICE_COLUMNS = ["open", "high", "low", "close"]


def read_first_rate(raw_dir: Path, symbol: str) -> pd.DataFrame:
    archive = raw_dir / "firstrate" / f"{symbol}.zip"
    member = f"{symbol}_1min_sample.csv"
    with ZipFile(archive) as zipped, zipped.open(member) as stream:
        frame = pd.read_csv(stream)
    local = pd.to_datetime(frame.pop("timestamp"), errors="raise")
    frame.insert(0, "timestamp", local.dt.tz_localize("America/New_York").dt.tz_convert("UTC"))
    frame.insert(1, "symbol", symbol)
    return frame


def read_yahoo(raw_dir: Path, symbol: str) -> pd.DataFrame:
    payload = json.loads((raw_dir / "yahoo" / f"{symbol}_query1.json").read_text(encoding="utf-8"))
    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame({"timestamp": pd.to_datetime(result["timestamp"], unit="s", utc=True), **quote})
    frame.insert(1, "symbol", symbol)
    return frame.dropna(subset=PRICE_COLUMNS + ["volume"])


def regular_session(frame: pd.DataFrame) -> pd.DataFrame:
    local = frame["timestamp"].dt.tz_convert("America/New_York")
    minutes = local.dt.hour * 60 + local.dt.minute
    return frame[(minutes >= 9 * 60 + 30) & (minutes < 16 * 60)].copy()


def fill_missing_minutes(frame: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill vendor-omitted no-trade bars without crossing a session."""
    output: list[pd.DataFrame] = []
    local_days = frame["timestamp"].dt.tz_convert("America/New_York").dt.date
    for day, daily in frame.groupby(local_days, sort=True):
        start = pd.Timestamp(day, tz="America/New_York") + pd.Timedelta(hours=9, minutes=30)
        grid = pd.date_range(start, periods=390, freq="min").tz_convert("UTC")
        symbol = str(daily["symbol"].iloc[0])
        indexed = daily.drop(columns="symbol").drop_duplicates("timestamp").set_index("timestamp").reindex(grid)
        indexed[PRICE_COLUMNS] = indexed[PRICE_COLUMNS].ffill()
        indexed["volume"] = indexed["volume"].fillna(0)
        indexed.insert(0, "symbol", symbol)
        indexed.index.name = "timestamp"
        output.append(indexed.reset_index().dropna(subset=PRICE_COLUMNS))
    return pd.concat(output, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    frames = [read_first_rate(args.raw_dir, symbol) for symbol in FIRST_RATE_SYMBOLS]
    frames += [read_yahoo(args.raw_dir, symbol) for symbol in YAHOO_SYMBOLS]
    frames = [fill_missing_minutes(regular_session(frame)) for frame in frames]

    common_days: set = set.intersection(*[
        set(frame["timestamp"].dt.tz_convert("America/New_York").dt.date.unique()) for frame in frames
    ])
    frames = [
        frame[frame["timestamp"].dt.tz_convert("America/New_York").dt.date.isin(common_days)]
        for frame in frames
    ]
    common_timestamps = set.intersection(*[set(frame["timestamp"]) for frame in frames])
    combined = pd.concat(
        [frame[frame["timestamp"].isin(common_timestamps)] for frame in frames], ignore_index=True
    )
    combined = combined.sort_values(["timestamp", "symbol"])
    combined["volume"] = combined["volume"].astype("int64")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(args.output, index=False)

    summary = {
        "output": str(args.output),
        "symbols": sorted(combined["symbol"].unique().tolist()),
        "sessions": sorted(map(str, common_days)),
        "bars_per_symbol": int(combined.groupby("symbol").size().min()),
        "rows": len(combined),
        "start_utc": str(combined["timestamp"].min()),
        "end_utc": str(combined["timestamp"].max()),
        "zero_volume_rows": int((combined["volume"] == 0).sum()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
