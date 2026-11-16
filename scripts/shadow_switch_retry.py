"""Development-ranked mean reversion during the trend observer's paused state."""
import hashlib
import itertools
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

import tqqq_bitcoin_pair_retry as base
from shadow_gate_retry import make_gate
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec

OUT = Path('runs/shadow_switch_retry')
STRESSES = [(1., 0), (2., 0), (1., 1)]


def reversion_signal(ratio, window, threshold, confirm):
    z = (ratio - ratio.rolling(window).mean()) / ratio.rolling(window).std().replace(0, np.nan)
    direction = -np.sign(z)
    active = z.abs() >= threshold
    if confirm:
        # Require price to have started moving toward its mean on the closed bar.
        active &= direction * ratio.diff() > 0
    value = direction.where(active, 0).fillna(0).to_numpy()
    return np.column_stack([value, -value]).astype(np.float32)


def switch_signal(trend, alternative, gate):
    return np.where(gate[:, None], trend, alternative)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    original, times, _ = base.context()
    local = times.tz_convert('America/New_York')
    keep = (local.minute == 30) & (local.hour >= 9) & (local.hour < 16)
    data = replace(original, timestamps=original.timestamps[keep], **{
        k: getattr(original, k)[keep] for k in ('open', 'high', 'low', 'close', 'volume')})
    times = times[keep]
    ratio = pd.Series(np.log(data.close[:, 0] / data.close[:, 1]))
    base.CACHE['x'] = data, times, ratio
    trend = base.pair_signal(dict(mode='dual_momentum', window=24, threshold=.75))
    spec = StrategySpec('shadow_switch', ('dual_momentum',), (1.,), 1, 1, 4, 60., 3., 2)
    observer_risk = replace(base.CFG.risk, daily_soft_loss=1., daily_hard_loss=1.,
                            max_drawdown=1., max_loss_streak=10**9)
    gates = {}
    for cost, delay in STRESSES:
        shadow = []
        run_backtest(data, trend, spec, base.CFG.execution, observer_risk, base.CFG.capital,
                     cost_multiplier=cost, signal_delay_bars=delay, exit_mode='joint_close', trade_log=shadow)
        gates[cost, delay] = make_gate(times, shadow, 24, .0001)

    candidates = [dict(id='anchor', kind='anchor'), dict(id='cash', kind='cash')]
    for window, threshold, confirm in itertools.product((12, 24, 48), (1., 1.5, 2.), (False, True)):
        candidates.append(dict(id=f'mr{window}_z{threshold:g}_c{int(confirm)}', kind='switch',
                               window=window, threshold=threshold, confirm=confirm))
    manifest = dict(candidates=candidates, selection='Rank switches by minimum return across six 2025 H1/H2 base/cost2/delay scenarios, then mean return, then ID; freeze top 3 before 2026.',
                    symbols=data.symbols, source_sha256=hashlib.sha256(Path('runs/tqqq_bitcoin_retry/yahoo_1h.csv').read_bytes()).hexdigest(),
                    risk='Account limits unchanged; observer-only halts disabled.', gate_window=24, gate_threshold=.0001,
                    warning='All periods reused research data; no pristine holdout. Hourly IBIT proxy, no news or multi-timeframe integration.')
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))

    bounds = {'2025H1': ('2025-01-01', '2025-07-01'), '2025H2': ('2025-07-01', '2026-01-01'),
              '2026': ('2026-01-01', '2026-11-14')}
    ledgers = []

    def evaluate(candidate, period, cost, delay, record=False):
        gate = gates[cost, delay]
        if candidate['kind'] == 'anchor':
            score = trend
        else:
            alt = np.zeros_like(trend) if candidate['kind'] == 'cash' else reversion_signal(
                ratio, candidate['window'], candidate['threshold'], candidate['confirm'])
            score = switch_signal(trend, alt, gate)
        a, b = [int(times.searchsorted(pd.Timestamp(x, tz='UTC'))) for x in bounds[period]]
        log = []
        result = run_backtest(data, score, spec, base.CFG.execution, base.CFG.risk, base.CFG.capital,
                             a, b, cost, delay, exit_mode='joint_close', trade_log=log)
        assert np.isclose(np.prod([1 + t['net_return'] for t in log]) - 1, result.total_return)
        if record:
            for t in log:
                state = 'trend' if candidate['kind'] == 'anchor' or gate[t['signal_index']] else 'reversion'
                ledgers.append(dict(candidate=candidate['id'], period=period, cost=cost, delay=delay, tactic=state, **t))
        return dict(id=candidate['id'], period=period, cost=cost, delay=delay, **result.to_dict())

    development = pd.DataFrame([evaluate(c, p, cost, delay) for c in candidates
                               for p in ('2025H1', '2025H2') for cost, delay in STRESSES])
    development.to_csv(OUT / 'development.csv', index=False)
    ranked = development[~development.id.isin(['anchor', 'cash'])].groupby('id').agg(
        worst_return=('total_return', 'min'), mean_return=('total_return', 'mean'),
        positive_scenarios=('total_return', lambda s: int((s > 0).sum()))).reset_index()
    ranked = ranked.sort_values(['worst_return', 'mean_return', 'id'], ascending=[False, False, True])
    ranked.to_csv(OUT / 'ranking.csv', index=False)
    selected_ids = ranked.head(3).id.tolist()
    # Persist selection before computing any 2026 candidate result.
    (OUT / 'selection.json').write_text(json.dumps(dict(selected_ids=selected_ids), indent=2))
    selected = [c for c in candidates if c['id'] in selected_ids + ['anchor', 'cash']]
    diagnostic = pd.DataFrame([evaluate(c, '2026', cost, delay, True) for c in selected for cost, delay in STRESSES])
    diagnostic.to_csv(OUT / 'diagnostic.csv', index=False)
    pd.DataFrame(ledgers).to_json(OUT / 'diagnostic_ledger.jsonl', orient='records', lines=True)
    manifest.update(development_evaluations=len(development), diagnostic_evaluations=len(diagnostic), observer_runs=3)
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(ranked.head(3).to_string(index=False))
    print(diagnostic[['id', 'cost', 'delay', 'total_return', 'max_drawdown', 'rounds', 'win_rate']].to_string(index=False))


if __name__ == '__main__':
    main()
