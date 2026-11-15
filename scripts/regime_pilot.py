"""Exploratory regime-switching pilot; previously inspected data is not holdout."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.features import FeatureCache
from autogrid.random_validation import _parse_specs
from autogrid.strategy import build_score


def main():
    data = load_market_data('data/alpaca_iex/market_final_45m.csv')
    cfg = load_config('configs/recent_win_search.yaml')
    specs = _parse_specs('runs/recent_win_45m/top30.csv')
    by_id = {s.strategy_id: s for s in specs}
    chosen = ['742431489569', 'ce51a1f4723f']
    cache = FeatureCache(data)
    plans = {i: (by_id[s], build_score(by_id[s], cache)) for i, s in enumerate(chosen)}
    spy = pd.Series(data.close[:, data.symbols.index('SPY')])
    ret = spy.pct_change(20)
    vol = spy.pct_change().rolling(20).std()
    # Fixed, predeclared illustration; no fitted thresholds and no use of future bars.
    regimes = np.where((ret.abs() > .01) & (vol < .012), 0,
                       np.where((ret.abs() <= .01) & (vol < .012), 1, -1))
    regimes[:60] = -1
    ts = pd.to_datetime(data.timestamps, utc=True)
    rows = []
    for label, start, stop in [('2024', '2024-01-01', '2025-01-01'),
                               ('2025', '2025-01-01', '2026-01-01'),
                               ('2026', '2026-01-01', '2026-11-14')]:
        a = int(np.searchsorted(ts, pd.Timestamp(start, tz='UTC')))
        b = int(np.searchsorted(ts, pd.Timestamp(stop, tz='UTC')))
        for name, plan in [('switch', (regimes, plans)), ('fixed_0', None), ('fixed_1', None)]:
            spec, score = plans[1 if name == 'fixed_1' else 0]
            for cost in (1.0, 2.0):
                result = run_backtest(data, score, spec, cfg.execution, cfg.risk, cfg.capital,
                                      a, b, cost_multiplier=cost, regime_plan=plan)
                rows.append({'period': label, 'strategy': name, 'cost_multiplier': cost, **result.to_dict()})
    out = Path('runs/regime_pilot'); out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / 'results.csv', index=False)
    (out / 'manifest.json').write_text(json.dumps({'symbols': list(data.symbols), 'strategy_ids': chosen,
        'warning': 'exploratory; previously inspected strategies and periods; not independent OOS',
        'regime': '20-bar SPY absolute return > 1% and 20-bar volatility < 1.2%: strategy 0; otherwise strategy 1 when volatility < 1.2%; otherwise cash',
        'execution': 'regime and score from completed prior bar; open position held until strategy exit; no mid-round switch'}, indent=2))
    print(pd.DataFrame(rows)[['period','strategy','cost_multiplier','total_return','win_rate','rounds','max_drawdown']].to_string(index=False))


if __name__ == '__main__':
    main()
