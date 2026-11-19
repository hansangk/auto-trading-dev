"""One immutable actual-snapshot forensic parity/receipt audit; never runs engine.
Run from repository root: PYTHONPATH=src:. python scripts/prospective_receipt_audit_20261120.py
"""
import csv,hashlib,json
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from scripts.prospective_receipt_context_20261120 import build_context,receipt_gate
from scripts.prospective_input_audit_20261119 import _etf_index,_source_index,timestamp
from scripts.prospective_quote_tail_20261120 import classify_payload
from scripts.prospective_postclose_partition_20261120 import classify_postclose
from scripts.venue_flow_signals_20261119 import signals
from scripts.venue_latency_calendar_20261119 import common_mask
from scripts.session_signal_provenance import mask_session_signals

OUT=Path('runs/prospective_receipt_parity_20261120_0800')
PREV=Path('runs/prospective_close_policy_20261120_0700')
SOURCE=Path('runs/prospective_postclose_access_20261120_0600/BTCUSDT_30m_LOCAL.json')
CONFIG=dict(family='flow_trend',efficiency=.55,flow_threshold=.1,lookback=4)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def reference_context(data,source,schedule):
    # Read-only transcription of frozen venue_flow_context.prepare batch math.
    # Align explicit :30 source timestamps; partial snapshots start06:30, not00.
    a=np.asarray(source,float);bars=[]
    for i in np.flatnonzero(a[:,0].astype('int64')%3600000==1800000):
        if i+1>=len(a):continue
        x,y=a[i],a[i+1]
        assert int(y[0])==int(x[6])+1
        bars.append(dict(start=pd.Timestamp(int(x[0]),unit='ms',tz='UTC'),end=pd.Timestamp(int(y[6])+1,unit='ms',tz='UTC'),open=x[1],high=max(x[2],y[2]),low=min(x[3],y[3]),close=y[4],flow=2*(x[9]+y[9])/(x[5]+y[5])-1))
    f=pd.DataFrame(bars);ends=pd.DatetimeIndex(f.end)
    times=pd.DatetimeIndex(pd.to_datetime(data.timestamps,utc=True));known=set(times);n=len(times)
    ctx={k:np.zeros(n,bool) for k in ('valid','history1','history4','history8')}
    ctx.update({k:np.full(n,np.nan) for k in ('flow_mean4','flow_mean8')})
    for side in ('current','prior'):ctx[side]={k:np.full(n,np.nan) for k in ('open','high','low','close','flow')}
    for i,t in enumerate(times):
        day=t.tz_convert('America/New_York').date().isoformat()
        decision=min(t+pd.Timedelta(hours=1),schedule.loc[day,'close'])
        j=int(ends.searchsorted(decision-pd.Timedelta(minutes=5),side='right')-1)
        if j<8:continue
        row=f.iloc[j];age=(decision-row.end).total_seconds()/60
        if not 5<=age<=65 or row.start not in known or row.end-row.start!=pd.Timedelta(hours=1) or str(row.start.tz_convert('America/New_York').date())!=day:continue
        ctx['valid'][i]=True
        for k in (1,4,8):ctx['history'+str(k)][i]=bool((np.diff(f.start.iloc[j-k:j+1].astype('int64'))==3600*10**9).all())
        for side,index in (('current',j),('prior',j-1)):
            for k in ctx[side]:ctx[side][k][i]=f[k].iloc[index]
        for k in (4,8):ctx['flow_mean'+str(k)][i]=f.flow.iloc[j-k:j].mean()
    return ctx

def assert_context(a,b,limit=None):
    count=0
    for k,v in a.items():
        fields=v if isinstance(v,dict) else {k:v}
        target=b[k] if isinstance(v,dict) else {k:b[k]}
        for name,x in fields.items():
            y=target[name]
            np.testing.assert_allclose(x[:limit],y[:limit],rtol=0,atol=1e-14,equal_nan=True)
            count+=1
    return count

def streams(data,ctx,schedule):
    times=pd.DatetimeIndex(pd.to_datetime(data.timestamps,utc=True))
    result={}
    for arm in ('source','price'):
        raw=signals(data,times,ctx,CONFIG,flow_removed=(arm=='price'))
        for model,duration in (('h120',120),('c180',180)):
            calendar=raw*common_mask(times,schedule,duration)[:,None]
            for delay in (0,1):
                result[model+'__'+arm+'__delay'+str(delay)]=mask_session_signals(calendar,times,delay,0,'event')
    return result

def main():
    if (OUT/'receipt_parity_audit.json').exists():raise RuntimeError('Protected completed checkpoint')
    if any(Path('runs').rglob('RUNNING.lock')) or any(Path('runs').rglob('call_intent_LOCAL.json')):
        raise RuntimeError('Unresolved local worker or intent')
    state=json.loads(Path('RETRY_STATE.json').read_text()) # prior07 local hash references
    m=json.loads((PREV/'analysis_manifest.json').read_text())
    metadata=json.loads((OUT/'verified_receipt_metadata.json').read_text())
    for p,w in metadata['sha256'].items():
        if sha(p)!=w:raise ValueError('Pinned Git receipt metadata changed: '+p)
    verified={}
    for group in ('artifact_sha256','new_private_hashes','prior06_private_hashes','original_data_hashes','frozen17_dependency_sha256'):
        for p,w in m[group].items():
            if sha(p)!=w:raise ValueError('Prior07immutable mismatch: '+p)
            verified[p]=w
    for val in state.values():
        if isinstance(val,dict):
            for p,w in val.items():
                if p.startswith('runs/') and isinstance(w,str) and len(w)==64:
                    if sha(p)!=w:raise ValueError('Trustedprivate mismatch: '+p)
                    verified[p]=w
    data=load_market_data(PREV/'normalized_ETF_LOCAL.csv',['TQQQ','SQQQ','IBIT','BITI'])
    times=pd.DatetimeIndex(pd.to_datetime(data.timestamps,utc=True))
    source=json.loads(SOURCE.read_text())
    schedule=pd.read_csv('runs/prospective_readiness_retry_20261119_1700/calendar_20261119.csv').set_index('day')
    for k in ('open','close'):schedule[k]=pd.to_datetime(schedule[k],utc=True)
    ctx,trace=build_context(data,source,schedule)
    ctx_checks=assert_context(ctx,reference_context(data,source,schedule))
    full=streams(data,ctx,schedule);ref=streams(data,reference_context(data,source,schedule),schedule)
    for key in full:np.testing.assert_array_equal(full[key],ref[key])
    prefix=[]
    for n in range(1,len(times)+1):
        partial=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
        end=min(times[n-1]+pd.Timedelta(hours=1),schedule.iloc[0]['close'])
        src=[r for r in source if int(r[6])+1<=end.value//10**6]
        pc,_=build_context(partial,src,schedule)
        assert_context(pc,ctx,n)
        ps=streams(partial,pc,schedule)
        for key in full:
            delay=int(key[-1]);known=max(0,n-1-delay)
            np.testing.assert_array_equal(ps[key][:known],full[key][:known])
            prefix.append(dict(prefix_etf_times=n,stream=key,finalized_known_entry_rows=known,trailing_unknown_rows=n-known,status='PASS'))
    final_etfs=_etf_index(list(csv.DictReader((PREV/'normalized_ETF_LOCAL.csv').read_text().splitlines())))
    final_sources=_source_index(source,timestamp('2026-11-19T21:05:51Z'))
    etf_first={};source_first={};snapshot=[]
    definitions=[
      ('prospective_access_retry_20261120_0100','fixed_bar_end_cutoff_utc','source_receipt_verified_bracket','BTCUSDT_30m_partial_LOCAL.json'),
      ('prospective_append_retry_20261120_0200','asof_bar_end_cutoff','source_host_bracket','BTCUSDT_30m_partial_LOCAL.json'),
      ('prospective_normalized_append_20261120_0400','cutoff','source_host_bracket','BTCUSDT_30m_partial_LOCAL.json'),
      ('prospective_five_hour_append_20261120_0500','cutoff','source_host_bracket','BTCUSDT_30m_partial_LOCAL.json'),
      ('prospective_postclose_access_20261120_0600','ETF_request_cutoff','source_host_bracket','BTCUSDT_30m_LOCAL.json')]
    for folder,cutkey,brkey,srcname in definitions:
        base=Path('runs')/folder;manifest=json.loads((base/'analysis_manifest.json').read_text())
        # These metadata paths are transitively pinned by prior manifests. Also
        # record bytes used now; verify raw against trusted state before parsing.
        receipts=json.loads((base/'ETF_access_manifest.json').read_text())['sources']
        count=0
        for item in receipts:
            p=item['raw_path']
            if p not in verified or sha(p)!=item['raw_sha256']:raise ValueError('Untrustedraw receipt mapping')
            receipt=timestamp(item['received_host_utc'])
            cutoff=manifest[cutkey]
            if timestamp(cutoff)>receipt:raise ValueError('Receipt predates completion cutoff')
            parser=classify_postclose if folder.endswith('0600') else classify_payload
            result=parser(json.loads(Path(p).read_text()),cutoff)
            for key,values in _etf_index(result['completed_rows']).items():
                if final_etfs.get(key)!=values:raise ValueError('ETFvintage changed')
                etf_first[key]=min(etf_first.get(key,receipt),receipt)
                count+=1
        srcpath=base/srcname
        if str(srcpath) not in verified:raise ValueError('Untrustedsource file')
        upper=timestamp(manifest[brkey][1]);lower=timestamp(manifest[brkey][0])
        if lower>upper:raise ValueError('Receipt bracket reversed')
        sr=_source_index(json.loads(srcpath.read_text()),upper)
        for key,values in sr.items():
            if final_sources.get(key)!=values:raise ValueError('Sourcevintage changed')
            source_first[key.isoformat()]=min(source_first.get(key.isoformat(),upper),upper)
        snapshot.append(dict(run=folder,completed_etf_rows=count,source_rows=len(sr),source_receipt_upper=upper.isoformat(),ETF_manifest_sha256=sha(base/'ETF_access_manifest.json'),snapshot_manifest_sha256=sha(base/'analysis_manifest.json')))
    if len(etf_first)!=28 or len(source_first)!=29:raise ValueError('Incomplete firstreceiptcoverage')
    receipt_rows=[]
    trace_by_i={t['index']:t for t in trace}
    raw_scores={arm:signals(data,times,ctx,CONFIG,flow_removed=arm=='price') for arm in ('source','price')}
    for model,duration in (('h120',120),('c180',180)):
        for i in np.flatnonzero(common_mask(times,schedule,duration) & ctx['valid']):
            item=trace_by_i[int(i)];decision=item['decision']
            er=[etf_first[(s,times[i].to_pydatetime())].isoformat() for s in data.symbols]
            for arm in ('source','price'):
                for scenario,cost,delay in (('base',1,0),('cost2',2,0),('delay1',1,1)):
                    entry=(times[i]+pd.Timedelta(hours=1+delay)).isoformat()
                    gate=receipt_gate(decision,er,{k:v.isoformat() for k,v in source_first.items()},item['guard_source_starts'],entry)
                    receipt_rows.append(dict(model=model,arm=arm,scenario=scenario,actual_cost_multiplier=cost,delay=delay,
                        signal_bar_start=times[i].isoformat(),retrospective_nonzero_score=bool(np.any(raw_scores[arm][i])),
                        source_context_valid=True,calendar_common=True,**gate))
    lag=[(r-min(k[1]+timedelta(hours=1),timestamp('2026-11-19T21:00:00Z'))).total_seconds() for k,r in etf_first.items()]
    # Import locally for explicit final-bar390-minute handling, never infer
    # financial periods or receipts from a bar START.
    summaries=[]
    for model in ('h120','c180'):
        for arm in ('source','price'):
            for scenario in ('base','cost2','delay1'):
                group=[r for r in receipt_rows if (r['model'],r['arm'],r['scenario'])==(model,arm,scenario)]
                summaries.append(dict(model=model,arm=arm,scenario=scenario,context_calendar_opportunities=len(group),
                    retrospective_onsets=sum(r['retrospective_nonzero_score'] for r in group),
                    observed_by_original_decision=sum(r['observed_by_decision'] for r in group),
                    observed_by_entry_only=sum(r['observed_by_entry'] and not r['observed_by_decision'] for r in group)))
    result=dict(status='ALGEBRAIC_PARITY_PASS_FROZEN_DECISION_RECEIPT_GATE_REJECTED_NO_ENGINE',
        verified_immutable_path_count=len(verified),context_array_fields_checked=ctx_checks,
        reference='Read-only transcription of frozen batch arithmetic; not an independent implementation/vendor/PIT warranty',
        source_pairing='Actual contiguous :30-start 30m pairs; snapshot starts06:30 so hardcoded array offset1 forbidden',
        frozen_ctx_valid_indices=np.flatnonzero(ctx['valid']).tolist(),score_stream_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in full.items()},
        source_context_trace=trace,prefix_checks=prefix,prefix_score_comparisons=len(prefix),reference_score_streams=len(full),
        prefix_semantics='Compare only finalized known-entry rows; original session mask can change trailing1+delay rows when entry clock appended.',
        receipt_metadata_provenance=metadata,snapshots=snapshot,first_observed_completed_ETF_rows=len(etf_first),first_observed_source_rows=len(source_first),
        ETF_first_receipt_lag_from_bar_end_seconds=dict(minimum=min(lag),maximum=max(lag)),
        opportunity_receipt_audit=receipt_rows,scenario_summary=summaries,
        receipt_semantics='First recorded completed bar observation, not vendor publication time. Reclassifying old payload today does not establish policy existed then. Source upper receipt uses actual host bracket, not HTTP body. Passing delayed entry observation never reconstructs unavailable original signal-time state.',
        input_hashes={str(PREV/'normalized_ETF_LOCAL.csv'):sha(PREV/'normalized_ETF_LOCAL.csv'),str(SOURCE):sha(SOURCE)},
        data_period=dict(ETF_start_inclusive='2026-11-19T14:30:00Z',ETF_end_exclusive='2026-11-19T21:00:00Z',source_start_inclusive='2026-11-19T06:30:00Z',source_end_exclusive='2026-11-19T21:00:00Z'),
        new_market_requests=0,engine_calls=0,orders=0,account_trades=0,financial_metrics=None,new_independent_validation=False,
        terminal_backtest_allowed=False,historical_PIT_reconstructed=False,algorithmic_signal_parity_verified=True,
        historical_receipt_signal_parity_verified=False,NEW_FULL_AccountState_initialized=False,models_adopted=[],
        remaining='Original frozen decision clock not supported by actual completed-ETF receipts. No retroactivePIT. Need new preregistered receipt-aware future decision/execution experiment, actual fresh price at execution with complete source/calendar/protection; then new FULL AccountState/model-control-stress and exact carried integration. Do not reinterpret existing delaystress as new strategy or resweep oldgrids.')
    with (OUT/'receipt_parity_audit.json').open('x') as f:f.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('status','frozen_ctx_valid_indices','prefix_score_comparisons','first_observed_completed_ETF_rows','ETF_first_receipt_lag_from_bar_end_seconds','scenario_summary','engine_calls','financial_metrics')}))
from datetime import timedelta
if __name__=='__main__':main()
