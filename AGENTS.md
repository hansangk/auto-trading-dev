# AutoGrid agents
This repository is for backtesting research only. Preserve point-in-time features, realistic cost and risk assumptions, and reproduce results with saved configs and inputs. Do not call 2026 a pristine holdout. Do not print, read into reports, or commit keys in `upload/` or environment files. Tests: `PYTHONPATH=src python -m unittest discover -s tests -q`.

## Cross-runner research handoff
Before every retry (Codex or Claude), read RETRY_STATE.json, RESEARCH_HANDOFF.md if present, RETRY_PROTOCOL_V2.md and the latest report. A RUNNING state owned by another runner is a checkpoint, not permission to launch a duplicate or clear a lock; verify status and resume only with evidence. Publish with expected parent SHA, never force overwrite another runner. Each completed retry updates state and the single handoff index with exact paths, data hashes, rejected combinations, next hypothesis and what did not run.
User's retry scope: a creative quant subagent proposes varied strategy families and bounded parameter grids each cycle; cache prior failures, keep concise output and limited shortlist. Include actual TQQQ/SQQQ/IBIT/BITI ETF buys and recent3/6month exploratory suitability plus causal trailing-window selection followed by next-month replay. Reused2026 and recent fitted winners are never independent confirmation. Preserve full cost/risk and no-real-order constraints.

## Source-activity continuation guard (2026-11-19)
The completed source_activity_grid_20261119_0700 runner is immutable research. For any newly authorized reproduction, prepare a new output and use scripts/source_activity_resume_guard_20261119.py; never restart the original research phase directly. A partial continuous-month prefix without recoverable exact AccountState is a blocker, not permission to replay completed months. Distinguish Nasdaq cash with a fixed Bitcoin research background from whole-account cash and from actual zero-trade months.

## Availability audit continuation (2026-11-19)
For availability_ablation_20261119_0800, never invoke the raw research phase to bypass the storage-only amendment. Any newly authorized copy resumes through scripts/availability_guarded_research_20261119.py with exact prefix ledger hashes, complete carried AccountState and plan/schedule provenance. Unresolved intent/missing state blocks replay; do not clear manifests/locks. The completed run is verified with scripts/availability_verify_20261119.py. Report postround soft-threshold contacts separately from uninstrumented actual soft-skip counts.


## Frozen venue isolation continuation (2026-11-19)
The completed venue_flow_retry_20261119_1200 and venue_isolation_retry_20261119_1300 outputs are immutable. Do not bypass manifests, clear unresolved intents, or replay completed months. Read exact original hashes and verified full AccountState/ledger prefixes before any authorized isolated reproduction. Distinguish wholecash isolation fallback from Bitcoin cash plus Nasdaq background. Paired source/control intervention support is required in both arms; new isolation profit must not be inferred by splicing a prior full-account leg. Same cost/delay labels with different actual values are not cache hits.


## Calendar/holding continuation (2026-11-19)
venue_latency_retry_20261119_1400 is completed immutable research. Do not replay closed grids or completed monthly prefixes. Cache identity includes hold/exit settings plus actual cost/delay values; identical h/c score arrays are different execution hypotheses. Duration60/hold1 has no intermediate joint-close protection and is label-only. Known-calendar common support must not inspect future quotes. Read prospective_shadow_plan.json before later collection; only newly completed post-freeze observations with separately audited ETF/source vintages qualify as shadow, never rename reused2026 a pristine holdout. Missing original state/ledgers or unresolved intent blocks exact replay.


## Prospective shadow readiness (2026-11-19)
Readiness-only WAITING is not a completed backtest and has NA financial metrics. Use scripts/prospective_shadow_guard_20261119.py with the frozen plan Git blob and a freshly verified calendar/current UTC. The current official fallback calendar covers ONLY2026-11-19; later NY dates require extension. Complete calendar hours do not prove actual source/ETF price coverage. Do not force-close positions at a partial download's last bar, count crossing-freeze warmup as new evaluation, or replay closed grids while waiting. Actual shadow execution still needs separate versioned input audit and new FULL AccountState per model/control/stress; currentguard never grants terminal backtest by calendar alone.
