"""Two-stage immutable input/support audit then bounded protected backtests."""
from pathlib import Path
from dataclasses import replace
import json,hashlib,os,sys
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG
from release_clock_20261119 import prepare,build_context,policy_scores,POLICIES
from latency_statistics_20261119 import paired_effect

OUT=Path('runs/release_clock_audit_20261119_0630')
DEV=[('2026-08-25','2026-10-01'),('2026-10-01','2026-11-14')]
CONFIGS=[dict(name=f'{p}_{clock}_{hold}',policy=p,clock=clock,hold_minutes=hold)
 for p in POLICIES for clock in ('coarse60','release5') for hold in (180,240)]

def scores_with_full_horizon(score,times,hold):
    # Calendar-only support includes the longest +5min stress. Suppression after
    # the separately computed decision-clock onsets does not create new onsets.
    out=score.copy();decision=times+pd.Timedelta(minutes=5)
    local=decision.tz_convert('America/New_York');close=local.normalize()+pd.Timedelta(hours=16)
    out[np.asarray(decision.tz_convert('America/New_York')+pd.Timedelta(minutes=hold+5)>close)]=0
    return out

def paired_events(scores,times,trace,hold):
    # Nasdaq uses QQQ hourly dependency + frozen session night/regime. Bitcoin
    # uses current BTC dependency + frozen session/first ETF hour. The two
    # clocks may have DIFFERENT events; unmatched events remain unmatched.
    result=[]
    for policy in POLICIES:
        maps={}
        for clock in ('coarse60','release5'):
            s=scores[f'{policy}_{clock}_{hold}'];mapping={}
            for i in np.flatnonzero(np.any(s!=0,axis=1)):
                target=int(np.flatnonzero(s[i])[0]);t=trace.iloc[i]
                dep=int(t.qqq_index if policy in ('nasdaq_source','qqq_parent') else t.btc_index)
                key=(t.day,dep,target)
                if key not in mapping:mapping[key]=int(i)
            maps[clock]=mapping
        for key in sorted(set(maps['coarse60'])&set(maps['release5'])):
            a,b=maps['coarse60'][key],maps['release5'][key]
            result.append(dict(policy=policy,day=key[0],dependency_index=key[1],target=key[2],hold_minutes=hold,
                coarse_signal_index=a,release_signal_index=b,coarse_entry_index=a+1,release_entry_index=b+1))
    return pd.DataFrame(result,columns=['policy','day','dependency_index','target','hold_minutes','coarse_signal_index','release_signal_index','coarse_entry_index','release_entry_index'])

def prepare_phase():
    if (OUT/'input_audit.json').exists():raise SystemExit('Prepared output protected')
    OUT.mkdir(parents=True,exist_ok=False)
    data,times,ctx,trace,meta,args=prepare(OUT)
    raw={clock:policy_scores(data,times,ctx,clock) for clock in ('coarse60','release5')}
    scores={c['name']:scores_with_full_horizon(raw[c['clock']][c['policy']],times,c['hold_minutes']) for c in CONFIGS}
    # Prefixes cut the first hour and a later session; past context/decisions
    # must remain unchanged when unobserved future5m bars are absent.
    prefix_checks=0
    for n in (7,13,101,803):
        d=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
        pc,_,_=build_context(d,times[:n],*args)
        for k in ctx:np.testing.assert_allclose(pc[k],ctx[k][:n],equal_nan=True)
        for clock in ('coarse60','release5'):
            for p,s in policy_scores(d,times[:n],pc,clock).items():np.testing.assert_array_equal(s,raw[clock][p][:n]);prefix_checks+=1
    np.savez_compressed(OUT/'scores_LOCAL.npz',**scores)
    support=[]
    pairframes=[]
    for hold in (180,240):pairframes.append(paired_events(scores,times,trace,hold))
    pairs=pd.concat(pairframes,ignore_index=True);pairs.to_csv(OUT/'paired_events_LOCAL.csv',index=False)
    for c in CONFIGS:
        s=scores[c['name']]
        for a,b in DEV:
            mask=(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'))
            q=pairs[(pairs.policy==c['policy'])&(pairs.hold_minutes==c['hold_minutes'])&(pairs.day>=a)&(pairs.day<b)]
            support.append(dict(**c,start=a,end_exclusive=b,raw_events=int(np.any(s[mask]!=0,axis=1).sum()),matched_events=len(q),matched_days=q.day.nunique()))
    pd.DataFrame(support).to_csv(OUT/'returnblind_support.csv',index=False)
    check=dict(context_prefix_checks=4,score_prefix_checks=prefix_checks,first_hour_buffer_minutes=5,source_buffer_minutes=5,
       no_shifted_dynamic_hourly_row=True,coarse_clock_mask_before_onsets=True)
    (OUT/'causality_checks.json').write_text(json.dumps(check,indent=2))
    (OUT/'configs.json').write_text(json.dumps(CONFIGS,indent=2))
    print(pd.DataFrame(support).to_string(index=False));print(json.dumps(check))

def run_phase():
    if (OUT/'manifest.json').exists():raise SystemExit('Completed output protected')
    if not (OUT/'preregistered_plan.json').exists():raise SystemExit('Preregistered plan missing')
    plan=json.loads((OUT/'preregistered_plan.json').read_text())
    for p,h in plan['prepared_hashes'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
    data=load_market_data(OUT/'five_minute_overlap_LOCAL.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    with np.load(OUT/'scores_LOCAL.npz') as f:scores={k:f[k] for k in f.files}
    cfgs={c['name']:c for c in CONFIGS};rows=[];ledger=[];usage=[]
    def evaluate(c,a,b,cost=1,delay=0):
        start,stop=[int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (a,b)];log=[]
        spec=StrategySpec(c['name'],(),(),1,1,c['hold_minutes']//5,60,3,24)
        r=run_backtest(data,scores[c['name']],spec,CFG.execution,CFG.risk,CFG.capital,start,stop,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
        assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
        for t in log:
            entry=int(times.get_loc(pd.Timestamp(t['entry'])));sig=int(t['signal_index']);end=int(times.get_loc(pd.Timestamp(t['end'])))
            assert entry==sig+1+delay
            assert times[entry].tz_convert('America/New_York').date()==times[sig].tz_convert('America/New_York').date()==times[end].tz_convert('America/New_York').date()
            reserved=entry+c['hold_minutes']//5-1
            assert reserved<len(times) and times[reserved]+pd.Timedelta(minutes=5)-times[entry]==pd.Timedelta(minutes=c['hold_minutes'])
            assert len(t['bought_symbols'])==1 and all(0<w<=.15000001 for w in t['bought_weights'])
        call=len(rows)+1;rows.append(dict(call_id=call,**c,start=a,end_exclusive=b,cost=cost,delay_bars=delay,delay_minutes=5*delay,**r.to_dict()))
        ledger.extend(dict(call_id=call,**t) for t in log)
        for symbol in data.symbols:usage.append(dict(call_id=call,symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in log)))
        pd.DataFrame(rows).to_csv(OUT/'all_evaluations.csv',index=False)
        pd.DataFrame(ledger).to_json(OUT/'ledger_LOCAL.jsonl',orient='records',lines=True)
        return rows[-1]
    for c in CONFIGS:
        for a,b in DEV:evaluate(c,a,b)
    base=pd.DataFrame(rows);rank=base.groupby('name').agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min')).reset_index()
    support=pd.read_csv(OUT/'returnblind_support.csv').groupby('name').agg(min_matched_events=('matched_events','min'),min_matched_days=('matched_days','min'))
    rank=rank.join(support,on='name');rank['sample_eligible']=(rank.min_rounds>=20)&(rank.min_matched_events>=20)&(rank.min_matched_days>=10)
    rank=rank.sort_values(['sample_eligible','worst','mean','name'],ascending=[False,False,False,True]);shortlist=rank[rank.sample_eligible].head(8).name.tolist()
    (OUT/'selection.json').write_text(json.dumps(dict(shortlist=shortlist,diagnostic_selected=[],approved=[],criteria='>=20actualrounds,>=20matched dependency events>=10days in EACH short development window. Long2025/full3m/6m unavailable; no promotion possible.'),indent=2))
    for name in shortlist:
        for a,b in DEV:
            for cost,delay in ((2,0),(1,1)):evaluate(cfgs[name],a,b,cost,delay)
    rank.to_csv(OUT/'ranking.csv',index=False);pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False)
    pairs=pd.read_csv(OUT/'paired_events_LOCAL.csv');labels=[];stats=[]
    for r in pairs.itertuples():
        a,b=int(r.coarse_entry_index),int(r.release_entry_index);h=int(r.hold_minutes)//5;j=int(r.target)
        coarse=.15*(data.close[a+h-1,j]/data.open[a,j]-1-.00046)
        release=.15*(data.close[b+h-1,j]/data.open[b,j]-1-.00046)
        assert times[a+h-1]+pd.Timedelta(minutes=5)-times[a]==times[b+h-1]+pd.Timedelta(minutes=5)-times[b]==pd.Timedelta(minutes=r.hold_minutes)
        labels.append(dict(policy=r.policy,day=r.day,hold_minutes=r.hold_minutes,release_minus_coarse=release-coarse,entry_advance_minutes=(times[a]-times[b]).total_seconds()/60))
    label=pd.DataFrame(labels,columns=['policy','day','hold_minutes','release_minus_coarse','entry_advance_minutes']);label.to_csv(OUT/'paired_path_labels_LOCAL.csv',index=False)
    observed=times.tz_convert('America/New_York').strftime('%Y-%m-%d')
    for p in POLICIES:
        for h in (180,240):
            for a,b in DEV:
                q=label[(label.policy==p)&(label.hold_minutes==h)&(label.day>=a)&(label.day<b)]
                days=sorted(set(observed[(observed>=a)&(observed<b)]))
                effect=paired_effect(q.release_minus_coarse.to_numpy(),q.day.to_numpy(),days)
                stats.append(dict(policy=p,hold_minutes=h,start=a,end_exclusive=b,**effect))
    pd.DataFrame(stats).to_csv(OUT/'paired_path_statistics.csv',index=False)
    files=['scripts/release_clock_20261119.py','scripts/release_clock_retry_20261119.py','src/autogrid/engine.py','configs/win60_search.yaml','scripts/hourly_night_signals_20261119.py','scripts/hourly_clock_audit_20261119.py','scripts/nasdaq_gate_controls_20261119.py','scripts/latency_statistics_20261119.py']
    manifest=dict(status='COMPLETE_SHORT_SAMPLE_REJECTED',engine_calls=len(rows),base_calls=32,stress_calls=len(rows)-32,definitions=16,new_alpha_trials=0,shortlist=shortlist,approved=[],independent_validation=False,news_macro=False,orders=0,raw_upload='not attempted',hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files},engine_unchanged=True,first_ETF_hour_buffer_minutes=5,protection_bar_minutes=5,cooldown_minutes=120,full_horizon=True,new_market_observations=0,periods=DEV)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));print(rank.to_string(index=False));print('new actual calls',len(rows),'trade records',len(ledger),'shortlist',shortlist)

if __name__=='__main__':
    if sys.argv[1:] == ['prepare']:prepare_phase()
    elif sys.argv[1:]==['run']:
        fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
        try:run_phase()
        finally:(OUT/'RUNNING.lock').unlink()
    else:raise SystemExit('Use prepare or run; completed output is protected')
