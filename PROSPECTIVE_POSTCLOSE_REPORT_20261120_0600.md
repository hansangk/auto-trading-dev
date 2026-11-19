# 실제 장마감 응답·원문 적격성 기각 — 2026-11-20 06시 KST

**ETF 정규봉 후보28개와 Binance30분봉29개를 실제 확보했다. 그러나3개ETF의추가마감행을현재동결규칙이거부해입력적격판정을기각했다. 백테스트/주문0회, 수익개선은미확인이다.** [실제감사](runs/prospective_postclose_access_20261120_0600/postclose_audit.json).

최신 [05시보고](PROSPECTIVE_FIVE_HOUR_REPORT_20261120_0500.md), AGENTS/state/handoff/protocol을먼저읽었다. 부모 `26bf9035169f0842c4026f003cea2112a8f7ad99`, RUNNING/사전계약 `2ee77294910d7a67cec03714ac9240993044ed5e`. [계약](runs/prospective_postclose_access_20261120_0600/preregistered_postclose_access.json)은취득전에저장했다. 이전worker false·로컬intent/lock없음·05artifact/기존36raw/01·02·04·05privatehash 일치를확인한뒤CASclaim했다. 외부worker생존은직접관측하지못하며expected-parent/force금지로덮어쓰기를막았다.

## 회고·사전 가설과 실제 취득

05시는장마감후현재분류기의incomplete-predecessor 조건이성립하지않는다는코드검토였을뿐실제마감응답을보지않았다. 이번가설은 실제응답에정규28행만있는지추가offclock행이있는지를확인하는것이다. 동결03분류기를바꾸지않고unknown행은기각,원문·수신시각·hash·과거값비교를보존하고 source29는가정floor21:05UTC이후에만요청하는기준을등록했다.

ETF요청bar-end cutoff는 **2026-11-19T21:04:07Z**였다. 4개HTTP200응답을21:04:14.515279~21:04:14.547955UTC에수신했다. 당시source마지막봉의가정floor는아직지나지않아29봉을미리요청하지않았다. 이후hostUTC로 **2026-11-19T21:05:51Z≥21:05**를확인한뒤Binance를요청했고,sourcehost관측구간은 2026-11-19T21:05:51Z~2026-11-19T21:05:52Z다. 늦은수신을과거봉종료/cutoff때사용가능했다는PIT증거로소급하지않는다.

|실제자료|구간 [시작,종료),UTC2026-11-19|관측수량|05대비고유추가|
|---|---|---:|---:|
|TQQQ/SQQQ/IBIT/BITI 정규1h후보|14:30~21:00|각7,총28(마지막30분포함)|8|
|Binance spotBTCUSDT30m|06:30~21:00|29|3|

정규후보의정확시각/OHLCV/중복과source12열·연속성/양수volume·quote·체결수/taker범위를검사했다. 01ETF4/source18 및05ETF20/source26의과거키누락0/수치변경0이었다. source보존해시는직렬화connector/추출행이며원본HTTPbody bytes가아니다.

## 실제 원인: 후보 봉 수와 원문 자격의 차이

|ETF|원문행수|현재분류기|관측된추가마감행|
|---|---:|---|---|
|TQQQ|8|기각|21:00:00,volume0,자체OHLC동일;metaMarketTime21:00:01|
|SQQQ|8|기각|21:00:00,volume0,자체OHLC동일;metaMarketTime21:00:00|
|IBIT|8|기각|21:00:00,volume0,자체OHLC동일;metaMarketTime21:00:01|
|BITI|7|정규행분류통과|추가행없음,마지막20:30정규봉volume28072|

세기각의정확오류는 `Off-clock tail lacks an incomplete regular predecessor`다. 모든정규구간이21:00에종료돼기존특례가성립하지않는다. 또한TQQQ/IBIT의metadata시각은마감행과1초달라단순히incomplete조건만완화하는것도근거있는해결이아니다.

**28개정규후보와29개source가있다는것은전체원문/PIT/계정자격통과가아니다.** raw gate가실패했으므로full-session qualifier를호출해candidate만통과시키는우회를하지않았다. 전체구조감사통과0/계정연속성false/AccountState초기화0/terminalfalse다. 추가행삭제·봉병합·시각이동·임의초단위허용오차를적용하지않았다. BITI에는추가행이없으므로모든종목의마지막행을일괄삭제하면유효20:30봉을잃는다.

이는05시의미래예상과달리**이번에는실제로관측한마감후모양**이다. 기존raw/02기각/03진단을보존하고새증거를별도기록했다. [관측·기각기록](runs/prospective_postclose_access_20261120_0600/observed_failures.json). 요청·검사프로세스exit0,전송/엔진실패0(엔진호출0),원문적격기각3이다.

## 성과·범위·재현·인계

이번 **기본/비용2배/1봉지연 모두 실제수익기간없음·거래수0·비용차감수익/승률/MDD NA**다. NA는현금수익0%가아니다. 진전은전체세션정규후보28/source29의실제접근과이전값보존확인이며,수익개선/채택/새독립기간검증은없다. 새unit/전체suite실행0,기존254PASS는과거기록만재사용했다.

창의퀀트 `postclose_quant_0600`은 [4군×8검토](runs/prospective_postclose_access_20261120_0600/quant_review.json)의 seasonal20/40×z1/1.5×확인1/2,costP50/75×1/2×확인1/2,shock20/40×z1/1.5×확인1/2,persistence2/3×20/40×1.25/1.5를32 PROPOSED_ONLY로유지했다. 새threshold/선정/전략실행0,seasonal이력/NBBO/paired표본미확보다. ≤64/개발상위≤8stress한도유지.

기존h120지연실패/c180작은표본·월별손실은미해결이다. [마지막실제성과](VENUE_LATENCY_RETRY_REPORT_20261119_1400.md)의669호출·정확기간/기본비용지연/승률MDD/최근3·6적합과strictprior3·6→다음달구분을보존했다. 닫힌flow32/단독4/달력보유8/완료월prefix 반복0이다. actualTQQQ/SQQQ/IBIT/BITI BUY구조,현재Bitcoin의IBIT/BITI ETF대용,h120hold2/c180calendar-onlyhold4·같은15%대조/비용·비중·손절을동결했다. 현물/차입공매도·뉴스/매크로자료·레버리지확대/손절제거0. 동일거래기회라벨과전체재실행수익은별개이며이번신규계산0. 재사용2026은독립검증이아니다.

[관측코드](scripts/prospective_postclose_access_20261120.py)/[manifest](runs/prospective_postclose_access_20261120_0600/analysis_manifest.json)에설정/기간/원본·코드·결과hash/부모와수신증거를저장했다. frozen17·기존36raw/source35,040행/ETF494세션·01/02/04/05hash를그대로보존하고신규7LOCAL파일hash를상태에추가했다. raw공개업로드/이전거절재시도0,LOCAL원본/context/ledger필요,hash만으로복원되지않는다. CRLF/LF달력정정도유지했다.

다음실질작업은**새모듈/사전기준/반례테스트로장마감보조행의별도정책을검토하는것**이다. 정확한세션끝/7정규행coverage/원문시각·0volume·동일OHLC/과거prefix 등실제증거를사용하되새규칙을현재분류기에조용히섞지않는다. 1초불일치에숫자허용오차를맞추거나마지막행을일괄삭제하지않는다. 같은응답진단은새독립검증이아니다.

이후에도진짜PIT·신호prefix-invariance/parity·새 FULLAccountState/model-control-stress 보호실행통합은미구현/미완료라곧바로백테스트나배포를허용하지않는다. 01신뢰/05접근기준을승격하지않고,수정은별도vintage,부분강제청산/resetP&L복사/미해결intent·누락state/ledger우회금지. 최소20실제거래·여러기간·cost2/delay전채택금지. 상태/소유권/체크포인트·부모·다음명령·원본hash를인계하고worker false로종료한다.
