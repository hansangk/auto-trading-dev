# 다섯 시간 완성봉·장마감 경계 — 2026-11-20 05시 KST

**실제 ETF 완성봉20개·Binance30분봉26개를 확보·검사했다. 백테스트/주문0회, 수익 개선은 미확인이다.** 20봉은20거래가 아니며 최소거래표본을통과하지않았다.

최신 [04시보고](PROSPECTIVE_NORMALIZED_APPEND_REPORT_20261120_0400.md), AGENTS/state/handoff/protocol을먼저읽었다. 부모 `07cbded03f0ed3a14c8785d94cae28797830de1b`, RUNNING/사전기준 `2c5e91ac6bc7b25264670917c74054d4d785cf38`. [계약](runs/prospective_five_hour_append_20261120_0500/preregistered_five_hour_append.json)은가격취득전에저장했다. 이전worker false·로컬intent/lock없음,04artifact/기존36raw/01·02·04privatehash 일치를확인했다. 외부worker 생존은직접관측하지못하며CAS/force금지로덮어쓰기를막았다.

## 회고·가설·실행

기존h120지연실패/c180작은표본·월별손실은미해결이다. [마지막실제성과](VENUE_LATENCY_RETRY_REPORT_20261119_1400.md)의669호출·정확기간·기본/비용2배/지연·거래수/승률/MDD 및 최근3·6적합과직전3·6→다음달구분을보존하며재실행하지않았다. 닫힌flow32/단독4/달력보유8/완료월prefix 반복0이다.

새가설은동결03분류기로다섯시간새응답을선별해도01/04과거키·수치가보존되는가다. unknownoffclock/coverage부족/수치변경이면기각·별도vintage이며 임계값을완화하지않는기준을사전저장했다.

cutoff **2026-11-19T20:03:04Z**,ETF4개HTTP200+Binanceconnector1응답을새ID/output에저장했다. [실제결과](runs/prospective_five_hour_append_20261120_0500/normalized_append_audit.json).

|자료|완성구간 [시작,종료),UTC2026-11-19|현재행수|04대비고유추가|
|---|---|---:|---:|
|TQQQ/SQQQ/IBIT/BITI 각1h|14:30~19:30|각5,총20|4|
|Binance spotBTCUSDT30m|06:30~19:30|26|2|

source12열/OHLCV/양수quote·체결수/taker범위/연속성과ETF정확clock/OHLCV/중복을검사했다. 분류기SHA `133c2c642725f13dea1aef968226668af69a4b84e83f73cf552587d8302d44b9`는변경하지않았고 미래3/미완성정규봉4/엄격metadata관측행1을격리했다. 병합/시각이동/가격수정0이다. 옛수집helper의first-hour strict표시는보존하고5시간검사와구분했다.

01ETF4/source18,04ETF16/source24의신뢰된원문SHA를먼저확인했고 **기존키누락0/수치변경0**이다. 이전raw/02기각/03진단을보존하고계정을전체자격으로승격하지않았다. ETFhost수신20:03:10.838757~20:03:10.894009UTC,sourcehost관측 2026-11-19T20:03:04Z~2026-11-19T20:03:07Z다. 늦은수신을cutoff/봉종료/end+5분의과거PIT로소급하지않는다. Binance해시는직렬화connector/추출행이지원본HTTPbody bytes가아니다.

## 장마감 경계

독립퀀트 `five_hour_quant_0500`이현재코드와기존반례 `test_predecessor_must_still_be_incomplete_at_cutoff`, `test_tail_strictly_inside_interval`을검토했다. 특례는 `previous <= cutoff < end`를요구하므로21:05UTC에는모든정규구간이종료돼off-clock꼬리행을허용할수없다. 정상완성봉만있는응답은분류가능하지만알수없는꼬리행은계속거부한다.

이는코드/기존합성반례검토이며 **실제장마감후응답을관측한것은아니다**. 전체ETF21:00UTC(KST06:00)/source가정floor21:05UTC(KST06:05)는실제접근/PIT/실행보장이아니다. 06:00회차에서마지막source봉을미리쓰거나부분자료끝을강제청산으로삼지않는다. 이번재시도강화는이자동허가오해를막고장마감후조건을인계한것이다.

## 성과·범위·재현·인계

이번 **기본/비용2배/1봉지연 모두 실제수익기간없음·거래수0·비용차감수익/승률/MDD NA**다. NA는0%현금수익이아니다. 진전은partialcoverage16/24→20/26와과거값보존확인뿐이며 수익개선/채택/새독립기간검증0이다. 새단위테스트/전체suite실행0,기존254PASS는이전기록만재사용했다. 실제요청/검사exit0,엔진실패0(호출0). 보고준비JS의잘못된속성이름이SyntaxError를냈지만파일/시세/엔진변경없이정정했다. [실패기록](runs/prospective_five_hour_append_20261120_0500/observed_failures.json).

[독립4군×8검토](runs/prospective_five_hour_append_20261120_0500/quant_review.json)의 seasonal20/40×z1/1.5×확인1/2, costP50/75×1/2×확인1/2, shock20/40×z1/1.5×확인1/2, persistence2/3×20/40×1.25/1.5는32 PROPOSED_ONLY다. 새threshold/선정/전략실행0,seasonal이력/NBBO/paired표본미확보다. 후속≤64/개발상위≤8stress한도유지.

실제TQQQ/SQQQ/IBIT/BITI BUY구조,현재Bitcoin의IBIT/BITI ETF대용,h120hold2/c180calendar-onlyhold4·같은15%대조/비용/비중/손절은동결이다. 현물/차입공매도·뉴스/매크로자료·레버리지확대/손절제거0. frozen동일기회효과와전체재실행수익은별개이며신규계산0. 재사용2026은독립검증이아니다.

[수집·검사코드](scripts/prospective_five_hour_append_20261120.py)/[manifest](runs/prospective_five_hour_append_20261120_0500/analysis_manifest.json)에입력출처·기간·원문/코드/설정/결과/부모hash를남겼다. frozen17/기존36raw·source35,040행/ETF494세션·01/02/04privatehash를그대로보존하고신규7LOCAL파일hash도기록했다. raw공개업로드/이전거절재시도0,LOCAL원본/context/ledger필요,hash만으로복원되지않는다. CRLF/LF달력정정도유지했다.

다음은새ID/output에서실제마감후payload를관측하고현재분류기의허용/거부를그대로기록한뒤근거가있을때만별도정책을검토하는것이다. 전체입력/PIT/달력/coverage, **signal prefix-invariance/parity·새 FULLAccountState/model-control-stress 보호실행통합은여전히미구현/미완료**다. 01신뢰/05접근기준hash·키·수치를비교하며수정은별도vintage,부분강제청산/resetP&L복사/미해결intent·누락state/ledger우회금지. 최소20실제거래·여러기간·cost2/delay전채택금지. 다음수익가설은동결모델의새실제기간강건성이며미검증이다. 상태/인계·소유권/체크포인트/부모/다음명령/hash를갱신하고worker false로종료한다.
