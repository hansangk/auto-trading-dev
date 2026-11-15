# AutoGrid Lab

> **Current research status (2026-11-15):** The previously used 2026 period has been examined repeatedly and is not an untouched holdout. No annual 30% strategy is independently validated. The old engine exits long and short legs separately, checks some loss limits after a round, and uses partial IEX bars. Read [HANDOFF_INDEX.md](HANDOFF_INDEX.md) and [CLAUDE_HANDOFF_PROMPT.md](CLAUDE_HANDOFF_PROMPT.md) before interpreting older reports.

## Codex + Claude Code collaboration

Clone this repository, install with `python -m pip install -e .`, and run `PYTHONPATH=src python -m unittest discover -s tests -q`. Each agent should work on a separate branch (`codex/<topic>` or `claude/<topic>`), commit code and report artifacts, then open a PR to merge into `main`. Start a new task with `git fetch origin && git switch main && git pull --ff-only`; update feature branches with `git rebase origin/main`. Never force-push over the other's work. The repository includes code, tests, configs, and research reports. Full raw IEX history and historical run artifacts are kept in the owner's separate handoff archives and must not be committed. Never commit `upload/`, credentials, `.env`, or live trading keys.

1분봉 OHLCV로 미국 우량주·ETF·비트코인 ETF의 **롱/숏 동시 보유 초단타 전략**을 대규모 탐색하는 백테스트 연구 프로젝트입니다. 실주문 코드는 의도적으로 포함하지 않았습니다.

핵심 원칙:

- 신호는 `t`분 종가까지의 정보만 사용하고 `t+1`분 시가 이후 진입
- 서로 다른 종목을 동시에 롱·숏하며 기본 순노출은 0에 가깝게 유지
- 수수료·슬리피지·공매 차입비용 및 보수적인 봉 내부 손절 순서 반영
- 개발 구간 walk-forward 검증으로 후보를 줄이고 마지막 holdout은 1회만 평가
- 승률뿐 아니라 순수익, 낙폭, 안정성, 비용·신호 지연 스트레스를 함께 평가
- 전략과 독립된 일일 손실 한도·최대낙폭 킬스위치 적용

> 손실 없는 전략은 없습니다. 1분 OHLCV만으로 호가 순서·부분체결을 재현할 수 없으므로 결과는 보수적으로 해석해야 합니다.

## 기본 유니버스

- 대형주·지수: `AAPL, MSFT, NVDA, AMZN, SPY, QQQ`
- 실물·매크로: `GLD, SLV, TLT, UUP`
- 비트코인 ETF: `IBIT`(현물형), `BITI`(인버스), `BITX`(일일 2배형)

비트코인 ETF는 상장 이력이 짧고, 인버스·레버리지 상품은 일일 재설정과 선물 롤 비용 때문에 현물 BTC 수익률의 단순 ±배수가 아닙니다. ETF 자체 1분봉으로 검증하고 일반 주식과 별도 군집 안정성 평가를 거칩니다.

## 가격 데이터

모든 종목에 공통된 정규장 타임스탬프가 필요합니다.

```csv
timestamp,symbol,open,high,low,close,volume
2026-01-02T14:30:00Z,SPY,600.0,600.2,599.8,600.1,123456
```

## 뉴스·매크로 point-in-time 데이터

뉴스는 기사 작성 시각이 아니라 **시스템이 실제로 수신해 매매에 이용할 수 있었던 시각**으로 결합합니다.

```csv
event_id,source,published_at,available_at,symbol,topic,sentiment,relevance,confidence,novelty,is_breaking
abc123,telegram,2026-01-02T14:31:02Z,2026-01-02T14:31:06Z,IBIT,regulation,-0.8,0.95,0.8,0.9,true
```

- `available_at >= published_at`를 강제
- 수신 분 이후에만 backward as-of join
- 중복 전파는 `event_id/source`로 제거
- relevance·confidence·novelty로 가중
- 이벤트 TTL 이후 자동 소멸
- 최종 후보는 1분·2분 신호 지연 스트레스를 별도 평가

실시간 운용 시에는 Twitter/X·Telegram·공식 경제지표·거래소 공지를 수집하는 계층과 주문 계층을 분리합니다. 과거 백테스트 파일과 실시간 스트림은 같은 이벤트 스키마를 사용하도록 설계했습니다.

## 공식 1분봉 다운로드

Alpaca Market Data API를 지원합니다. 무료 Basic은 IEX feed라 미국 전체 거래량이 아닌 일부만 포함하므로 1차 전략 탐색용입니다. 최종 스캘핑 검증에는 SIP 또는 별도의 틱·호가 데이터가 필요합니다.

API 키를 셸 환경변수로 설정한 뒤 실행합니다. 키는 파일이나 로그에 저장하지 않습니다.

```bash
export ALPACA_API_KEY_ID="..."
export ALPACA_API_SECRET_KEY="..."

autogrid download-alpaca \
  --start 2024-02-01T00:00:00Z \
  --end 2026-11-01T00:00:00Z \
  --feed iex \
  --output data/alpaca_1m.csv
```

다운로더는 API 페이지네이션, 미국 동부시간 정규장 필터, 중복 제거, 13종목 공통 타임스탬프 정렬을 자동 수행합니다.

## 빠른 시작

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

python -m autogrid.cli generate-demo --output data/demo.csv --days 35
python -m autogrid.cli validate-data --input data/demo.csv
python -m autogrid.cli search --input data/demo.csv --config configs/search.yaml --output runs/demo
```

## 무료 샘플 및 분봉 비용 탐색

`scripts/prepare_free_sample.py`는 FirstRate Data 샘플과 Yahoo chart 샘플을 정규화하고,
`scripts/resample_market_data.py`는 세션 기준으로 5~60분 OHLCV를 만든다. 무료 샘플 결과는
`FREE_DATA_TEST_REPORT.md`, 분봉별 비용 탐색 결과는 `TIMEFRAME_COST_REPORT.md`에 정리되어 있다.

무료 표본은 파이프라인 검증용이며 실거래 성과 근거로 사용하지 않는다.

개별주를 제외한 SPY·QQQ·GLD·SLV·IBIT·BITI·BITX 전용 재실행 결과는
`MACRO7_TEST_REPORT.md`와 `runs/macro7_*` 결과 파일에 있다.

## 장기 랜덤구간 검증

Alpaca IEX 2024-01-11~2026-11-13 데이터로 개별주를 제외하고 30·45·60분봉을
각 1만 개씩 탐색했다. 2026-08-21 이후 60거래일은 완전히 잠근 뒤 마지막에 한 번만
평가했고, 그 안에서 5/10/20/40거래일 랜덤 창 96개를 추가 검증했다.

- 엄격한 실전 통과: 0개
- 조건부 연구 1순위: 45분봉 `zclose_10 40% + OBV_20 60%`
- 잠금 OOS: +0.706%, 승률 50.0%, PF 1.24, MDD 0.738%
- 비용 2배: +0.013%로 엣지 대부분 소멸
- 독립 라운드: 약 60회로 표본 기준 미달

따라서 현재 코드는 백테스트 연구 전용이며 페이퍼·실주문 승인을 내리지 않는다.
상세 결과는 `LONG_RANDOM_VALIDATION_REPORT.md`, 전체 1~30위는
`LONG_RANDOM_TOP30.csv`를 참고한다. 다음 검증은 BITO로 2021년 이후를 연장하고
SIP 또는 틱·호가 데이터에서 재실행해야 한다.

실제 뉴스 파일이 있으면 `--events events.csv`를 추가합니다.

결과:

- `top30.csv`: 최종 holdout 상위 30개
- `all_validation.csv`: walk-forward 검증 전체
- `run.json`: 데이터·설정 해시와 구간 정보
- `checkpoint.jsonl`: 완료 후보 증분 체크포인트

중단 후 같은 명령에 `--resume`을 붙이면 완료 후보를 건너뜁니다.

## 병렬·계층형 탐색

`workers: 0`은 CPU 코어 하나를 남기고 병렬 실행합니다.

1. 수십 개 지표에서 서로 다른 성격의 1~3개 조합을 광범위 탐색
2. lookback·가중치·롱/숏 수·보유시간·손절·익절·cooldown 탐색
3. 개발 구간 walk-forward로 후보 축소
4. shortlist만 비용 1.5배·2배 및 신호 1·2분 지연 평가
5. 마지막 holdout 결과와 검증 안정성을 합쳐 1~30위 출력

전체 직교곱이 지나치게 커질 때는 고정 seed의 재현 가능한 샘플링을 사용합니다. 하루 이상 돌릴 경우 `max_candidates`를 늘리면 됩니다.

## 리스크 기본값

초기자금 1억 원, gross 100%, 종목당 15%, 일일 -0.50% soft stop, -0.75% hard stop, 전체 -5% MDD 킬스위치입니다. 하드 스톱은 전략이 해제할 수 없습니다.

## 테스트

```bash
python -m unittest discover -s tests -v
```

