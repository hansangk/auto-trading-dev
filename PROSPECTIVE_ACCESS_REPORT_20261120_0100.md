# 첫 실제 부분자료 접근·감사 — 2026-11-20 01시 KST

**실제 ETF 완성봉4개와 Binance30분봉18개를 새로 확보·부분감사했다. 실제 백테스트0회, 실거래 주문0회다.** 비용차감수익 개선/새 독립기간 검증/채택은 아직0이다. [부분감사](runs/prospective_access_retry_20261120_0100/session_access_audit.json)/[해시·계보](runs/prospective_access_retry_20261120_0100/prefix_snapshot_integrity.json).

## 회고·사전 기준

최신 [00시 보고](PROSPECTIVE_READINESS_REPORT_20261120_0000.md), AGENTS/state/handoff/protocol을 먼저 읽었다. 기존 h120 기본1위 지연실패와 c180의 작은표본·직전6개월→다음달16회 손실은 해결되지 않았다. [마지막 실제 성과](VENUE_LATENCY_RETRY_REPORT_20261119_1400.md)의 정확기간/기본·비용2배·1봉지연/거래수·승률·MDD/최근3·6적합과 인과적월별 결과를 보존하며 기존669호출을 새로 세지 않는다. 닫힌 flow32·단독4·달력/보유8·완료월prefix는 반복하지 않았다.

이번 새 가설은 **달력상 완성된 첫시간봉이 실제 공급자 응답에도 존재하는가**다. 부모 `5c66a149a3f08e32af704c14b7de869c41ae9969`; RUNNING/사전계약 `9e2cfac0aaaa3f72009f55f66ff4a15a48492abc`. [계약](runs/prospective_access_retry_20261120_0100/preregistered_access_contract.json)을 취득 전에 저장했다. 이전 WAITING/worker false·로컬 미해결intent/lock부재,00artifact 및 원본36hash일치 후 CAS claim했다. 외부worker 생존은 직접 관측하지 못하며 force없이 expected-parent를 확인했다.

사전 기준은 네ETF의 실제14:30–15:30UTC 완성봉과 source06:30–15:30UTC의18연속30분봉이다. 원문/공급자/시각/hash를 보존하고 미래/미완성/이동·합성봉을 쓰지 않는다. 접근성·부분구조 통과를 전체입력·PIT·알파/백테스트로 부르지 않는다.

## 실제 취득 결과와 시각 구분

2026-11-19 16:04:22 UTC readiness는 완료가능한 ETF시간창1개, **PARTIAL_SESSION_OBSERVATIONS_ONLY_NO_TERMINAL_BACKTEST**였다. 그 점검당시 fetched0이었고 이후에 아래자료를 취득했다. 원본 readiness를 덮어쓰지 않았고 실제 취득수는 별도manifest/RETRY_STATE에 기록했다.

|자료|실제 요청/응답|선별한 완성구간 [시작,종료)|수량|
|---|---|---|---:|
|TQQQ/SQQQ/IBIT/BITI|Yahoo query2 chart,1h,각HTTP200|2026-11-19 14:30~15:30UTC|각1봉,총4|
|BTCUSDT spot|연결 Binance kline,30m,12열|2026-11-19 06:30~15:30UTC|18봉|

직접취득 ETF의 응답body bytes를 LOCAL에 저장했다. symbol/USD/NYtimezone/OHLCV/정확 clock·중복을 확인했다. source는 exact시작·종료,18개·12열,누락/중복0·양수volume/quote/tradecount·taker범위를 실제 검사했다. source는 **직렬화한 connector envelope와 추출행** 해시이며 원본HTTP wire/body bytes를 확보했다고 주장하지 않는다. 실제조회5회(ETF4+connector1), 재조회0이다.

고정 **bar-end cutoff16:04:22UTC**는 수신시각이 아니다. ETF실제 host수신16:06:29.519121~16:06:29.524025UTC, Binance 응답은 검증시계16:06:20~16:06:22UTC 사이 관측했다. 나중 관측은 cutoff/과거봉종료/가정end+5분에 이미 사용가능했다는 증거가 아니다. 현재 최초관측을 과거 PIT로 소급하지 않는다.

## 원인 분석·실패를 보존한 부분 감사

각 ETF응답에는 14:30완성봉,15:30미완성봉 외에도16:05:39 또는16:06:28의 **cutoff뒤 off-clock행**이 붙었다. 최초 collector는 이 추가행 때문에 strict완전coverage 성공0으로 표시했다. HTTP200 네건/완성봉4개와는 다른 지표다. 최초raw·manifest를 그대로 보존했다.

그 뒤 원래의 미래자료금지 기준에 따라 **timestamp>cutoff를 먼저 별도 제외**하고, cutoff안의 off-clock행은 여전히 기각하는 파티션 감사를 추가했다. 실제 각3행→완성1/미완성1/cutoff뒤1로 분리했으며 미래행의 OHLC값을 후보입력에 읽어 넣지 않았다. 이 분류보완은 응답 관측후의 ingestion진단이고 전략선정이나 독립검증이 아니다.

부분감사 최초adapter는 기존API에 문자열 대신datetime을 전달해 실패했다. [attempt1](runs/prospective_access_retry_20261120_0100/partial_audit_attempt1.log)을 보존하고 aware ISO문자열로 수정한 [attempt2](runs/prospective_access_retry_20261120_0100/partial_audit_attempt2.log)가 통과했다. 같은raw를 재사용했으며 재취득/엔진0이다. [전체 실패기록](runs/prospective_access_retry_20261120_0100/observed_failures.json). 첫실패뒤 출력이 없음을 확인한 검사exit2도 기록했다.

기존 full-session qualifier는 실제부분자료를 **Incomplete/future ETF session refused**로 거부했다. 인터페이스실패를 포함한2회 시도, 완전감사통과0이다. 유효 부분감사1회와 구분한다. 실제 전체세션 ETF는21:00UTC(KST06:00)까지, 현재 source가정floor는21:05UTC까지 필요하다. 최초모델결정 가능16:30UTC도 아직 당시future이며 가격접근/실행보장이 아니다. partialdownload끝 강제청산이나 미래가격 합성으로 수익을 만들지 않았다.

## 성과·전략 범위

|이번 조건|실제 수익 평가기간|신규엔진/거래|비용차감수익·승률·MDD|
|---|---|---:|---|
|기본|없음|0/0|NA|
|비용2배|없음|0/0|NA|
|1봉지연|없음|0/0|NA|

자료기간은 전략수익 기간이 아니며 NA를0%현금수익으로 채우지 않는다. 기존대비 진전은 **달력추정에서 실제22개 부분자료의 접근·구조검증으로 넘어간 것**이다. 수익개선은 미확인이다. 새unit/전체suite실행0, 이전241PASS는 기존증거만 재사용했다. 이번은 실제payload 불변성 검사/구조감사 실행이며 합성테스트 수를 늘리지 않았다.

독립 창의퀀트 `first_hour_access_quant_0100`은 [기존4군×8=32 범위](runs/prospective_access_retry_20261120_0100/quant_review.json)와 필요한실제증거를 검토했다. 계절성taker residual/실제cost gate/비동기shock/flow지속·활동량은 PROPOSED_ONLY, 새threshold·구현·선정·탐색0이다. 부분 OHLCV가 seasonal history/NBBO/paired표본을 공급한다고 주장하지 않는다. 새근거 탐색≤64/개발상위≤8 stress예산은 유지한다.

actual TQQQ/SQQQ/IBIT/BITI BUY구조, 활성Bitcoin역할의 IBIT/BITI ETF대용, h120hold2/c180calendar-onlyhold4·같은15%가격대조와 비용·손절·비중을 그대로 두었다. sourceBTCUSDT는 참고시세이며 현물매매나 차입공매도 실행이 아니다. 네ETF신규체결0, 레버리지확대/손절제거/뉴스·매크로시점자료0이다. 동일거래기회 라벨과 전체계정수익은 별개이며 이번계산0. 최근3/6적합과 strictprior3/6→다음달 구분을 유지했고 새재적합0이다. 새로취득한 동결후 봉이어도 재사용2026을 독립holdout이라 부르지 않는다.

## 코드·원본·다음 인계

[수집기](scripts/prospective_access_20261120.py)와 [부분감사](scripts/prospective_partial_audit_20261120.py)는 이번 고정첫시간창 전용이다. 기존17 frozen dependency는 실제SHA를 재확인하며 변경하지 않았다. 코드/설정/원본7개 신규LOCAL파일 hash·수신증거·부분결과는 [manifest](runs/prospective_access_retry_20261120_0100/analysis_manifest.json)에 기록했다. 신규raw는 공개업로드하지 않았다. 이전거절원본도 재시도하지 않았다.

기존 Binance35,040행(UTC2024-11-14포함~2026-11-14미포함)/ETF494정상세션(2024-11-14~2026-11-13) 및 원본36hash는 그대로다. LOCAL원본/context/원장 접근이 필요하며 hash만으로 복원되지 않는다. CRLF/LF달력 차이 [21시정정](runs/prospective_readiness_retry_20261119_2100/calendar_byte_provenance.json)도 유지한다.

다음수집은 **새ID/output**로 실제완성구간을 늘리고 최초관측시각·future/incomplete 파티션을 남긴다. 이번raw/output을 재조회/덮어쓰지 않는다. 최초신뢰prefix는 ETF `partial_ETF_LOCAL.csv` SHA256 `89ddb737486b7a768e0daab76933aad9496ff57af2b360c1371c8ef000c566b2`, source `BTCUSDT_30m_partial_LOCAL.json` SHA256 `7d6d6eaf8ea98808f781ecf363de12e84972125336bed0696c717503b1911090`이다. 실제raw와정규화행이 일치함을 확인했다. 다음snapshot은 이hash/과거키·수치불변을 비교하며 수정되면 별도vintage로 분리한다.

완전입력/PIT자격, **signal prefix-invariance/parity와 새 FULL AccountState/model-control-stress 보호실행 통합은 여전히 미구현/미완료**다. 구조감사는 terminal허용이 아니다. sourceovernight/weekend 실제연속성, 과거resetP&L복사금지, 미해결intent/누락state·ledger failclosed를 유지한다. 다음수익가설은 동결모델의 새로운 실제기간 cost/delay강건성이고 아직 미검증이다. 최소20거래·여러기간·stress전 채택하지 않는다. 상태/인계/소유권·부모·다음명령·신규원본hash를 갱신하고 worker false로 종료한다.
