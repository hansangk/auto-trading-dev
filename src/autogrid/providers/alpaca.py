from __future__ import annotations

import csv
from datetime import datetime, time
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import urllib.error
import time as time_module
from zoneinfo import ZoneInfo

import pandas as pd

from ..data import DEFAULT_UNIVERSE

ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
NY = ZoneInfo("America/New_York")


def _request(url: str, key: str, secret: str, max_attempts: int = 8) -> dict:
    request = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
        "User-Agent": "AutoGrid-Lab/0.2",
    })
    for attempt in range(max_attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == max_attempts - 1:
                raise
            retry_after = error.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else min(60.0, 2.0 ** attempt)
            time_module.sleep(delay)
        except (TimeoutError, urllib.error.URLError):
            if attempt == max_attempts - 1:
                raise
            time_module.sleep(min(60.0, 2.0 ** attempt))
    raise RuntimeError("Alpaca 요청 재시도 횟수를 초과했습니다.")


def download_alpaca_bars(
    output: str | Path,
    start: str,
    end: str,
    symbols: tuple[str, ...] = DEFAULT_UNIVERSE,
    feed: str = "iex",
    adjustment: str = "all",
    alignment: str = "common",
) -> dict:
    """Download Alpaca 1-minute bars and retain common regular-session timestamps.

    Credentials are read from ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY only.
    They are never written to output files or logs.
    """
    key = os.environ.get("ALPACA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("ALPACA_API_KEY_ID와 ALPACA_API_SECRET_KEY 환경변수가 필요합니다.")
    if feed not in {"iex", "sip"}:
        raise ValueError("feed는 iex 또는 sip여야 합니다.")
    if alignment not in {"common", "raw"}:
        raise ValueError("alignment는 common 또는 raw여야 합니다.")
    params = {
        "symbols": ",".join(symbols), "timeframe": "1Min", "start": start, "end": end,
        "limit": "10000", "adjustment": adjustment, "feed": feed, "sort": "asc",
    }
    rows: list[dict] = []
    page_token = None
    pages = 0
    while True:
        request_params = dict(params)
        if page_token: request_params["page_token"] = page_token
        payload = _request(f"{ENDPOINT}?{urllib.parse.urlencode(request_params)}", key, secret)
        pages += 1
        bars = payload.get("bars") or {}
        if isinstance(bars, dict):
            for symbol, items in bars.items():
                for bar in items:
                    rows.append({
                        "timestamp": bar["t"], "symbol": symbol,
                        "open": bar["o"], "high": bar["h"], "low": bar["l"],
                        "close": bar["c"], "volume": bar["v"],
                    })
        else:
            for bar in bars:
                rows.append({
                    "timestamp": bar["t"], "symbol": bar.get("S") or bar.get("symbol"),
                    "open": bar["o"], "high": bar["h"], "low": bar["l"],
                    "close": bar["c"], "volume": bar["v"],
                })
        page_token = payload.get("next_page_token")
        if not page_token: break
    if not rows:
        raise RuntimeError("API가 분봉을 반환하지 않았습니다. 기간·심볼·구독 feed를 확인하세요.")
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    local = frame["timestamp"].dt.tz_convert(NY)
    regular = (local.dt.time >= time(9, 30)) & (local.dt.time < time(16, 0))
    frame = frame.loc[regular].drop_duplicates(["timestamp", "symbol"]).sort_values(["timestamp", "symbol"])
    counts = frame.groupby("timestamp")["symbol"].nunique()
    common = counts[counts == len(symbols)].index
    complete = frame[frame["timestamp"].isin(common)].copy() if alignment == "common" else frame.copy()
    output_path = Path(output); output_path.parent.mkdir(parents=True, exist_ok=True)
    complete.to_csv(output_path, index=False, quoting=csv.QUOTE_MINIMAL)
    coverage = frame.groupby("symbol")["timestamp"].nunique().reindex(symbols, fill_value=0)
    return {
        "output": str(output_path), "feed": feed, "alignment": alignment, "pages": pages,
        "raw_rows": len(frame), "common_rows": len(complete),
        "common_minutes": len(common), "symbols": list(symbols),
        "coverage_minutes": {symbol: int(value) for symbol, value in coverage.items()},
        "warning": "IEX is a partial-volume feed; use SIP/tick data before live deployment." if feed == "iex" else None,
    }
