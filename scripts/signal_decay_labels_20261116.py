"""Development-only forward path labels; never an entry feature or account return."""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from single_asset_retry_20261116 import signals
OUT=Path('runs/signal_decay_retry_20261116');INPUT=Path('runs/inverse_etf_retry_20261116')

def label_paths(data,times,score):
 dates=times.tz_convert('America/New_York').strftime('%Y-%m-%d');rows=[]
 for i in range(1,len(times)):
  if not(pd.Timestamp('2025-01-01',tz='UTC')<=times[i]<pd.Timestamp('2026-01-01',tz='UTC')):continue
  period='2025H1' if times[i]<pd.Timestamp('2025-07-01',tz='UTC') else '2025H2'
  for delay in (0,1):
   sig=i-1-delay
   if sig<0:continue
   indices=np.flatnonzero(score[sig]);count=len(indices)
   if not count:continue
   for hold in (1,2,4):
    end=i+hold-1
    # All requested closes must exist within the same local regular session.
    if end>=len(times) or dates[end]!=dates[i]:continue
    ret=data.close[end,indices]/data.open[i,indices]-1
    rows.append(dict(period=period,date=dates[i],entry=str(times[i]),signal_index=sig,positions=count,delay=delay,hold=hold,gross_mean=float(ret.mean()),gross_account=float(.15*ret.sum()),tickers=[data.symbols[j] for j in indices]))
 return pd.DataFrame(rows)

def main():
 source=json.loads((INPUT/'source.json').read_text());assert hashlib.sha256((INPUT/'market.csv.gz').read_bytes()).hexdigest()==source['sha256']
 data=load_market_data(INPUT/'market.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
 labels=label_paths(data,times,signals(data,times)['single8']);labels.to_json(OUT/'forward_labels.jsonl',orient='records',lines=True)
 out=[]
 for key,g in labels.groupby(['period','positions','delay','hold']):
  day=g.groupby('date').gross_mean.mean().to_numpy();rng=np.random.default_rng(20261116)
  boot=day[rng.integers(0,len(day),size=(2000,len(day)))].mean(axis=1);lo,hi=np.quantile(boot,[.025,.975])
  out.append(dict(zip(['period','positions','delay','hold'],key))|dict(labels=len(g),days=len(day),mean_gross_bps=g.gross_mean.mean()*1e4,mean_net_base_bps=(g.gross_mean.mean()-.00046)*1e4,mean_net_cost2_bps=(g.gross_mean.mean()-.00092)*1e4,day_equal_mean_bps=day.mean()*1e4,day_boot_low_bps=lo*1e4,day_boot_high_bps=hi*1e4))
 summary=pd.DataFrame(out);summary.to_csv(OUT/'forward_summary.csv',index=False)
 common=labels[labels.hold==4][['period','date','entry','signal_index','positions','delay']]
 paired=labels.merge(common,on=['period','date','entry','signal_index','positions','delay'],how='inner')
 matched=paired.groupby(['period','positions','delay','hold']).agg(labels=('gross_mean','size'),mean_gross=('gross_mean','mean')).reset_index()
 matched['mean_gross_bps']=matched.pop('mean_gross')*1e4;matched.to_csv(OUT/'matched_horizon_summary.csv',index=False)
 print(summary.to_string(index=False))
 (OUT/'label_manifest.json').write_text(json.dumps(dict(status='COMPLETE',source_sha256=source['sha256'],source=source,scope='Only2025 development, overlapping label opportunities, unprotected fixed horizon labels not portfolio returns. Within-date grouping, block CI does not cure serial dependence or multiple testing.',cost_bps=4.6,cost2_bps=9.2,bootstrap_seed=20261116,bootstrap_resamples=2000),indent=2))
if __name__=='__main__':main()
