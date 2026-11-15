"""Past-only monthly regime specialist selection; retrospective research."""
import json
from pathlib import Path
from itertools import product
import numpy as np
import pandas as pd
from tqqq_bitcoin_pair_retry import context, pair_signal, CFG
from autogrid.strategy import StrategySpec
from autogrid.engine import run_backtest

OUT = Path('runs/dynamic_tactics')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data, times, ratio = context()
    # Only completed hourly prices; engine executes from next bar.
    ret = ratio.diff()
    vol = ret.rolling(40).std().shift(1).replace(0, np.nan)
    trend = ratio.diff(16) / (vol * 4)
    shock = ret.abs() / vol
    states = np.where(trend > 1, 1, np.where(trend < -1, 2, 0))
    states = np.where(shock > 2.5, 3, states)
    states = np.where(vol.isna(), -1, states)
    specialists = []
    for mode, window, threshold, stop, hold in product(
        ('momentum', 'mean_reversion', 'dual_momentum', 'macd'),
        (6, 24), (.75, 1.5), (60., 150.), (2, 6)
    ):
        x = dict(mode=mode, window=window, threshold=threshold, stop=stop, hold=hold, tp=3.)
        sid = str(len(specialists))
        spec = StrategySpec(sid, (mode,), (1.,), 1, 1, hold, stop, 3., 2)
        specialists.append((x, spec, pair_signal(x)))
    months = pd.date_range('2025-07-01', '2026-11-01', freq='MS', tz='UTC')
    schedules = {n: np.full(len(times), -1, dtype=int) for n in (5, 15)}
    audit = []
    for month in months:
        start = int(times.searchsorted(month - pd.Timedelta(days=180)))
        end = int(times.searchsorted(month))
        next_end = int(times.searchsorted(month + pd.offsets.MonthBegin(1)))
        # All training trades close strictly before the decision timestamp.
        for state in range(4):
            metrics = []
            for idx, (x, spec, score) in enumerate(specialists):
                gated = score.copy()
                gated[states != state] = 0
                r = run_backtest(data, gated, spec, CFG.execution, CFG.risk, CFG.capital, start, end, 2., 0)
                metrics.append((r.total_return - .5 * r.max_drawdown, idx, r))
            for minimum, schedule in schedules.items():
                eligible = [v for v in metrics if v[2].rounds >= minimum and v[2].total_return > 0 and v[2].profit_factor > 1.1]
                choice = max(eligible, key=lambda v: (v[0], -v[1])) if eligible else None
                if choice:
                    schedule[end:next_end][states[end:next_end] == state] = choice[1]
                audit.append(dict(month=str(month), state=state, minimum=minimum,
                                  specialist=choice[1] if choice else None,
                                  train_return=choice[2].total_return if choice else None,
                                  train_rounds=choice[2].rounds if choice else 0))
        print('selected', month.strftime('%Y-%m'), flush=True)
    mapping = {i: (s, score) for i, (_, s, score) in enumerate(specialists)}
    results = []
    for minimum, schedule in schedules.items():
        for period, first, last in [('2025H2','2025-07-01','2026-01-01'), ('2026','2026-01-01','2026-11-14')]:
            for cost, delay in [(1.,0),(2.,0),(1.,1)]:
                r = run_backtest(data, specialists[0][2], specialists[0][1], CFG.execution, CFG.risk, CFG.capital,
                                 int(times.searchsorted(pd.Timestamp(first,tz='UTC'))),
                                 int(times.searchsorted(pd.Timestamp(last,tz='UTC'))), cost, delay,
                                 regime_plan=(schedule, mapping))
                results.append(dict(minimum=minimum, period=period, cost=cost, delay=delay, **r.to_dict()))
    pd.DataFrame(results).to_csv(OUT/'results.csv', index=False)
    pd.DataFrame(audit).to_csv(OUT/'decisions.csv', index=False)
    (OUT/'specialists.json').write_text(json.dumps([x for x,_,_ in specialists],indent=2))
    print(pd.DataFrame(results)[['minimum','period','cost','delay','total_return','win_rate','rounds']].to_string(index=False))

if __name__ == '__main__':
    main()
