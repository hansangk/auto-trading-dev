"""Actual five-minute source-release audit; frozen policies, no fitted thresholds.

The two decision clocks are evaluated BEFORE onset state is consumed. Daily
night/regime values are copied only from the audited preopen/prior-close fields;
all dynamic hourly sources are joined again at each actual five-minute decision.
Actual first-hour ETF input is released at10:35, with an assumed5minute buffer.
"""
from pathlib import Path
from dataclasses import replace
import hashlib,json,gzip
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from hourly_clock_audit_20261119 import parse_source,completed_index,trailing_rms,trailing_return
from hourly_night_signals_20261119 import signals
from nasdaq_gate_controls_20261119 import _onsets

BASE=Path('runs/hourly_clock_retry_20261119_0300')
FINE=Path('runs/extended_snapshot_20261118/refreshed_all_LOCAL.csv.gz')
INPUT_HASHES={str(FINE):'ebbdc8b683532ba96bf5c1358f5656833d6c33fe6833268ce1e13a777254b851',
 str(BASE/'audit_v2/audited_ETF_LOCAL.csv.gz'):'163e532099c1465e951543680730951b7b29a6d16021ff3affe31c23fd77e3d7',
 str(BASE/'audit_v2/context_LOCAL.npz'):'3811f0891d7579401b560ef00794ca7e318311f929ac1455ce47f2e2204572e0'}
POLICIES={'nasdaq_source':dict(family='night_nasdaq',a=5,b=.5),
          'qqq_parent':None,
          'btc_acceptance':dict(family='night_acceptance',a=.5,b=.25),
          'btc_exhaustion':dict(family='night_exhaustion',a=.8,b=.25)}

def decision_mask(times,clock):
    decision=pd.DatetimeIndex(times)+pd.Timedelta(minutes=5)
    if clock=='release5':return np.ones(len(times),bool)
    if clock!='coarse60':raise ValueError(clock)
    # Same old decision clocks, including the final short RTH bar. No onset
    # updates occur between these observed decisions.
    local=decision.tz_convert('America/New_York')
    return ((local.minute==30)&(local.hour>=10)&(local.hour<=15))|((local.hour==16)&(local.minute==0))

def first_hour_return(data,times,ix,decision):
    op=times[ix[0]]
    expected=pd.date_range(op,periods=12,freq='5min')
    if decision<op+pd.Timedelta(minutes=65) or len(ix)<12:return np.nan
    if not pd.DatetimeIndex(times[ix[:12]]).equals(expected):return np.nan
    j=data.symbols.index('IBIT')
    return float(np.log(data.close[ix[11],j]/data.open[ix[0],j]))

def policy_scores(data,times,ctx,clock):
    context={k:v.copy() for k,v in ctx.items()}
    context['valid'] &= decision_mask(times,clock)
    scores={k:signals(data,times,context,c) for k,c in POLICIES.items() if c is not None}
    # Only remove the BTC predicates; preserve exactly the common data support.
    common=context['valid'].copy()
    for k in ('night_return','night_scale','qqq_regime5','qqq_rth','qqq_gap'):
        common &= np.isfinite(context[k])
    common &= context['night_scale']>0
    side=np.sign(context['qqq_regime5'])
    desired=np.where((side!=0)&(side*context['qqq_rth']>0),side,0.)
    local=times.tz_convert('America/New_York');quotes=np.isfinite(data.close)&(data.close>0)
    scores['qqq_parent']=_onsets(local.date,common,desired,quotes,data.symbols.index('TQQQ'),data.symbols.index('SQQQ'))
    return scores

def build_context(data,times,schedule,qqq,btc,olddata,oldtimes,oldctx):
    n=len(times);days=times.tz_convert('America/New_York').strftime('%Y-%m-%d')
    olddays=oldtimes.tz_convert('America/New_York').strftime('%Y-%m-%d')
    firstold={d:int(np.flatnonzero(olddays==d)[0]) for d in np.unique(olddays)}
    oldlast={d:int(np.flatnonzero(olddays==d)[-1]) for d in np.unique(olddays)}
    fields=['night_return','night_scale','first_btc_preopen_price','qqq_regime5','qqq_regime10','qqq_gap','ibit_gap','same_day_first_ibit','btc_now','btc_vol480','btc_trend24','btc_trend48','btc_pullback1','btc_pullback3','qqq_rth']
    ctx={k:np.full(n,np.nan) for k in fields};ctx['valid']=np.zeros(n,bool)
    qends=pd.DatetimeIndex(qqq.end);bends=pd.DatetimeIndex(btc.end)
    all_days=list(schedule.index);fineix={d:np.flatnonzero(days==d) for d in np.unique(days)}
    decisions=times+pd.Timedelta(minutes=5);trace=[];fallback=[]
    for day,ix in fineix.items():
        op,cl=schedule.loc[day,['open','close']];old=firstold[day]
        # Audited daily dependencies: frozen before the RTH open or based only
        # on earlier completed daily closes. No dynamic hourly row is shifted.
        for k in ('night_return','night_scale','first_btc_preopen_price','qqq_regime5','qqq_regime10','qqq_gap'):
            ctx[k][ix]=oldctx[k][old]
        pos=all_days.index(day);previous=all_days[pos-1] if pos else None
        previous_close=None
        if previous in fineix:
            previous_close= data.close[fineix[previous][-1],data.symbols.index('IBIT')]
            origin='actual_five_minute_previous_session'
        elif previous in oldlast:
            previous_close=olddata.close[oldlast[previous],olddata.symbols.index('IBIT')]
            origin='audited_hourly_previous_session_boundary'
        else:origin='missing_previous_official_session'
        if previous_close is not None:
            ctx['ibit_gap'][ix]=np.log(data.open[ix[0],data.symbols.index('IBIT')]/previous_close)
        fallback.append(dict(day=day,previous=previous,prior_IBIT_close_origin=origin))
        for i in ix:
            decision=decisions[i];j=completed_index(bends,decision);qj=completed_index(qends,decision)
            ctx['same_day_first_ibit'][i]=first_hour_return(data,times,ix,decision)
            if j>=0:
                ctx['btc_now'][i]=btc.close.iloc[j]
                # Frozen policies here need current BTC and nightly fields only.
                # Unused trend fields stay NaN, rather than importing a future row.
            if qj>=0 and qqq.day.iloc[qj]==day:
                ctx['qqq_rth'][i]=np.log(qqq.close.iloc[qj]/qqq.open.iloc[qj])
            else:qj=-1
            ctx['valid'][i]=(np.isfinite(ctx['night_return'][i]) and np.isfinite(ctx['night_scale'][i]) and ctx['night_scale'][i]>0 and np.isfinite(ctx['ibit_gap'][i]) and j>=0)
            trace.append(dict(index=int(i),day=day,decision=str(decision),qqq_index=qj,btc_index=j,
                qqq_end=str(qends[qj]) if qj>=0 else None,btc_end=str(bends[j]) if j>=0 else None))
    return ctx,pd.DataFrame(trace),pd.DataFrame(fallback)

def prepare(out):
    for p,h in INPUT_HASHES.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
    schedule=pd.read_csv(BASE/'calendar_schedule.csv',index_col='day')
    for k in ('open','close'):schedule[k]=pd.to_datetime(schedule[k],utc=True)
    qqq,qmeta=parse_source('QQQ',schedule);btc,bmeta=parse_source('BTC-USD',schedule)
    olddata=load_market_data(BASE/'audit_v2/audited_ETF_LOCAL.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);oldtimes=pd.to_datetime(olddata.timestamps,utc=True)
    with np.load(BASE/'audit_v2/context_LOCAL.npz') as f:oldctx={k:f[k] for k in f.files}
    olddays=set(oldtimes.tz_convert('America/New_York').strftime('%Y-%m-%d'))
    frame=pd.read_csv(FINE);frame.timestamp=pd.to_datetime(frame.timestamp,utc=True);frame['day']=frame.timestamp.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    days=sorted(set(frame.day)&olddays);frame=frame[frame.day.isin(days)].drop(columns='day')
    path=out/'five_minute_overlap_LOCAL.csv.gz';path.write_bytes(gzip.compress(frame.to_csv(index=False).encode(),mtime=0))
    data=load_market_data(path,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    for day in days:
        assert day in schedule.index
        assert schedule.loc[day,'close']-schedule.loc[day,'open']==pd.Timedelta(minutes=390)
        actual=times[times.tz_convert('America/New_York').strftime('%Y-%m-%d')==day]
        assert actual.equals(pd.date_range(schedule.loc[day,'open'],schedule.loc[day,'close'],freq='5min',inclusive='left'))
    ctx,trace,fallback=build_context(data,times,schedule,qqq,btc,olddata,oldtimes,oldctx)
    np.savez_compressed(out/'context_LOCAL.npz',**ctx);trace.to_csv(out/'source_trace_LOCAL.csv',index=False);fallback.to_csv(out/'gap_origins.csv',index=False)
    # Aggregate actual contiguous5m bars to original hourly starts and compare
    # same keys. This is a DATA/VINTAGE audit, not a strategy return comparison.
    deltas=[]
    for day in days:
        for start in oldtimes[oldtimes.tz_convert('America/New_York').strftime('%Y-%m-%d')==day]:
            end=min(start+pd.Timedelta(hours=1),schedule.loc[day,'close']);ix=np.flatnonzero((times>=start)&(times<end));oldi=int(oldtimes.get_loc(start))
            assert len(ix)==int((end-start).total_seconds()/300)
            for field in ('open','high','low','close','volume'):
                x=getattr(data,field)[ix];agg=x[0] if field=='open' else x[-1] if field=='close' else x.max(axis=0) if field=='high' else x.min(axis=0) if field=='low' else x.sum(axis=0)
                old=getattr(olddata,field)[oldi]
                for j,symbol in enumerate(data.symbols):deltas.append(dict(field=field,symbol=symbol,changed=bool(not np.isclose(agg[j],old[j],rtol=0,atol=1e-8)),relative_abs=float(abs(agg[j]/old[j]-1)) if old[j] else None))
    delta=pd.DataFrame(deltas);delta.groupby(['symbol','field']).agg(keys=('changed','size'),changed=('changed','sum'),max_relative_abs=('relative_abs','max')).to_csv(out/'hourly_vintage_summary.csv')
    meta=dict(days=days,sessions=len(days),first_start=str(times[0]),last_end=str(times[-1]+pd.Timedelta(minutes=5)),input_hashes=INPUT_HASHES,overlap_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),context_sha256=hashlib.sha256((out/'context_LOCAL.npz').read_bytes()).hexdigest(),source_meta={'QQQ':qmeta,'BTC-USD':bmeta},calendar_sha256=hashlib.sha256((BASE/'calendar_schedule.csv').read_bytes()).hexdigest(),assumed_source_buffer_minutes=5,max_source_age_minutes=65,first_ETF_hour_buffer_minutes=5,new_market_observations=0,independent_validation=False,news_macro=False,orders=0)
    (out/'input_audit.json').write_text(json.dumps(meta,indent=2))
    return data,times,ctx,trace,meta,(schedule,qqq,btc,olddata,oldtimes,oldctx)
