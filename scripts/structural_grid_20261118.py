"""Single-factor controls and bounded development selection on fixed five-minute data."""
from pathlib import Path
from dataclasses import replace
import json,hashlib,os
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG
from episode_signals_20261118 import signals as episode_signals
from five_minute_grid_20261118 import signals as momentum_signals
from structural_signals_20261118 import candidates,signals
from session_signal_provenance import mask_session_signals
OUT=Path('runs/structural_grid_20261118')
INPUT=Path('runs/extended_snapshot_20261118/refreshed_all_LOCAL.csv.gz')
STRESS=[('base',1,0),('cost2',2,0),('delay1',1,1)]

def main():
    if (OUT/'manifest.json').exists():raise SystemExit('Complete output protected')
    assert hashlib.sha256(INPUT.read_bytes()).hexdigest()=='ebbdc8b683532ba96bf5c1358f5656833d6c33fe6833268ce1e13a777254b851'
    data=load_market_data(INPUT,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    grid=candidates();byid={c['name']:c for c in grid};scores={c['name']:signals(data,times,c) for c in grid}
    parents={'compression_parent':dict(family='compression',a=.75,b=4),'chase1_parent':dict(family='chasecancel',a=1,b=.25),'chase3_parent':dict(family='chasecancel',a=3,b=.5)}
    for name,c in parents.items():scores[name]=episode_signals(data,times,c)
    scores['momentum_parent']=momentum_signals(data,times,dict(family='momentum',a=4,b=.5))
    score=np.zeros_like(data.close)
    for _,group in pd.Series(np.arange(len(times))).groupby(times.tz_convert('America/New_York').date):
        ix=group.to_numpy();i=ix[23];r=data.close[i]/data.open[ix[0]]-1;j=int(np.argmax(r))
        if r[j]>0:score[i,j]=1 if j<2 else -1
    scores['control']=score
    for n in (101,803,1711):
        prefix=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
        for c in grid:np.testing.assert_array_equal(signals(prefix,times[:n],c),scores[c['name']][:n])
    masks={(name,d):mask_session_signals(score,times,d,0,'event') for name,score in scores.items() for d in (0,1)}
    def parent(c):
        if c['family']=='compression_expiry':return 'compression_parent'
        if c['family']=='adverse_chase':return 'chase1_parent' if c['a']==1 else 'chase3_parent'
        return 'momentum_parent'
    cache={};logs={};rows=[]
    def evaluate(name,start,end,scenario,cost,delay):
        key=(name,start,end,scenario)
        if key not in cache:
            a,b=[int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (start,end)];log=[]
            result=run_backtest(data,masks[name,delay],StrategySpec(name,(),(),1,1,12,60,3,2),CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
            assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,result.total_return)
            assert all(0<w<=.15000001 for t in log for w in t['bought_weights'])
            row=dict(name=name,start=start,end_exclusive=end,scenario=scenario,**result.to_dict());cache[key]=row;logs[key]=log;rows.append(row)
        return cache[key]
    periods=[('2026-08-25','2026-09-20'),('2026-09-20','2026-10-19')]
    base=pd.DataFrame([evaluate(c['name'],a,b,*STRESS[0]) for c in grid for a,b in periods])
    rank=base.groupby('name').agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min')).sort_values(['worst','mean'],ascending=False)
    shortlist=rank[rank.min_rounds>=20].head(8).index.tolist()
    stress=[]
    for name in shortlist+list(parents)+['momentum_parent','control']:
        for a,b in periods:
            for scenario,cost,delay in STRESS:stress.append(evaluate(name,a,b,scenario,cost,delay))
    ranking=[]
    for name in shortlist:
        cells=[x for x in stress if x['name']==name];p=parent(byid[name]);controls=[next(x for x in stress if x['name']==p and x['start']==r['start'] and x['scenario']==r['scenario']) for r in cells]
        eligible=min(r['rounds'] for r in cells)>=20
        passed=eligible and all(r['total_return']>0 and r['total_return']>ref['total_return'] and r['max_drawdown']<=ref['max_drawdown'] and not r['mdd_halt'] for r,ref in zip(cells,controls))
        ranking.append(dict(name=name,parent=p,worst=min(r['total_return'] for r in cells),min_rounds=min(r['rounds'] for r in cells),eligible=eligible,research_pass=passed))
    final=pd.DataFrame(ranking).sort_values(['eligible','worst','name'],ascending=[False,False,True]);selected=final[final.eligible].head(3).name.tolist()
    final.to_csv(OUT/'stress_ranking.csv',index=False);rank.to_csv(OUT/'base_ranking.csv')
    (OUT/'selection.json').write_text(json.dumps(dict(shortlist=shortlist,selected=selected,research_pass=final[final.research_pass].name.tolist(),approved=[],reason='Reused2026, no independent confirmation'),indent=2))
    for name in selected+list(parents)+['momentum_parent','control']:
        for scenario,cost,delay in STRESS:evaluate(name,'2026-10-19','2026-11-18',scenario,cost,delay)
    attribution=[];usage=[]
    for c in grid:
        p=parent(c)
        for a,b in periods:
            for scenario,cost,delay in STRESS:
                for t in logs[p,a,b,scenario]:
                    k=t['signal_index'];s=masks[c['name'],delay][k];baseline=masks[p,delay][k]
                    attribution.append(dict(name=c['name'],parent=p,start=a,scenario=scenario,identical_roles=bool(np.array_equal(s,baseline)),candidate_active=bool(np.any(s)),baseline_net=t['net_return']))
    pd.DataFrame(attribution).groupby(['name','parent','start','scenario','identical_roles','candidate_active']).baseline_net.agg(['count','mean','sum']).to_csv(OUT/'fixed_parent.csv')
    for key,log in logs.items():
        name,start,end,scenario=key
        for symbol in data.symbols:usage.append(dict(name=name,start=start,scenario=scenario,symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in log)))
    pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False);pd.DataFrame(rows).to_csv(OUT/'all_evaluations.csv',index=False)
    pd.DataFrame(rows)[lambda x:x.start=='2026-10-19'].to_csv(OUT/'diagnostic.csv',index=False)
    hashes={c['name']:hashlib.sha256(masks[c['name'],0][times<pd.Timestamp('2026-10-19',tz='UTC')].tobytes()).hexdigest() for c in grid}
    (OUT/'aliases.json').write_text(json.dumps(dict(hashes=hashes,distinct=len(set(hashes.values()))),indent=2))
    (OUT/'manifest.json').write_text(json.dumps(dict(status='COMPLETE_RESEARCH_ONLY',engine_calls=len(rows),candidates=16,shortlist=len(shortlist),selected=selected,approved=[],input_sha256=hashlib.sha256(INPUT.read_bytes()).hexdigest(),prefix_checks=48,independent_validation=False,news_macro=False,orders=0,hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['scripts/structural_grid_20261118.py','scripts/structural_signals_20261118.py','scripts/episode_signals_20261118.py','scripts/five_minute_grid_20261118.py','configs/win60_search.yaml','src/autogrid/engine.py']}),indent=2))
    print(final.to_string(index=False));print('calls',len(rows),'selected',selected)
if __name__=='__main__':
    fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    try:main()
    finally:(OUT/'RUNNING.lock').unlink()
