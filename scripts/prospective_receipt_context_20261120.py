"""Frozen-model input algebra and receipt audit only; no orders or engine.
Exact-span joins preserve the frozen batch semantics, including j>=8.
Context/score parity does not establish historical observability.
"""
from datetime import timedelta
import numpy as np
import pandas as pd
from scripts.prospective_input_audit_20261119 import _source_index, timestamp
from scripts.venue_latency_calendar_20261119 import common_mask

FIELDS = ('open','high','low','close','flow')
HOUR = pd.Timedelta(hours=1)

def build_context(data, source_rows, schedule):
    times = pd.DatetimeIndex(pd.to_datetime(data.timestamps, utc=True))
    # Validates supplied ETF clock and independently verified normal calendar.
    common_mask(times, schedule, 120)
    if not len(times):
        raise ValueError('Nonempty ETF rows required')
    source_rows = list(source_rows)
    if not source_rows:
        raise ValueError('Actual source rows required')
    latest = max(int(r[6])+1 for r in source_rows)
    asof = timestamp('1970-01-01T00:00:00Z') + timedelta(milliseconds=latest, minutes=5)
    _source_index(source_rows, asof)
    raw = {int(r[0]):r for r in source_rows}
    bars=[]
    for key in sorted(raw):
        if key % 3600000 != 1800000 or key+1800000 not in raw:
            continue
        x,y = raw[key],raw[key+1800000]
        volume=float(x[5])+float(y[5])
        bars.append(dict(start=pd.Timestamp(key,unit='ms',tz='UTC'),
            end=pd.Timestamp(int(y[6])+1,unit='ms',tz='UTC'),
            open=float(x[1]),high=max(float(x[2]),float(y[2])),
            low=min(float(x[3]),float(y[3])),close=float(y[4]),
            flow=2*(float(x[9])+float(y[9]))/volume-1,
            halves=(pd.Timestamp(key,unit='ms',tz='UTC'),pd.Timestamp(key+1800000,unit='ms',tz='UTC'))))
    n=len(times)
    ctx={k:np.zeros(n,bool) for k in ('valid','history1','history4','history8')}
    ctx.update({k:np.full(n,np.nan) for k in ('flow_mean4','flow_mean8')})
    for side in ('current','prior'):
        ctx[side]={k:np.full(n,np.nan) for k in FIELDS}
    trace=[]
    if not bars:
        return ctx, trace
    ends=pd.DatetimeIndex([b['end'] for b in bars])
    known=set(times)
    for i,t in enumerate(times):
        day=t.tz_convert('America/New_York').date().isoformat()
        closed=pd.Timestamp(schedule.loc[day,'close'])
        decision=min(t+HOUR,closed)
        j=int(ends.searchsorted(decision-pd.Timedelta(minutes=5),side='right')-1)
        if j<8:
            continue
        row=bars[j]
        age=(decision-row['end']).total_seconds()/60
        if not (5<=age<=65 and row['start'] in known and row['end']-row['start']==HOUR
                and row['start'].tz_convert('America/New_York').date().isoformat()==day):
            continue
        ctx['valid'][i]=True
        for k in (1,4,8):
            starts=[b['start'] for b in bars[j-k:j+1]]
            ctx['history'+str(k)][i]=all(b-a==HOUR for a,b in zip(starts,starts[1:]))
        for side,index in (('current',j),('prior',j-1)):
            for k in FIELDS:
                ctx[side][k][i]=bars[index][k]
        for k in (4,8):
            ctx['flow_mean'+str(k)][i]=np.mean([b['flow'] for b in bars[j-k:j]])
        trace.append(dict(index=i,decision=decision.isoformat(),
            source_start=row['start'].isoformat(),source_end=row['end'].isoformat(),
            assumed_release_floor=(row['end']+pd.Timedelta(minutes=5)).isoformat(),
            age_minutes=age,guard_source_starts=[h.isoformat() for b in bars[j-8:j+1] for h in b['halves']],required_source_starts=[h.isoformat() for b in bars[j-4:j+1] for h in b['halves']]))
    return ctx, trace

def receipt_gate(decision, etf_receipts, source_receipts, source_starts, entry):
    """Compare first recorded receipts with original signal and entry clocks.
    Caller verifies raw lineage, completion and same-vintage values separately.
    Passing the later entry clock never reconstructs a frozen earlier decision.
    """
    decision,entry=timestamp(decision),timestamp(entry)
    if entry<decision:
        raise ValueError('Entry precedes original decision')
    if len(etf_receipts)!=4 or not source_starts:
        raise ValueError('Four ETF receipts and source dependencies required')
    etf=[timestamp(r) for r in etf_receipts]
    required=[]
    for key in source_starts:
        canonical=timestamp(key).isoformat()
        if canonical not in source_receipts:
            raise ValueError('Missing actual source receipt: '+canonical)
        required.append(timestamp(source_receipts[canonical]))
    ready=max(etf+required)
    return dict(original_decision_utc=decision.isoformat(),entry_utc=entry.isoformat(),
        all_required_first_observed_utc=ready.isoformat(),
        observed_by_decision=ready<=decision, observed_by_entry=ready<=entry,
        signal_receipt_lag_seconds=(ready-decision).total_seconds(),
        terminal_backtest_allowed=False)
