# Codex ↔ Claude 인계 — 2026-11-19 KST

최신 보고서 [REFERENCE_RETRY_REPORT_20261119.md](REFERENCE_RETRY_REPORT_20261119.md). 상태 COMPLETE_REJECTED, run_id reference_retry_20261119, owner Codex. 백테스트 worker 종료, 실거래0. 다음 실행 전 원격 AGENTS/RETRY_STATE/RESEARCH_HANDOFF/RETRY_PROTOCOL_V2/최신보고서를 확인하고 타인 RUNNING이면 중복·덮어쓰기 금지. 최초 연구 부모 c2eb4730a83644213b0fd1f10e0d6f44208338f9, 소유권 claim138b31400856491a36083a7804d93609c6cd7188, 사전설계 f56a926a72befff4ca3b20d9d1e3ee7492784fec, 완료집계 체크포인트3a3badaf73394d487c986747130675bb0a5f0b6b. expected-parent 갱신만 사용하며 기존Claude문서 보존.

실제82계좌재실행/121tests PASS(8.917초). reference_quant가 수익을 보지 않고4전략군×4=16설정 제안·구현.16distinct개발배열, 표본적격2개만 스트레스/설명진단, 개발전체통과0·채택0. 전체1위 shock3/2는 양개발 각각1라운드로 미선정. 14개는 최소표본20미달. 개발적격 동조3/.5와6/.5는 개발손익/비용기준실패. selection/ranking CSV의 동일16조합은 새 근거 없이 반복하지 말 것.

QQQ/BTC-USD 확정5분 원천을 새로 확보했다. BTC는9/21시작, 네ETF와동시78봉 완전거래일33개만 평가. 개발A9/21~9/30(6일),B10/1~10/18(8일),진단10/19~11/17(19일). 반복2026 독립아님.3/6개월적합 및 직전3/6선정다음달연속검증은 기간부족으로미실행. 공식달력·호가·최초공표PIT·뉴스/매크로 미사용. 종료확정봉 사용하지만 기본추가공표지연0 가정,1봉지연은5분.

동조3/.5 진단 기본/cost2/delay1 −1.0406/−2.2053/−1.6364%,81라운드43.21%승률1.7903%MDD(기본). 동조6/.5 −.4893/−1.5820/−1.5195%,80라운드42.50%승률1.5762%MDD. 기존ETF −.9977/−1.8607/−1.7756%,96라운드44.79%승률1.7724%MDD. 후자는이전3조건6메트릭재현됨. 원천만바꾼모멘텀은 −1.2839/−2.1562/−2.2775%로악화. 일부진단손실감소를채택근거로사용하지말것.

공통고정잠재기회 A92/B120개에서 원천동의필터는 역할138→137/190→188만제거. 사건평균net증분 +.0299/+.2381bp는계좌수익아님. 개발전체계좌는동의필터를써도기존과같았다. source_overlap.json의전체신호차이도참조. 계좌거래수20을정보개입표본20과혼동하지말것.

실제TQQQ/SQQQ/IBIT/BITI매수,IBIT는Bitcoin ETF대용,BITI선물인버스. 역할당15%/남는현금/hold12x5분/60bp종가확인후다음시가손절/3R/원계좌보호고정. 동조3/.5진단기본실제매수35/46/35/46,6/.5는38/42/38/42. 상세ticker_usage/account_replays에서모든조건비교.

입력:
- 동결ETF runs/extended_snapshot_20261118/refreshed_all_LOCAL.csv.gz SHA256 ebbdc8b683532ba96bf5c1358f5656833d6c33fe6833268ce1e13a777254b851
- 정합ETF runs/reference_retry_20261119/aligned_ETF_LOCAL.csv.gz SHA256 a672f4d76a6216e743270abb97fae31f421a955985fa718cd82c6c423430e99c
- 원천 runs/reference_retry_20261119/references_LOCAL.csv.gz SHA256 836d92f572b14bf0a622b637b7009ca6e261f09e7b567e36bec4ab206a689075
- QQQraw bc6f0f271dcc2ea11b0bf466860cc89f8cf72a50baa873d82b9f4e40d6a0c5d2; BTCraw822594b9648cf3627c9bd54992cc66531fdc922551b03d6355b76bf2af677836. URL/취득시각/제외일은reference_provenance.json.

공개업로드거절원본재업로드없음. *_LOCAL원본/상세원장/잠재경로는로컬전용; 원격집계만으로동일hash재현했다고하지말것. 새다운로드빈티지는별도실험으로취급.

다음명령: `sha256sum runs/reference_retry_20261119/references_LOCAL.csv.gz runs/extended_snapshot_20261118/refreshed_all_LOCAL.csv.gz` 다음 `PYTHONPATH=src python -m unittest discover -s tests -q`. 보존실험재현은 scripts/reference_retry_20261119.py,완료guard우회없이동일hash입력·새고유출력경로/사전계획필요. 현재경로를다시실행하면완료guard종료가정상.

다음미실행가설: 개발A/B에서직전원천움직임이ETF자체과거움직임외추가선행정보를주는가. 원천lag0/1/3비교의같은사건·실제매수역할·미래가격라벨을먼저사전정의하고분석하며,라벨을신호에되먹이지말것. 전략탐색전에return-blind기회수/역할변경수로식별가능성확인. BITI현물/선물불일치와명목민감도오차는별도단일요소대조. 충분한개입·양개발비용후증거없으면종료하고같은임계재탐색금지. 이감사코드는아직구현/실행하지않음.

이전 DIRECTION_CONTROL_REPORT_20261119.md, STRUCTURAL_GRID_REPORT_20261118.md, CLAUDE_CONTINUATION_20261118.md 보존.
