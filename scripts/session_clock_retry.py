"""Entry-clock ablation with unchanged anchor and gross leg attribution."""
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
import tqqq_bitcoin_pair_retry as base
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec

OUT=Path('runs/session_clock_retry')
STRESSES=[(1.,0),(2.,0),(1.,1)]
POLICIES={'anchor':tuple(range(9,16)),'open_only':(9,), 'early':(9,10), 'middle':(11,12),
          'late':(13,14,15),'exclude_open':tuple(range(10,16)),
          'exclude_close':tuple(range(9,15)),'first_half':(9,10,11,12),'second_half':(12,13,14,15)}


def clock_mask(times,hours,delay):
    # Clock eligibility is known at order time. Map it to the engine's lagged
    # signal slot without reading any future OHLCV or treating it as a predictor.
    allowed=np.isin(times.tz_convert('America/New_York').hour,hours)
    mask=np.zeros(len(times),bool);lag=1+delay
    mask[:-lag]=allowed[lag:]
    return mask


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    original,times,_=base.context();local=times.tz_convert('America/New_York')
    keep=(local.minute==30)&(local.hour>=9)&(local.hour<16)
    data=replace(original,timestamps=original.timestamps[keep],**{k:getattr(original,k)[keep] for k in ('open','high','low','close','volume')})
    times=times[keep];ratio=pd.Series(np.log(data.close[:,0]/data.close[:,1]));base.CACHE['x']=data,times,ratio
    score=base.pair_signal(dict(mode='dual_momentum',window=24,threshold=.75))
    spec=StrategySpec('session_anchor',('dual_momentum',),(1.,),1,1,4,60.,3.,2)
    bounds={'2025H1':('2025-01-01','2025-07-01'),'2025H2':('2025-07-01','2026-01-01'),'2026':('2026-01-01','2026-11-14')}
    manifest=dict(policies=POLICIES,source_sha256=hashlib.sha256(Path('runs/tqqq_bitcoin_retry/yahoo_1h.csv').read_bytes()).hexdigest(),
        selection='Minimum20 rounds in every development scenario; rank worst return then mean then ID. Freeze top3 before2026. Promotion all6 positive and each better than anchor.',
        change_to_retry='Order-time clock ablation; anchor/exits/exposure fixed; long/short gross attribution and ledger identity checks; fixed entry opportunities versus full replay.',
        warning='Reused periods not independent holdout; Yahoo hourly IBIT proxy. No fresh/news/macro data; clock filters use known order-time timestamps only.')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    rows=[];audit=[];record=[]
    def evaluate(period,names):
        a,b=[int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in bounds[period]]
        for cost,delay in STRESSES:
            baseline_log=[]
            baseline=run_backtest(data,score,spec,base.CFG.execution,base.CFG.risk,base.CFG.capital,a,b,cost,delay,exit_mode='joint_close',trade_log=baseline_log)
            for name in names:
                mask=clock_mask(times,POLICIES[name],delay)
                if name=='anchor':r,log=baseline,baseline_log
                else:
                    gated=score.copy();gated[~mask]=0;log=[]
                    r=run_backtest(data,gated,spec,base.CFG.execution,base.CFG.risk,base.CFG.capital,a,b,cost,delay,exit_mode='joint_close',trade_log=log)
                assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
                for t in log:
                    assert np.isclose(t['long_gross_return']+t['short_gross_return']-t['cost_return'],t['net_return'])
                    assert pd.to_datetime(t['entry'],utc=True).tz_convert('America/New_York').hour in POLICIES[name]
                rows.append(dict(id=name,period=period,cost=cost,delay=delay,delta_anchor=r.total_return-baseline.total_return,**r.to_dict()))
                for keep_bucket in (True,False):
                    subset=[t for t in baseline_log if bool(mask[t['signal_index']])==keep_bucket]
                    audit.append(dict(id=name,period=period,cost=cost,delay=delay,bucket='admitted' if keep_bucket else 'rejected',rounds=len(subset),
                        **{k:sum(t[k] for t in subset) for k in ('long_gross_return','short_gross_return','cost_return','net_return')}))
                if period=='2026':
                    for t in log:record.append(dict(candidate=name,period=period,cost=cost,delay=delay,**t))
    for p in ('2025H1','2025H2'):evaluate(p,list(POLICIES))
    dev=pd.DataFrame(rows);dev.to_csv(OUT/'development.csv',index=False)
    rank=dev[dev.id!='anchor'].groupby('id').agg(worst_return=('total_return','min'),mean_return=('total_return','mean'),worst_delta=('delta_anchor','min'),min_rounds=('rounds','min'),positive_scenarios=('total_return',lambda s:int((s>0).sum()))).reset_index()
    rank['eligible']=rank.min_rounds>=20
    rank['promotion_pass']=rank.eligible&(rank.positive_scenarios==6)&(rank.worst_delta>0)
    rank=rank.sort_values(['eligible','worst_return','mean_return','id'],ascending=[False,False,False,True]);rank.to_csv(OUT/'ranking.csv',index=False)
    selected=rank[rank.eligible].head(3).id.tolist()
    (OUT/'selection.json').write_text(json.dumps(dict(selected_ids=selected,promotion_pass=rank[rank.promotion_pass].id.tolist()),indent=2))
    evaluate('2026',['anchor']+selected)
    frame=pd.DataFrame(rows);diag=frame[frame.period=='2026'];diag.to_csv(OUT/'diagnostic.csv',index=False)
    pd.DataFrame(audit).to_csv(OUT/'leg_attribution.csv',index=False)
    pd.DataFrame(record).to_json(OUT/'diagnostic_ledger.jsonl',orient='records',lines=True)
    manifest.update(evaluations=len(frame),development_evaluations=len(dev),diagnostic_evaluations=len(diag))
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(rank.to_string(index=False));print(diag[['id','cost','delay','total_return','win_rate','rounds','max_drawdown']].to_string(index=False))


if __name__=='__main__':main()
