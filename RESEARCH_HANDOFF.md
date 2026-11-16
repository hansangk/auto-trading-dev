# Codex ↔ Claude 공통 연구 인계

상태 COMPLETE_REJECTED. run_id microstructure_grid_retry_20261117. 최신보고서 MICROSTRUCTURE_GRID_RETRY_REPORT_20261117.md. RETRY_STATE.json/AGENTS.md/RETRY_PROTOCOL_V2.md와최신부모커밋을먼저읽고RUNNING다른소유자의작업을덮어쓰지말것.

- 신호: scripts/microstructure_signals_20261117.py. 갭흡수/거래량압력/자산간지연/실패돌파4군×16=64조합 실제구현.
- 실행: PYTHONPATH=src python scripts/microstructure_grid_retry_20261117.py
- 결과: runs/microstructure_grid_retry_20261117/. plan/candidates/development_screen/stress_ranking/diagnostic/recent_rankings/walkforward/all_evaluations/failed_signatures. 2,074평가는독립전략수가아님.
- 최신결과: 개발합격0.2026-01-01~11-13개발1위갭3R기본1.0033%/비용2배.6209%/지연1.6144%,49라운드. 기존앵커7.8648/3.5411/5.7078%.최근6개월사후거래량후보2.3084/.9203/.6956%,127라운드,halt없음이나같은창앵커7.0774%보다낮음. 최근3개월표본충족최고도음수.
- 다음달연속계좌: 직전3개월선택-5.0239/-5.2567/-.8404%,직전6개월-4.7789/-4.6893/-.0594%. 2026재사용진단. 일부조건계좌중단을다음달초기화하지않음.
- 표본상한: signal_event_counts.csv. 최근3개월갭최대15/실패돌파16진입봉이라20라운드불가. 기준을낮추지말것.
- 테스트: PYTHONPATH=src python -m unittest discover -s tests -q (65개).
- 체크포인트: walkforward_decisions.jsonl/account_checkpoints.jsonl 및fixed_decisions.csv/monthly.csv. AccountState.current_date는JSON문자열이므로재개시date로복원,동일MarketData/원래인덱스/평탄세션경계필수. killed계좌재개금지. 전체거래원장은로컬재생성.
- 원본: runs/inverse_etf_retry_20261116/market.csv.gz SHA256 e0dea9e76a9c7f57b5d3791912e85473a29f5d31d4743783cf17b29a95c09fbd. GitHub에는없음(과거공개업로드거절),같은파일없으면동일재현주장금지. 새다운로드는새경로/해시/대조군으로구분.

다음미실행우선순위: 2025개발의동일신호사건에서기본/1봉지연실제가격경로를고정비교해큰지연성과차이를설명하고실제ETF/월/세션별귀인. 이후2025개발에서갭/거래량신호의겹침·역할별gross/비용·날짜별손익보완성을먼저계측. 근거가있을때노출을합치지않는상호배타라우팅을64예산안에사전등록. 현재실패파라미터의단순재탐색이나2026사후양수끼리합치기금지. 창의퀀트하위에이전트·단계선정최대8스트레스·최근3/6적합과다음달연속검증구분·실패보존을유지. 실매수4ETF/15%한도/보호조건/현금/실주문금지. 끝나면상태와인계갱신후expectedparent로저장.
