# Completed higher-timeframe structure retry — 2026-11-16

Decision: reject the new router as a return improvement. No risk or exposure increase. The existing trend anchor remains a research comparator, not a validated live strategy.

Prior failure: using recent trend losses to trigger mean reversion added losing trades. This experiment instead conditions entry on observed relative-price structure: 24-bar efficiency ratio, completed 2-hour direction, and optional prior-day direction. Mean reversion is permitted only at low efficiency with higher-timeframe disagreement/neutrality. Otherwise wait in cash.

Data: existing Yahoo hourly TQQQ/IBIT, IBIT as the Bitcoin proxy. New York :30 bars 09:30–15:30 only. Completed two-hour pairs are 09:30+10:30, 11:30+12:30, 13:30+14:30; each value is exposed only at the second bar's close. The final partial session block is excluded from two-hour indicators. Daily direction uses the prior session close only. Two-hour and daily directions use EMA(3)-EMA(8) on log(TQQQ/IBIT). Engine entries consume lagged signals. This is hourly/2-hour/daily confirmation, not one-minute execution.

Grid: dual momentum/breakout × window 12/24/48 × efficiency threshold 0.2/0.4 × daily confirmation on/off × range tactic on/off × hold 4/6 = 96 candidates, plus anchor. Mean reversion uses 24-bar z-score >=1.5 in magnitude and a closed-bar move toward the mean. Stops, target, exposure and risk controls remain unchanged from the joint-exit anchor. Both legs enter together. Risk checks/drawdown remain round-boundary, and joint stops trigger on closes and execute next open; no guaranteed stop price.

582 development backtests: 97 policies × 2025 H1/H2 × base/cost2/delay1. Rank by minimum of six development returns, then mean return, then ID. Save five selected IDs before 2026. 18 diagnostic runs: top five plus anchor × three stresses. Total 600 account backtests. All candidates have at most two positive development scenarios out of six; none passes cross-period/stress profitability.

## Results

2026 means January 1–November 13 (about 10.5 months). These are cumulative net returns, not weekly or annualized.

| Candidate | Development rank | 2026 base | Costs ×2 | Delay 1 bar | Base rounds |
|---|---:|---:|---:|---:|---:|
| Anchor | control | +8.44% | +4.02% | +5.83% | 259 |
| 8c4e395db900 | 1 | +0.61% | -0.31% | -0.86% | 67 |
| e2cf71bf5495 | 2 | +0.44% | -0.59% | -0.75% | 75 |
| 80f7ccddab0e | 3 | +1.05% | -0.05% | +0.14% | 79 |
| d141c44a283c | 4 | +1.15% | approximately 0.00% negative | -1.33% | 83 |
| c4b731c6fe2d | 5 | +0.87% | -0.33% | +0.25% | 87 |

The first-ranked policy uses dual momentum 12, efficiency >=0.4, 2-hour and prior-day agreement, no range entries and hold 6. It returns -1.29% in 2025 H1 and -1.64% in H2 at base costs; its worst development scenario is -1.99%. Its 2026 recorded drawdown is 1.55%, but lower participation is not a new profitable edge. Choosing rank 4 afterward because its 2026 return is highest would be diagnostic-period selection and is not done here.

## Failure review and continuation

Observed: stricter confirmations reduce rounds from 259 to 67 for the first-ranked candidate, while profit falls from 8.44% to 0.61%; doubled costs and delayed entries turn it negative. Adding the range tactic worsens the two comparable selected trend-only policies. Hypothesis: persistent higher-timeframe direction may be a late filter for a short-lived intraday relative-price opportunity. The engine closes positions within the same UTC date, so daily confirmation does not make this a multi-day strategy. This horizon mismatch needs controlled attribution, not another large unconstrained parameter sweep.

Next experiment should keep the anchor signal/exits fixed and separately ablate each filter on the same prospective entries, reporting admitted versus rejected opportunities and their cost/delay outcomes. Test whether higher-timeframe agreement adds incremental expectancy before rebuilding a router. Keep cash as a valid tactic. Do not enlarge positions to force the target return.

## Reproduction and limitations

`PYTHONPATH=src python scripts/structure_mtf_retry.py`

`PYTHONPATH=src python -m unittest discover -s tests -q`

28 tests pass, including every-prefix checks that truncated/future bars cannot alter prior higher-timeframe indicators and a routing separation check. Ledger compounding is checked in every account run. Manifest records grid, selection rule, and input SHA-256. Archived development/ranking/selection/diagnostic/manifest files are under `runs/structure_mtf_retry`. Full diagnostic ledger is generated locally by the script.

2025/2026 have been repeatedly reused; this is exploratory diagnosis, not independent holdout performance. No fresh market data were acquired this round. No historical news/macro feeds, true spot BTC execution, historical bid/ask, real borrow/locate constraints or complete early-close calendar audit. Bar delay is not always exactly one hour. Risk limits can be exceeded by gaps/intraround moves. Gross exposure was not increased and account protections were not removed.
