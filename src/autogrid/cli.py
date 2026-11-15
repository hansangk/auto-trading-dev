from __future__ import annotations

import argparse
import json

from .agents import antithesis, synthesis, thesis
from .config import load_config
from .data import generate_demo, load_market_data
from .search import run_search


def main() -> None:
    parser = argparse.ArgumentParser(prog="autogrid", description="1분봉 롱숏 전략 대규모 그리드서치")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("generate-demo")
    demo.add_argument("--output", required=True); demo.add_argument("--days", type=int, default=35); demo.add_argument("--seed", type=int, default=20261114)
    validate = commands.add_parser("validate-data")
    validate.add_argument("--input", required=True); validate.add_argument("--events")
    search = commands.add_parser("search")
    search.add_argument("--input", required=True); search.add_argument("--events")
    search.add_argument("--config", default="configs/search.yaml"); search.add_argument("--output", required=True); search.add_argument("--resume", action="store_true")
    review = commands.add_parser("review"); review.add_argument("--top30", required=True)
    download = commands.add_parser("download-alpaca")
    download.add_argument("--output", required=True); download.add_argument("--start", required=True); download.add_argument("--end", required=True)
    download.add_argument("--symbols", default="AAPL,MSFT,NVDA,AMZN,SPY,QQQ,GLD,SLV,TLT,UUP,IBIT,BITI,BITX")
    download.add_argument("--feed", choices=("iex", "sip"), default="iex")
    download.add_argument("--alignment", choices=("common", "raw"), default="common")
    random_validate = commands.add_parser("random-validate")
    random_validate.add_argument("--input", required=True); random_validate.add_argument("--top30", required=True)
    random_validate.add_argument("--config", default="configs/search.yaml"); random_validate.add_argument("--output", required=True)
    random_validate.add_argument("--evaluation-start", required=True)
    random_validate.add_argument("--window-days", default="5,10,20,40")
    random_validate.add_argument("--samples-per-size", type=int, default=25)
    random_validate.add_argument("--seed", type=int, default=20261115)
    args = parser.parse_args()
    if args.command == "generate-demo":
        generate_demo(args.output, args.days, args.seed); print(f"생성 완료: {args.output}")
    elif args.command == "validate-data":
        data = load_market_data(args.input, events_path=args.events)
        print(f"검증 통과: {data.shape[0]:,} bars × {data.shape[1]} symbols / news={data.sentiment is not None}")
    elif args.command == "search":
        data = load_market_data(args.input, events_path=args.events); cfg = load_config(args.config)
        top = run_search(data, cfg, args.output, args.resume); print(top.to_string(index=False))
    elif args.command == "review":
        import pandas as pd
        rows = pd.read_csv(args.top30).to_dict("records")
        reports = [
            {"strategy_id": row["strategy_id"], "정": thesis(row).__dict__, "반": antithesis(row).__dict__, "합": synthesis(row).__dict__}
            for row in rows
        ]
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    elif args.command == "download-alpaca":
        from .providers.alpaca import download_alpaca_bars
        symbols = tuple(item.strip().upper() for item in args.symbols.split(",") if item.strip())
        result = download_alpaca_bars(args.output, args.start, args.end, symbols, args.feed, alignment=args.alignment)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "random-validate":
        from .random_validation import run_random_validation
        data = load_market_data(args.input); cfg = load_config(args.config)
        windows = tuple(int(value) for value in args.window_days.split(",") if value.strip())
        result = run_random_validation(
            data, cfg, args.top30, args.output, args.evaluation_start,
            windows, args.samples_per_size, args.seed,
        )
        print(result.head(30).to_string(index=False))


if __name__ == "__main__":
    main()

