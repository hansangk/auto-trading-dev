"""Preregistered fixed Nasdaq participation audit; no strategy selection/refit."""
from pathlib import Path
from dataclasses import asdict
import json,hashlib,os
import pandas as pd
import numpy as np
from autogrid.data import load_market_data
from autogrid.engine import run_backtest,AccountState
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG
from hourly_night_signals_20261119 import candidates,signals
from nasdaq_gate_controls_20261119 import build_controls
from nasdaq_gate_statistics_20261119 import matched_effect
from session_signal_provenance import mask_session_signals
OUT=Path('runs/nasdaq_gate_audit_20261119_0330');PREV=Path('runs/hourly_clock_retry_20261119_0300');AUDIT=PREV/'audit_v2'
DEV=[('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01')]
DIAG=('2026-01-01','2026-11-14');RECENT=[('2026-08-14','2026-11-14'),('2026-05-14','2026-11-14')]
STRESS=[('base',1,0),('cost2',2,0),('delay1',1,1)]
IDS=['source','qqq_consensus','qqq_gap_side','opposite']+[f'session_cash_{i}' for i in range(4)]

def main():
    if (OUT/'manifest.json').exists():raise SystemExit('Completed run protected')
    for name,h in [('audited_ETF_LOCAL.csv.gz','163e532099c1465e951543680730951b7b29a6d16021ff3affe31c23fd77e3d7'),('context_LOCAL.npz','3811f0891d7579401b560ef00794ca7e318311f929ac1455ce47f2e2204572e0')]:assert hashlib.sha256((AUDIT/name).read_bytes()).hexdigest()==h
    data=load_market_data(AUDIT/'audited_ETF_LOCAL.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);ny=times.tz_convert('America/New_York');days=np.asarray(ny.strftime('%Y-%m-%d'))
    with np.load(AUDIT/'context_LOCAL.npz') as f:ctx={k:f[k] for k in f.files}
    scores,metadata=build_controls(data,times,ctx);assert all(metadata['identities'][x] for x in ['old_source_array_exact','session_fields_frozen','source_equals_day_gated_parent','qqq_regime_side_equals_source','qqq_hour_side_equals_source'])
    (OUT/'control_definitions.json').write_text(json.dumps(metadata,indent=2))
    preflight=[];hashes={}
    for n,s in scores.items():
        for a,b in DEV:
            mask=(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'));event=np.any(s,axis=1)&mask
            preflight.append(dict(name=n,start=a,end_exclusive=b,onsets=int(event.sum()),active_days=len(set(days[event]))))
        hashes[n]=hashlib.sha256(s[times<pd.Timestamp(DIAG[0],tz='UTC')].tobytes()).hexdigest()
    pd.DataFrame(preflight).to_csv(OUT/'return_blind_preflight.csv',index=False)
    # Every original QQQ parent event; common support for both entry latencies.
    labels=[];directions=[];parent=scores['qqq_consensus']
    for a,b in DEV+[DIAG]+RECENT:
        for k in np.flatnonzero(np.any(parent,axis=1)):
            if not pd.Timestamp(a,tz='UTC')<=times[k]<pd.Timestamp(b,tz='UTC'):continue
            last=k
            while last+1<len(times) and days[last+1]==days[k]:last+=1
            end=min(k+4,last)
            if k+2>end:continue
            j=int(np.flatnonzero(parent[k])[0]);admit=int(np.any(scores['source'][k]));regime=int(np.sign(ctx['qqq_regime5'][k]));gap=int(np.sign(ctx['qqq_gap'][k]));decision=min(ny[k]+pd.Timedelta(hours=1),ny[k].normalize()+pd.Timedelta(hours=16));early=int(decision.hour*60+decision.minute<=750);stratum=f'{regime}|{gap}|{early}'
            for delay in (0,1):
                gross=.15*(data.close[end,j]/data.open[k+1+delay,j]-1);cost=.15*.00046;net=gross-cost
                labels.append(dict(start=a,end_exclusive=b,delay=delay,day=days[k],event=k,stratum=stratum,admit=admit,gross=gross,cost=cost,net=net))
                if admit:
                    for n in ['qqq_gap_side','opposite','hash_side_0','hash_side_1']:
                        cols=np.flatnonzero(scores[n][k]);cg=.15*np.sum(data.close[end,cols]/data.open[k+1+delay,cols]-1);cc=.15*len(cols)*.00046
                        directions.append(dict(name=n,start=a,end_exclusive=b,delay=delay,day=days[k],event=k,source_net=net,control_net=cg-cc,delta=net-cg+cc))
    lf=pd.DataFrame(labels);lf.to_csv(OUT/'opportunity_labels_LOCAL.csv',index=False);df=pd.DataFrame(directions);df.to_csv(OUT/'direction_labels_LOCAL.csv',index=False)
    lf.groupby(['start','end_exclusive','delay','admit']).agg(events=('net','size'),days=('day','nunique'),mean_gross=('gross','mean'),mean_cost=('cost','mean'),mean_net=('net','mean')).to_csv(OUT/'fixed_opportunity.csv')
    df.groupby(['name','start','end_exclusive','delay']).agg(events=('delta','size'),mean_source_net=('source_net','mean'),mean_control_net=('control_net','mean'),mean_delta=('delta','mean')).to_csv(OUT/'fixed_direction.csv')
    matched=[]
    for a,b in DEV+[DIAG]+RECENT:
        observed=sorted(set(days[(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'))]))
        for delay in (0,1):matched.append(dict(start=a,end_exclusive=b,delay=delay,**matched_effect(lf[(lf.start==a)&(lf.end_exclusive==b)&(lf.delay==delay)],observed)))
    pd.DataFrame(matched).to_csv(OUT/'matched_information.csv',index=False)
    calls=[];rows=[];logs={};cache={};logical={};usage=[]
    def bounds(a,b):return [int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (a,b)]
    def evaluate(n,a,b,scenario='base',cost=1,delay=0):
        key=(n,a,b,scenario)
        if key not in logical:
            lo,hi=bounds(a,b);s=mask_session_signals(scores[n],times,delay,0,'event');digest=hashlib.sha256(s[max(0,lo-1-delay):hi].tobytes()).hexdigest();ck=(a,b,scenario,digest)
            if ck not in cache:
                log=[];r=run_backtest(data,s,StrategySpec(n,(),(),1,1,4,60,3,2),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
                assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return);assert all(0<w<=.150000001 for t in log for w in t['bought_weights'])
                ident=len(calls)+1;call=dict(call_id=ident,kind='reset',first_policy=n,start=a,end_exclusive=b,scenario=scenario,**r.to_dict());calls.append(call);logs[ident]=log;cache[ck]=call
                if ident==1 or ident%20==0:pd.DataFrame(calls).to_csv(OUT/'running_calls.csv',index=False)
            call=cache[ck];row=dict(call);row.update(name=n);rows.append(row);logical[key]=row
            for symbol in data.symbols:usage.append(dict(name=n,start=a,end_exclusive=b,scenario=scenario,call_id=call['call_id'],symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in logs[call['call_id']])))
        return logical[key]
    for a,b in DEV:
        for n in scores:evaluate(n,a,b)
    for a,b in DEV+[DIAG]+RECENT:
        for n in IDS:
            for scenario,cost,delay in STRESS:evaluate(n,a,b,scenario,cost,delay)
    # Monthly choices are imported unchanged: this isolates selected component execution.
    choices=pd.read_csv(PREV/'monthly_choices.csv');choices=choices[choices.months==6];grid={c['name']:c for c in candidates()};old={n:signals(data,times,ctx,grid[n]) for n in choices.selected.unique() if n!='cash'};old['cash']=np.zeros_like(data.close)
    target='night_nasdaq_a5_b0.5';assert all(not n.startswith('night_nasdaq') or n==target for n in old)
    old_gap=signals(data,times,ctx,grid[target],control=True);assert np.array_equal(old[target],scores['source'])
    monthly=[];segments=[];states=[];monthly_usage=[]
    for variant in ['original','replace_qqq_consensus','replace_qqq_gap']:
        for scenario,cost,delay in STRESS:
            state=AccountState();whole=[];maxdd=0.;firsthalt=None
            for choice in choices.itertuples():
                a=choice.month;b=str(min(pd.Timestamp(a)+pd.DateOffset(months=1),pd.Timestamp(DIAG[1])).date());n=choice.selected;s=old[n]
                if n==target and variant=='replace_qqq_consensus':s=scores['qqq_consensus']
                if n==target and variant=='replace_qqq_gap':s=old_gap
                lo,hi=bounds(a,b);log=[];r=run_backtest(data,mask_session_signals(s,times,delay,0,'event'),StrategySpec(n,(),(),1,1,4,60,3,2),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True,account_state=state)
                ident=len(calls)+1;calls.append(dict(call_id=ident,kind='monthly',first_policy=variant,start=a,end_exclusive=b,scenario=scenario,selected=n,**r.to_dict()));logs[ident]=log;whole.extend(log);maxdd=max(maxdd,r.max_drawdown)
                if r.mdd_halt and firsthalt is None:firsthalt=a
                segments.append(dict(variant=variant,scenario=scenario,month=a,selected=n,call_id=ident,**r.to_dict(),state=asdict(state)))
                for symbol in data.symbols:monthly_usage.append(dict(variant=variant,scenario=scenario,month=a,selected=n,symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in log)))
            net=np.array([t['net_return'] for t in whole]);total=state.equity/CFG.capital-1;assert np.isclose(np.prod(1+net)-1,total)
            monthly.append(dict(variant=variant,scenario=scenario,start=DIAG[0],end_exclusive=DIAG[1],total_return=total,rounds=len(net),win_rate=float(np.mean(net>0)) if len(net) else 0.,max_drawdown=maxdd,ever_halted=firsthalt is not None,first_halt_month=firsthalt,final_equity=state.equity,final_peak=state.peak,final_killed=state.killed))
    # Exact frozen-source regressions, including original continuous six-month selector.
    prior=pd.read_csv(PREV/'reset_window_results.csv');reg=[]
    for a,b in DEV+[DIAG]+RECENT:
        for scenario,_,_ in STRESS:
            x=logical[('source',a,b,scenario)];y=prior[(prior.name==target)&(prior.start==a)&(prior.end_exclusive==b)&(prior.scenario==scenario)].iloc[0]
            fields=['total_return','max_drawdown','rounds','win_rate','costs','trades'];assert all(np.isclose(x[k],y[k]) for k in fields);reg.append(dict(kind='source_static',start=a,end_exclusive=b,scenario=scenario,pass_regression=True))
    prevwf=pd.read_csv(PREV/'continuous_walkforward.csv')
    for row in monthly:
        if row['variant']=='original':
            oldrow=prevwf[(prevwf.months==6)&(prevwf.scenario==row['scenario'])].iloc[0];assert all(np.isclose(row[k],oldrow[k]) for k in ['total_return','rounds','win_rate','max_drawdown']);reg.append(dict(kind='original_monthly',scenario=row['scenario'],pass_regression=True))
    pd.DataFrame(reg).to_csv(OUT/'regression.csv',index=False);pd.DataFrame(rows).to_csv(OUT/'account_results.csv',index=False);pd.DataFrame(calls).to_csv(OUT/'actual_calls.csv',index=False);pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False);pd.DataFrame(monthly_usage).to_csv(OUT/'monthly_ticker_usage.csv',index=False)
    pd.DataFrame(monthly).to_csv(OUT/'monthly_counterfactual.csv',index=False);(OUT/'monthly_state_checkpoints.json').write_text(json.dumps(segments,indent=2,default=str))
    for ident,log in logs.items():pd.DataFrame(log).to_json(OUT/f'call_{ident}_ledger_LOCAL.jsonl',orient='records',lines=True)
    for row in segments:
        for t in logs[row['call_id']]:assert set(t['bought_symbols'])<=set(data.symbols) and all(0<w<=.150000001 for w in t['bought_weights'])
    required=DEV+[RECENT[1]];info_pass=all(r['information_pass'] for r in matched if (r['start'],r['end_exclusive']) in required)
    files=['scripts/nasdaq_gate_audit_20261119.py','scripts/nasdaq_gate_controls_20261119.py','scripts/nasdaq_gate_statistics_20261119.py','tests/test_nasdaq_gate_controls.py','tests/test_nasdaq_gate_statistics.py','src/autogrid/engine.py','configs/win60_search.yaml']
    manifest=dict(status='COMPLETE_FIXED_NASDAQ_INFORMATION_AUDIT',engine_calls=len(calls),reset_calls=sum(r['kind']=='reset' for r in calls),monthly_calls=99,logical_reset_cells=len(rows),controls=16,distinct_dev_arrays=len(set(hashes.values())),stress_ids=IDS,information_pass=info_pass,approved=[],new_alpha_trials=0,ETF_sha256=hashlib.sha256((AUDIT/'audited_ETF_LOCAL.csv.gz').read_bytes()).hexdigest(),context_sha256=hashlib.sha256((AUDIT/'context_LOCAL.npz').read_bytes()).hexdigest(),monthly_choices_sha256=hashlib.sha256((PREV/'monthly_choices.csv').read_bytes()).hexdigest(),code_config_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files},independent_validation=False,news_macro=False,orders=0,raw_upload='Not attempted',reused2026=True,selection_note='Nasdaq5frozenafterpreviousrecent6fit; currentauditretrospective,notindependentconfirmatorytest')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(metadata['identities']));print(pd.DataFrame(matched).to_string(index=False));print(pd.DataFrame(monthly).to_string(index=False));print('calls',len(calls))
if __name__=='__main__':
    fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    try:main()
    finally:(OUT/'RUNNING.lock').unlink()
