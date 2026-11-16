# Research retry protocol v2 — 2026-11-16

Purpose: improve both strategy and the experiment loop. A retry is a falsifiable research iteration, not another random seed or an attempt to fit a required return on reused data.

1. Read latest branch reports and running-job/checkpoint state. Do not overwrite another researcher's changes or launch duplicate jobs. Record the input code/data version, exact periods, universe and proxy instruments.
2. Review what failed, and what was ambiguous about the previous experiment. State one mechanism, an explicit comparator, a planned shortlist rule and rejection criteria before execution. Keep a record of hypotheses already rejected. Change the protocol only with a reason, not for novelty.
3. Separate entry, exit, sizing, routing and execution changes. If multiple must change, use ablations. Keep an anchored comparator and cash where appropriate. Never raise exposure or remove protections merely to clear a target.
4. For entry filters, perform BOTH frozen-opportunity attribution and full replay. Attribution partitions the baseline's existing rounds by the information at their original signal index. Its sums/means are not portfolio returns. Replay can change entry timing, risk halts and later opportunities, so report it separately. Baseline logs truncated by a drawdown halt do not represent all latent opportunities.
5. Use completed-bar information, explicit release timestamps and prefix-invariance tests for derived timeframes. Macro/news require actual point-in-time histories. Do not fabricate missing feeds.
6. Choose candidates using development periods and stress tests only. Freeze shortlist before diagnostics. A least-bad winner remains rejected if it fails predeclared criteria. A minimum-round threshold screens tiny samples; it does not prove statistical reliability. Include uncertainty and multiple-testing concerns before promotion.
7. Keep reused 2026 labeled diagnostic. A new filter cannot restore independence to a repeatedly inspected period. Independently confirm on untouched data before any deployment claim. Record costs, delays, borrow/execution limitations, drawdown measurement granularity and true holding horizon.
8. Report net cumulative return with exact dates, drawdown, rounds, win rate, profit factor, baseline delta, cost2 and delay1 separately. Never confuse percentage points with percentages or weekly with cumulative returns. Retain losing trials and raw ranking rather than only winners.
9. Save code/tests/config/manifest/results/report to the authorized development branch. Generated large ledgers can be reproducible local outputs if this is explicitly stated. Leave a concrete next hypothesis and a handoff identifying what ran and what did not.
10. Scheduled runs must report unavailable execution/data access truthfully; never substitute a plan for a completed backtest or claim an ongoing worker after it ended. Real orders remain out of scope.

Initial v2 adoption: `scripts/anchor_filter_audit.py` fixes anchor signal and exits, audits ten single filters plus anchor, requires at least 20 rounds per development scenario for diagnostic eligibility, and requires all six development scenarios positive and each better than anchor for its research promotion screen. These thresholds are this experiment's preregistered rules, not universal statistical assurance. Every candidate failed promotion.

Known protocol weakness to address next: ranking on worst return tends to prefer sparse participation. Pair return improvements with opportunity coverage and confidence, and add new independent periods. Also examine potential code-path effects: gated replay can find opportunities the frozen baseline never executed. Do not infer causality from raw aggregate return differences alone.

2026-11-16 holding retry evidence-based additions:
- Missing raw inputs must be recovered or explicitly versioned as a new data snapshot. Compare its hash before experiments. If different, rerun all comparators and separate data-revision differences from strategy deltas; never silently overwrite archived metrics. Pin the actual CSV when practical.
- Decompose any net improvement into gross leg contributions and costs, using capital-weighted ledger accounting. Fewer rounds and lower costs do not establish improved price-path capture. For exit changes, full replay changes future opportunities and is not a matched-entry causal comparison.
- Latest evidence/handoff: HOLDING_RETRY_REPORT_20261116.md; hold-only top1 rejected across development, despite slightly higher reused-2026 base profit.

2026-11-16 user scope correction — real inverse ETF implementation:
- Research universe now includes actual TQQQ/SQQQ/IBIT/BITI ETF buys. Distinguish a bearish signal, borrowed short sale, and purchase of an inverse ETF. Verify actual per-ticker ledger counts; a ticker present only in downloaded files is not evidence it was traded.
- Isolate instrument implementation from direction logic and timeframe filters. An inverse ETF price path is not the negative spot ETF return; replay actual bars with correct purchase sign and no short borrow charge. Keep capital caps and protective stops, acknowledge differing underlying sensitivity.
- Latest experiment and next handoff: INVERSE_ETF_RETRY_REPORT_20261116.md. All development candidates rejected; next is fixed-cap single-asset participation ablation, not yet run.

2026-11-16 single-asset participation evidence:
- Explicitly select nonzero buy roles for optional participation; do not let zero-score assets become phantom second holdings. Leave unused allocation in cash. Reconcile actual ETF order counts instead of assuming two orders per round.
- A profitable frozen subset in reused2026 is insufficient: report the same subset's development cost/delay stresses and the complete replay separately. Here single-opportunity subsets also failed development stresses, so do not repeat a simple single-only filter based on2026 alone.
- Latest handoff SINGLE_ASSET_RETRY_REPORT_20261116.md: 51 runs, all candidates rejected; next diagnose development forward-path decay as labels, not future information in signals.

2026-11-16 forward-label/exhaustion evidence:
- Compare horizons on a common entry cohort when possible; horizon-specific session truncation changes sample composition. Forward labels are development diagnostics, not entry features or account returns; keep paired actual inverse-ETF paths separate from protected replay.
- Worse original gross paths do not imply a profitable inverse strategy. Full/dual-only/single-only direction swaps were ablated; all rejected, with full inversion failing cost2 in both development halves and losing reused2026. Do not repeat this family without a new mechanism.
- Normalize archived period types before regression checks; report aborted attempts separately. Latest handoff: SIGNAL_DECAY_RETRY_REPORT_20261116.md (39 completed backtests). Next diagnose repeated entries into unchanged states before considering event-onset entries.

2026-11-16 event-onset retry evidence:
- A change in the signal vector is not necessarily new actionable information: disappearing roles alone must not trigger onset entries. Specify the event precisely and test both positive and negative cases.
- Entry gating need not reduce full-replay turnover when stops/cooldowns/account halts alter future opportunities. Report frozen admitted/rejected baseline rounds and full account costs/order counts separately; event gating here increased diagnostic replay costs and lost more money.
- Latest handoff EVENT_ENTRY_RETRY_REPORT_20261116.md:27 completed account runs, all rejected. Next measure exit reasons, gap effects and intraround marks with output-invariance logging before changing exits.

## User-approved broad/adaptive retry workflow (2026-11-16)
A retry now includes an explicitly delegated creative quant review, diverse strategy families and bounded parameter grids, followed by staged development/stress selection and ablations. Default budget64 candidates (4 families×16 parameter settings), at most8 shortlisted candidates; expand only with evidence. Cache old failures; do not substitute endless tiny filter tests for broad research.
Assess recent3/6month windows too: full-window best fits are exploratory in-sample rankings and may matter for regime research despite poor older performance. Separately choose from strictly preceding3/6months and replay the next calendar month, freezing choice before observing that month. Call this causal walk-forward research on reused data, not an untouched holdout. Minimum samples and cost/delay screens apply before selection; cash fallback when none qualifies.
Codex↔Claude coordination: read RETRY_STATE.json and RESEARCH_HANDOFF.md first, use a unique run ID, claim RUNNING with expected branch parent before work, save checkpoints, then COMPLETE with exact reproduction commands/data hashes/results and concrete next actions. Never replace someone else's newer commit or reset others' work. Summarize progress/results briefly; detailed grids and failures belong in CSV/JSON/report.

2026-11-17 continuous account correction:
- Monthly walk-forward portfolio claims must preserve account equity/peak, daily state, loss streak, cooldown and permanent kill across segments. AccountState is optional; use the same MarketData/global indices and flat session-boundary stops. Do not reset a halted account at calendar boundaries.
- Report ever_halted/first halt and actual trade counts, not only final-month killed status. Reduced terminal loss after earlier permanent halt is risk execution, not new alpha. Compare continuity components to isolate causes.
- Latest report CONTINUOUS_RISK_RETRY_REPORT_20261117.md:27 account scenarios/300engine calls;55tests. No new grid fitted in this execution-only correction. Next4creative families and64bounded settings are proposed in runs/continuous_risk_retry_20261117/quant_next_proposals.md, not implemented/tested.

2026-11-17 new OHLCV families:
- Count signal-time entry opportunities as an upper bound before spending attention on sparse-event winners. Recent3month gap/breakout cannot reach20rounds; keep ineligible rather than relax the sample screen.
- Monthly selection must exclude candidates that halted in training stresses, even when terminal return is positive. Use carried AccountState for deployment and preserve full decision/account checkpoints; cash/halted months are legitimate zero-trade outcomes.
- Latest MICROSTRUCTURE_GRID_RETRY_REPORT_20261117.md: new64grid,2074engine calls,65tests,all rejected. Next measure development gap/volume complementarity before any capped exclusive combination; no blindly repeated grid or diagnostic-fit promotion.

2026-11-17 matched-event and routing-identifiability evidence:
- Separate fixed signal-cohort delayed-entry paths (same exit versus equal holding duration) from full account replay. Effects differed by half-year; do not call delayed account improvements universal timing alpha.
- Count distinct development entry arrays and actual interventions vs a source union.64 nominal routing configs produced8entry arrays/32signal-exit configs; most memory routers changed0-2bars only, so their mechanics were not identified. Preserve aliases and do not pad them with new thresholds.
- Use matched-exit pure components and non-summed source-union controls. Cached controls require data/engine/component/config hashes. Latest COHORT_ROUTING_RETRY_REPORT_20261117.md:1050newcalls,77tests,no approvals. Next fixed-union role attribution plus turnover-matched cash controls; close routing hypothesis if support is sparse or non-replicated, rather than re-sweep it.
