"""Frozen 2025 union-role falsification; additive ledger amounts, not a portfolio.

The baseline's realized stops, entries, sizing and equity path remain fixed. A
replacement ETF's unobserved return is never inferred by negating an ETF return.
Conditional permutations use fitted within-month retained counts; they are an
ex-post information diagnostic, not implementable cash policies or causal tests.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from cohort_routing_controls_20261117 import source_union
from cohort_routing_signals_20261117 import _prior_efficiency, signals
from inverse_etf_retry_20261116 import CFG
from microstructure_signals_20261117 import signals as component_signals

SEED = 20261117
INPUT = Path('runs/inverse_etf_retry_20261116')
OUT = Path('runs/role_information_retry_20261117')
SOURCE_HASH = 'e0dea9e76a9c7f57b5d3791912e85473a29f5d31d4743783cf17b29a95c09fbd'
ROLES = {'equity': ('TQQQ', 'SQQQ'), 'bitcoin': ('IBIT', 'BITI')}
STRATA = ['half', 'month', 'role', 'signal_hour_ny']
AMOUNTS = ['gross_amount', 'cost_amount', 'net_amount']
WARNING = ('Frozen union-ledger additive capital-weighted amounts, not routed '
           'portfolio returns or a causal effect. Baseline stops/equity/halt truncate '
           'opportunities. Replacement ETF returns are unobserved. Exact-count '
           'conditional cash selections are fitted ex post; exchangeability is '
           'unproved. Reused 2025 is development; 2026 is excluded. No real orders.')


def _context(i, role_index, times, efficiency):
    t = times[i].tz_convert('America/New_York')
    e = float(efficiency[i, role_index])
    # Exact frozen floating-point router boundaries are .4-.15 and .4+.15.
    bucket = ('missing' if not np.isfinite(e) else 'low_le_0.25' if e <= .4-.15
              else 'high_ge_0.55' if e >= .4+.15 else 'middle_0.25_0.55')
    return dict(signal_time=str(times[i]), signal_date=t.strftime('%Y-%m-%d'),
                half=f'{t.year}H{1 if t.month <= 6 else 2}',
                month=t.strftime('%Y-%m'), signal_hour_ny=int(t.hour),
                prior_efficiency=e, efficiency_bin=bucket)


def _status(actual, scores, symbols, role_symbols):
    chosen = [s for s in role_symbols if scores[symbols.index(s)] != 0]
    if len(chosen) > 1:
        raise ValueError('Candidate must select at most one actual ETF per role')
    return ('suppressed' if not chosen else 'retained' if chosen[0] == actual
            else 'replacement'), (chosen[0] if chosen else '')


def decompose_union_legs(log, candidate_scores, times, prior_efficiency, symbols):
    """Partition executed baseline actual-ETF roles at original signal_index.

    Gross and costs are return contributions times original pre-round equity.
    Joint round costs allocate proportional to actual role weights. Replacement
    rows retain the original ETF PnL only; selected_* is zero, never inverted.
    """
    times = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    symbols = tuple(symbols)
    rows = []
    for round_id, t in enumerate(log):
        i = int(t['signal_index'])
        base = float(t['equity'])-float(t['pnl'])
        weights = {s: float(w) for s, w in zip(t['bought_symbols'], t['bought_weights'])}
        total_weight = sum(weights.values())
        if total_weight <= 0:
            raise ValueError('Executed round must have positive actual weights')
        round_rows = []
        for j, (role, role_symbols) in enumerate(ROLES.items()):
            actual = [s for s in role_symbols if s in weights]
            if len(actual) > 1:
                raise ValueError('Expected at most one actual ETF per baseline role')
            if not actual:
                continue
            actual = actual[0]
            legacy = 'long' if role == 'equity' else 'short'
            weight = weights[actual]
            gross = float(t[f'{legacy}_gross_return'])
            cost = float(t['cost_return'])*weight/total_weight
            status, chosen = _status(actual, candidate_scores[i], symbols, role_symbols)
            row = dict(round_id=round_id, signal_index=i, entry=t['entry'], end=t['end'],
                       role=role, actual_etf=actual, candidate_etf=chosen,
                       status=status, retained=status == 'retained', weight=weight,
                       base_equity=base, invested_amount=base*weight,
                       gross_return_contribution=gross, cost_return_contribution=cost,
                       net_return_contribution=gross-cost,
                       gross_amount=base*gross, cost_amount=base*cost,
                       net_amount=base*(gross-cost),
                       **_context(i, j, times, prior_efficiency))
            for k in AMOUNTS:
                row['selected_'+k] = row[k] if row['retained'] else 0.
            round_rows.append(row)
        if not np.isclose(sum(r['gross_return_contribution'] for r in round_rows), t['gross_return']):
            raise AssertionError('Role gross accounting failed')
        if not np.isclose(sum(r['cost_return_contribution'] for r in round_rows), t['cost_return']):
            raise AssertionError('Role cost accounting failed')
        if not np.isclose(sum(r['net_amount'] for r in round_rows), t['pnl']):
            raise AssertionError('Capital-weighted role PnL accounting failed')
        rows.extend(round_rows)
    return pd.DataFrame(rows)


def conditional_cash_permutations(frame, draws=2000, seed=SEED):
    """Exact retained-order/weight matching; no return or seed optimization.

    Returns draw totals (all/per role), support by stratum and expected row-level
    contributions used for paired day-block contrasts. Distinct actual weights
    are conditioned on within the requested strata, ensuring exact weight sums.
    Zero/all retained strata have no conditional variation and remain reported.
    """
    f = frame.reset_index(drop=True).copy()
    if f.empty:
        raise ValueError('No executed baseline roles')
    rng = np.random.default_rng(seed)
    chosen = np.zeros((draws, len(f)), dtype=bool)
    support = []
    f['conditional_probability'] = 0.
    for keys, g in f.groupby(STRATA+['weight'], sort=True, dropna=False):
        idx = g.index.to_numpy()
        n, k = len(idx), int(g.retained.sum())
        f.loc[idx, 'conditional_probability'] = k/n
        for d in range(draws):
            chosen[d, rng.choice(idx, k, replace=False)] = True
        support.append(dict(zip(STRATA+['weight'], keys), opportunities=n, retained=k,
                            suppressed=int((g.status == 'suppressed').sum()),
                            replacement=int((g.status == 'replacement').sum()),
                            retained_weight=float(g.loc[g.retained, 'weight'].sum()),
                            varying=0 < k < n, low_support=n < 20,
                            retained_fraction=k/n))
    records = []
    for role in ['all']+sorted(f.role.unique().tolist()):
        idx = np.arange(len(f)) if role == 'all' else np.flatnonzero(f.role.eq(role))
        mask = chosen[:, idx]
        record = pd.DataFrame(dict(draw=np.arange(draws), role=role,
                                   orders=mask.sum(axis=1),
                                   weight=mask @ f.weight.to_numpy()[idx],
                                   invested_amount=mask @ f.invested_amount.to_numpy()[idx]))
        for amount in AMOUNTS:
            record[amount] = mask @ f[amount].to_numpy()[idx]
        observed = f.iloc[idx]
        assert (record.orders == observed.retained.sum()).all()
        np.testing.assert_allclose(record.weight,
                                   observed.loc[observed.retained, 'weight'].sum())
        records.append(record)
    for amount in AMOUNTS:
        f['expected_'+amount] = f.conditional_probability*f[amount]
        f['contrast_'+amount] = f['selected_'+amount]-f['expected_'+amount]
    return pd.concat(records, ignore_index=True), pd.DataFrame(support), f


def session_block_bootstrap(frame, draws=2000, seed=SEED, block_days=1):
    """Paired fixed-ledger contrast, resampling whole NY sessions jointly.

    block_days=5 uses circular runs of five observed trading sessions; n sessions
    are drawn per replicate. Counts/weights are exact in permutations, not in
    resampled days. Fixed fitted stratum probabilities are not re-estimated.
    """
    if block_days < 1:
        raise ValueError('block_days must be positive')
    rng = np.random.default_rng(seed)
    days = sorted(frame.signal_date.unique())
    n = len(days)
    if not n:
        raise ValueError('No sessions')
    starts = rng.integers(0, n, size=(draws, int(np.ceil(n/block_days))))
    indices = ((starts[:, :, None]+np.arange(block_days)) % n).reshape(draws, -1)[:, :n]
    rows = []
    for role in ['all']+sorted(frame.role.unique().tolist()):
        g = frame if role == 'all' else frame[frame.role.eq(role)]
        for amount in AMOUNTS:
            daily = g.groupby('signal_date')['contrast_'+amount].sum().reindex(days, fill_value=0).to_numpy()
            totals = daily[indices].sum(axis=1)
            rows.append(dict(role=role, metric=amount, block_days=block_days,
                             sessions=n, estimate=float(daily.sum()),
                             lower_95=float(np.quantile(totals, .025)),
                             upper_95=float(np.quantile(totals, .975)),
                             bootstrap_mean=float(totals.mean()), draws=draws, seed=seed))
    return pd.DataFrame(rows)


def _group_summaries(frame):
    results = []
    for keys in (['half', 'stress', 'role', 'status'],
                 ['half', 'stress', 'role', 'efficiency_bin', 'status'],
                 ['half', 'stress', 'month', 'role', 'status']):
        g = frame.groupby(keys, dropna=False).agg(
            orders=('weight', 'size'), weight=('weight', 'sum'),
            invested_amount=('invested_amount', 'sum'),
            gross_amount=('gross_amount', 'sum'), cost_amount=('cost_amount', 'sum'),
            net_amount=('net_amount', 'sum')).reset_index()
        g['grouping'] = '|'.join(keys)
        results.append(g)
    return pd.concat(results, ignore_index=True)


def main(output=OUT):
    output = Path(output)
    if (output/'fixed_role_manifest.json').exists():
        raise SystemExit('Attribution already completed; use a fresh output path')
    output.mkdir(parents=True, exist_ok=True)
    actual_hash = hashlib.sha256((INPUT/'market.csv.gz').read_bytes()).hexdigest()
    if actual_hash != SOURCE_HASH:
        raise ValueError('Pinned input hash mismatch')
    # Preregistered fixed design is written before any engine calls.
    design = dict(source_union='gap(.5,.6), volume(6,2), per-role gap priority',
                  candidate='daily_regime(.4,.15), hold4,target3,stop60', seed=SEED,
                  permutation_draws=2000, bootstrap_draws=2000,
                  conditional_strata=STRATA+['actual_weight'], bootstrap_blocks=[1, 5],
                  futility='Fail unless each role >=20 retained in each half/stress, '
                  'net advantage vs conditional permutation mean >0 in all six '
                  'half/stress cells, and session and 5-day block net CI lower>0 '
                  'in every cell. No promotion without untouched data.', warning=WARNING)
    (output/'fixed_role_design.json').write_text(json.dumps(design, indent=2))
    data = load_market_data(INPUT/'market.csv.gz', ['TQQQ', 'SQQQ', 'IBIT', 'BITI'])
    times = pd.DatetimeIndex(pd.to_datetime(data.timestamps, utc=True))
    gap = component_signals(data, times, dict(family='gap_absorption', p1=.5, p2=.6))
    volume = component_signals(data, times, dict(family='volume_pressure', p1=6, p2=2))
    union = source_union(gap, volume)
    candidate = signals(data, times, dict(family='daily_regime', p1=.4, p2=.15))
    source_indices = [data.symbols.index(s) for s in ('TQQQ', 'IBIT')]
    efficiency = _prior_efficiency(*[getattr(data, k)[:, source_indices]
                                    for k in ('open', 'high', 'low', 'close')], times)
    ledgers, permutations, supports, bootstraps, evaluations, decisions, opportunities = [], [], [], [], [], [], []
    for half, a, b in [('2025H1', '2025-01-01', '2025-07-01'),
                       ('2025H2', '2025-07-01', '2026-01-01')]:
        start, stop = [int(times.searchsorted(pd.Timestamp(t, tz='UTC'))) for t in (a, b)]
        for i in range(start, stop):
            for j, (role, role_symbols) in enumerate(ROLES.items()):
                active = [s for s in role_symbols if union[i, data.symbols.index(s)] != 0]
                if active:
                    status, chosen = _status(active[0], candidate[i], data.symbols, role_symbols)
                    opportunities.append(dict(signal_index=i, role=role, actual_etf=active[0],
                                              candidate_etf=chosen, status=status,
                                              **_context(i, j, times, efficiency)))
        for stress, cost, delay in [('base', 1., 0), ('cost2', 2., 0), ('delay1', 1., 1)]:
            log = []
            result = run_backtest(data, union, StrategySpec('frozen_union', (), (), 1, 1, 4, 60, 3, 2),
                                  CFG.execution, CFG.risk, CFG.capital, start, stop, cost, delay,
                                  exit_mode='joint_close', funded_pair=True,
                                  funded_allow_single=True, trade_log=log)
            np.testing.assert_allclose(np.prod([1+t['net_return'] for t in log])-1, result.total_return)
            legs = decompose_union_legs(log, candidate, times, efficiency, data.symbols)
            legs['stress'] = stress
            draw, support, enriched = conditional_cash_permutations(legs)
            boot = pd.concat([session_block_bootstrap(enriched, block_days=d) for d in (1, 5)], ignore_index=True)
            for frame in (draw, support, boot):
                frame['half'], frame['stress'] = half, stress
            ledgers.append(enriched); permutations.append(draw); supports.append(support); bootstraps.append(boot)
            evaluations.append(dict(half=half, stress=stress, cost=cost, delay=delay,
                                    start=a, end_exclusive=b, **result.to_dict()))
            counts = legs[legs.retained].groupby('role').size().reindex(ROLES, fill_value=0)
            actual = float(legs.selected_net_amount.sum())
            random = draw[draw.role.eq('all')].net_amount
            ci = boot[boot.role.eq('all') & boot.metric.eq('net_amount')]
            advantage = actual-float(random.mean())
            decisions.append(dict(half=half, stress=stress, retained_equity=int(counts.equity),
                                  retained_bitcoin=int(counts.bitcoin), selected_net_amount=actual,
                                  permutation_mean=float(random.mean()), incremental_net_amount=advantage,
                                  permutation_upper_tail_p=(1+int((random >= actual).sum()))/(len(random)+1),
                                  permutation_lower_95=float(random.quantile(.025)),
                                  permutation_upper_95=float(random.quantile(.975)),
                                  varying_strata=int(support.varying.sum()),
                                  total_strata=len(support),
                                  varying_opportunities=int(support.loc[support.varying, 'opportunities'].sum()),
                                  low_support_strata=int(support.low_support.sum()),
                                  session_ci_lower=float(ci[ci.block_days.eq(1)].lower_95.iloc[0]),
                                  dayblock5_ci_lower=float(ci[ci.block_days.eq(5)].lower_95.iloc[0]),
                                  passes=bool(counts.min() >= 20 and advantage > 0 and (ci.lower_95 > 0).all())))
    full = pd.concat(ledgers, ignore_index=True)
    frames = {'fixed_role_ledger.csv': full, 'fixed_role_groups.csv': _group_summaries(full),
              'fixed_role_permutation_draws.csv': pd.concat(permutations, ignore_index=True),
              'fixed_role_permutation_support.csv': pd.concat(supports, ignore_index=True),
              'fixed_role_bootstrap.csv': pd.concat(bootstraps, ignore_index=True),
              'fixed_role_baseline_replay.csv': pd.DataFrame(evaluations),
              'fixed_role_futility.csv': pd.DataFrame(decisions),
              'fixed_role_signal_opportunities.csv': pd.DataFrame(opportunities)}
    for name, frame in frames.items():
        frame.to_csv(output/name, index=False)
    code = ['scripts/fixed_role_attribution_20261117.py', 'scripts/cohort_routing_signals_20261117.py',
            'scripts/cohort_routing_controls_20261117.py', 'scripts/microstructure_signals_20261117.py',
            'src/autogrid/engine.py', 'configs/win60_search.yaml']
    manifest = dict(status='COMPLETE', engine_calls=6, source_sha256=actual_hash,
                    periods=['2025H1', '2025H2'], independent_holdout=False,
                    seed=SEED, draws=2000, design=design, warning=WARNING,
                    passes_futility=all(d['passes'] for d in decisions),
                    files=list(frames), code_hashes={p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in code})
    (output/'fixed_role_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(pd.DataFrame(decisions).to_string(index=False))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    main(parser.parse_args().output)
