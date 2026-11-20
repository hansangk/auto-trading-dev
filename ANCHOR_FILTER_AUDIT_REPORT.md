# Anchor-fixed filter audit retry — 2026-11-16

## Verdict
No candidate passes the predeclared promotion screen. This iteration improves failure diagnosis and the research protocol, not the achieved net return. Keep the +8.44% anchor as a diagnostic comparator; its 2025 losses still prevent calling it a robust strategy.

## Why retry logic changed
The preceding 96-candidate structure search changed signal window, gates, routing and holding horizon together. It could not isolate why returns deteriorated. Here the dual-momentum-24 anchor, threshold .75, holding parameter 4, joint exit, stop60bp/target3 and sizing/risk limits are held fixed. Ten filters are each applied separately: 2h agreement/opposition; prior-day agreement/opposition; both/either agreement; efficiency low (<.2), middle ([.2,.4)), high (>=.4), and non-high (<.4). Signals use completed 2h/prior-session daily data from `structure_mtf_retry.py` and execute with the normal lag.

Two distinct analyses run: (1) partition the anchor's fixed completed trades into admitted/rejected buckets; (2) replay the full account with each filtered signal. The first measures selection on the same opportunities; it is NOT an executable portfolio backtest. The second measures actual entry scheduling, costs, halts and compounding. Anchor drawdown halts truncate frozen ledgers, limiting that attribution to executed baseline opportunities.

## Selection and accounting
11 policies × two development halves of 2025 × base/cost2/delay1 = 66 account evaluations. Require at least 20 rounds in every development scenario for the diagnostic shortlist; rank eligible filters by worst return, then mean, then ID. Freeze the top three before 2026. Promotion screen requires all six development returns positive and each exceeding the anchor. No filter passes. Three shortlisted filters plus anchor × three stresses = 12 diagnostic evaluations, 78 total. Attribution also reuses anchor logs. Every run checks ledger compounding against engine output.

## Returns
All are cumulative net returns. 2026 is January 1–November 13, about 10.5 months, not a weekly result. 2025 H1/H2 are calendar half-years.

| Policy | 2025 H1 base | 2025 H2 base | 2026 base | 2026 cost2 | 2026 delay1 | 2026 base rounds |
|---|---:|---:|---:|---:|---:|---:|
| Anchor | -0.34% | -5.04% | +8.44% | +4.02% | +5.83% | 259 |
| Middle efficiency | +0.83% | -1.38% | +5.79% | +3.79% | +3.69% | 138 |
| Low efficiency | +1.85% | -2.02% | +0.40% | -0.25% | +0.87% | 47 |
| Opposite prior-day direction | +0.11% | -2.53% | +4.63% | +3.57% | +4.65% | 74 |

Middle efficiency is development rank 1, with a worst development return of -2.26% and only one positive scenario out of six. Its base 2026 win rate is 49.28%, recorded drawdown 2.62%. The opposite-prior-day variant retains nearly all its base profit under one-bar delay, but is negative in five development scenarios. No 2026 result is used to revise the shortlist.

## What was learned
In the fixed 2026 anchor ledger, middle efficiency admits 113 rounds with mean net account return 4.61 bp, versus 146 rejected rounds averaging +2.05 bp. It selects higher average expectancy but rejects profitable opportunities too. Full replay executes 138 rounds (not 113), showing why frozen attribution and executable results must not be conflated.

Opposite prior-day direction admits 74 baseline rounds averaging +6.34 bp and excludes 185 rounds averaging +1.89 bp in 2026. These are means on executed baseline rounds, not independent causal evidence. In 2025 H2 both admitted and rejected groups lose. Direction agreement across timeframes is therefore not an automatic quality guarantee. The findings are exploratory and period-dependent.

The 2h-opposition filter has the least-negative unqualified worst return (-0.82%) but only four rounds in its thinnest development scenario. The new minimum-round rule prevents promoting a sparse apparent winner. None of the ten filters meets the six-positive-scenario promotion rule.

## Next falsifiable hypothesis
Before constructing another router, separate relative-price opportunity from market-wide direction: audit the unchanged anchor's long and short contribution by completed broad trend/volatility state and time-of-session, with fixed entries and a replay control. Verify whether the missing return is caused by unproductive entries, an offsetting hedge leg, or the intraday forced exit. Do not infer an improved strategy solely from a better mean trade or remove the short leg without explicitly revisiting the paired mandate. Acquire untouched periods for confirmation before any promotion claim.

## Reproduction / handoff
`PYTHONPATH=src python scripts/anchor_filter_audit.py`

`PYTHONPATH=src python -m unittest discover -s tests -q`

30 tests pass, including partition conservation and neutral-direction behavior, plus existing higher-timeframe causality tests. Source hashes, exact rules and counts are in the manifest. Development, ranking, selection, diagnostic and opportunity-attribution CSVs are archived. Diagnostic trade ledger is regenerated locally. See `RETRY_PROTOCOL_V2.md` for the strengthened loop, also incorporated into the hourly scheduled task.

Limits: reused 2025/2026, no pristine holdout; hourly Yahoo TQQQ/IBIT ETF proxy, no fresh data or historical news/macro this round; no complete exchange-calendar/early-close audit or actual bid/ask/borrow-availability model. Stops execute after close-based triggers at the next open, not guaranteed prices. Intraround risk can exceed recorded round-boundary limits. Costs2 and delay1 are separate tests. No live orders and no risk/exposure increases.
