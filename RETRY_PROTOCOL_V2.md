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
