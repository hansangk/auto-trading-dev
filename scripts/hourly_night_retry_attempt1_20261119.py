"""Frozen2025 selection, reused2026 diagnostics and causal monthly accounts."""
from pathlib import Path
from dataclasses import asdict
import hashlib,json,os
import pandas as pd
import numpy as np
from autogrid.data import load_market_data
from autogrid.engine import run_backtest,AccountState
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG,signals as legacy_signals
from hourly_night_signals_20261119 import candidates,signals
from session_signal_provenance import mask_session_signals
OUT=Path('runs/hourly_clock_retry_20261119_0300')
AUDIT=OUT/'audit_v2'
DEV=[('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01')]
DIAG=('2026-01-01','2026-11-14')
STRESS=(('base',1,0),('cost2',2,0),('delay1',1,1))

def main():
    if (OUT/'manifest.json').exists():raise SystemExit('Completed retry protected')
    audit=json.loads((AUDIT/'audit_manifest.json').read_text())
    for p,h in [(AUDIT/'audited_ETF_LOCAL.csv.gz',audit['ETF_audited_sha256']),(AUDIT/'context_LOCAL.npz',audit['context_sha256'])]:assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    data=load_market_data(AUDIT/'audited_ETF_LOCAL.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);days=times.tz_convert('America/New_York').date
    with np.load(AUDIT/'context_LOCAL.npz') as f:ctx={k:f[k] for k in f.files}
    grid=candidates();score={c['name']:signals(data,times,ctx,c) for c in grid}
    score.update({c['name']+'__control':signals(data,times,ctx,c,control=True) for c in grid})
    score['matched_legacy']=legacy_signals(data,times)['funded_relative'];score['cash']=np.zeros_like(data.close)
    preflight=[];devmask=(times>=pd.Timestamp(DEV[0][0],tz='UTC'))&(times<pd.Timestamp(DEV[-1][1],tz='UTC'));reps={};aliases={}
    for c in grid:
        n=c['name'];digest=hashlib.sha256(score[n][devmask].tobytes()).hexdigest();aliases[n]=reps.setdefault(digest,n)
        for a,b in DEV:
            m=(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'));changed=np.any(score[n]!=score[n+'__control'],axis=1)&m
            preflight.append(dict(name=n,start=a,source_onsets=int(np.any(score[n][m],axis=1).sum()),control_onsets=int(np.any(score[n+'__control'][m],axis=1).sum()),changed_role_decisions=int(changed.sum()),changed_days=len(set(days[changed])),development_alias=aliases[n]))
    pd.DataFrame(preflight).to_csv(OUT/'return_blind_preflight.csv',index=False)
    calls=[];rows=[];actual={};logical={};logs={};usage=[]
    def bounds(a,b):return [int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (a,b)]
    def evaluate(n,a,b,scenario='base',cost=1,delay=0,purpose='development'):
        key=(n,a,b,scenario)
        if key not in logical:
            lo,hi=bounds(a,b);s=mask_session_signals(score[n],times,delay,0,'event');digest=hashlib.sha256(s[max(0,lo-1-delay):hi].tobytes()).hexdigest();ck=(a,b,scenario,digest)
            if ck not in actual:
                log=[];r=run_backtest(data,s,StrategySpec(n,(),(),1,1,4,60,3,2),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
                assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
                assert all(0<w<=.150000001 for t in log for w in t['bought_weights'])
                ident=len(calls)+1;call=dict(call_id=ident,kind='reset_window',first_policy=n,start=a,end_exclusive=b,scenario=scenario,purpose=purpose,**r.to_dict());calls.append(call);actual[ck]=call;logs[ident]=log
            call=actual[ck];ident=call['call_id'];row=dict(name=n,start=a,end_exclusive=b,scenario=scenario,purpose=purpose,call_id=ident,**{k:v for k,v in call.items() if k not in ('kind','first_policy','start','end_exclusive','scenario','purpose')});rows.append(row);logical[key]=row
            for symbol in data.symbols:usage.append(dict(name=n,start=a,scenario=scenario,call_id=ident,symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in logs[ident])))
        return logical[key]
    base=[]
    for c in grid:
        for a,b in DEV:
            base.append(evaluate(c['name'],a,b));evaluate(c['name']+'__control',a,b)
    rank=pd.DataFrame(base).groupby('name').agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min')).sort_values(['worst','mean'],ascending=False)
    shortlist=[n for n in rank.index if rank.loc[n,'min_rounds']>=20 and aliases[n]==n][:8]
    (OUT/'shortlist.json').write_text(json.dumps(dict(shortlist=shortlist,aliases=aliases,selected_using='2025H1/H2 base only'),indent=2))
    for n in ['matched_legacy','cash']+[x for n in shortlist for x in (n,n+'__control')]:
        for a,b in DEV:
            for s,c,d in STRESS:evaluate(n,a,b,s,c,d)
    pool=[];passed=[];failures=[]
    for c in grid:
        n=c['name'];reason=[]
        if rank.loc[n,'min_rounds']<20:reason.append('BASE_MIN20_FAILED')
        if aliases[n]!=n:reason.append('SOURCE_SCORE_ALIAS_OF_'+aliases[n])
        if n in shortlist:
            group=[logical[(n,a,b,s)] for a,b in DEV for s,_,_ in STRESS]
            if min(x['rounds'] for x in group)>=20:pool.append(n)
            else:reason.append('STRESS_MIN20_FAILED')
            if min(x['total_return'] for x in group)<=0:reason.append('NONPOSITIVE_DEVELOPMENT_CELL')
            if any(x['hard_halts'] or x['mdd_halt'] for x in group):reason.append('DEVELOPMENT_HALT')
            if any(logical[(n,a,b,s)]['total_return']<=logical[(n+'__control',a,b,s)]['total_return'] for a,b in DEV for s,_,_ in STRESS):reason.append('NO_UNIFORM_RETURN_INCREMENT_VS_PAIRED_CONTROL')
            if any(logical[(n,a,b,s)]['max_drawdown']>logical[(n+'__control',a,b,s)]['max_drawdown'] for a,b in DEV for s,_,_ in STRESS):reason.append('MDD_WORSE_THAN_PAIRED_CONTROL')
            if any(x['changed_role_decisions']<20 or x['changed_days']<10 for x in preflight if x['name']==n):reason.append('INSUFFICIENT_NIGHT_INTERVENTION')
            if not reason:passed.append(n)
        elif not reason:reason.append('BELOW_GLOBAL_TOP8')
        failures.append(dict(**c,reasons=reason,independent_history_missing=True))
    (OUT/'selection.json').write_text(json.dumps(dict(shortlist=shortlist,diagnostic_pool=pool,development_screen_pass=passed,approved=[],failures=failures),indent=2))
    # Frozen pool is set before any2026 result access.
    for n in ['matched_legacy','cash']+[x for n in pool for x in (n,n+'__control')]:
        for s,c,d in STRESS:evaluate(n,*DIAG,s,c,d,purpose='reused2026_diagnostic')
    fitted=[]
    for months in (3,6):
        end=pd.Timestamp('2026-11-14');a=str((end-pd.DateOffset(months=months)).date());b=str(end.date())
        for n in pool:
            result=[evaluate(n,a,b,s,c,d,purpose=f'recent{months}m_fitted') for s,c,d in STRESS]
            fitted.append(dict(months=months,name=n,start=a,end_exclusive=b,worst_stress=min(r['total_return'] for r in result),min_rounds=min(r['rounds'] for r in result),**{k:result[0][k] for k in ('total_return','rounds','win_rate','max_drawdown')}))
    pd.DataFrame(fitted,columns=['months','name','start','end_exclusive','worst_stress','min_rounds','total_return','rounds','win_rate','max_drawdown']).sort_values(['months','total_return'],ascending=[True,False]).to_csv(OUT/'recent_fitted_ranks.csv',index=False)
    # Causal training: same global2025 pool, preceding3/6months only, atmonthstart.
    decisions=[];month_starts=list(pd.date_range('2026-01-01','2026-11-01',freq='MS'));choices={}
    for months in (3,6):
        for month in month_starts:
            a=str((month-pd.DateOffset(months=months)).date());b=str(month.date());eligible=[]
            for n in pool:
                group=[evaluate(n,a,b,s,c,d,purpose=f'train{months}m') for s,c,d in STRESS]
                if min(r['rounds'] for r in group)>=20 and min(r['total_return'] for r in group)>0 and not any(r['mdd_halt'] or r['hard_halts'] for r in group):eligible.append((min(r['total_return'] for r in group),np.mean([r['total_return'] for r in group]),n))
            selected=max(eligible)[2] if eligible else 'cash';choices[(months,b)]=selected;decisions.append(dict(months=months,month=b,training_start=a,training_end_exclusive=b,eligible_count=len(eligible),selected=selected,pool_frozen_2025=True))
    pd.DataFrame(decisions).to_csv(OUT/'monthly_choices.csv',index=False)
    wf=[];wfsegments=[]
    for months in (3,6):
        for scenario,cost,delay in STRESS:
            state=AccountState();whole=[];maxdd=0.;firsthalt=None
            for month in month_starts:
                a=str(month.date());b=str(min(month+pd.DateOffset(months=1),pd.Timestamp(DIAG[1])).date());n=choices[(months,a)];lo,hi=bounds(a,b);log=[]
                r=run_backtest(data,mask_session_signals(score[n],times,delay,0,'event'),StrategySpec(n,(),(),1,1,4,60,3,2),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True,account_state=state)
                ident=len(calls)+1;calls.append(dict(call_id=ident,kind='continuous_month',first_policy=n,start=a,end_exclusive=b,scenario=scenario,purpose=f'walkforward{months}m',**r.to_dict()));logs[ident]=log;whole.extend(log);maxdd=max(maxdd,r.max_drawdown)
                if r.mdd_halt and firsthalt is None:firsthalt=a
                wfsegments.append(dict(months=months,scenario=scenario,month=a,selected=n,call_id=ident,**r.to_dict(),state=asdict(state)))
            net=np.array([x['net_return'] for x in whole]);total=float(state.equity/CFG.capital-1);assert np.isclose(np.prod(1+net)-1,total)
            wf.append(dict(months=months,scenario=scenario,start=DIAG[0],end_exclusive=DIAG[1],total_return=total,rounds=len(net),win_rate=float(np.mean(net>0)) if len(net) else 0.,max_drawdown=maxdd,ever_halted=firsthalt is not None,first_halt_month=firsthalt,final_equity=state.equity,final_peak=state.peak,final_killed=state.killed,cash_months=sum(x['selected']=='cash' for x in decisions if x['months']==months)))
    pd.DataFrame(wf).to_csv(OUT/'continuous_walkforward.csv',index=False);(OUT/'monthly_state_checkpoints.json').write_text(json.dumps(wfsegments,indent=2,default=str))
    # Fixed-control-cohort labels, clipped common exit. Not account returns.
    attr=[]
    for c in grid:
        n=c['name'];control=score[n+'__control']
        for a,b in DEV:
            for k in np.flatnonzero(np.any(control,axis=1)):
                if not pd.Timestamp(a,tz='UTC')<=times[k]<pd.Timestamp(b,tz='UTC'):continue
                last=k
                while last+1<len(times) and days[last+1]==days[k]:last+=1
                end=min(k+4,last)
                if k+2>end:continue
                original=np.flatnonzero(control[k]);selected=np.flatnonzero(score[n][k])
                if c['family']=='trend_pullback':
                    trend=ctx['btc_trend'+str(c['a'])][k];night=ctx['night_return'][k]
                    selected=original if trend*night>0 and abs(night)>=.5*abs(trend) else np.array([],int)
                for delay in (0,1):
                    cg=.15*np.sum(data.close[end,original]/data.open[k+1+delay,original]-1);cc=.15*len(original)*.00046
                    sg=.15*np.sum(data.close[end,selected]/data.open[k+1+delay,selected]-1);sc=.15*len(selected)*.00046
                    attr.append(dict(name=n,start=a,delay=delay,day=str(days[k]),retained=bool(np.array_equal(original,selected)),switched=bool(len(selected) and not np.array_equal(original,selected)),removed=not bool(len(selected)),control_gross=cg,control_cost=cc,control_net=cg-cc,source_gross=sg,source_cost=sc,source_net=sg-sc))
    af=pd.DataFrame(attr);af.to_csv(OUT/'fixed_control_labels_LOCAL.csv',index=False)
    if len(af):af.groupby(['name','start','delay']).agg(events=('control_net','size'),retained=('retained','sum'),switched=('switched','sum'),removed=('removed','sum'),mean_control_gross=('control_gross','mean'),mean_control_cost=('control_cost','mean'),mean_control_net=('control_net','mean'),mean_source_gross=('source_gross','mean'),mean_source_cost=('source_cost','mean'),mean_source_net=('source_net','mean')).to_csv(OUT/'fixed_opportunity.csv')
    rank.to_csv(OUT/'ranking.csv');pd.DataFrame(rows).to_csv(OUT/'reset_window_results.csv',index=False);pd.DataFrame(calls).to_csv(OUT/'actual_calls.csv',index=False);pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False)
    for ident,log in logs.items():pd.DataFrame(log).to_json(OUT/f'call_{ident}_ledger_LOCAL.jsonl',orient='records',lines=True)
    files=['scripts/hourly_night_retry_20261119.py','scripts/hourly_night_signals_20261119.py','scripts/hourly_clock_audit_20261119.py','tests/test_hourly_night_signals.py','tests/test_hourly_clock_audit.py','src/autogrid/engine.py','configs/win60_search.yaml']
    manifest=dict(status='COMPLETE_HOURLY_NIGHT_RESEARCH',engine_calls=len(calls),reset_window_actual_calls=sum(x['kind']=='reset_window' for x in calls),continuous_calls=66,logical_reset_cells=len(rows),nominal_candidates=16,distinct_source_development_arrays=len(reps),shortlist=shortlist,diagnostic_pool=pool,development_screen_pass=passed,approved=[],data=audit,code_config_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files},independent_validation=False,news_macro=False,orders=0,raw_upload='Not attempted',recent_fit_scope='Only2025frozenpool; fittedrankingnotindependent',monthly='2025poolfrozen before2026; strictlyprior3/6training;6continuousaccounts,flatdayboundary,permanentkillpreserved')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));print(rank.to_string());print('shortlist',shortlist,'pool',pool);print(pd.DataFrame(wf).to_string(index=False));print('actualcalls',len(calls))
if __name__=='__main__':
    fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    try:main()
    finally:(OUT/'RUNNING.lock').unlink()
