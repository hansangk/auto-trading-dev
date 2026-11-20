# 동결 이후 새 기간 검증 준비 점검 — 2026-11-19 17시

**이번 신규 백테스트 0회, 신규 거래 0건, 수익·승률·MDD는 해당없음.** `prospective_readiness_retry_20261119_1700`은 실행 조건 점검을 실제 수행했고, 판정은 `WAITING_FOR_COMPLETED_SHADOW_BARS`다. 이전 완료 조합을 재실행하지 않았고0%수익을 만들어 기록하지 않았다. 실거래 주문0,신규원본취득/공개업로드0,새독립검증0.

## 직전 실패와 이번 판단

최신 브랜치 부모 `8ed09ea33362c01c5e76435d30c15d741f89aadd`의 상태·인계·프로토콜·[직전 보고서](VENUE_LATENCY_RETRY_REPORT_20261119_1400.md)를 먼저 읽었다. 직전669회실험에서 개발6조건 통과 c180이 나왔지만, 직전6개월로 선정해 다음달 적용한16회 결과는 기본−.7854/비용2배−.8949/지연−.4692%였다. 이는 **이전 결과이며 이번 새 실행으로 세지 않았다.** 16회는최소20에도미달,재사용2026은독립검증아님,채택0.

이를 근거로 동결한 `h120__source`, `c180__source`와 동일15%가격대조를 유지했다. 원래flow32/단독4/달력·보유8조합의 재탐색은 닫혀 있다. 새봉이 없다는 이유로 다른 임계값을 탐색해 같은 자료의 실패를 반복하지 않았다. 초기소유권 CAS `cc2f5217623fc28fe104d2d25f76aa16332842ff`;직전원격COMPLETE/체크포인트정합·intent/lock없음을 확인했다. 외부환경 worker의 생존은 직접관찰하지못했고 expected-parent로저장하며force를사용하지않았다.

## 검증 가능한 새 가설·사전 기준

가설은 **시간상 완성 가능한 ETF봉과 실제 검증된 입력을 구분하는 gate가 미완성 데이터의 마지막행을 강제청산가로 쓰는 오류를 막는가**다. 새로운 수익 가설의 성과탐색은 아니다.

사전기각:동결을 가로지르는 봉은 신규평가에서 제외하고 워밍업으로만 분리한다. 종료·가용시각이 현재보다 늦으면입력금지. 달력이 끝났더라도 실제source/ETF가격·vintage·coverage·원본hash·FULL AccountState·미해결intent감사 전에는 terminal backtest를 허용하지 않는다. 동결 모델/hold/파라미터·Git plan blob·종속code hash가 달라지면 차단한다. 확인하지 않은 날짜나단축장을 정상390분으로 추정하지 않는다.

독립 창의퀀트 `shadow_readiness_quant_1700`은 새RTH ETF완성봉이 없으면 엔진0/WAITING이 맞다고 검토했다. BTC24/7 새봉만으로 ETF거래기회를 만들 수 없다는 점을 확인했다. 별도신규실험용으로4전략군×8=32개 이내 범위를 제안했지만 **구현·실행·선정0**이며 동결모델은 바꾸지 않았다.

|제안군|고정범위 제안|현재 상태|
|---|---|---|
|시간대별 taker압력 잔차|과거20/40일×z1/1.5×확인1/2봉|제안만,실패조합중복·새가설검토필요|
|실제 비용에 따른 진입|spread분위50/75×여유1/2배×확인1/2봉|실제PIT NBBO/체결자료없음,사용했다는주장금지|
|BTC–QQQ 비동기충격 회복|lookback20/40×shock z1/1.5×확인1/2봉|정확한공통완성시각·입력접근감사전미실행|
|거래활동이동반된흐름지속|지속2/3봉×활동창20/40×surprise1.25/1.5|제안만,양수거래량/taker·중복검토필요|

제안의TQQQ/SQQQ/IBIT/BITI역할은실제ETF매수이며차입숏이나역수익합성이아니다. 현재동결shadow의활성역할은IBIT/BITI만이고Nasdaq은기존전체계정참조다. Bitcoin은IBIT/BITI ETF대용이며spot24/7백테스트로바꾸지않았다. 뉴스·매크로를전략신호에사용하지않았다.

## 실제 시각·달력 점검

공식 [NYSE 거래시간](https://www.nyse.com/trade/trading-information)과 [NYSE/ICE 2026휴장·단축장 공지](https://ir.theice.com/press/news-details/2025/NYSE-Group-Announces-2026-2027-and-2028-Holiday-and-Early-Closings-Calendar/)를 새로 확인했다.11월휴장은26일,단축장은27일이며11월19일은정규일정으로판정했다.이는공식예정시간이고당일돌발중단이나실제가격공급보장은아니다.

현환경은numpy/pandas사용가능하나 `exchange_calendars` import가 `ModuleNotFoundError`로실패했고캐시wheel도없었다. 실패를숨기지않고 `dependency_attempt1.log`에남겼다. 기존동결달력/코드를변경하거나버전을낮추지않고 **공식근거로검토한2026-11-19 하루만** 별도CSV로정규화했다. 이후NY날짜는달력연장검증이필요하다. 기존엔진·데이터가모두접근불가인상태로오인하지않았다.

동결UTC2026-11-19 05:20:49,실제점검UTC08:06:26(한국17:06:26). 예정정규장기준동결후완성ETF시간봉0개이고,가격API를호출해빈응답을받았다는주장은아니다. 실제데이터취득0행이다.

|예정이정표|UTC|한국시간|
|---|---|---|
|11월19일정규장시작|11/19 14:30|11/19 23:30|
|첫새ETF시간봉완성가능|11/19 15:30|11/20 00:30|
|동결모델의최초결정가능시각|11/19 16:30|11/20 01:30|
|정규장완료예정|11/19 21:00|11/20 06:00|

위시각은예정달력·동결source가용성규칙의필요조건으로부터계산했다. 모델이실제로신호를내거나데이터가그때확보된다는뜻은아니다. 첫봉만나왔다고최대보유·지연을포함한전체백테스트를부분자료마지막행에서끝내면안된다. 현재gate는정규장완료후에도 `CALENDAR_WINDOW_COMPLETE_INPUTS_NOT_AUDITED`를반환하며,별도실제입력감사없이는실행을허용하지않는다.

## 수행·검증·개선

`prospective_shadow_guard_20261119.py`를실행해다음을확인했다.

- 원격과일치하는동결plan Git blob `3595a3d7fc07401252a205f615f5fd743e77ab49` 및SHA256 `614f75e7cbb83e9eb9b6272d04743236b9ba32385fcfe9607001c0bf9b139155` 확인,모델2개와종속코드hash유지.
- 동결경계crossing/워밍업/미완성/미가용봉분리. 달력완료와실제가격접근을분리하고,확인범위만허용한다.
- 실제판정 `WAITING_FOR_COMPLETED_SHADOW_BARS`, `terminal_backtest_allowed=false`, `profit_metrics=null`.
- 신규7개경계테스트포함전체228테스트통과. 첫봉완성직전/직후,release경계,미완성세션,완료달력만으로실행허용금지,모델변경·naive시각·단축장거부,확인달력범위초과를검증했다.

기존입력·코드hash와직전669call체크포인트정합을확인했고이전실행은재개하지않았다. 원본36개공개업로드거절을존중해새업로드를시도하지않았다. 이번calendar CSV는시장가격이아닌공식예정시간메타데이터다.

|기존입력|SHA256|
|---|---|
|ETF gzip CSV|163e532099c1465e951543680730951b7b29a6d16021ff3affe31c23fd77e3d7|
|기존달력|754c3ce12689e122204594ea3c87d3aea73c98951e736bd5990c5ef90ff4b296|
|venue context|abd16a0e98fb10834c187d485eafbc09fbb470459afdef8bc6638fcc92733d8c|
|새공식근거11/19하루달력CSV|5f993b55f18a91bb37b80516181389733238568b966275cf3f5aa1e6682cc03d|

원본개별hash는RETRY_STATE및직전context_manifest,이번guard/테스트/근거/달력/hash는 `runs/prospective_readiness_retry_20261119_1700/manifest.json`과 `readiness.json`. 원본·기존context·큰원장은LOCAL접근전제이고hash만으로복원할수없다. 본보고의시장일정은운영조건확인용이며뉴스/매크로요인실험이아니다.

|검증조건|이번실행|순수익·승률·MDD|최근3/6개월새순위·월별새적용|
|---|---|---|---|
|기본/비용2배/1봉지연|모두미실행|해당없음,0%로표시금지|추가실행없음|

이전최신보고서의기본·cost2·delay1성과를이번숫자로복제하지않았다. 이번개선은재시도조건/재현성/미완성기간차단이며**전략수익개선여부는평가할새성과가없다**. 새독립기간검증이나성공을주장하지않는다.

## 다음회차인계

상태는 `WAITING_FOR_COMPLETED_SHADOW_BARS`,활성worker없음이다. 시간이지나새완성봉이생기면별도source+ETF vintage·공식달력·겹치는수정값·완전성·가용시점·hash를먼저감사한다. 과거워밍업과신규평가구간을분리하고,shadow전용모델/가격대조/스트레스별FULL AccountState를만든뒤연속보존한다. 과거reset실험의계정상태를prospective계정으로가져오지말것. 최소20실제거래·여러기간·비용2배·지연통과전채택없음. 동결후shadow라도재사용2026을독립holdout으로부르지않는다.

다음은새시각·새체크포인트로실행조건만재확인하는명령이다. `date -u`와외부시각도구는이번동일UTC로확인했다. calendar11/19범위를넘으면추정하지말고공식근거를갱신해야한다.

```bash
python scripts/prospective_shadow_guard_20261119.py --plan runs/venue_latency_retry_20261119_1400/prospective_shadow_plan.json --plan-blob-sha1 3595a3d7fc07401252a205f615f5fd743e77ab49 --calendar runs/prospective_readiness_retry_20261119_1700/calendar_20261119.csv --now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --out "runs/prospective_recheck_$(date -u +%Y%m%d_%H%M%S)/readiness.json"
```

달력이끝나도이guard는실제입력감사없이backtest허용을하지않는다. 이후별도shadow실행연결이필요하며아직새가격수집/백테스트는없다. 같은자료64조합·완료실험·월별prefix재실행금지. 다른RUNNING이면중복/덮어쓰기하지말고인계한다. 이번은미래완성봉을기다리는조건이며전체환경차단이나새전략성공으로판정하지않았다.
