"""Frozen hourly source availability audit. No price interpolation or outcomes."""
from pathlib import Path
import json,hashlib,gzip
import pandas as pd
import numpy as np
from autogrid.data import load_market_data
OUT=Path('runs/hourly_clock_retry_20261119_0300')
RAW=Path('runs/source_lead_audit_20261119_0200/hourly_access')
ETF=Path('runs/inverse_etf_retry_20261116/market.csv.gz')
HASH={'QQQ':'a62a158a1f6a3fc85ef803c277543408e7b46c629630787013427218827271ad','BTC-USD':'5a470cea79415bc73c87eaeeb5740fe8c5e1f95c2b72e9f05e68e8def54cb206'}

def parse_source(symbol,schedule):
    path=RAW/(symbol+'_raw_LOCAL.json');assert hashlib.sha256(path.read_bytes()).hexdigest()==HASH[symbol]
    body=json.loads(path.read_text())['chart']['result'][0];frame=pd.DataFrame(body['indicators']['quote'][0]);frame['start']=pd.to_datetime(body['timestamp'],unit='s',utc=True)
    cols=['open','high','low','close','volume'];finite=np.isfinite(frame[cols]).all(axis=1);nulls=frame[~finite]
    f=frame[finite].copy();assert not f.start.duplicated().any()
    assert (f[['open','high','low','close']]>0).all().all() and (f.volume>=0).all()
    assert (f.high>=f[['open','low','close']].max(axis=1)).all() and (f.low<=f[['open','high','close']].min(axis=1)).all()
    f['day']=f.start.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    good=[];ends=[]
    for row in f.itertuples():
        if symbol=='BTC-USD':ok=row.start.minute==0 and row.start.second==0;end=row.start+pd.Timedelta(hours=1)
        else:
            ok=False;end=row.start+pd.Timedelta(hours=1)
            if row.day in schedule.index:
                op,cl=schedule.loc[row.day,['open','close']];ok=row.start in pd.date_range(op,cl,freq='h',inclusive='left');end=min(end,cl)
        good.append(ok);ends.append(end)
    f['end']=pd.to_datetime(ends,utc=True);f=f[np.asarray(good)].copy()
    cutoff=pd.Timestamp(json.loads((RAW/'access_manifest.json').read_text())['sources'][0]['fetched_utc'])
    f=f[f.end+pd.Timedelta(minutes=5)<=cutoff].sort_values('end').reset_index(drop=True)
    invalid_days=nulls.start.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d').value_counts().to_dict()
    meta=dict(raw_rows=len(frame),null_rows=len(nulls),invalid_days=invalid_days,finite_offgrid_rows=int(len(good)-sum(good)),accepted_rows=len(f),first_start=str(f.start.min()),last_end=str(f.end.max()),raw_sha256=HASH[symbol])
    return f,meta

def completed_index(ends,decision,buffer_minutes=5,max_age_minutes=65):
    """Index actual source end available by decision; never manufacture a bar."""
    ends=pd.DatetimeIndex(ends);k=int(ends.searchsorted(decision-pd.Timedelta(minutes=buffer_minutes),side='right'))-1
    if k<0 or decision-ends[k]>pd.Timedelta(minutes=max_age_minutes):return -1
    return k

def trailing_return(frame,j,n):
    if j<n:return np.nan
    times=pd.DatetimeIndex(frame.end.iloc[j-n:j+1])
    if not np.all(np.diff(times.asi8)==3_600_000_000_000):return np.nan
    return float(np.log(frame.close.iloc[j]/frame.close.iloc[j-n]))

def trailing_rms(frame,j,n=480):
    if j<n:return np.nan
    times=pd.DatetimeIndex(frame.end.iloc[j-n:j+1])
    if not np.all(np.diff(times.asi8)==3_600_000_000_000):return np.nan
    return float(np.sqrt(np.mean(np.diff(np.log(frame.close.iloc[j-n:j+1].to_numpy()))**2)))

def main():
    if (OUT/'audit_manifest.json').exists():raise SystemExit('Completed audit protected')
    assert hashlib.sha256(ETF.read_bytes()).hexdigest()=='e0dea9e76a9c7f57b5d3791912e85473a29f5d31d4743783cf17b29a95c09fbd'
    schedule=pd.read_csv(OUT/'calendar_schedule.csv',index_col='day');schedule['open']=pd.to_datetime(schedule.open,utc=True);schedule['close']=pd.to_datetime(schedule.close,utc=True)
    assert '2025-01-09' not in schedule.index
    regular=schedule[(schedule.close-schedule.open)==pd.Timedelta(minutes=390)]
    qqq,qmeta=parse_source('QQQ',schedule);btc,bmeta=parse_source('BTC-USD',schedule)
    frame=pd.read_csv(ETF);frame.timestamp=pd.to_datetime(frame.timestamp,utc=True);frame['day']=frame.timestamp.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    daily={};full=[];excluded=[]
    for day,g in frame.groupby('day'):
        if day not in regular.index:excluded.append(dict(day=day,reason='short_session_not_full_390min',rows=len(g)));continue
        expected=pd.date_range(schedule.loc[day,'open'],schedule.loc[day,'close'],freq='h',inclusive='left')
        if all(set(g[g.symbol==s].timestamp)==set(expected) and len(g[g.symbol==s])==7 for s in ('TQQQ','SQQQ','IBIT','BITI')):
            full.append(day);daily[day]={s:(g[g.symbol==s].sort_values('timestamp').iloc[0]['open'],g[g.symbol==s].sort_values('timestamp').iloc[-1]['close']) for s in ('TQQQ','SQQQ','IBIT','BITI')}
        else:excluded.append(dict(day=day,reason='ETF_missing_hour',rows=len(g)))
    clean=frame[frame.day.isin(full)].drop(columns='day');path=OUT/'audited_ETF_LOCAL.csv.gz';path.write_bytes(gzip.compress(clean.to_csv(index=False).encode(),mtime=0))
    data=load_market_data(path,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);days=times.tz_convert('America/New_York').strftime('%Y-%m-%d');qdays={}
    for day,g in qqq.groupby('day'):
        if day in regular.index:
            expected=pd.date_range(schedule.loc[day,'open'],schedule.loc[day,'close'],freq='h',inclusive='left')
            if set(g.start)==set(expected) and len(g)==7:qdays[day]=g.sort_values('start')
    fields=['night_return','night_scale','btc_now','btc_trend24','btc_trend48','btc_vol480','btc_pullback1','btc_pullback3','qqq_regime5','qqq_regime10','qqq_rth','ibit_gap','qqq_gap','same_day_first_ibit','first_btc_preopen_price','btc_age_minutes','qqq_age_minutes']
    ctx={k:np.full(len(times),np.nan) for k in fields};ctx['valid']=np.zeros(len(times),bool);availability=[];day_stats=[]
    all_days=list(schedule.index);regdays=list(regular.index);btcend=pd.DatetimeIndex(btc.end);qqqend=pd.DatetimeIndex(qqq.end)
    for day,series in pd.Series(np.arange(len(times))).groupby(days):
        ix=series.to_numpy();op,cl=schedule.loc[day,['open','close']];pos=all_days.index(day);previous=all_days[pos-1] if pos else None
        anchor_close=schedule.loc[previous,'close'] if previous else None
        anchor=int(btcend.searchsorted(anchor_close,side='right'))-1 if anchor_close is not None else -1
        pre=completed_index(btcend,op);night=np.nan;scale=np.nan;preprice=np.nan
        if anchor>=0 and pre>anchor and btcend[anchor]==anchor_close and np.all(np.diff(btcend[anchor:pre+1].asi8)==3_600_000_000_000):
            night=float(np.log(btc.close.iloc[pre]/btc.close.iloc[anchor]));scale=trailing_rms(btc,anchor)*np.sqrt(pre-anchor);preprice=float(btc.close.iloc[pre])
        gap=np.nan;qgap=np.nan
        if previous in daily:gap=float(np.log(daily[day]['IBIT'][0]/daily[previous]['IBIT'][1]))
        if previous in qdays and day in qdays:qgap=float(np.log(qdays[day].iloc[0]['open']/qdays[previous].iloc[-1]['close']))
        first=float(np.log(data.close[ix[0],2]/data.open[ix[0],2]));reg={}
        for lookback in (5,10):
            ri=regdays.index(day);prior=regdays[max(0,ri-lookback-1):ri]
            reg[lookback]=float(np.log(qdays[prior[-1]].iloc[-1]['close']/qdays[prior[0]].iloc[-1]['close'])) if len(prior)==lookback+1 and all(d in qdays for d in prior) else np.nan
        for i in ix:
            decision=min(times[i]+pd.Timedelta(hours=1),cl)
            j=completed_index(btcend,decision);qj=completed_index(qqqend,decision)
            ctx['night_return'][i]=night;ctx['night_scale'][i]=scale;ctx['first_btc_preopen_price'][i]=preprice;ctx['ibit_gap'][i]=gap;ctx['qqq_gap'][i]=qgap;ctx['same_day_first_ibit'][i]=first
            ctx['qqq_regime5'][i]=reg[5];ctx['qqq_regime10'][i]=reg[10]
            if j>=0:
                ctx['btc_now'][i]=btc.close.iloc[j];ctx['btc_age_minutes'][i]=(decision-btcend[j]).total_seconds()/60
                ctx['btc_vol480'][i]=trailing_rms(btc,j-1)
                for h in (24,48):ctx['btc_trend'+str(h)][i]=trailing_return(btc,j,h)
                for h in (1,3):
                    if j-h+1>=0 and (btc.start.iloc[j-h+1:j+1]>=op).all():ctx['btc_pullback'+str(h)][i]=trailing_return(btc,j,h)
                availability.append(dict(decision=str(decision),symbol='BTC-USD',source_end=str(btcend[j]),age_minutes=ctx['btc_age_minutes'][i]))
            if qj>=0 and qqq.day.iloc[qj]==day:
                ctx['qqq_rth'][i]=np.log(qqq.close.iloc[qj]/qqq.open.iloc[qj]);ctx['qqq_age_minutes'][i]=(decision-qqqend[qj]).total_seconds()/60
                availability.append(dict(decision=str(decision),symbol='QQQ',source_end=str(qqqend[qj]),age_minutes=ctx['qqq_age_minutes'][i]))
            ctx['valid'][i]=np.isfinite(night) and np.isfinite(scale) and scale>0 and np.isfinite(gap) and j>=0
        day_stats.append(dict(day=day,night_available=bool(np.isfinite(night) and np.isfinite(scale) and scale>0),ETF_gap_available=bool(np.isfinite(gap)),QQQ_gap_available=bool(np.isfinite(qgap)),usable_rows=int(ctx['valid'][ix].sum())))
    a=pd.DataFrame(availability);assert (pd.to_datetime(a.source_end,utc=True)+pd.Timedelta(minutes=5)<=pd.to_datetime(a.decision,utc=True)).all();assert a.age_minutes.between(5,65).all()
    np.savez_compressed(OUT/'context_LOCAL.npz',**ctx);a.to_csv(OUT/'source_availability_LOCAL.csv',index=False)
    a.groupby('symbol').age_minutes.agg(['count','min','max','median']).to_csv(OUT/'availability_summary.csv');pd.DataFrame(day_stats).to_csv(OUT/'day_coverage.csv',index=False);pd.DataFrame(excluded).to_csv(OUT/'excluded_days.csv',index=False)
    manifest=dict(status='AUDIT_COMPLETE',raw_source={'QQQ':qmeta,'BTC-USD':bmeta},ETF_original_sha256=hashlib.sha256(ETF.read_bytes()).hexdigest(),ETF_audited_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),context_sha256=hashlib.sha256((OUT/'context_LOCAL.npz').read_bytes()).hexdigest(),calendar_sha256=hashlib.sha256((OUT/'calendar_schedule.csv').read_bytes()).hexdigest(),calendar_package='exchange_calendars4.13.3 XNYS plus primaryNYSEclosurescrosscheck',full_normal_ETF_days=len(full),excluded_ETF_days=excluded,first=str(times[0]),last=str(times[-1]),usable_rows=int(ctx['valid'].sum()),usable_days=int(sum(x['usable_rows']>0 for x in day_stats)),model_source_publication_buffer_minutes=5,max_source_age_minutes=65,BTC_clock='Actual00minute ends available; no shifting/interpolation',QQQ_clock='Actual30min starts, clippedtoofficialclose; source>=5minpublicationbuffer',sampling_limitation='WholeETFnormalcomplete days selectedretrospectivelyforbacktestavailability; cannotassumefuturedataqualityknownlive. Sourcefeatures onlypastvalidbars; no wholeQQQdaymask on BTC-onlysignals.',code_sha256=hashlib.sha256(Path('scripts/hourly_clock_audit_20261119.py').read_bytes()).hexdigest(),orders=0,raw_upload='Not attempted',independent_validation=False)
    (OUT/'audit_manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
