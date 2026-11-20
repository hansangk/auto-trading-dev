# Completed-trade shadow gate retry — 2026-11-16

## Verdict
The gate reduces losses in the failing period but does not establish positive expectancy across periods. Keep the joint-exit anchor as a research comparator; do not promote either method to live trading. The >10% return objective remains unmet with the retained risk controls.

## Review and hypothesis
Separate-leg exits previously destroyed the relative-value trade. Joint exits improved 2026 but lost approximately 5% in 2025 H2. Volatility balancing reduced both losses and profits. This experiment tests a different failure mechanism: keep a hypothetical observer trading while the account pauses, and resume actual simulated entries only when recent completed observer rounds have positive mean net return. This avoids a permanently paused strategy having no new observations with which to recover.

## Method
TQQQ/IBIT hourly Yahoo bars; IBIT is the Bitcoin ETF proxy, not 24-hour spot BTC. Dual momentum window 24, threshold 0.75; paired long/short entries, joint exit, 60 bp stop parameter, target multiple 3, holding parameter 4. Existing account risk limits and sizing are unchanged. Observer-only risk halts are disabled to continue gathering hypothetical outcomes; its equity is not reported as account performance.

Six policies (always-on; 6/12/24 completed rounds with mean >0; 12/24 with mean >0.0001) × two periods × three execution assumptions = 36 account evaluations plus three observer runs. The 0.0001 threshold is one basis point of account-level net round return, not asset price return. Completed outcomes are released after their recorded end bar; the engine applies its normal signal lag as well. Historical observer trades warm up the gate before each reporting period; account equity resets for each period.

## Results
All returns are cumulative, net of modeled costs. 2025 H2: July 1–December 31. 2026: January 1–November 13, approximately 10.5 months. Costs ×2 and delay are separate scenarios, not a combined stress.

| Policy | 2025 H2 base | 2025 costs ×2 | 2025 delay 1 bar | 2026 base | 2026 costs ×2 | 2026 delay 1 bar |
|---|---:|---:|---:|---:|---:|---:|
| Always-on anchor | -5.04% | -5.17% | -5.00% | +8.44% | +4.02% | +5.83% |
| Last 6, mean >0 | -1.58% | -2.44% | -0.95% | +6.19% | +3.40% | +2.46% |
| Last 12, mean >0 | -1.81% | -2.15% | -1.85% | +7.14% | +2.25% | +0.74% |
| Last 24, mean >0 | -2.98% | -0.83% | -1.08% | +7.48% | +3.32% | +3.87% |
| Last 12, mean >1 bp | -1.79% | -1.83% | -1.60% | +5.50% | +1.12% | +0.25% |
| Last 24, mean >1 bp | -0.63% | -0.49% | -0.14% | +6.49% | +3.30% | +3.41% |

The last-24 / 1 bp policy has the least-negative worst stress return in 2025 H2 among these candidates. Its base 2026 result is +6.49%, round win rate 53.53%, profit factor 1.47, 170 rounds and 1.36% recorded drawdown, versus the anchor's +8.44%, 50.58%, 259 rounds and 3.94% recorded drawdown. In 2025 H2 it trades only 11 rounds (three under doubled costs), so the smaller loss is largely reduced participation and is not evidence of a profitable replacement strategy. Every policy loses in 2025 H2 under every tested assumption.

## Interpretation and next falsifiable test
The gate is useful as a candidate risk overlay, but recent profitability is a lagging condition and cannot create an edge when the underlying regime is unfavorable. It also skips profitable recoveries and changes entry timing. Test a separate, predeclared mean-reversion tactic for the paused state against a cash alternative; select only on development windows, lock it, and validate on untouched data. Do not optimize the repeatedly inspected 2026 sample until it crosses a target.

## Limits and verification
- These are exploratory reused periods, not independent out-of-sample proof. The anchor itself was informed by prior 2026 results.
- Shadow outcomes are hypothetical completed trades, not the account's realized executions. Stress runs recompute observer gates, so stress differences include policy adaptation.
- Input filtering keeps New York :30 timestamps from 09:30 through 15:30. This is not a complete exchange-calendar/early-close audit. One bar is not always exactly one hour.
- Historical news, sentiment and macro release timestamps are not integrated. This experiment does not implement the requested multi-timeframe strategy.
- Account risk checks and recorded drawdown are at round boundaries; intraround losses, gaps, borrow availability and real fills can differ. Joint close triggers execute at the next open, not instantly at a guaranteed stop price.
- 24 unit tests pass, including a test that changing a future observer outcome cannot change prior gate values. Every account run reconciles compounded round returns to its result.

Reproduce: `PYTHONPATH=src python scripts/shadow_gate_retry.py`; tests: `PYTHONPATH=src python -m unittest discover -s tests -q`.
Archived files: script, gate test, result CSV, and run manifest. The full shadow ledger is generated locally by the script.
