"""Resume cached results after alias audit; evaluate only missing unique cells."""
from pathlib import Path
import json,hashlib
import pandas as pd
import numpy as np
from structural_grid_20261118 import OUT,INPUT,STRESS
from structural_signals_20261118 import candidates,signals
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG
from session_signal_provenance import mask_session_signals

def main():
    if (OUT/'unique_selection.json').exists():raise SystemExit('Unique finalization already complete')
    hashes=json.loads((OUT/'aliases.json').read_text())['hashes'];base=pd.read_csv(OUT/'base_ranking.csv')
    seen=set();names=[];alias={}
    for row in base.itertuples():
        h=hashes[row.name]
        if h in seen:alias[row.name]=next(n for n in names if hashes[n]==h)
        else:seen.add(h);names.append(row.name)
    shortlist=[n for n in names if base.set_index('name').loc[n,'min_rounds']>=20][:8]
    existing=pd.read_csv(OUT/'all_evaluations.csv');cache={(r['name'],r['start'],r['end_exclusive'],r['scenario']):r for r in existing.to_dict('records')}
    data=load_market_data(INPUT,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    configs={c['name']:c for c in candidates()};new=[];usage=[]
    def evaluate(name,start,end,scenario,cost,delay):
        key=(name,start,end,scenario)
        if key not in cache:
            score=mask_session_signals(signals(data,times,configs[name]),times,delay,0,'event');a,b=[int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (start,end)];log=[]
            r=run_backtest(data,score,StrategySpec(name,(),(),1,1,12,60,3,2),CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
            assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
            row=dict(name=name,start=start,end_exclusive=end,scenario=scenario,**r.to_dict());cache[key]=row;new.append(row)
            for s in data.symbols:usage.append(dict(name=name,start=start,scenario=scenario,symbol=s,buys=sum(s in t['bought_symbols'] for t in log)))
        return cache[key]
    def parent(c):
        if c['family']=='compression_expiry':return 'compression_parent'
        if c['family']=='adverse_chase':return 'chase1_parent' if c['a']==1 else 'chase3_parent'
        return 'momentum_parent'
    periods=[('2026-08-25','2026-09-20'),('2026-09-20','2026-10-19')];rank=[]
    for n in shortlist:
        cells=[evaluate(n,a,b,*stress) for a,b in periods for stress in STRESS];refs=[cache[parent(configs[n]),r['start'],r['end_exclusive'],r['scenario']] for r in cells]
        eligible=min(r['rounds'] for r in cells)>=20
        passed=eligible and all(r['total_return']>0 and r['total_return']>ref['total_return'] and r['max_drawdown']<=ref['max_drawdown'] and not r['mdd_halt'] for r,ref in zip(cells,refs))
        rank.append(dict(name=n,parent=parent(configs[n]),worst=min(r['total_return'] for r in cells),min_rounds=min(r['rounds'] for r in cells),eligible=eligible,research_pass=passed))
    ranking=pd.DataFrame(rank).sort_values(['eligible','worst','name'],ascending=[False,False,True]);selected=ranking[ranking.eligible].head(3).name.tolist();assert len({hashes[n] for n in selected})==len(selected)
    for n in selected:
        for stress in STRESS:evaluate(n,'2026-10-19','2026-11-18',*stress)
    ranking.to_csv(OUT/'unique_stress_ranking.csv',index=False)
    pd.DataFrame(cache.values()).to_csv(OUT/'final_evaluations.csv',index=False)
    pd.DataFrame(new).to_csv(OUT/'added_unique_evaluations.csv',index=False);pd.DataFrame(usage).to_csv(OUT/'added_ticker_usage.csv',index=False)
    selection=dict(shortlist=shortlist,selected=selected,aliases=alias,research_pass=ranking[ranking.research_pass].name.tolist(),approved=[],additional_calls=len(new),prior_calls=118,total_calls=118+len(new))
    (OUT/'unique_selection.json').write_text(json.dumps(selection,indent=2));print(json.dumps(selection,indent=2))
    m=json.loads((OUT/'manifest.json').read_text());m.update(phase1_calls=m['engine_calls'],additional_unique_calls=len(new),total_calls=118+len(new),distinct_candidates=len(names),final_selected=selected,final_research_pass=selection['research_pass'],finalizer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest());(OUT/'manifest.json').write_text(json.dumps(m,indent=2))
if __name__=='__main__':main()
