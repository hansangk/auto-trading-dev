# BITI 비정규 행 원인 진단·격리 검증 — 2026-11-20 03시 KST

**기존 응답8개 재검사와 전체254개 테스트를 통과했다. 새 시세조회/백테스트/주문은0회다.** 알려진 실시간 관측행 패턴만 격리했고 완성봉 가격·시각의 변경/병합은0이다. 수익개선/채택/새독립기간 검증은 여전히 미확인이다.

최신 [02시보고](PROSPECTIVE_APPEND_REPORT_20261120_0200.md), AGENTS/state/handoff/protocol을 먼저 읽었다. 부모 `391171d66405cf808ad7ba45e3dcf1223ee50e16`, 소유권/사전계약 `b1fd51a2ce5a20109fabda54d32693622b663e14`. 이전worker false/로컬intent·lock없음 및 기존artifact·36raw·01/02각7privatehash 일치 확인 후 CASclaim했다. 외부worker생존은 직접관측하지 못하며 force없는expected-parent갱신을 유지했다. [사전기준](runs/prospective_tail_diagnosis_20261120_0300/preregistered_tail_contract.json).

## 가설·근거·실제 변경

02시BITI17:05:37행은 cutoff17:07:25보다 이르므로 future행으로 제외할 수 없었다. 이번 가설은 그 행이 **정규봉 대신, 미완성구간에 별도로 붙은 메타데이터 일치 관측행일 가능성**이다. 검증은 같은payload의ingestion진단이며 새로운독립표본/알파실험이 아니다.

01/02각네ETF 총8응답에서 마지막 timestamp==regularMarketTime, 거래량0, 자체OHLC모두동일, 바로앞정규봉구간 내부, 해당정규구간은cutoff때미완성이라는 조건을 실제확인했다. [관측행렬](runs/prospective_tail_diagnosis_20261120_0300/tail_observation_matrix.json). meta.regularMarketPrice와의정확일치는 반올림차이가 있어 조건으로쓰지 않았다.

[yfinance상위 구현](https://github.com/ranaroussi/yfinance/blob/main/yfinance/utils.py)의 별도live행처리도 확인했다. [출처SHA](runs/prospective_tail_diagnosis_20261120_0300/upstream_code_evidence.json)를 기록했다. 이는 클라이언트구현의 보조근거이며 Yahoo공식API보증이 아니다. 해당코드의행병합은 채택하지 않았다.

[순수분류함수](scripts/prospective_quote_tail_20261120.py)는 최종off-clock행에 위조건이 모두맞고 직전정규구간이아직미완성일 때만 별도격리한다. 미래행/미완성정규봉은다르게분류하고, 중간offclock·metadata불일치·거래량비영·가격비동일·이미종료된구간 등은 기각한다. 새가격/시각을만들거나 기존봉에합치지 않는다. hardcoded NY11월19일 정상세션 전용이며 장마감후패턴·이후달력까지해결했다고 하지 않는다.

## 실제 검증과 한계

독립퀀트 `tail_quant_0300`에 두신규파일 구현·반례검사를 위임했다. focused13PASS 뒤 root가 전체**254PASS**를1회실행했다(241기존+13신규). [테스트](tests/test_prospective_quote_tail.py)/[로그](runs/prospective_tail_diagnosis_20261120_0300/tests_final.log). 신규합성테스트는metadata·거래량·위치·구간완성각조건을변형하고 중복/비단조·잘못된OHLCV·병합방지를검증한다. 실제시세검증이나전략수익으로세지않는다.

[실제payload재검사](runs/prospective_tail_diagnosis_20261120_0300/actual_replay.json)는 미래행7/미완성정규행8/조건일치실시간행1을 격리했다. 01완성4행과02완성8행은 각원본CSV의정규화키·수치와 정확히같았다. 버전합계12행은 겹치는구간이며 고유ETF행은8개다. 기존source20봉은재취득하지 않았다. 모든기존raw/02기각결과를보존했고 신뢰prefix01을 full자격으로승격하지 않았다.

**이분류는 관측행 후보의좁은진단이지 vendor의미의보증이나전체입력/PIT/계정연속성 통과가 아니다.** Unknownoffclock는계속거부한다. 02당시원문clock기각은그대로남고03진단정책/코드해시가별도로추가됐다. 새payload에서똑같은조건을다시확인해야한다.

웹raw URL open/find는DisabledError였지만 렌더링GitHub조회와직접읽기에서클라이언트코드를확인했다. 파일작성전존재확인명령exit2는아직작성중인파일부재였고 검증실패가아니다. [실패기록](runs/prospective_tail_diagnosis_20261120_0300/observed_failures.json). 신규테스트/실제재검사실패0, 엔진실패0(호출0).

## 성과·범위·다음 인계

이번 **기본/비용2배/1봉지연 모두 실제수익기간없음·거래수0·비용차감수익/승률/MDD NA**다. NA는0%현금수익이 아니다. 기존대비개선은 명확한메타데이터조건의입력격리와반례검증에한정된다. 과거h120지연실패/c180작은표본·월별손실은미해결이며 [마지막실제성과](VENUE_LATENCY_RETRY_REPORT_20261119_1400.md)의 정확기간·스트레스/최근3·6적합과직전3·6→다음달 결과를보존했다. 기존669호출/닫힌flow32·단독4·달력보유8·완료월prefix 재실행0이다.

창의퀀트의 [기존4군×8=32검토](runs/prospective_tail_diagnosis_20261120_0300/quant_review.json)는 seasonal20/40×z1/1.5×확인1/2, costP50/75×1/2×확인1/2, shock20/40×z1/1.5×확인1/2, persistence2/3×20/40×1.25/1.5를 PROPOSED_ONLY로유지했다. 새threshold/전략구현/선정0, seasonal이력/NBBO/paired표본미확보다. 후속탐색≤64/기본상위≤8stress한도유지.

actualTQQQ/SQQQ/IBIT/BITI BUY구조, 현재Bitcoin의IBIT/BITI ETF대용, 동결h120hold2/c180calendar-onlyhold4·같은15%가격대조/비용·손절·비중은그대로다. 현물/차입공매도·실거래0, 레버리지확대/손절제거/뉴스·매크로시점자료0. 동일거래기회합계와전체수익은별개이며신규계산0. 재사용2026은독립검증이아니다.

현재실제확보자료는ETF[2026-11-19 14:30,16:30)UTC8행/source[06:30,16:30)20행 그대로다. 기존source35,040행[2024-11-14,2026-11-14)/ETF494세션과원본hash를유지했다. [manifest](runs/prospective_tail_diagnosis_20261120_0300/analysis_manifest.json)에코드/입력/결과/원본hash·부모/기준을기록했다. 신규시장raw업로드/이전거절업로드재시도0, LOCAL자료가필요하며해시만으로복원되지않는다. CRLF/LF달력정정도보존했다.

다음은 새ID/output에서 이좁은분류를적용해 실제완성구간·prefix/수신시각을확인하는것이다. 전체ETF21:00UTC/source가정21:05UTC까지와실제PIT가필요하며 **signal prefix-invariance/parity/새 FULLAccountState/model-control-stress 보호실행 통합은여전히미구현**이다. 부분자료끝강제청산·과거resetP&L복사·미해결intent/누락state·ledger우회금지. 최소20거래·여러기간·cost2/delay전채택하지않는다. 다음수익가설은동결모델의실제새기간강건성이고미검증이다. 소유권/체크포인트/원본hash/다음명령을갱신하고worker false로종료한다.
