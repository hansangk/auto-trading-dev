"""Causal session-aligned 2h/daily structure router; development-only selection."""
import hashlib
import itertools
import json
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
import tqqq_bitcoin_pair_retry as base
from shadow_switch_retry import reversion_signal
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec

OUT = Path('runs/structure_mtf_retry')
STRESSES = [(1., 0), (2., 0), (1., 1)]


def structure(times, ratio):
    """Output at each base bar CLOSE; execution must use a subsequent bar."""
    local = times.tz_convert('America/New_York')
    dates = np.array(local.date)
    hours = np.array(local.hour)
    values = pd.Series(np.asarray(ratio, float), index=times)
    # Full pairs 09:30+10:30, 11:30+12:30, 13:30+14:30 only.
    # Release at second member's close; never use an incomplete pair.
    events = []
    for i in range(1, len(times)):
        if hours[i] in (10, 12, 14) and hours[i-1] == hours[i]-1 and dates[i] == dates[i-1] and times[i]-times[i-1] == pd.Timedelta(hours=1):
            events.append(i)
    two = values.iloc[events]
    direction2 = np.sign(two.ewm(span=3, adjust=False).mean() - two.ewm(span=8, adjust=False).mean())
    two_aligned = direction2.reindex(times, method='ffill').fillna(0).to_numpy()
    # Today's daily close is never exposed to today's intraday rows.
    daily = values.groupby(dates).last()
    daily_direction = np.sign(daily.ewm(span=3, adjust=False).mean()-daily.ewm(span=8, adjust=False).mean()).shift(1).fillna(0)
    day_aligned = pd.Series(dates).map(daily_direction).to_numpy()
    r = pd.Series(np.asarray(ratio, float))
    efficiency = (r.diff(24).abs()/r.diff().abs().rolling(24).sum().replace(0, np.nan)).fillna(0).to_numpy()
    return two_aligned, day_aligned, efficiency


def route(trend, reversion, two, daily, efficiency, cutoff, align_daily, use_range):
    direction = trend[:, 0]
    trend_ok = (efficiency >= cutoff) & (direction * two > 0)
    if align_daily:
        trend_ok &= direction * daily > 0
    # Do not infer reversal from failed trends: require low directional efficiency
    # AND disagreement/neutrality between the completed higher timeframes.
    range_ok = (efficiency < cutoff / 2) & (two * daily <= 0)
    out = np.zeros_like(trend)
    states = np.zeros(len(trend), int)
    out[trend_ok] = trend[trend_ok]; states[trend_ok] = 1
    if use_range:
        out[range_ok] = reversion[range_ok]; states[range_ok] = 2
    return out, states


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    original, times, _ = base.context()
    local = times.tz_convert('America/New_York')
    keep = (local.minute == 30) & (local.hour >= 9) & (local.hour < 16)
    data = replace(original, timestamps=original.timestamps[keep], **{k:getattr(original,k)[keep] for k in ('open','high','low','close','volume')})
    times = times[keep]; ratio = pd.Series(np.log(data.close[:,0]/data.close[:,1]))
    base.CACHE['x'] = data, times, ratio
    two, daily, efficiency = structure(times, ratio)
    mr = reversion_signal(ratio, 24, 1.5, True)
    candidates = [dict(id='anchor', mode='dual_momentum', window=24, hold=4)]
    for mode, window, cutoff, align_daily, use_range, hold in itertools.product(
            ('dual_momentum','breakout'), (12,24,48), (.2,.4), (False,True), (False,True), (4,6)):
        c = dict(mode=mode,window=window,cutoff=cutoff,align_daily=align_daily,use_range=use_range,hold=hold)
        c['id'] = hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:12]
        candidates.append(c)
    signals = {}
    for c in candidates:
        trend = base.pair_signal(dict(mode=c['mode'],window=c['window'],threshold=.75))
        signals[c['id']] = (trend, np.ones(len(times),int)) if c['id']=='anchor' else route(
            trend,mr,two,daily,efficiency,c['cutoff'],c['align_daily'],c['use_range'])
    manifest = dict(candidates=candidates,source_sha256=hashlib.sha256(Path('runs/tqqq_bitcoin_retry/yahoo_1h.csv').read_bytes()).hexdigest(),
                    selection='Worst of six 2025 H1/H2 base/cost2/delay returns, then mean, then ID; persist top 5 before 2026.',
                    availability='2h full session pairs at second base bar close; prior-session daily direction only; engine signal shifted.',
                    warning='Reused periods; no independent holdout. Risk/exposure unchanged. No news/macro. IBIT proxy.')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    bounds = {'2025H1':('2025-01-01','2025-07-01'),'2025H2':('2025-07-01','2026-01-01'),'2026':('2026-01-01','2026-11-14')}
    logs = []
    def evaluate(c, period, cost, delay, record=False):
        score, states = signals[c['id']]
        spec = StrategySpec(c['id'],(c['mode'],),(1.,),1,1,c['hold'],60.,3.,2)
        a,b = [int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in bounds[period]]
        ledger = []
        result = run_backtest(data,score,spec,base.CFG.execution,base.CFG.risk,base.CFG.capital,a,b,cost,delay,exit_mode='joint_close',trade_log=ledger)
        assert np.isclose(np.prod([1+t['net_return'] for t in ledger])-1,result.total_return)
        if record:
            for t in ledger:
                logs.append(dict(candidate=c['id'],period=period,cost=cost,delay=delay,tactic=int(states[t['signal_index']]),**t))
        return dict(id=c['id'],period=period,cost=cost,delay=delay,**result.to_dict())
    dev = pd.DataFrame([evaluate(c,p,cost,delay) for c in candidates for p in ('2025H1','2025H2') for cost,delay in STRESSES])
    dev.to_csv(OUT/'development.csv',index=False)
    rank = dev[dev.id!='anchor'].groupby('id').agg(worst_return=('total_return','min'),mean_return=('total_return','mean'),
              positive_scenarios=('total_return',lambda s:int((s>0).sum())),min_rounds=('rounds','min')).reset_index()
    rank = rank.sort_values(['worst_return','mean_return','id'],ascending=[False,False,True])
    rank.to_csv(OUT/'ranking.csv',index=False)
    selected = rank.head(5).id.tolist()
    (OUT/'selection.json').write_text(json.dumps(dict(selected_ids=selected),indent=2))
    diag = pd.DataFrame([evaluate(c,'2026',cost,delay,True) for c in candidates if c['id'] in selected+['anchor'] for cost,delay in STRESSES])
    diag.to_csv(OUT/'diagnostic.csv',index=False)
    pd.DataFrame(logs).to_json(OUT/'diagnostic_ledger.jsonl',orient='records',lines=True)
    manifest.update(development_evaluations=len(dev),diagnostic_evaluations=len(diag))
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(rank.head(5).to_string(index=False))
    print(diag[['id','cost','delay','total_return','rounds','max_drawdown']].to_string(index=False))


if __name__=='__main__':
    main()
