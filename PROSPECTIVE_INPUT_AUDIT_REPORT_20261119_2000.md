# 실제 입력 감사 준비 — 2026-11-19 20시 KST

**신규 실제 백테스트 0회, 새 가격 취득 0회, 실제 입력 감사 0회.** `prospective_input_audit_retry_20261119_2000`은 입력 감사 코드와 합성 경계 테스트를 완료했고, 새 완성봉을 기다린다. 백테스트 완료나 전략 수익 개선으로 보고하지 않는다.

## 회고·가설·사전 기준

직전 14시 연구의 기본 1위 h120은 2025 하반기 지연 수익 −0.1966%로 탈락했다. c180은 개발 6셀을 통과했지만 직전 6개월로 골라 다음달 적용한 2026 정책은 16회, 기본 −0.7854%/비용2배 −0.8949%/지연 −0.4692%였다. 최소20 미달이며 채택은 0이다. 17–19시는 새 ETF 완성봉 없이 readiness만 기록했다. 종료된 flow32·단독4·달력/보유8 재탐색은 새 증거가 없어 반복하지 않았다.

재시도 로직의 약점은 **달력상 준비와 실제 입력 검증 사이의 연결이 없다는 점**이다. 새 가설은 정확한 세션 coverage, 실제 source 형식·연속성, 원본 수정 방지 감사를 먼저 구현하면 잘못된 입력의 후속 실행을 차단할 수 있다는 것이다. 이는 수익 가설이 아니며 알파 전략을 바꾸지 않는다.

연구 부모 `fe1b84c7c31060c3076fcaf8c14af129ecb4c2ae`, 소유권 claim `c0041dcca36c46a6d56bb7e15a4a2df501aefb89`, 코드 검증 전 기준 저장 `443df07f07e2b3b52c7cdcfd08ec11fa5f7e3f7a`. [사전 기준](runs/prospective_input_audit_retry_20261119_2000/preregistered_input_contract.json). 원격 WAITING/worker false 및 로컬 unresolved intent/lock 부재 확인 후 CAS로 시작했다. 다른 환경의 worker 생존은 직접 관측하지 못하므로 expected-parent/force 금지를 유지한다.

합격 기준은 정상 NY 390분 세션이 실제 종료되어야 하며, 각 TQQQ/SQQQ/IBIT/BITI에 7개 bar START(마지막30분 포함), 합계28행이 정확히 있어야 한다. source는 실제 Binance 형식12열/30분, RTH8시간 전부터 종료까지29봉/세션, 전체 스냅샷 연속, 양수 OHLCV·quote량·정수체결수 및 taker범위를 만족해야 한다. source end+가정5분≤asof를 요구한다. 누락·중복·미래·미완성·freeze경계 침범·기존행 수정/삭제는 기각한다. 이전 스냅샷 비교는 API 인자로 지원하며 CLI에는 아직 연결하지 않았다.

## 실제 수행과 한계

- [감사 코드](scripts/prospective_input_audit_20261119.py)와 [합성 테스트](tests/test_prospective_input_audit.py)를 추가했다. frozen plan Git blob 및17 dependency SHA256 검증, 입력파일·코드·출력 해시, 기존 출력 덮어쓰기 거부가 포함된다.
- 신규 합성 테스트10개, 전체 **238개 PASS**. [로그](runs/prospective_input_audit_retry_20261119_2000/tests_final.log). 합성 CLI 테스트는 전체 세션, 결측/미래/수정·잘못된 가격/체결량, 기존 출력 보호 및 dependency변조 거부를 검증했다. 이는 실제 가격 취득·실제 전략 실험이 아니다.
- 기존 원본36파일 SHA256 전부 일치. 원본·context·원장은 LOCAL 접근 전제이며 이전 공개 업로드 거절 파일을 재업로드하지 않았다. 해시만으로 소실 입력을 복원할 수 없다.
- 감사 통과 뒤에도 `terminal_backtest_allowed=false`, engine0, metrics null이다. 공식 달력 진위, 실제 가격의 공급자/수집 vintage, 역사적 PIT 수신시점은 별도 증거가 필요하다. end+5분은 가정이며 실제 수신시각이 아니다.
- source 전체 연속성을 요구하므로 익일 append 때 실제 overnight/weekend source 봉도 필요하다. 평가 ETF warmup은 포함하지 않는다. calendar 행 자체가 모든 대상 세션을 빠짐없이 포함하는지는 별도 공식달력 감사 책임이다.
- 신호 parity, 모델/가격대조/스트레스별 새 FULL AccountState, 실제 실행 adapter는 **아직 미구현**이다. 과거 reset P&L을 prospective state로 복사하지 않는다. 원본 구간 전체 hash 이외의 실제 새 입력 감사는 0회다.

2026-11-19 **20:03:11 KST**(11:03:11 UTC) [실제 readiness](runs/prospective_input_audit_retry_20261119_2000/readiness.json): 동결후 완료될 수 있는 RTH ETF봉0, terminal허용 false. 공식 확인 달력은 Nov19 하루뿐이다. RTH 개장23:30, 첫 시간봉 완성 Nov20 00:30, 모델 최초 결정 가능01:30, 세션 종료06:00 KST다. 시간 도달만으로 가격 접근이나 실행 준비가 보장되지 않는다. 본 감사의 전체세션 source 조건은 종료후 가정5분까지 필요하다. 이후 NY 날짜는 공식 달력 확장이 먼저다.

## 전략 검토와 성과 비교

독립 창의퀀트 `prospective_input_quant_2000`에 검토·두 신규파일 구현을 위임했다. [검토 기록](runs/prospective_input_audit_retry_20261119_2000/quant_review.json)의 기존 4군×8=32개는 **PROPOSED_ONLY**, 구현/선정/실행0이다. 계절성 taker residual(20/40세션×z1/1.5×확인1/2), 실제비용 gate(spread50/75백분위×비용1/2×확인1/2), 비동기 shock회복(lookback20/40×z1/1.5×확인1/2), flow지속+활동량(2/3봉×20/40세션×1.25/1.5)을 재검토했다. 실제 NBBO 등이 없으므로 사용했다고 하지 않는다. 새 탐색은 최대64, 개발상위최대8 stress 한도를 유지하되 대기 중에 새 임계값을 늘리지 않았다.

동결 `h120__source`(hold2), `c180__source`(calendar-only, hold4)와 같은15% 가격대조를 유지했다. c180은180분 보유전략이 아니다. 전체 universe는 실제 TQQQ/SQQQ/IBIT/BITI BUY 구조이고 현재 shadow의 활성 Bitcoin 역할은 IBIT/BITI ETF 대용이다. BTC 현물이나 차입 공매도가 아니며 이번 네 티커 신규 거래는 모두0이다. 레버리지/손절/비용/보유 설정 변경0, 뉴스·매크로 시점 자료 사용0, 실거래 주문0.

|이번 조건|실제 평가 수익 기간|신규 엔진 실행|비용차감 수익·승률·MDD|신규 거래|
|---|---|---:|---|---:|
|기본|없음|0|NA|0|
|비용2배|없음|0|NA|0|
|1봉지연|없음|0|NA|0|

NA를 현금 수익0%로 채우지 않는다. 다음 표는 **기존14시 결과를 인용**하며 신규 실행이 아니다. 기간은 시작포함/종료미포함, MDD는 실현 회차 기준이다.

|c180 source 기존 개발 기간|조건|순수익|거래수|승률|MDD|
|---|---|---:|---:|---:|---:|
|2025-01-01~2025-07-01|기본|+1.1393%|25|56.00%|0.5145%|
|동일|비용2배|+0.9650%|25|56.00%|0.5557%|
|동일|1봉지연|+0.1479%|25|60.00%|0.5220%|
|2025-07-01~2026-01-01|기본|+0.4245%|21|57.14%|0.2531%|
|동일|비용2배|+0.2791%|21|57.14%|0.3288%|
|동일|1봉지연|+0.2299%|21|66.67%|0.1949%|

기존 최근3개월(2026-08-14≤t<11-14) 기본1위 c120 +.3678%, 최근6개월(05-14≤t<11-14) c180 +.2740%는 같은 자료 적합이다. c180 최근3개월13회는 최소20 미달이다. 직전3/6개월로 선정한 다음달 검증과 구분한 모든 stress/승률/MDD는 [기존 성과 보고](VENUE_LATENCY_RETRY_REPORT_20261119_1400.md)에 보존했다. 이번 순위/월별 선정 재실행0. 재사용2026은 독립검증이 아니며 새 독립기간 검증0, 채택0이다. 필터 기회라벨 합계와 실제 전체계정 수익은 여전히 별도이며 이번 감사는 어느 쪽도 새로 계산하지 않았다.

## 원본·실패·다음 회차

기존 source는 Binance BTCUSDT30m 35,040행, UTC2024-11-14포함~2026-11-14미포함; ETF는 기존2024-11-14~2026-11-13 정상494세션 자료다. [manifest](runs/prospective_input_audit_retry_20261119_2000/analysis_manifest.json)에 현재 코드/plan/달력/검증 로그 SHA256, 원본36hash와 기간을 보존했다. ETF gzip SHA256 `163e532099c1465e951543680730951b7b29a6d16021ff3affe31c23fd77e3d7`, 기존 venue context `abd16a0e98fb10834c187d485eafbc09fbb470459afdef8bc6638fcc92733d8c`, plan `614f75e7cbb83e9eb9b6272d04743236b9ba32385fcfe9607001c0bf9b139155`. 이번 새 실제 입력 기간은 없다.

이번 실제 명령 실패는 로컬 `git status --short`가 checkout 부재로 exit128인 것뿐이며, 연결된 GitHub CAS 게시를 사용했다. 합성 기각 fixture는 의도된 성공 조건이다. 기존 calendar package 부재/1일 fallback 한계는 해결됐다고 주장하지 않는다. 전체 테스트 실행 오류0, 새 엔진 실패0(실행0). 개선은 **실제 입력 감사 준비와 오류 차단**이며 비용차감 수익 개선은 아직 입증되지 않았다.

다음 가설은 동결 두 모델의 새로운 실제 입력에서 비용/지연 강건성이 유지되는가다. 먼저 freshUTC readiness 및 공식달력, 실제 ETF/source provenance를 확보하고 새 감사 API/CLI를 적용한다. 그 뒤 signal parity와 새 FULL AccountState 실행 연결을 구현·사전검증해야 한다. 표본20·여러기간·cost2/delay 통과 전에는 승자 채택 금지. 새 자료 없이 닫힌 그리드/완료 월prefix를 재실행하지 않는다. `RETRY_STATE.json`과 `RESEARCH_HANDOFF.md`에 소유권·체크포인트·원본hash·다음 명령을 갱신하고 worker를 종료한다.
