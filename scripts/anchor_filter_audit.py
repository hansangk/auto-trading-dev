"""Separate fixed-opportunity attribution from executable filter replay."""
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
import tqqq_bitcoin_pair_retry as base
from structure_mtf_retry import structure
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec

OUT=Path('runs/anchor_filter_audit')
STRESSES=[(1.,0),(2.,0),(1.,1)]


def masks(direction,two,daily,eff):
    return {'anchor':np.ones(len(direction),bool),
            'two_agree':direction*two>0,'two_oppose':direction*two<0,
            'daily_agree':direction*daily>0,'daily_oppose':direction*daily<0,
            'both_agree':(direction*two>0)&(direction*daily>0),
            'either_agree':(direction*two>0)|(direction*daily>0),
            'eff_low':eff<.2,'eff_mid':(eff>=.2)&(eff<.4),
            'eff_high':eff>=.4,'eff_not_high':eff<.4}


def attribute(log,mask):
    buckets={'admitted':[],'rejected':[]}
    for t in log:
        buckets['admitted' if mask[t['signal_index']] else 'rejected'].append(t['net_return'])
    return [dict(bucket=k,rounds=len(v),sum_net_return=float(np.sum(v)),
                 mean_net_return=float(np.mean(v)) if v else None,
                 wins=sum(x>0 for x in v)) for k,v in buckets.items()]


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    original,times,_=base.context();local=times.tz_convert('America/New_York')
    keep=(local.minute==30)&(local.hour>=9)&(local.hour<16)
    data=replace(original,timestamps=original.timestamps[keep],**{k:getattr(original,k)[keep] for k in ('open','high','low','close','volume')})
    times=times[keep];ratio=pd.Series(np.log(data.close[:,0]/data.close[:,1]))
    base.CACHE['x']=data,times,ratio
    score=base.pair_signal(dict(mode='dual_momentum',window=24,threshold=.75))
    filters=masks(score[:,0],*structure(times,ratio))
    spec=StrategySpec('anchor_audit',('dual_momentum',),(1.,),1,1,4,60.,3.,2)
    bounds={'2025H1':('2025-01-01','2025-07-01'),'2025H2':('2025-07-01','2026-01-01'),'2026':('2026-01-01','2026-11-14')}
    manifest=dict(source_sha256=hashlib.sha256(Path('runs/tqqq_bitcoin_retry/yahoo_1h.csv').read_bytes()).hexdigest(),
        policies=list(filters),selection='Require >=20 rounds per development scenario for diagnostic shortlist; sort worst net return then mean then ID; top 3 plus anchor. Promotion requires every development scenario positive AND better than anchor; 2026 cannot alter selection.',
        change_to_retry='One-factor ablation; fixed anchor entry/exit parameters; frozen-ledger attribution distinguished from full replay; explicit reject gate; no 2026 winner picking.',
        warning='All periods reused, no independent holdout. Attribution sums are NOT portfolio returns. Account risk unchanged. No news/macro.')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    rows=[];attr=[];ledgers=[]
    def evaluate(period,ids,record=False):
        a,b=[int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in bounds[period]]
        for cost,delay in STRESSES:
            anchor_log=[]
            baseline=run_backtest(data,score,spec,base.CFG.execution,base.CFG.risk,base.CFG.capital,a,b,cost,delay,exit_mode='joint_close',trade_log=anchor_log)
            for name in ids:
                masked=score.copy();masked[~filters[name]]=0
                if name=='anchor':r,log=baseline,anchor_log
                else:
                    log=[]
                    r=run_backtest(data,masked,spec,base.CFG.execution,base.CFG.risk,base.CFG.capital,a,b,cost,delay,exit_mode='joint_close',trade_log=log)
                assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
                rows.append(dict(id=name,period=period,cost=cost,delay=delay,delta_anchor=r.total_return-baseline.total_return,**r.to_dict()))
                for t in attribute(anchor_log,filters[name]):attr.append(dict(id=name,period=period,cost=cost,delay=delay,**t))
                if record:
                    for t in log:ledgers.append(dict(candidate=name,period=period,cost=cost,delay=delay,**t))
    for p in ('2025H1','2025H2'):evaluate(p,list(filters))
    dev=pd.DataFrame(rows);dev.to_csv(OUT/'development.csv',index=False)
    rank=dev[dev.id!='anchor'].groupby('id').agg(worst_return=('total_return','min'),mean_return=('total_return','mean'),
        worst_delta=('delta_anchor','min'),min_rounds=('rounds','min'),positive_scenarios=('total_return',lambda s:int((s>0).sum()))).reset_index()
    rank['eligible_diagnostic']=rank.min_rounds>=20
    rank['promotion_pass']=(rank.positive_scenarios==6)&(rank.worst_delta>0)&rank.eligible_diagnostic
    rank=rank.sort_values(['eligible_diagnostic','worst_return','mean_return','id'],ascending=[False,False,False,True])
    rank.to_csv(OUT/'ranking.csv',index=False)
    selected=rank[rank.eligible_diagnostic].head(3).id.tolist()
    (OUT/'selection.json').write_text(json.dumps(dict(selected_ids=selected,promotion_pass=rank[rank.promotion_pass].id.tolist()),indent=2))
    evaluate('2026',['anchor']+selected,True)
    frame=pd.DataFrame(rows);frame[frame.period=='2026'].to_csv(OUT/'diagnostic.csv',index=False)
    pd.DataFrame(attr).to_csv(OUT/'opportunity_attribution.csv',index=False)
    pd.DataFrame(ledgers).to_json(OUT/'diagnostic_ledger.jsonl',orient='records',lines=True)
    manifest.update(account_evaluations=len(frame),development_evaluations=len(dev),diagnostic_evaluations=int((frame.period=='2026').sum()))
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(rank.to_string(index=False))
    print(frame[frame.period=='2026'][['id','cost','delay','total_return','rounds','win_rate','max_drawdown']].to_string(index=False))


if __name__=='__main__':main()
