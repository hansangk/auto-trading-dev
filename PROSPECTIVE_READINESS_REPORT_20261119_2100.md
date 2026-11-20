# 새 완성봉 대기·달력 바이트 출처 정정 — 2026-11-19 21시 KST

**실제 readiness 1회, 신규 백테스트0회, 새 가격 취득0회.** `prospective_readiness_retry_20261119_2100`. 새 성과나 채택은 없으며 기본·비용2배·1봉지연 모두 수익기간 없음/수익·승률·MDD NA, 신규 거래0이다. 현금전략 수익0%라는 뜻이 아니다.

## 회고와 사전 판단

최신 [20시 보고](PROSPECTIVE_INPUT_AUDIT_REPORT_20261119_2000.md), AGENTS/RETRY_STATE/RESEARCH_HANDOFF/RETRY_PROTOCOL_V2를 먼저 읽었다. 기존 h120 기본1위는2025H2 지연−.1966%로 탈락, c180 개발통과도 직전6개월로 선정한 다음달 정책16회 기본−.7854/비용2배−.8949/지연−.4692%여서 채택하지 않았다. 상세 정확기간·승률·MDD는 [마지막 실제 성과](VENUE_LATENCY_RETRY_REPORT_20261119_1400.md)에 그대로 있다. 기존669calls를 신규로 세지 않았다.

이번은 현재 UTC/동결해시/달력으로 새 완성 ETF 구간이 있는지 확인하는 체크포인트다. 완료 구간이 없으면 닫힌 flow32·단독4·달력/보유8 조합 및 완료 월prefix는 재실행하지 않는다는 기준을 유지했다. 연구 부모 `f4bc9e6a50f9d2dbe48817bfcce556f55fd99d9c`; RUNNING CAS claim `16898e8eea84e0712fa4767778ff1462249d2dbf`. 이전 WAITING/worker false, 로컬 unresolved intent/lock 부재, 원본36 및20시 artifact SHA 일치 후 claim했다. 다른 환경 worker 생존은 직접 관측할 수 없으며 expected-parent/force금지를 유지했다.

## 실제 발견·재시도 로직 개선

현재 원격 plan/guard/input-auditor Git blob은 LOCAL과 일치했다. 그러나 **기존 달력의 원격 바이트 동일성 주장은 정정한다.** 공개 LF 파일과 LOCAL CRLF 파일은 날짜/시작/종료 값이 같지만 바이트·SHA가 다르다. 20시 이전의 포괄적인 달력 blob 일치 표현은 부정확했다.

|달력 표현|길이|SHA256|Git blob SHA1|
|---|---:|---|---|
|LOCAL CRLF 원본|80|5f993b55f18a91bb37b80516181389733238568b966275cf3f5aa1e6682cc03d|07615ffae2648a7e361d82a0608ab898126e0b44|
|GitHub LF 공개본|78|c1542f649163d91e9ece62300021e00bc8de166616164d98b116edadc1d9495f|f077238e83ce42b8679e7c3ca7fa52a29f3bd2cb|

양쪽을 CSV로 파싱해 모든 행이 같고, 차이가 CRLF→LF뿐임을 실제 확인했다. [증거](runs/prospective_readiness_retry_20261119_2100/calendar_byte_provenance.json). 기존 원본·manifest·과거 수치·공개 파일은 덮어쓰지 않았다. 이번 guard는 기존 SHA에 맞는 LOCAL CRLF를 사용했다. 공개 LF에서 재현할 경우 다른 입력 SHA를 기록해야 한다. semantic equality를 byte equality나 다른 원본의 동일성으로 일반화하지 않는다. 앞으로 비교 실패를 발견하면 즉시 중단/분류하고 exec exit가0인지 확인한 후 다음 단계로 진행한다.

사전점검 실패2건을 [관측 로그](runs/prospective_readiness_retry_20261119_2100/observed_preflight_failures.log)에 남겼다: calendar blob assertion exit1, 오케스트레이션 structuredClone 미지원 ReferenceError. 이 실패 호출은 claim/파일변경/엔진 실행 전에 끝났으며 JSON 복제로 정정한 뒤 별도 claim을 성공시켰다. 전략/엔진 실패가 아니다. 새 단위테스트/전체suite 실행0; 코드 변경이 없어 이전20시238PASS를 **기존 검증으로만** 재사용했다.

## 실제 readiness·독립 검토

2026-11-19 12:01:30 UTC [guard 결과](runs/prospective_readiness_retry_20261119_2100/readiness.json): WAITING_FOR_COMPLETED_SHADOW_BARS, 완료 가능한 동결후 ETF봉0, fetchedETF/source0, terminal false, engine0, 주문0, 금융metrics null. 공식달력은 Nov19 하루만 확인되어 있다. Nov19 KST23:30 개장, Nov20 00:30 첫 hourly 완성,01:30 최초 모델 결정 가능,06:00 세션종료다. 단지 달력상 가능시각이며 가격 취득 보장이 아니다.

창의 퀀트 `shadow_readiness_quant_2100`은 기존4전략군×8=32 범위와 필요자료를 [독립 재검토](runs/prospective_readiness_retry_20261119_2100/quant_review.json)했다. 계절성 taker residual, 실제 execution cost gate, 비동기 shock 회복, flow 지속/활동량 모두 **PROPOSED_ONLY**다. 새 제안으로 조합수를 부풀리지 않았고 구현/선정/실행0이다. 실제 NBBO, 충분한 source활동 이력 및 ETF/source PIT 증거가 없다. 기본64개 이하/상위최대8개 stress 한도는 후속 새 증거가 있는 탐색에 적용한다.

frozen h120 hold2/c180 calendar-only hold4 및 같은15% 가격대조/비용/보호/비중 변경0. actual BUY universe TQQQ/SQQQ/IBIT/BITI, 현재 활성 Bitcoin 역할은 IBIT/BITI ETF 대용이다. BTC현물·차입공매도와 구분한다. 이번 네 티커 신규 체결0. 최근3/6개월 동일자료적합 순위 및 엄격한 직전3/6→다음달 연구는 기존 성과에 구분 보존했고 새 재적합0이다. 재사용2026은 독립검증이 아니며 새 독립기간0, 뉴스·매크로 사용0, 레버리지 확대/손절 제거0이다. 필터의 frozen 거래기회 효과나 전체계정 수익을 이번에 새로 계산하지 않았다.

## 입력·다음 인계

기존 원본 source: Binance BTCUSDT 실제30분35,040행, UTC2024-11-14포함~2026-11-14미포함. ETF 기존2024-11-14~2026-11-13 정상494세션. 원본36 SHA, ETF/context/plan/달력 및 이번 코드/출력은 [manifest](runs/prospective_readiness_retry_20261119_2100/analysis_manifest.json)와 RETRY_STATE에 기록했다. 이전 공개 업로드 거절 파일은 재업로드하지 않았다. LOCAL 원본·context·원장 접근 전제이며 해시만으로 복원되지 않는다.

개선은 줄바꿈 표현에 따른 provenance 오류 발견·정정이며 **수익 개선은 입증되지 않았다**. 다음에는 freshUTC+새 공식달력 범위+실제 source/ETF vintage/PIT/원본hash·coverage를 먼저 확인한다. 준비된 입력감사도 구조 검증일 뿐 terminal을 허용하지 않는다. signal parity 및 새 FULL AccountState/model-control-stress 실행 통합은 여전히 미구현이며, 실제자료를 기다리는 것과 별도 작업이다. 과거 reset account를 prospective로 복사하거나 partial download 끝을 강제청산으로 만들지 않는다. 최소20/여러기간/cost2/delay 전 채택 금지.

RETRY_STATE와 bounded RESEARCH_HANDOFF를 새 checkpoint/소유권/부모/다음명령/hash로 갱신하고 worker false로 종료한다. 대기 상태이며 전체 환경 접근불가나 작업 완료로 해석하지 않는다.
