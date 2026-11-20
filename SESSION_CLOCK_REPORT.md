# Session-clock / leg attribution retry — 2026-11-16

## Decision and hypothesis
Reject session filtering as an improvement. Hypothesis tested: adverse intraday windows or a systematically losing hedge leg explain the anchor's weak cross-period results. Keep the dual-momentum24/.75 anchor, hold4, stop60bp/target3, joint exits and account sizing/risk controls fixed. Eight session filters plus anchor: 09:30 only, 09:30–10:30, 11:30–12:30, 13:30–15:30, exclude09:30, exclude15:30, 09:30–12:30, 12:30–15:30. All refer to New York order-entry bar starts, not signal-bar hours. Both long and short remain present.

The order clock is evaluated at simulated entry, independently of delayed signal age. Clock masks are mapped to the engine's signal slots using only timestamps, not future OHLCV. This avoids attributing a previous-day signal to the wrong entry session. Test coverage includes overnight and delayed-entry cases. No new risk/exposure changes.

## Run and selection
54 development evaluations (9 policies ×2025 H1/H2 ×base/cost2/delay1), then 12 diagnostic evaluations (top3+anchor ×three stresses): 66 account runs. At least20 rounds in every development scenario required for eligibility. Rank by minimum net return, then mean, then ID. Persist shortlist before2026. Promotion requires all six development scenarios positive and each better than anchor. No policy passes; selected late/open-only/second-half variants lose in all six development scenarios.

## Results
2026 = January1–November13, about10.5 months. Returns below are cumulative after modeled costs, not weekly.

| Policy | 2026 base | Costs doubled | Signal delayed1 bar | Base rounds | Recorded max drawdown |
|---|---:|---:|---:|---:|---:|
| Anchor | +8.44% | +4.02% | +5.83% |259|3.94%|
| Development rank1: late13:30–15:30 | +1.68% | +0.19% | +1.49% |107|1.05%|
| Rank2: open09:30 only | +3.67% | +2.30% | +3.73% |96|2.52%|
| Rank3: second half12:30–15:30 | +2.62% | +0.97% | +2.53% |117|1.11%|

Late-only base returns are -1.23% in2025 H1 and -0.62% in H2; worst development scenario -2.03%. Its lower drawdown is accompanied by far lower profit. No 2026 winner replaces the development-selected candidate after inspection.

## Leg-level failure diagnosis
Engine logging now includes each leg's gross account return contribution. Execution math is unchanged; remote engine was compared to the previous local version before publishing. Each round verifies long gross + short gross - total costs = net return. Full ledger compounding also reconciles to account output.

Anchor gross contribution and total cost expressed as percent of initial capital (additive realized P&L attribution; these are not standalone leg-strategy returns):

| Period | Long gross | Short gross | Costs deducted | Net account |
|---|---:|---:|---:|---:|
|2025 H1|-0.77%|+2.39%|1.97%|-0.34%|
|2025 H2|-3.54%|-0.12%|1.38%|-5.04%|
|2026|+9.23%|+2.89%|3.69%|+8.44%|

Thus the short side is not a consistently losing drag. Both legs make gross profit in2026;2025 H2 loses predominantly on the long side. Aggregate costs are material in every period. This does not justify dropping either leg: removing a leg would change exposure, exits, capital and subsequent trades.

Frozen-entry attribution reinforces the opportunity-cost issue. The late filter admits106 of the baseline's2026 rounds with a summed net account return of1.49 percentage points and rejects153 rounds summing6.71 points. Those sums are NOT compounded portfolio returns. Full late replay makes107 rounds and earns1.68%; it has different opportunities. In2025 H1 the rejected group has positive summed net return, while in H2 it loses. A fixed clock filter therefore cannot reliably separate winning from losing regimes across these periods. Baseline halts also limit the frozen opportunity sample.

## Retry-loop review / handoff
Improved this iteration: distinguish execution clock from signal clock under lag; record leg contributions before proposing changes to hedging; reconcile round and account accounting; preserve frozen-opportunity versus replay distinction. Retain rejected clock hypotheses so the next cycle does not repeat an unexplained time-window sweep.

Next hypothesis: the intraday forced exit and joint profit/stop rule may truncate favorable paths after valid entries. Keep entry signals fixed and compare a small predeclared set of exit policies, with explicit gap and holding-risk accounting, before combining more entry filters. Use available per-leg contribution data to assess whether improvements are due to exits rather than increasing risk. Do not disable protection or select parameters on reused2026. Independent new data remains necessary for promotion.

Reproduce: `PYTHONPATH=src python scripts/session_clock_retry.py`. Tests: `PYTHONPATH=src python -m unittest discover -s tests -q` (31 passed). Development/ranking/selection/diagnostic/leg-attribution/manifest files archived under `runs/session_clock_retry`; full diagnostic ledger is regenerated locally. Initial run stopped on timezone parsing in an assertion, corrected to UTC-aware parsing before the completed run; no partial results counted.

Limits: existing reused hourly Yahoo TQQQ/IBIT proxy data; no new independent sample, historical news/macro, real borrow availability or bid/ask simulation. Early-close calendar not fully audited. Entry bars are not uniformly one hour and close-based joint stops fill next open; drawdown/risk checks are round-boundary rather than intraround. No real orders. Cost2 and delay1 are separate scenarios.
