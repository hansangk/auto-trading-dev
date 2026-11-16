# Trend pause → mean-reversion switch retry (2026-11-16)

## Decision
Reject this switch as an improvement. The best development-ranked alternative underperforms cash during the paused state in every tested 2026 execution scenario. No deployment or risk-limit relaxation. The >10% cumulative net return goal remains unmet.

## Review → hypothesis → reconstruction
The prior shadow gate reduced 2025 H2 losses from -5.04% to -0.63%, but reduced 2026 profit from +8.44% to +6.49%. This retry asks whether the paused state contains a different opportunity: relative-price mean reversion rather than trend following. A losing trend strategy is not by itself evidence of mean reversion, so cash remains an explicit control.

The anchor is TQQQ versus IBIT dual momentum (window 24, threshold 0.75). Its hypothetical observer continues trading while the simulated account pauses. The last 24 completed observer net returns must average more than 1 bp for trend entries to remain enabled. Otherwise the alternative uses the z-score of log(TQQQ/IBIT), buying the relatively depressed leg and shorting the other. Grid: lookback 12/24/48 × threshold 1/1.5/2 standard deviations × with/without a completed-bar move toward the mean = 18 alternatives. This is a relative-price z-score experiment, not proof that these two assets form a stationary spread.

Both tactics retain identical sizing and exits to isolate the effect of entry switching: paired long/short, joint-close trigger, 60 bp stop parameter, 3× target, holding parameter 4. Existing account daily-loss, drawdown and streak controls stay in place. Tactics switch only for new entries; open trades are not forcibly reclassified.

## Selection and execution
18 alternatives + anchor + cash control × 2025 H1/H2 × base/costs doubled/one-bar signal delay = 120 development evaluations. Rank alternatives by their worst return across these six development scenarios, then mean return, then ID. Save the top three IDs before evaluating 2026. Three chosen alternatives + two controls × three execution scenarios = 15 diagnostic evaluations. Total: 135 account backtests plus three observer runs.

Observer halts are disabled solely to gather hypothetical completed outcomes; reported account results use unchanged risk limits. Outcome release is after the recorded exit bar, with the engine's additional signal lag. Each stress scenario regenerates its observer and therefore its gate. These are adaptive-policy stress tests, not frozen-entry cost calculations.

## Results
Returns below are cumulative net returns, not weekly or annualized. 2025 H1 is January–June; H2 July–December. 2026 is January 1–November 13, roughly 10.5 months.

| Policy | 2025 H1 base | 2025 H2 base | 2026 base | 2026 costs ×2 | 2026 delay 1 bar |
|---|---:|---:|---:|---:|---:|
| Always-on trend anchor | -0.34% | -5.04% | +8.44% | +4.02% | +5.83% |
| Pause into cash | -2.23% | -0.63% | +6.49% | +3.30% | +3.41% |
| Rank 1: MR 24 / z=2 / confirmation | -1.89% | -0.62% | +6.08% | +2.83% | +2.78% |
| Rank 2: MR 12 / z=1.5 / confirmation | -2.18% | -1.01% | +5.94% | +2.72% | +2.27% |
| Rank 3: MR 12 / z=2 / confirmation | -2.23% | -0.63% | +6.49% | +3.30% | +3.41% |

Rank 1's worst development scenario is -1.99%, modestly less negative than cash's -2.26%. However, all six development scenarios for this candidate lose. Its 2026 base win rate is 52.57%, with 175 paired rounds and 1.36% recorded drawdown. Rank 3 reproduces cash results: no alternative trades were executed in those evaluated scenarios, so its tie is not evidence of a second edge.

## Failure attribution
In the 2026 base run, rank 1 adds five mean-reversion rounds to the same 170 trend rounds. The five rounds contribute -401,649 in simulated P&L on a 100,000,000 initial account. Their sum of account-level net round returns is approximately -0.3862 percentage points; modeled costs are 0.0697 percentage points, leaving gross returns negative too (approximately -0.3165 points). These sums are attribution measures, not compounded portfolio returns. The problem is not merely fees: the proposed reversal entries themselves lose. Additional compounding effects explain the remainder of the portfolio difference.

Rank 2 adds eight mean-reversion rounds, also negative. Rank 3 is too selective to add trades. A weak trend signal does not reliably identify a profitable reversal regime. The small executed sample also prevents treating this result as a broad rejection of every mean-reversion method.

## Archive and continuation for Claude/Codex
Keep the anchor and cash gate as research controls; do not replace them with this switch. Next falsifiable hypothesis: route based on directly observed price structure (range/trend strength and completed higher-timeframe alignment) rather than inferring mean reversion from a trend strategy's losses. Evaluate each tactic standalone and its incremental trades against cash. A new dataset/time period is needed for independent confirmation; repeatedly tuning 2026 cannot provide it.

Reproduce from repository root:

```bash
PYTHONPATH=src python scripts/shadow_switch_retry.py
PYTHONPATH=src python -m unittest discover -s tests -q
```

Saved: `runs/shadow_switch_retry/development.csv`, `ranking.csv`, `selection.json`, `diagnostic.csv`, `manifest.json`. The script also regenerates `diagnostic_ledger.jsonl` locally (not uploaded). Manifest records the input data SHA-256 and exact grid. 26 tests pass, including signal-prefix invariance and exclusive tactic routing. Every run reconciles compounded ledger net returns to engine output.

## Material limits
- All periods are reused research data; 2026 is diagnostic, not an untouched holdout. The anchor and gate came from earlier inspected results. Ranking this grid on 2025 does not undo that contamination.
- Data are Yahoo hourly TQQQ/IBIT bars; IBIT is a US-hours ETF proxy, not 24-hour spot Bitcoin. No historical news, macro timestamp feeds or multiple-timeframe indicators are integrated in this experiment.
- New York :30 bars from 09:30 to 15:30 are retained as a heuristic. Early closes and the full exchange calendar are not fully audited. One-bar delay is not always one hour.
- Joint exits execute at the next open after the close-based trigger. Stops do not guarantee a price or zero loss. Account drawdown and risk checks are round-boundary metrics, not full intraround mark-to-market protection.
- No real borrow/locate availability, historical bid/ask or order-book execution model. Base commission/slippage are modeled assumptions. Doubled-cost and delayed-entry scenarios are separate, not combined.
