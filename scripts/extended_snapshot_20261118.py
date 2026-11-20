"""Versioned input audit and fixed strategy replays. No re-selection or refit."""
from pathlib import Path
import json,hashlib,gzip,os
import pandas as pd
import numpy as np
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from episode_signals_20261118 import signals as episodes
from five_minute_grid_20261118 import signals as original
from inverse_etf_retry_20261116 import CFG
from session_signal_provenance import mask_session_signals
OUT=Path('runs/extended_snapshot_20261118')
OLD=Path('runs/session_provenance_20261118')
SYMBOLS=['TQQQ','SQQQ','IBIT','BITI'];VALUES=['open','high','low','close','volume']
MODELS=[dict(name='compression_0.75_4',family='compression',a=.75,b=4),dict(name='chasecancel_1_0.25',family='chasecancel',a=1,b=.25),dict(name='chasecancel_3_0.5',family='chasecancel',a=3,b=.5)]

def raw_frame(directory):
    provenance=json.loads((directory/'five_minute_provenance.json').read_text())
    frames=[]
    for source in provenance['sources']:
        symbol=source['symbol'];raw=(directory/(symbol+'_5m_LOCAL.json')).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==source['sha256']
        x=json.loads(raw)['chart']['result'][0];q=x['indicators']['quote'][0]
        f=pd.DataFrame(dict(timestamp=pd.to_datetime(x['timestamp'],unit='s',utc=True),symbol=symbol,**{k:q[k] for k in VALUES})).dropna()
        ny=f.timestamp.dt.tz_convert('America/New_York');minute=ny.dt.hour*60+ny.dt.minute
        f=f[(ny.dt.weekday<5)&(minute>=570)&(minute<960)&(ny.dt.minute%5==0)&(ny.dt.second==0)&(f.timestamp+pd.Timedelta(minutes=7)<=pd.Timestamp(provenance['cutoff_utc']))]
        assert np.isfinite(f[VALUES]).all().all();assert (f[VALUES[:4]]>0).all().all();assert (f.volume>=0).all()
        assert (f.high>=f[['open','low','close']].max(axis=1)).all();assert (f.low<=f[['open','high','close']].min(axis=1)).all()
        frames.append(f)
    frame=pd.concat(frames);assert not frame.duplicated(['timestamp','symbol']).any()
    return frame

def full_sessions(frame):
    frame=frame.copy();frame['day']=frame.timestamp.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    full=[]
    for day,g in frame.groupby('day'):
        expected=set(pd.date_range(day+' 09:30',periods=78,freq='5min',tz='America/New_York').tz_convert('UTC'))
        if all(set(g[g.symbol==s].timestamp)==expected and len(g[g.symbol==s])==78 for s in SYMBOLS):full.append(day)
    return frame[frame.day.isin(full)].drop(columns='day'),full

def save(frame,path):
    path.write_bytes(gzip.compress(frame.sort_values(['timestamp','symbol']).to_csv(index=False).encode(),mtime=0))

def main():
    if (OUT/'manifest.json').exists():raise SystemExit('Completed run protected')
    assert hashlib.sha256((OLD/'five_minute_common_LOCAL.csv.gz').read_bytes()).hexdigest()=='bddc0f35373383fd0e74d30dc1d5feae0bc507e40f22916e2f6c9ed0ec2b3836'
    before=raw_frame(OLD);after=raw_frame(OUT)
    a=before.set_index(['timestamp','symbol']).sort_index();b=after.set_index(['timestamp','symbol']).sort_index();common=a.index.intersection(b.index)
    changed={col:int((~np.isclose(a.loc[common,col],b.loc[common,col],rtol=0 if col=='volume' else 1e-9,atol=0 if col=='volume' else 1e-8)).sum()) for col in VALUES}
    added=b.index.difference(a.index);dropped=a.index.difference(b.index)
    recovered=sum(a.index.get_level_values('timestamp').min()<=t<=a.index.get_level_values('timestamp').max() for t,s in added)
    old_full,old_dates=full_sessions(before);new_full,new_dates=full_sessions(after)
    shared_dates=sorted(set(old_dates)&set(new_dates));shared=new_full[new_full.timestamp.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d').isin(shared_dates)]
    versions={'archived':old_full,'refreshed_same_dates':shared,'refreshed_all':new_full}
    for name,f in versions.items():save(f,OUT/(name+'_LOCAL.csv.gz'))
    audit=dict(old_raw_qualified_rows=len(before),new_raw_qualified_rows=len(after),shared_symbol_keys=len(common),revised_fields=changed,added_symbol_keys=len(added),recovered_inside_old_span=recovered,dropped_symbol_keys=len(dropped),old_full_dates=old_dates,new_full_dates=new_dates,shared_full_dates=shared_dates,restored_old_span_dates=[d for d in new_dates if old_dates[0]<=d<=old_dates[-1] and d not in old_dates],calendar_verified=False)
    (OUT/'overlap_audit.json').write_text(json.dumps(audit,indent=2))
    rows=[];usage=[];calls=0
    common_periods=[('2026-10-19','2026-11-01'),('2026-11-01','2026-11-14'),('2026-11-16','2026-11-18')]
    older=[('2026-08-25','2026-09-20'),('2026-09-20','2026-10-01'),('2026-10-01','2026-10-19')]
    for version in versions:
        data=load_market_data(OUT/(version+'_LOCAL.csv.gz'),SYMBOLS);times=pd.to_datetime(data.timestamps,utc=True)
        scores={c['name']:episodes(data,times,c) for c in MODELS}
        scores['momentum_parent']=original(data,times,dict(family='momentum',a=4,b=.5))
        control=np.zeros_like(data.close)
        for _,group in pd.Series(np.arange(len(times))).groupby(times.tz_convert('America/New_York').date):
            ix=group.to_numpy();i=ix[23];r=data.close[i]/data.open[ix[0]]-1;j=int(np.argmax(r))
            if r[j]>0:control[i,j]=1 if j<2 else -1
        scores['control']=control
        for start,end in common_periods+(older if version=='refreshed_all' else []):
            first,last=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in (start,end)]
            for name,score in scores.items():
                for scenario,cost,delay in [('base',1,0),('cost2',2,0),('delay1',1,1)]:
                    log=[];masked=mask_session_signals(score,times,delay,0,'event')
                    result=run_backtest(data,masked,StrategySpec(name,(),(),1,1,12,60,3,2),CFG.execution,CFG.risk,CFG.capital,first,last,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
                    assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,result.total_return)
                    assert all(0<w<=.15000001 for t in log for w in t['bought_weights'])
                    rows.append(dict(version=version,start=start,end_exclusive=end,name=name,scenario=scenario,**result.to_dict()));calls+=1
                    for s in SYMBOLS:usage.append(dict(version=version,start=start,name=name,scenario=scenario,symbol=s,buys=sum(s in t['bought_symbols'] for t in log)))
    results=pd.DataFrame(rows);results.to_csv(OUT/'replays.csv',index=False);pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False)
    left=results[results.version=='archived'].set_index(['start','end_exclusive','name','scenario']);right=results[results.version=='refreshed_same_dates'].set_index(['start','end_exclusive','name','scenario'])
    delta=right[['total_return','rounds','max_drawdown','win_rate']]-left[['total_return','rounds','max_drawdown','win_rate']];delta.to_csv(OUT/'same_dates_data_delta.csv')
    files=['scripts/extended_snapshot_20261118.py','scripts/fetch_extended_snapshot_20261118.py','scripts/episode_signals_20261118.py','scripts/five_minute_grid_20261118.py','src/autogrid/engine.py','configs/win60_search.yaml','scripts/session_signal_provenance.py']
    (OUT/'manifest.json').write_text(json.dumps(dict(status='COMPLETE_FROZEN_EXTENSION',calls=calls,new_candidates=0,adoption=False,input_hashes={str(OUT/(n+'_LOCAL.csv.gz')):hashlib.sha256((OUT/(n+'_LOCAL.csv.gz')).read_bytes()).hexdigest() for n in versions},source_sha256=json.loads((OUT/'five_minute_provenance.json').read_text())['sha256'],frozen_models=[c['name'] for c in MODELS],code_hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files},independent_validation=False,news_macro=False,orders=0),indent=2))
    print(json.dumps(audit,indent=2));print('calls',calls,'maxrevisiondelta',delta.total_return.abs().max())
if __name__=='__main__':
    fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    try:main()
    finally:(OUT/'RUNNING.lock').unlink()
