# 자동매매 · Claude Code 인계 목차

2026-11-15. 아래 5개 압축 파일을 같은 빈 디렉터리에 풀어 `src/`, `scripts/`, `tests/`, `configs/`, `runs/`, `data/`를 복원한다. `CLAUDE_HANDOFF_PROMPT.md`를 Claude Code에 그대로 붙여넣는다. Git 저장소로 가져가도 되지만 키 파일·환경변수를 커밋하지 않는다.

- `AUTOGRID_CODE_REPORTS_20261115.zip`: 모든 현지 Python 소스·설정·테스트·루트 Markdown 보고서 및 Claude 프롬프트.
- `AUTOGRID_RUNS_PART1_20261115.zip` 및 `AUTOGRID_RUNS_PART2_20261115.zip`: 현지 `runs`의 CSV/JSON/JSONL/Markdown 연구 산출물, 체크포인트, 순위. 둘 다 같은 디렉터리에 풀 것. 로그와 중복 ZIP은 제외.
- `AUTOGRID_DATA_PART1_20261115.zip` 및 `AUTOGRID_DATA_PART2_20261115.zip`: 현지 `data`의 CSV/JSON 원자료와 재집계 데이터. 두 파일 모두 같은 디렉터리에 풀 것. 업로드/키 폴더 제외.

동일하게 포장된 중복 과거 ZIP은 제외하고 압축 내용의 상대경로와 SHA-256을 각 ZIP의 `ARCHIVE_SHA256.json`에 넣었다. 압축 해제 후 `python -m pip install -e .`, `PYTHONPATH=src python -m unittest discover -s tests -q`. 테스트는 코드 기능 일부만 확인하며 투자 성과를 인증하지 않는다. 자동 주문은 포함되지 않는다.

연구의 읽는 순서: `STRATEGY_RESEARCH_LOG.md`, `CHRONOLOGICAL_RESEARCH_REPORT.md`, `REGIME_FAILURE_DIAGNOSTIC.md`, `MULTIFRAME_WIN_ARCHIVE.md`, `MULTIFRAME_CONFIRMATION_RETRY.md`, `PAIR_REGIME_RETRY_REPORT.md`, `BETA_JOINT_RETRY_REPORT.md`, `TECHNICAL_BREADTH_RETRY_REPORT.md`, `SELECTIVE_FAST_RETRY_REPORT.md`, `ANCHOR_REFINE_RETRY_REPORT.md`, `WIN64_PAYOFF_GRID_REPORT.md`, `PROFIT_PRIORITY_RETRY_REPORT.md`, `RETURN_TARGET_ASYMMETRIC_REPORT.md`, `DUAL_HORIZON_RETRY_REPORT.md`, `CONVEX_BREAKOUT_RETRY_REPORT.md`, `REGIME_REPRO_RETRY_REPORT.md`. 파일이 존재하지 않는 과거 보고는 해당 runs와 다른 ZIP의 이전 버전을 확인한다.

현재 데이터는 Alpaca IEX 무료 부분 봉, 2024-01-11~2026-11-13. 2026년은 이미 반복 열람되어 새 홀드아웃이 아니다. 독립적인 미래 수익이나 연30%를 확인하지 못했다. 최대 수익과 승률을 섞어 하나의 지표로 보지 말고 전체 기간·연도·주간 기간 및 비용 스트레스를 함께 보고하라.

직전 시도(새 regime): `runs/regime_repro_retry`: 240개 개발+개발 상위30개의 연도 분할60개+최근 기본/비용2배/1봉 지연90개=390회. 개발1위 최근 +0.691%, 비용2배 -1.277%, 지연 -0.673%; 2024/2025 모두 양수26/30, 2026 양수16/30. 결론은 보편적 재현성 미확보. 스크립트 `scripts/regime_repro_retry.py`.

중요한 오류 이력: 초기 엔진이 진입 봉 전체 거래량을 미리 알아보는 누출을 사용했으며 현재 `data.volume[i-1]`로 고쳤다. 기존 보고서 전부 수정 후 재산출된 것은 아니므로 오래된 성적표는 잠정치다. 각 실험의 실행 버전과 `runs` 입력을 비교하라. 15/60분의 마지막으로 완료된 봉 정렬과 시간대·조기폐장 처리도 점검하라.

비밀키는 의도적으로 제외했다. `upload/` 전체, 캐시, 대형 중복 기존 ZIP, 로그는 아카이브하지 않았다. GitHub 업로드 시 `.gitignore`를 검토하고 `upload/`이 추적되지 않도록 한다. 소스 아카이브의 경로 목록을 검증한 다음에만 공개 저장소로 올린다.
