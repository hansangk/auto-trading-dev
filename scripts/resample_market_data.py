#!/usr/bin/env python3
"""Aggregate normalized 1-minute OHLCV into larger, session-aligned bars."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--minutes", default="5,10,15,30,60")
    parser.add_argument("--common-only", action="store_true")
    args = parser.parse_args()

    source = pd.read_csv(args.input)
    source["timestamp"] = pd.to_datetime(source["timestamp"], utc=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for minutes in [int(value) for value in args.minutes.split(",")]:
        local = source["timestamp"].dt.tz_convert("America/New_York")
        session_open = local.dt.normalize() + pd.Timedelta(hours=9, minutes=30)
        bucket = ((local - session_open).dt.total_seconds() // (minutes * 60)).astype(int)
        bucket_timestamp = (session_open + pd.to_timedelta(bucket * minutes, unit="min")).dt.tz_convert("UTC")
        frame = source.assign(session=local.dt.date, bucket=bucket, bucket_timestamp=bucket_timestamp)
        result = (
            frame.groupby(["symbol", "session", "bucket"], sort=True, as_index=False)
            .agg(
                timestamp=("bucket_timestamp", "first"),
                open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"),
            )
            [["timestamp", "symbol", "open", "high", "low", "close", "volume"]]
            .sort_values(["timestamp", "symbol"])
        )
        if args.common_only:
            symbol_count = result["symbol"].nunique()
            counts = result.groupby("timestamp")["symbol"].nunique()
            common = counts[counts == symbol_count].index
            result = result[result["timestamp"].isin(common)].copy()
        destination = args.output_dir / f"market_{minutes}m.csv"
        result.to_csv(destination, index=False)
        print(f"{minutes}m: {len(result):,} rows -> {destination}")


if __name__ == "__main__":
    main()
