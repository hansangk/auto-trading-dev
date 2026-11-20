# Creative quant proposals — not implemented or tested this run

Execution-state correction takes priority; reuse the prior64candidate/22decision cache to isolate it. Do not describe these proposals as backtest results.

1. Overnight-gap absorption: gap vs prior-session ATR cutoff{.5,1.0}; completed first-bar close-location{.6,.8}.
2. Volume-confirmed auction pressure: completed signed-body×relative-volume lookback{6,12}; relative-volume trigger{1.5,2.0}.
3. Cross-market delayed response: completed Nasdaq→Bitcoin lag{1,2}; rolling standardized residual cutoff{.75,1.25}; prior24bar beta/normalizer only.
4. Failed-breakout rejection: prior-session level penetration{.25,.5}ATR; close back inside within{1,2}completed bars.

Each family2×2signal settings×hold{2,4}×target{2,3}=16, total64. Stop60bp/max15%ETF unchanged; actual TQQQ/SQQQ/IBIT/BITI buys and proper completed-bar timestamps. First preregister acceptance, then development screen and max8stress shortlist; recent3/6descriptive fit separate from preceding-window→next-month continuous-risk replay. No real orders.

Independent review: carry_peak=carry_all on adaptive samples isolates global drawdown memory as main observed difference. Early permanent halt can improve endpoint loss without improving prediction. Report halt date and trade counts.
