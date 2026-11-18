"""Audited completed-hour activity features with exact calendar-slot donors.

No execution or labels. Source and ETF arms share end/availability clocks.
Zero reported volume is unavailable, not a low-activity signal. BTC source
volume is screened separately and blocked by a preregistered quality rule.
"""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from hourly_clock_audit_20261119 import parse_source,completed_index,BASE

OUT=Path('runs/source_activity_grid_20261119_0700')
ETF=BASE/'audit_v2/audited_ETF_LOCAL.csv.gz'
ETF_HASH='163e532099c1465e951543680730951b7b29a6d16021ff3affe31c23fd77e3d7'

def seasonal_features(frame,schedule):
    """Current volume / prior20/40 same normal-session slot median.

    Every calendar donor must exist with positive volume; do not skip missing
    donors to construct20observations. Current/future sessions are excluded.
    Current source day's later bars never determine its feature availability.
    """
    regular=schedule[(schedule.close-schedule.open)==pd.Timedelta(minutes=390)]
    days=list(regular.index);positions={d:i for i,d in enumerate(days)}
    f=frame.copy().reset_index(drop=True);slots=[];mapping={}
    for i,r in enumerate(f.itertuples()):
        slot=None
        if r.day in positions:
            offset=(r.start-regular.loc[r.day,'open']).total_seconds()/3600
            if offset==int(offset) and 0<=offset<7:slot=int(offset);mapping[(r.day,slot)]=i
        slots.append(slot)
    result={k:f[k].to_numpy(float) for k in ('open','high','low','close')}
    for lookback in (20,40):
        value=np.full(len(f),np.nan)
        for i,r in enumerate(f.itertuples()):
            slot=slots[i]
            if slot is None or r.volume<=0:continue
            pos=positions[r.day]
            if pos<lookback:continue
            donors=[mapping.get((d,slot)) for d in days[pos-lookback:pos]]
            if any(j is None for j in donors):continue
            volumes=f.volume.iloc[donors].to_numpy(float)
            if np.isfinite(volumes).all() and (volumes>0).all():value[i]=float(r.volume/np.median(volumes))
        result['rvol'+str(lookback)]=value
    return result

def previous_bar(frame,j):
    if j<=0:return -1
    a,b=frame.iloc[j-1],frame.iloc[j]
    if a.day!=b.day or a.end!=b.start:return -1
    if b.end-b.start!=pd.Timedelta(hours=1) or a.end-a.start!=pd.Timedelta(hours=1):return -1
    return j-1

def prepare():
    if (OUT/'context_manifest.json').exists():raise SystemExit('Prepared context protected')
    assert hashlib.sha256(ETF.read_bytes()).hexdigest()==ETF_HASH
    quality=json.loads((OUT/'source_quality.json').read_text())
    passed={s:all(r['positive_fraction']>=.95 for r in quality[s]['volume'][:2]) for s in ('QQQ','BTC-USD')}
    assert passed=={'QQQ':True,'BTC-USD':False}
    schedule=pd.read_csv(BASE/'calendar_schedule.csv',index_col='day')
    for k in ('open','close'):schedule[k]=pd.to_datetime(schedule[k],utc=True)
    qqq,qmeta=parse_source('QQQ',schedule)
    data=load_market_data(ETF,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);local=times.tz_convert('America/New_York')
    frame=pd.read_csv(ETF);frame=frame[frame.symbol=='TQQQ'].copy();frame['start']=pd.to_datetime(frame.timestamp,utc=True);frame['day']=frame.start.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    frame['end']=[min(t+pd.Timedelta(hours=1),schedule.loc[d,'close']) for t,d in zip(frame.start,frame.day)]
    frame=frame.sort_values('end').reset_index(drop=True)
    end_lookup={t:i for i,t in enumerate(frame.end)}
    source=seasonal_features(qqq,schedule);etf=seasonal_features(frame,schedule)
    n=len(times);fields=('open','high','low','close','rvol20','rvol40')
    ctx={'valid':np.zeros(n,bool)}
    for feed in ('source','ETF'):
        ctx[feed]={k:np.full(n,np.nan) for k in fields}
        ctx[feed].update({'prev_'+k:np.full(n,np.nan) for k in fields})
        ctx[feed]['prev_contiguous']=np.zeros(n,bool)
    ends=pd.DatetimeIndex(qqq.end);trace=[]
    for i,t in enumerate(times):
        day=local[i].strftime('%Y-%m-%d');decision=min(t+pd.Timedelta(hours=1),schedule.loc[day,'close']);j=completed_index(ends,decision)
        if j<0 or qqq.day.iloc[j]!=day:continue
        k=end_lookup.get(ends[j])
        if k is None or frame.day.iloc[k]!=day or frame.start.iloc[k]!=qqq.start.iloc[j]:continue
        ctx['valid'][i]=True
        for feed,f,features,index in (('source',qqq,source,j),('ETF',frame,etf,k)):
            for field in fields:ctx[feed][field][i]=features[field][index]
            prev=previous_bar(f,index)
            if prev>=0:
                for field in fields:ctx[feed]['prev_'+field][i]=features[field][prev]
                ctx[feed]['prev_contiguous'][i]=True
        trace.append(dict(index=int(i),day=day,decision=str(decision),source_index=int(j),source_start=str(qqq.start.iloc[j]),source_end=str(ends[j]),ETF_matched_end=str(frame.end.iloc[k]),age_minutes=(decision-ends[j]).total_seconds()/60,previous_source_contiguous=bool(ctx['source']['prev_contiguous'][i]),previous_ETF_contiguous=bool(ctx['ETF']['prev_contiguous'][i])))
    serial={'valid':ctx['valid'],**{feed+'__'+k:v for feed in ('source','ETF') for k,v in ctx[feed].items()}}
    np.savez_compressed(OUT/'activity_context_LOCAL.npz',**serial)
    tr=pd.DataFrame(trace);assert (pd.to_datetime(tr.source_end,utc=True)+pd.Timedelta(minutes=5)<=pd.to_datetime(tr.decision,utc=True)).all();assert tr.age_minutes.between(5,65).all()
    tr.to_csv(OUT/'source_trace_LOCAL.csv',index=False)
    summary=[]
    for feed in ('source','ETF'):
        for lookback in (20,40):
            for a,b in [('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01'),('2026-01-01','2026-11-14')]:
                mask=(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'))
                summary.append(dict(feed=feed,lookback=lookback,start=a,end_exclusive=b,decision_rows=int(mask.sum()),common_source_rows=int((mask&ctx['valid']).sum()),positive_complete_seasonal_rows=int((mask&ctx['valid']&np.isfinite(ctx[feed]['rvol'+str(lookback)])).sum())))
    pd.DataFrame(summary).to_csv(OUT/'feature_availability.csv',index=False)
    manifest=dict(status='PREPARED_BEFORE_PNL',source_quality_gate='>=95%positive reportedvolume EACH2025half; zero unavailable,notlowflow',source_quality_pass=passed,QQQ_raw=qmeta,ETF_sha256=ETF_HASH,context_sha256=hashlib.sha256((OUT/'activity_context_LOCAL.npz').read_bytes()).hexdigest(),calendar_sha256=hashlib.sha256((BASE/'calendar_schedule.csv').read_bytes()).hexdigest(),donors='All20/40previous NORMALcalendar sessions samehour ordinal; everydonorpositive/present; no currentday/future/skipmissing',source_join='QQQ actualend+5min<=ETFdecision,age<=65,currentRTHday; ETFfeatureusesEXACTsamecompletedstart/end',QQQ_not_whole_current_day_gated=True,news_macro=False,independent_validation=False,new_market_observations=0,orders=0)
    (OUT/'context_manifest.json').write_text(json.dumps(manifest,indent=2));print(pd.DataFrame(summary).to_string(index=False));return data,times,ctx

def load_prepared():
    data=load_market_data(ETF,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    with np.load(OUT/'activity_context_LOCAL.npz') as f:
        ctx={'valid':f['valid'],**{feed:{k.split('__')[1]:f[k] for k in f.files if k.startswith(feed+'__')} for feed in ('source','ETF')}}
    return data,times,ctx

if __name__=='__main__':prepare()
