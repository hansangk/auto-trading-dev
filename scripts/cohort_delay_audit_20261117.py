"""2025-only matched signal events: actual ETF entry delay paths, not portfolio returns."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from microstructure_signals_20261117 import candidates,signals
OUT=Path('runs/cohort_routing_retry_20261117');INPUT=Path('runs/inverse_etf_retry_20261116')

def main():
 source=json.loads((INPUT/'source.json').read_text());assert hashlib.sha256((INPUT/'market.csv.gz').read_bytes()).hexdigest()==source['sha256']
 data=load_market_data(INPUT/'market.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);dates=times.tz_convert('America/New_York').strftime('%Y-%m-%d');local=times.tz_convert('America/New_York');grid={c['name']:c for c in candidates()}
 chosen=['gap_absorption_p0.5_q0.6_h4_t3','volume_pressure_p6_q2_h4_t3'];scores={n:signals(data,times,grid[n]) for n in chosen};rows=[]
 for name,score in scores.items():
  for s in range(len(times)-6):
   if not(pd.Timestamp('2025-01-01',tz='UTC')<=times[s]<pd.Timestamp('2026-01-01',tz='UTC')):continue
   if dates[s+1]!=dates[s+5]:continue
   indices=np.flatnonzero(score[s]);period='2025H1' if times[s]<pd.Timestamp('2025-07-01',tz='UTC') else '2025H2'
   for k in indices:
    base=data.close[s+4,k]/data.open[s+1,k]-1
    delay_fixed=data.close[s+4,k]/data.open[s+2,k]-1
    delay_equal=data.close[s+5,k]/data.open[s+2,k]-1
    rows.append(dict(strategy=name,period=period,date=dates[s],month=dates[s][:7],signal_index=s,signal_hour=int(local[s].hour),symbol=data.symbols[k],base_gross_bps=base*1e4,delay_fixedexit_bps=delay_fixed*1e4,delay_equalhold_bps=delay_equal*1e4,base_net_bps=base*1e4-4.6,delay_net_fixed_bps=delay_fixed*1e4-4.6,delay_net_equal_bps=delay_equal*1e4-4.6))
 f=pd.DataFrame(rows);f.to_csv(OUT/'matched_event_paths.csv',index=False)
 for label,groups in [('matched_path_summary',['strategy','period']),('matched_path_attribution',['strategy','period','symbol','month','signal_hour'])]:
  z=f.groupby(groups).agg(events=('base_gross_bps','size'),base_gross_bps=('base_gross_bps','mean'),delay_fixedexit_bps=('delay_fixedexit_bps','mean'),delay_equalhold_bps=('delay_equalhold_bps','mean'),base_net_bps=('base_net_bps','mean'),delay_net_fixed_bps=('delay_net_fixed_bps','mean'),delay_net_equal_bps=('delay_net_equal_bps','mean')).reset_index();z.to_csv(OUT/(label+'.csv'),index=False)
 overlap=[]
 a,b=[scores[n] for n in chosen];active_a=np.any(a!=0,axis=1);active_b=np.any(b!=0,axis=1)
 for label,start,end in [('2025H1','2025-01-01','2025-07-01'),('2025H2','2025-07-01','2026-01-01')]:
  mask=(times>=pd.Timestamp(start,tz='UTC'))&(times<pd.Timestamp(end,tz='UTC'))
  overlap.append(dict(period=label,gap_only=int((mask&active_a&~active_b).sum()),volume_only=int((mask&~active_a&active_b).sum()),both=int((mask&active_a&active_b).sum()),same_vector=int((mask&active_a&active_b&np.all(a==b,axis=1)).sum())))
 pd.DataFrame(overlap).to_csv(OUT/'development_overlap.csv',index=False)
 (OUT/'audit_manifest.json').write_text(json.dumps(dict(source_sha256=source['sha256'],period='2025only',selection='Two names fixed from prior2025development rankings, no2026performance used',warning='Matched potentially overlapping signal events, no stop/cooldown/account halts; perETF means are NOT account returns. Same-cohort labels only where full4bar+delay exists in same local session.'),indent=2))
 print(pd.read_csv(OUT/'matched_path_summary.csv').to_string(index=False));print(pd.DataFrame(overlap).to_string(index=False))
if __name__=='__main__':main()
