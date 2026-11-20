"""Fixed holding/delay factorial, real protected replay and calendar support."""
from pathlib import Path
from dataclasses import replace,asdict
import json,hashlib,os
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest,AccountState,BacktestResult
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG
from hourly_night_signals_20261119 import candidates,signals
from nasdaq_gate_controls_20261119 import build_controls
from session_signal_provenance import mask_session_signals
from latency_schedules_20261119 import configurations,cohort_scores,rawpaired_labels,SCHEDULES,FUTURE_ALPHA_PROPOSALS
from latency_statistics_20261119 import paired_effect
OUT=Path('runs/latency_decomposition_20261119_0600');PREV=Path('runs/hourly_clock_retry_20261119_0300');GATE=Path('runs/nasdaq_gate_audit_20261119_0330');AUDIT=PREV/'audit_v2'
DEV=[('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01')];OTHER=[('2026-01-01','2026-11-14'),('2026-08-14','2026-11-14'),('2026-05-14','2026-11-14')]

def main():
    if (OUT/'manifest.json').exists():raise SystemExit('Completed retry protected')
    audit=json.loads((AUDIT/'audit_manifest.json').read_text())
    for p,h in [(AUDIT/'audited_ETF_LOCAL.csv.gz',audit['ETF_audited_sha256']),(AUDIT/'context_LOCAL.npz',audit['context_sha256'])]:assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    for p in [GATE/'manifest.json',PREV/'manifest.json']:
        for f,h in json.loads(p.read_text())['code_config_sha256'].items():assert hashlib.sha256(Path(f).read_bytes()).hexdigest()==h
    provenance=json.loads((OUT/'cache_provenance.json').read_text())
    for p,v in provenance['verified'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==v['sha256']
    data=load_market_data(AUDIT/'audited_ETF_LOCAL.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);ny=times.tz_convert('America/New_York');days=np.asarray(ny.strftime('%Y-%m-%d'))
    with np.load(AUDIT/'context_LOCAL.npz') as f:ctx={k:f[k] for k in f.files}
    controls,identity=build_controls(data,times,ctx);policy={'source':controls['source'],'parent':controls['qqq_consensus']};cfgs=configurations();scores={c['name']:cohort_scores(policy[c['policy']],times,c['cohort']) for c in cfgs};byname={c['name']:c for c in cfgs}
    (OUT/'signal_hashes.json').write_text(json.dumps({n:hashlib.sha256(s.tobytes()).hexdigest() for n,s in scores.items()},indent=2))
    day_data={};ordinal={}
    for day,ix in pd.Series(np.arange(len(times))).groupby(days):
        indices=ix.to_numpy();d=replace(data,timestamps=data.timestamps[indices],**{k:getattr(data,k)[indices] for k in ('open','high','low','close','volume')});day_data[day]=(d,times[indices])
        for pos,k in enumerate(indices):ordinal[int(k)]=pos
    # Frozenprice labels; no entry signal is derived from these future paths.
    policies={**policy,'bitcoin_frozen_control':signals(data,times,ctx,dict(family='night_exhaustion',a=.8,b=.25))};labels=[]
    for name,s in policies.items():
        for k in np.flatnonzero(np.any(s,axis=1)):
            j=int(np.flatnonzero(s[k])[0]);d,tt=day_data[days[k]];raw=rawpaired_labels(d,tt,ordinal[int(k)],j)
            row=dict(policy=name,day=days[k],event=int(k),ordinal=ordinal[int(k)],symbol=data.symbols[j],common=ordinal[int(k)]<=1,**{flag:raw[flag] for flag in ('sameexitA_C','equalbarsA_B','equalwall4A_B','equalwall3D_C')})
            for family in SCHEDULES:
                x=raw[family];row['net_'+family]=.15*(x['gross_return']-.00046) if x else np.nan;row['minutes_'+family]=x['duration_minutes'] if x else np.nan
            labels.append(row)
    frame=pd.DataFrame(labels);frame.to_csv(OUT/'raw_price_labels_LOCAL.csv',index=False)
    contrasts={'same_exit_C_A':('C','A','sameexitA_C'),'equal_bars_B_A':('B','A','equalbarsA_B'),'equal_wall3_C_D':('C','D','equalwall3D_C'),'equal_wall4_B_A':('B','A','equalwall4A_B'),'holding_A_D':('A','D',None),'holding_B_C':('B','C',None)};stats=[];statcache={}
    for name in policies:
        for a,b in DEV+OTHER:
            all_days=sorted(set(days[(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'))]));f=frame[(frame.policy==name)&(frame.day>=a)&(frame.day<b)]
            for cohort in ('native','common'):
                g=f if cohort=='native' else f[f.common]
                for contrast,(x,y,flag) in contrasts.items():
                    q=g[g['net_'+x].notna()&g['net_'+y].notna()]
                    if flag:q=q[q[flag]]
                    key=(name,a,b,contrast,tuple(q.event));value=q['net_'+x]-q['net_'+y]
                    if key not in statcache:statcache[key]=paired_effect(value.to_numpy(),q.day.to_numpy(),all_days)
                    stats.append(dict(policy=name,start=a,end_exclusive=b,cohort=cohort,contrast=contrast,**statcache[key],mean_minutes_x=float(q['minutes_'+x].mean()) if len(q) else None,mean_minutes_y=float(q['minutes_'+y].mean()) if len(q) else None))
    pd.DataFrame(stats).to_csv(OUT/'paired_path_statistics.csv',index=False)
    calls=[];rows=[];logs={};cached=[];logical={};usage=[];exits=[];old=pd.read_csv(GATE/'account_results.csv');metric_fields=list(BacktestResult.__dataclass_fields__)
    def bounds(a,b):return [int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in (a,b)]
    def inspect_log(log,hold,delay,origin,name,a,b,cost):
        for t in log:
            entry,end=[int(times.searchsorted(pd.Timestamp(t[k]))) for k in ('entry','end')];signal=int(t['signal_index']);assert entry==signal+1+delay and days[entry]==days[end]==days[signal]
            assert len(t['bought_symbols'])==1 and all(0<w<=.150000001 for w in t['bought_weights'])
            last=entry
            while last+1<len(times) and days[last+1]==days[entry]:last+=1
            reserved=min(entry+hold-1,last);assert end<=reserved
            j=data.symbols.index(t['bought_symbols'][0]);w=t['bought_weights'][0];gross=t['gross_return'];op=w*(data.open[end,j]/data.open[entry,j]-1);cl=w*(data.close[end,j]/data.open[entry,j]-1);isopen=bool(np.isclose(gross,op,rtol=0,atol=1e-9));isclose=bool(np.isclose(gross,cl,rtol=0,atol=1e-9));assert isopen or isclose
            endclose=min(ny[end]+pd.Timedelta(hours=1),ny[end].normalize()+pd.Timedelta(hours=16));release=min(ny[reserved]+pd.Timedelta(hours=1),ny[reserved].normalize()+pd.Timedelta(hours=16))
            actual=ny[end] if isopen and not isclose else endclose if isclose and not isopen else None
            exits.append(dict(origin=origin,name=name,start=a,end_exclusive=b,cost=cost,hold=hold,delay=delay,phase='ambiguous_equal_price' if isopen and isclose else 'open' if isopen else 'close',actual_index_earlier_than_reserved=end<reserved,actual_minutes=(actual-ny[entry]).total_seconds()/60 if actual is not None else None,reserved_minutes=(release-ny[entry]).total_seconds()/60,reserved_gap_minutes=(release-actual).total_seconds()/60 if actual is not None else None))
    def evaluate(c,a,b,cost=1):
        key=(c['name'],a,b,cost)
        if key not in logical:
            n=c['name'];hold,delay=c['hold'],c['delay'];cacheable=c['cohort']=='native' and hold==4 and cost==1
            if cacheable:
                parent='source' if c['policy']=='source' else 'qqq_consensus';scenario='base' if delay==0 else 'delay1';r=old[(old.name==parent)&(old.start==a)&(old.end_exclusive==b)&(old.scenario==scenario)].iloc[0]
                metrics={k:r[k] for k in metric_fields};log=[json.loads(x) for x in (GATE/f'call_{int(r.call_id)}_ledger_LOCAL.jsonl').read_text().splitlines() if x];origin='CACHED_OLD_VERIFIED';ident=None;cached.append(dict(name=n,start=a,end_exclusive=b,cost=cost,old_call_id=int(r.call_id),old_policy=parent,old_scenario=scenario))
            else:
                lo,hi=bounds(a,b);log=[];r=run_backtest(data,mask_session_signals(scores[n],times,delay,0,'event'),StrategySpec(n,(),(),1,1,hold,60,3,2),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True);metrics=r.to_dict();ident=len(calls)+1;origin='NEW_CALL';call=dict(call_id=ident,kind='reset',name=n,start=a,end_exclusive=b,cost=cost,hold=hold,delay=delay,**metrics);calls.append(call);logs[ident]=log
                if ident==1 or ident%20==0:pd.DataFrame(calls).to_csv(OUT/'running_calls.csv',index=False)
            assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,metrics['total_return']);inspect_log(log,hold,delay,origin,n,a,b,cost)
            row=dict(**c,start=a,end_exclusive=b,cost=cost,execution=origin,call_id=ident,**metrics);rows.append(row);logical[key]=row
            for symbol in data.symbols:usage.append(dict(name=n,start=a,end_exclusive=b,cost=cost,execution=origin,symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in log)))
        return logical[key]
    for c in cfgs:
        for a,b in DEV:evaluate(c,a,b)
    selected=[c for c in cfgs if c['cohort']=='common' and c['policy']=='parent' and min(logical[(c['name'],a,b,1)]['rounds'] for a,b in DEV)>=20]
    assert len(selected)<=8
    (OUT/'selection.json').write_text(json.dumps(dict(stress_configs=[c['name'] for c in selected],source_common_rejected='Returnblindmax12/15<20',source_equalwall4='NO_SUPPORT',alpha_approved=[]),indent=2))
    for c in selected:
        for a,b in DEV:evaluate(c,a,b,2)
        for a,b in OTHER:
            for cost in (1,2):evaluate(c,a,b,cost)
    # Existingmonthlychoices, changeonlyNasdaqsource schedule; otherassets unchanged.
    choices=pd.read_csv(PREV/'monthly_choices.csv');choices=choices[choices.months==6];grid={c['name']:c for c in candidates()};oldscore={n:signals(data,times,ctx,grid[n]) for n in choices.selected.unique() if n!='cash'};oldscore['cash']=np.zeros_like(data.close);target='night_nasdaq_a5_b0.5';assert np.array_equal(oldscore[target],policy['source'])
    monthly=[];states=[];monthlyusage=[]
    for family,(hold,delay) in SCHEDULES.items():
        for cost in (1,2):
            state=AccountState();all_log=[];maxdd=0.;firsthalt=None
            for choice in choices.itertuples():
                a=choice.month;b=str(min(pd.Timestamp(a)+pd.DateOffset(months=1),pd.Timestamp('2026-11-14')).date());n=choice.selected;h,d=(hold,delay) if n==target else (4,0);lo,hi=bounds(a,b);log=[]
                r=run_backtest(data,mask_session_signals(oldscore[n],times,d,0,'event'),StrategySpec(n,(),(),1,1,h,60,3,2),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,d,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True,account_state=state)
                ident=len(calls)+1;calls.append(dict(call_id=ident,kind='monthly',name=family,start=a,end_exclusive=b,cost=cost,hold=h,delay=d,selected=n,**r.to_dict()));logs[ident]=log;inspect_log(log,h,d,'NEW_CALL',family,a,b,cost);all_log.extend(log);maxdd=max(maxdd,r.max_drawdown)
                if r.mdd_halt and firsthalt is None:firsthalt=a
                states.append(dict(family=family,cost=cost,month=a,selected=n,hold=h,delay=d,call_id=ident,**r.to_dict(),state=asdict(state)))
                for symbol in data.symbols:monthlyusage.append(dict(family=family,cost=cost,month=a,selected=n,symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in log)))
            net=np.array([t['net_return'] for t in all_log]);total=state.equity/CFG.capital-1;assert np.isclose(np.prod(1+net)-1,total)
            monthly.append(dict(family=family,cost=cost,start='2026-01-01',end_exclusive='2026-11-14',total_return=total,rounds=len(net),win_rate=float(np.mean(net>0)) if len(net) else 0.,max_drawdown=maxdd,ever_halted=firsthalt is not None,first_halt_month=firsthalt,final_equity=state.equity,final_peak=state.peak))
    prior=pd.read_csv(GATE/'monthly_counterfactual.csv');reg=[]
    for row in monthly:
        if row['family']=='A':
            oldrow=prior[(prior.variant=='original')&(prior.scenario==('base' if row['cost']==1 else 'cost2'))].iloc[0];assert all(np.isclose(row[k],oldrow[k]) for k in ('total_return','rounds','win_rate','max_drawdown'));reg.append(dict(cost=row['cost'],passed=True))
    pd.DataFrame(reg).to_csv(OUT/'monthly_regression.csv',index=False);pd.DataFrame(monthly).to_csv(OUT/'monthly_schedule_counterfactual.csv',index=False);(OUT/'monthly_state_checkpoints.json').write_text(json.dumps(states,indent=2,default=str));pd.DataFrame(monthlyusage).to_csv(OUT/'monthly_ticker_usage.csv',index=False)
    pd.DataFrame(rows).to_csv(OUT/'account_results.csv',index=False);pd.DataFrame(calls).to_csv(OUT/'actual_calls.csv',index=False);pd.DataFrame(cached).to_csv(OUT/'cached_cells.csv',index=False);pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False);ef=pd.DataFrame(exits);ef.to_csv(OUT/'protected_exit_analysis.csv',index=False)
    ef.groupby(['origin','name','start','end_exclusive','cost','phase']).agg(rounds=('hold','size'),early_index=('actual_index_earlier_than_reserved','sum'),mean_actual_minutes=('actual_minutes','mean'),mean_reserved_minutes=('reserved_minutes','mean'),mean_reserved_gap=('reserved_gap_minutes','mean')).to_csv(OUT/'protected_exit_summary.csv')
    for ident,log in logs.items():pd.DataFrame(log).to_json(OUT/f'call_{ident}_ledger_LOCAL.jsonl',orient='records',lines=True)
    (OUT/'creative_quant_proposals.json').write_text(json.dumps(FUTURE_ALPHA_PROPOSALS,indent=2))
    files=['scripts/latency_decomposition_20261119.py','scripts/latency_schedules_20261119.py','scripts/latency_statistics_20261119.py','tests/test_latency_schedules.py','tests/test_latency_statistics.py','src/autogrid/engine.py','configs/win60_search.yaml']
    manifest=dict(status='COMPLETE_LATENCY_DECOMPOSITION',engine_calls=len(calls),reset_new_calls=sum(c['kind']=='reset' for c in calls),monthly_new_calls=88,cached_old_reset_cells=len(cached),logical_reset_cells=len(rows),control_definitions=16,eligible_stress_configs=[c['name'] for c in selected],strict240_Nasdaq_support=0,source_common_dev_support=[12,15],approved=[],new_alpha_grid=0,ETF_sha256=audit['ETF_audited_sha256'],context_sha256=audit['context_sha256'],code_config_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files},independent_validation=False,news_macro=False,orders=0,raw_upload='Not attempted',monthly_scope='Nasdaq-only executionfamilychanges; othercrypto hold4/delay0; fixedchoices/continuousrisk')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));print(pd.DataFrame(monthly).to_string(index=False));print('newcalls',len(calls),'cached',len(cached),'selected',[c['name'] for c in selected])
if __name__=='__main__':
    fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    try:main()
    finally:(OUT/'RUNNING.lock').unlink()
