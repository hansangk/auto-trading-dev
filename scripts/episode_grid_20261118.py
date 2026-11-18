"""Short-sample real-five-minute pilot with completed fifteen-minute features."""
from pathlib import Path
from dataclasses import replace
from itertools import product
import json,hashlib,gzip,os
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG
from session_signal_provenance import mask_session_signals
OUT=Path('runs/episode_grid_20261118')
INPUT=Path('runs/session_provenance_20261118/five_minute_common_LOCAL.csv.gz')
from episode_signals_20261118 import candidates,signals
from five_minute_grid_20261118 import signals as parent_signals

def main():
    if (OUT/'manifest.json').exists():raise SystemExit('Completed output protected')
    assert hashlib.sha256(INPUT.read_bytes()).hexdigest()=='bddc0f35373383fd0e74d30dc1d5feae0bc507e40f22916e2f6c9ed0ec2b3836'
    frame=pd.read_csv(INPUT);frame['timestamp']=pd.to_datetime(frame.timestamp,utc=True)
    frame['day']=frame.timestamp.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    # A full session must contain exactly all78five-minute starts for all4symbols.
    full=[]
    for day,g in frame.groupby('day'):
        expected=pd.date_range(day+' 09:30',periods=78,freq='5min',tz='America/New_York').tz_convert('UTC')
        if all(set(g[g.symbol==s].timestamp)==set(expected) and len(g[g.symbol==s])==78 for s in ('TQQQ','SQQQ','IBIT','BITI')):full.append(day)
    clean=frame[frame.day.isin(full)].drop(columns='day');path=OUT/'complete_sessions_LOCAL.csv.gz'
    path.write_bytes(gzip.compress(clean.to_csv(index=False).encode(),mtime=0))
    data=load_market_data(path,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    grid=candidates();scores={c['name']:signals(data,times,c) for c in grid}
    scores['momentum_parent']=parent_signals(data,times,dict(family='momentum',a=4,b=.5))
    # Intraday prefix cut checks prove future15min closes do not rewrite signals.
    for n in (101,389,803):
        prefix=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
        for c in grid:np.testing.assert_array_equal(signals(prefix,times[:n],c),scores[c['name']][:n])
    # Frozen relative opening-hour leader is the same-cap control, no fit here.
    control=np.zeros_like(data.close)
    for _,g in pd.Series(np.arange(len(times))).groupby(times.tz_convert('America/New_York').date):
        ix=g.to_numpy()
        if len(ix)>=24:
            i=ix[23];r=data.close[i]/data.open[ix[0]]-1;j=int(np.argmax(r))
            if r[j]>0:control[i,j]=1 if j<2 else -1
    scores['control']=control;rows=[];ledger=[];cache={}
    def evaluate(name,a,b,cost=1,delay=0):
        key=(name,a,b,cost,delay)
        if key not in cache:
            start,stop=[int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (a,b)];log=[]
            score=mask_session_signals(scores[name],times,delay,0,'event')
            result=run_backtest(data,score,StrategySpec(name,(),(),1,1,12,60,3,2),CFG.execution,CFG.risk,CFG.capital,start,stop,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
            assert np.isclose(np.prod([1+x['net_return'] for x in log])-1,result.total_return)
            assert all(0<w<=.15000001 for x in log for w in x['bought_weights'])
            row=dict(name=name,start=a,end_exclusive=b,cost=cost,delay=delay,**result.to_dict());rows.append(row);cache[key]=row
            ledger.extend(dict(name=name,start=a,cost=cost,delay=delay,**t) for t in log)
        return cache[key]
    periods=[('2026-10-19','2026-11-01'),('2026-11-01','2026-11-14')];stress=[(1,0),(2,0),(1,1)]
    base=pd.DataFrame([evaluate(c['name'],a,b) for c in grid for a,b in periods])
    rank=base.groupby('name').agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min')).sort_values(['worst','mean'],ascending=False)
    shortlist=rank[rank.min_rounds>=20].head(8).index.tolist()
    cells=[]
    for name in shortlist+['control','momentum_parent']:
        for a,b in periods:
            for cost,delay in stress:cells.append(evaluate(name,a,b,cost,delay))
    selected=[]
    for name in shortlist:
        group=[x for x in cells if x['name']==name]
        if min(x['rounds'] for x in group)>=20:selected.append(name)
    selected=selected[:3]
    (OUT/'selection.json').write_text(json.dumps(dict(shortlist=shortlist,diagnostic_selected=selected,approved=[],reason='Short development windows, no2025or3/6month history; promotion disabled'),indent=2))
    for name in ['control','momentum_parent']+selected:
        for cost,delay in stress:evaluate(name,'2026-11-16','2026-11-18',cost,delay)
    rank.to_csv(OUT/'ranking.csv');pd.DataFrame(cells).to_csv(OUT/'development_stress.csv',index=False)
    pd.DataFrame(rows).to_csv(OUT/'all_evaluations.csv',index=False)
    pd.DataFrame(rows)[lambda d:d.start=='2026-11-16'].to_csv(OUT/'diagnostic.csv',index=False)
    pd.DataFrame(ledger).to_json(OUT/'ledger_LOCAL.jsonl',orient='records',lines=True)
    usage=[]
    for row in rows:
        group=[t for t in ledger if all(t[k]==row[k] for k in ('name','start','cost','delay'))]
        for symbol in data.symbols:usage.append({k:row[k] for k in ('name','start','cost','delay')}|dict(symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in group)))
    fixed=[]
    for row in ledger:
        if row['name']!='momentum_parent' or row['start']=='2026-11-16':continue
        k=row['signal_index']
        for c in grid:
            candidate=mask_session_signals(scores[c['name']],times,row['delay'],0,'event')
            fixed.append(dict(name=c['name'],family=c['family'],start=row['start'],cost=row['cost'],delay=row['delay'],identical_roles=bool(np.array_equal(candidate[k],scores['momentum_parent'][k])),candidate_active=bool(np.any(candidate[k])),net=row['net_return']))
    pd.DataFrame(fixed).groupby(['name','family','start','cost','delay','identical_roles','candidate_active']).net.agg(['count','mean','sum']).to_csv(OUT/'fixed_parent.csv')
    devmask=times<pd.Timestamp('2026-11-14',tz='UTC')
    aliases={c['name']:hashlib.sha256(scores[c['name']][devmask].tobytes()).hexdigest() for c in grid}
    (OUT/'signal_aliases.json').write_text(json.dumps(dict(hashes=aliases,distinct=len(set(aliases.values()))),indent=2))
    pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False)
    (OUT/'manifest.json').write_text(json.dumps(dict(status='COMPLETE_SHORT_SAMPLE',calls=len(rows),candidates=16,shortlist=shortlist,selected=selected,approved=[],sessions=full,input_sha256=hashlib.sha256(INPUT.read_bytes()).hexdigest(),complete_input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),prefix_checks=48,independent_validation=False,news_macro=False,orders=0,hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['scripts/episode_grid_20261118.py','scripts/episode_signals_20261118.py','scripts/five_minute_grid_20261118.py','src/autogrid/engine.py','configs/win60_search.yaml','scripts/session_signal_provenance.py']}),indent=2))
    print(rank.to_string());print('calls',len(rows),'selected',selected)
if __name__=='__main__':
    fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    try:main()
    finally:(OUT/'RUNNING.lock').unlink()
