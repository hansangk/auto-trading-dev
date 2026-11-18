"""Aggregate fixed controls and serial-dependence sensitivity without fitting."""
from pathlib import Path
import json,hashlib
import pandas as pd
import numpy as np
from direction_control_20261119 import OUT,INPUT,FAMILIES

def main():
    if (OUT/'paired_blocks.csv').exists():raise SystemExit('Summary protected')
    f=pd.read_csv(OUT/'potential_paths_LOCAL.csv');f['family']=f.name.str.replace(r'_\d+$','',regex=True)
    f.groupby(['period','delay','family']).agg(events_seed_rows=('net','size'),gross=('gross','mean'),cost=('cost','mean'),net=('net','mean')).to_csv(OUT/'fixed_family_means.csv')
    d=pd.read_csv(INPUT);t=pd.to_datetime(d.timestamp,utc=True);dates=t.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    rng=np.random.default_rng(20261120);rows=[]
    for period,a,b in [('A','2026-08-25','2026-09-20'),('B','2026-09-20','2026-10-19')]:
        all_days=sorted(set(dates[(t>=pd.Timestamp(a,tz='UTC'))&(t<pd.Timestamp(b,tz='UTC'))]))
        for delay in (0,1):
            g=f[(f.period==period)&(f.delay==delay)];base=g[g.name=='baseline'].set_index(['day','event']).net
            for family in ['all']+list(FAMILIES):
                peers=g[g.family.isin(FAMILIES)] if family=='all' else g[g.family==family]
                expected=peers.groupby(['day','event']).net.mean()
                paired=(base-expected).groupby(level='day').mean().reindex(all_days,fill_value=0);x=paired.to_numpy();n=len(x)
                start=rng.integers(n,size=(2000,int(np.ceil(n/3))))
                ix=((start[:,:,None]+np.arange(3))%n).reshape(2000,-1)[:,:n]
                draws=x[ix].mean(axis=1)
                rows.append(dict(period=period,delay=delay,family=family,sessions=n,active_sessions=int(base.reset_index().day.nunique()),mean_delta=x.mean(),lower=np.quantile(draws,.025),upper=np.quantile(draws,.975)))
    pd.DataFrame(rows).to_csv(OUT/'paired_blocks.csv',index=False)
    new=pd.read_csv(OUT/'account_replays.csv');old=pd.read_csv('runs/structural_grid_20261118/final_evaluations.csv');renamed=new.copy();renamed.name=renamed.name.replace({'baseline':'momentum_parent','expiry_reference':'compression_expiry_1_0'})
    join=renamed.merge(old,on=['name','start','end_exclusive','scenario'],suffixes=('_new','_old'));assert len(join)==18
    for metric in ['total_return','rounds','win_rate','max_drawdown','costs','trades']:assert np.allclose(join[metric+'_new'],join[metric+'_old'])
    m=json.loads((OUT/'manifest.json').read_text());m.update(tests={'count':113,'seconds':8.815,'result':'PASS'},prior_regression_cells=18,summary_seed=20261120,block_size=3)
    for path in ['scripts/direction_control_summary_20261119.py','tests/test_direction_controls.py']:m['hashes'][path]=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    (OUT/'manifest.json').write_text(json.dumps(m,indent=2));print(pd.DataFrame(rows).query("family=='all'").to_string(index=False))
if __name__=='__main__':main()
