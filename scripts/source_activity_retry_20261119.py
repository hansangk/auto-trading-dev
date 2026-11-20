"""Bounded32-source/32matched-control grid; frozen Bitcoin background.

Phases: prepare, development, research. The2025pool is persisted before2026.
All actual calls/ledgers checkpoint immediately; same-run exact array aliases
are reused without being counted as new backtests. No market inputs uploaded.
"""
from pathlib import Path
from dataclasses import asdict
import hashlib,json,os,sys
import numpy as np
import pandas as pd
from autogrid.engine import run_backtest,AccountState
from autogrid.strategy import StrategySpec
from source_activity_context_20261119 import OUT,load_prepared,BASE
from source_activity_signals_20261119 import candidates,signals
from hourly_night_signals_20261119 import signals as night_signals
from inverse_etf_retry_20261116 import CFG
from session_signal_provenance import mask_session_signals
from latency_statistics_20261119 import paired_effect

DEV=[('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01')]
STRESS=(('base',1,0),('cost2',2,0),('delay1',1,1))
DIAG=('2026-01-01','2026-11-14')
SPEC=lambda n:StrategySpec(n,(),(),1,1,4,60,3,2)

def dump(path,value):
    # Profit factor is infinite when there are wins and no losses. Keep that
    # exact semantic as a string in shared JSON, never emit invalid Infinity.
    def clean(x):
        if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
        if isinstance(x,(list,tuple)):return [clean(v) for v in x]
        if isinstance(x,(float,np.floating)) and not np.isfinite(x):return 'Infinity' if x>0 else '-Infinity' if x<0 else None
        return x
    path.write_text(json.dumps(clean(value),indent=2,default=str,allow_nan=False)+'\n')

def prepare_scores():
    if (OUT/'score_manifest.json').exists():raise SystemExit('Prepared scores protected')
    data,times,ctx=load_prepared();grid=candidates();raw={};checks=0
    for c in grid:
        for feed,prefix in [('source','source__'),('ETF','ETF__')]:raw[prefix+c['name']]=signals(data,times,ctx,c,feed)
        raw['no_volume__'+c['name']]=signals(data,times,ctx,c,'source',True)
    for n in (103,803,1803):
        from dataclasses import replace
        d=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
        pc={'valid':ctx['valid'][:n],**{feed:{k:v[:n] for k,v in ctx[feed].items()} for feed in ('source','ETF')}}
        for c in grid:
            for feed,prefix in [('source','source__'),('ETF','ETF__')]:
                np.testing.assert_array_equal(signals(d,times[:n],pc,c,feed),raw[prefix+c['name']][:n]);checks+=1
    with np.load(BASE/'audit_v2/context_LOCAL.npz') as f:old={k:f[k] for k in f.files}
    coin=night_signals(data,times,old,dict(family='night_exhaustion',a=.8,b=.25))
    score={n:s+coin for n,s in raw.items()}
    score['coin_only']=coin;score['legacy_nasdaq']=coin+night_signals(data,times,old,dict(family='night_nasdaq',a=5,b=.5))
    np.savez_compressed(OUT/'scores_LOCAL.npz',**score)
    np.savez_compressed(OUT/'Nasdaq_scores_LOCAL.npz',**raw)
    pre=[];aliases={};reps={};days=times.tz_convert('America/New_York').strftime('%Y-%m-%d')
    dev=(times>=pd.Timestamp(DEV[0][0],tz='UTC'))&(times<pd.Timestamp(DEV[-1][1],tz='UTC'))
    for c in grid:
        name=c['name'];s,e,v=[mask_session_signals(raw[p+name],times,0,0,'event') for p in ('source__','ETF__','no_volume__')]
        digest=hashlib.sha256(s[dev].tobytes()).hexdigest();aliases[name]=reps.setdefault(digest,name)
        for a,b in DEV:
            m=(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'))
            changed_etf=np.any(s!=e,axis=1)&m;changed_vol=np.any(s!=v,axis=1)&m
            pre.append(dict(name=name,start=a,end_exclusive=b,source_onsets=int(np.any(s[m]!=0,axis=1).sum()),ETF_onsets=int(np.any(e[m]!=0,axis=1).sum()),no_volume_onsets=int(np.any(v[m]!=0,axis=1).sum()),changed_vs_ETF=int(changed_etf.sum()),changed_ETF_days=len(set(days[changed_etf])),changed_vs_no_volume=int(changed_vol.sum()),changed_volume_days=len(set(days[changed_vol])),source_development_alias=aliases[name]))
    pd.DataFrame(pre).to_csv(OUT/'returnblind_preflight.csv',index=False)
    dump(OUT/'score_manifest.json',dict(status='PREPARED_BEFORE_PNL',source_definitions=32,ETF_controls=32,total_grid_definitions=64,distinct_source_development_arrays=len(reps),aliases=aliases,score_prefix_checks=checks,score_sha256=hashlib.sha256((OUT/'scores_LOCAL.npz').read_bytes()).hexdigest(),Nasdaq_score_sha256=hashlib.sha256((OUT/'Nasdaq_scores_LOCAL.npz').read_bytes()).hexdigest(),fixed_Bitcoin='night_exhaustion(.8,.25) oldauditedhourly; signalarrayfixed,realizedcoinsareNOTcached',capital='EachNasdaq/Bitcoinrole15%,0/1/2active roles,total<=30%unchangedoriginalcap',source_volume_BTC='BLOCKED_quality_positive<95%; notlowparticipation signal',independent_validation=False,orders=0))
    print(pd.DataFrame(pre).to_string(index=False))

class Runner:
    def __init__(self):
        self.data,self.times,self.ctx=load_prepared();self.days=self.times.tz_convert('America/New_York').strftime('%Y-%m-%d')
        plan=json.loads((OUT/'preregistered_plan.json').read_text())
        for p,h in plan['hashes'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
        with np.load(OUT/'scores_LOCAL.npz') as f:self.score={k:f[k] for k in f.files}
        path=OUT/'execution_checkpoint_LOCAL.json';state=json.loads(path.read_text()) if path.exists() else {}
        self.calls=state.get('calls',[]);self.rows=state.get('rows',[]);self.actual=state.get('actual',{});self.logical=state.get('logical',{})
    def save(self):
        dump(OUT/'execution_checkpoint_LOCAL.json',dict(calls=self.calls,rows=self.rows,actual=self.actual,logical=self.logical))
        pd.DataFrame(self.calls).to_csv(OUT/'actual_calls.csv',index=False);pd.DataFrame(self.rows).to_csv(OUT/'reset_window_results.csv',index=False)
    def bounds(self,a,b):return [int(self.times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in (a,b)]
    def readlog(self,ident):return [json.loads(x) for x in (OUT/f'call_{ident}_ledger_LOCAL.jsonl').read_text().splitlines() if x]
    def metrics(self,log):
        Nasdaq=sum(any(s in ('TQQQ','SQQQ') for s in t['bought_symbols']) for t in log)
        btc=sum(any(s in ('IBIT','BITI') for s in t['bought_symbols']) for t in log)
        return dict(Nasdaq_rounds=Nasdaq,Bitcoin_rounds=btc,one_role_rounds=sum(len(t['bought_symbols'])==1 for t in log),two_role_rounds=sum(len(t['bought_symbols'])==2 for t in log),max_actual_gross=max([sum(t['bought_weights']) for t in log],default=0))
    def record(self,n,a,b,scenario,purpose,kind,r,log):
        ident=len(self.calls)+1
        self.calls.append(dict(call_id=ident,kind=kind,first_policy=n,start=a,end_exclusive=b,scenario=scenario,purpose=purpose,**r.to_dict(),**self.metrics(log)))
        for t in log:
            sig=int(t['signal_index']);entry=int(self.times.get_loc(pd.Timestamp(t['entry'])));end=int(self.times.get_loc(pd.Timestamp(t['end'])))
            assert self.days[sig]==self.days[entry]==self.days[end]
            assert all(0<w<=.150000001 for w in t['bought_weights']) and sum(t['bought_weights'])<=.300000001
        # Python float JSON preserves round-trip precision; do not repeat the
        # prior pandas10-decimal fractional-return serialization problem.
        (OUT/f'call_{ident}_ledger_LOCAL.jsonl').write_text(''.join(json.dumps(t,separators=(',',':'))+'\n' for t in log))
        return ident
    def evaluate(self,n,a,b,scenario='base',cost=1,delay=0,purpose='development'):
        lk=json.dumps([n,a,b,scenario]);
        if lk in self.logical:return self.rows[self.logical[lk]]
        lo,hi=self.bounds(a,b);s=mask_session_signals(self.score[n],self.times,delay,0,'event')
        digest=hashlib.sha256(s[max(0,lo-1-delay):hi].tobytes()).hexdigest();ck=json.dumps([a,b,scenario,digest])
        if ck not in self.actual:
            log=[];r=run_backtest(self.data,s,SPEC(n),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
            assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
            self.actual[ck]=self.record(n,a,b,scenario,purpose,'reset_window',r,log)
        ident=self.actual[ck];call=self.calls[ident-1]
        row=dict(name=n,start=a,end_exclusive=b,scenario=scenario,purpose=purpose,call_id=ident,**{k:v for k,v in call.items() if k not in ('call_id','first_policy','kind','start','end_exclusive','scenario','purpose')})
        self.logical[lk]=len(self.rows);self.rows.append(row);self.save();return row

def development():
    if (OUT/'selection.json').exists():raise SystemExit('Development selection protected')
    r=Runner();grid=candidates();base=[]
    for c in grid:
        for feed in ('source__','ETF__'):
            for a,b in DEV:base.append(r.evaluate(feed+c['name'],a,b))
    for n in ('coin_only','legacy_nasdaq'):
        for a,b in DEV:r.evaluate(n,a,b,purpose='fixed_reference')
    frame=pd.DataFrame(base);rank=frame.groupby('name').agg(worst=('total_return','min'),mean=('total_return','mean'),min_Nasdaq_rounds=('Nasdaq_rounds','min'),min_total_rounds=('rounds','min'),any_halt=('mdd_halt','max'),max_hard_halts=('hard_halts','max')).reset_index()
    pre=pd.read_csv(OUT/'returnblind_preflight.csv');meta=json.loads((OUT/'score_manifest.json').read_text());eligible=[]
    for row in rank[rank.name.str.startswith('source__')].itertuples():
        n=row.name[len('source__'):];p=pre[pre.name==n]
        if row.min_Nasdaq_rounds>=20 and not row.any_halt and row.max_hard_halts==0 and p.changed_vs_ETF.min()>=20 and p.changed_ETF_days.min()>=10 and p.changed_vs_no_volume.min()>=20 and p.changed_volume_days.min()>=10 and meta['aliases'][n]==n:eligible.append(row.name)
    ranked=rank.sort_values(['worst','mean','name'],ascending=[False,False,True]);selected=[n for n in ranked.name if n in eligible][:4]
    stressed=[x for n in selected for x in (n,'ETF__'+n[len('source__'):])]
    dump(OUT/'shortlist.json',dict(source_shortlist=selected,stressed_grid_definitions=stressed,budget=8,chosen_from_2025_only=True))
    for n in stressed:
        for a,b in DEV:
            for scenario,cost,delay in STRESS:r.evaluate(n,a,b,scenario,cost,delay)
    # A fixed-reference replay is not another parameter candidate. Added
    # Nasdaq participation must improve the unchanged Bitcoin background.
    for a,b in DEV:
        for scenario,cost,delay in STRESS:r.evaluate('coin_only',a,b,scenario,cost,delay,purpose='fixed_background_reference')
    for n in selected:
        for a,b in DEV:r.evaluate('no_volume__'+n[len('source__'):],a,b,purpose='fixed_single_information_ablation_base_only')
    pool=[];passes=[];rejections=[]
    for c in grid:
        n='source__'+c['name'];row=rank[rank.name==n].iloc[0];p=pre[pre.name==c['name']];reason=[]
        if row.min_Nasdaq_rounds<20:reason.append('NASDAQAUTUALBUY_MIN20_FAILED')
        if row.any_halt or row.max_hard_halts:reason.append('BASE_ACCOUNT_HALT')
        if meta['aliases'][c['name']]!=c['name']:reason.append('EXACT_DEVELOPMENT_ALIAS_OF_'+meta['aliases'][c['name']])
        if p.changed_vs_ETF.min()<20 or p.changed_ETF_days.min()<10:reason.append('SOURCE_VS_ETF_INTERVENTION_SUPPORT_FAILED')
        if p.changed_vs_no_volume.min()<20 or p.changed_volume_days.min()<10:reason.append('VOLUME_REMOVAL_INTERVENTION_SUPPORT_FAILED')
        if n in selected:
            e='ETF__'+c['name'];groups={x:[r.evaluate(x,a,b,s,cost,delay) for a,b in DEV for s,cost,delay in STRESS] for x in (n,e)}
            if all(min(v['Nasdaq_rounds'] for v in g)>=20 and not any(v['mdd_halt'] or v['hard_halts'] for v in g) for g in groups.values()):pool.extend((n,e))
            else:reason.append('PAIRED_STRESS_MIN20_OR_HALT_FAILED')
            if min(v['total_return'] for v in groups[n])<=0:reason.append('NONPOSITIVE_DEVELOPMENT_STRESS')
            if any(s['total_return']<=t['total_return'] for s,t in zip(groups[n],groups[e])):reason.append('NO_UNIFORM_INCREMENT_VS_MATCHED_ETF')
            if any(s['max_drawdown']>t['max_drawdown'] for s,t in zip(groups[n],groups[e])):reason.append('MDD_WORSE_THAN_MATCHED_ETF')
            background=[r.evaluate('coin_only',a,b,s,cost,delay) for a,b in DEV for s,cost,delay in STRESS]
            if any(s['total_return']<=t['total_return'] or s['max_drawdown']>t['max_drawdown'] for s,t in zip(groups[n],background)):reason.append('NO_UNIFORM_IMPROVEMENT_VS_FIXED_BITCOIN_BACKGROUND')
            if any(r.evaluate(n,a,b)['total_return']<=r.evaluate('no_volume__'+c['name'],a,b)['total_return'] for a,b in DEV):reason.append('BASE_VOLUME_ABLATION_NO_UNIFORM_INCREMENT')
            if not reason:passes.append(n)
        elif not reason:reason.append('BELOW_2025_TOP4_SOURCE')
        rejections.append(dict(**c,reasons=reason,independent_history_missing=True))
    ranked.to_csv(OUT/'ranking.csv',index=False)
    dump(OUT/'selection.json',dict(source_shortlist=selected,stressed_grid_definitions=stressed,diagnostic_pool=pool,development_screen_pass=passes,approved=[],rejections=rejections,crypto='Fixed signal only; actualBitcointrades andPNL recomputed ineachwholeaccount'))
    dump(OUT/'development_checkpoint.json',dict(status='DEVELOPMENT_COMPLETE_POOL_FROZEN_BEFORE_2026',actual_calls=len(r.calls),logical_reset_cells=len(r.rows),pool=pool,source_shortlist=selected));r.save()
    print(ranked.to_string(index=False));print('shortlist',selected,'pool',pool,'actualcalls',len(r.calls))

def research():
    if (OUT/'manifest.json').exists():raise SystemExit('Completed run protected')
    r=Runner();selection=json.loads((OUT/'selection.json').read_text());pool=selection['diagnostic_pool'];fitted=[]
    for n in ['coin_only','legacy_nasdaq']+pool:
        for s,c,d in STRESS:r.evaluate(n,*DIAG,s,c,d,purpose='reused2026_diagnostic')
    for months in (3,6):
        end=pd.Timestamp(DIAG[1]);a=str((end-pd.DateOffset(months=months)).date());b=str(end.date())
        for n in pool:
            group=[r.evaluate(n,a,b,s,c,d,purpose=f'recent{months}m_fit') for s,c,d in STRESS]
            background=[r.evaluate('coin_only',a,b,s,c,d,purpose='recent_fixed_background') for s,c,d in STRESS]
            fitted.append(dict(months=months,name=n,start=a,end_exclusive=b,worst_stress=min(x['total_return'] for x in group),min_Nasdaq_rounds=min(x['Nasdaq_rounds'] for x in group),base_delta_vs_coin=group[0]['total_return']-background[0]['total_return'],worst_delta_vs_coin=min(x['total_return']-y['total_return'] for x,y in zip(group,background)),**{k:group[0][k] for k in ('total_return','rounds','Nasdaq_rounds','win_rate','max_drawdown')}))
    ff=pd.DataFrame(fitted,columns=['months','name','start','end_exclusive','worst_stress','min_Nasdaq_rounds','base_delta_vs_coin','worst_delta_vs_coin','total_return','rounds','Nasdaq_rounds','win_rate','max_drawdown']);ff.sort_values(['months','total_return'],ascending=[True,False]).to_csv(OUT/'recent_fitted_ranks.csv',index=False)
    choices={};decisions=[];months=list(pd.date_range('2026-01-01','2026-11-01',freq='MS'))
    for trailing in (3,6):
        for month in months:
            a=str((month-pd.DateOffset(months=trailing)).date());b=str(month.date());eligible=[]
            background=[r.evaluate('coin_only',a,b,s,c,d,purpose='prior_window_fixed_background') for s,c,d in STRESS] if pool else []
            for n in pool:
                group=[r.evaluate(n,a,b,s,c,d,purpose=f'prior{trailing}m_training') for s,c,d in STRESS]
                increment=all(x['total_return']>y['total_return'] and x['max_drawdown']<=y['max_drawdown'] for x,y in zip(group,background))
                if min(x['Nasdaq_rounds'] for x in group)>=20 and min(x['total_return'] for x in group)>0 and increment and not any(x['mdd_halt'] or x['hard_halts'] for x in group):eligible.append((min(x['total_return'] for x in group),np.mean([x['total_return'] for x in group]),n))
            n=max(eligible)[2] if eligible else 'coin_only';choices[(trailing,b)]=n;decisions.append(dict(trailing_months=trailing,month=b,training_start=a,training_end_exclusive=b,selected=n,eligible_count=len(eligible),Nasdaq_cash=n=='coin_only',whole_account_cash=False,pool_frozen_before_2026=True))
    pd.DataFrame(decisions).to_csv(OUT/'monthly_choices.csv',index=False)
    wf=[];segments=[];schedule_cache={}
    for trailing in (3,6):
        schedule=tuple(choices[(trailing,str(m.date()))] for m in months)
        for scenario,cost,delay in STRESS:
            cachekey=(schedule,scenario)
            if cachekey in schedule_cache:
                prior,oldsegs=schedule_cache[cachekey];wf.append(dict(prior,trailing_months=trailing,reused_same_run_schedule=True));segments.extend(dict(s,trailing_months=trailing,reused_same_run_schedule=True) for s in oldsegs);continue
            state=AccountState();whole=[];maxdd=0;halt=None;own=[]
            for month,n in zip(months,schedule):
                a=str(month.date());b=str(min(month+pd.DateOffset(months=1),pd.Timestamp(DIAG[1])).date());lo,hi=r.bounds(a,b);log=[]
                result=run_backtest(r.data,mask_session_signals(r.score[n],r.times,delay,0,'event'),SPEC(n),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True,account_state=state)
                ident=r.record(n,a,b,scenario,f'continuous_prior{trailing}m','continuous_month',result,log);whole.extend(log);maxdd=max(maxdd,result.max_drawdown)
                if result.mdd_halt and halt is None:halt=a
                seg=dict(trailing_months=trailing,scenario=scenario,month=a,selected=n,call_id=ident,**result.to_dict(),state=asdict(state),reused_same_run_schedule=False);segments.append(seg);own.append(seg);r.save()
            net=np.asarray([t['net_return'] for t in whole]);total=state.equity/CFG.capital-1;assert np.isclose(np.prod(1+net)-1,total)
            row=dict(trailing_months=trailing,scenario=scenario,start=DIAG[0],end_exclusive=DIAG[1],total_return=total,rounds=len(whole),Nasdaq_rounds=r.metrics(whole)['Nasdaq_rounds'],Bitcoin_rounds=r.metrics(whole)['Bitcoin_rounds'],win_rate=float(np.mean(net>0)) if len(net) else 0,max_drawdown=maxdd,ever_halted=halt is not None,first_halt_month=halt,final_equity=state.equity,final_peak=state.peak,Nasdaq_cash_months=schedule.count('coin_only'),whole_cash_months=0,reused_same_run_schedule=False)
            wf.append(row);schedule_cache[cachekey]=(row,own)
    pd.DataFrame(wf).to_csv(OUT/'continuous_walkforward.csv',index=False);dump(OUT/'monthly_state_checkpoints.json',segments)
    # Development-only same-opportunity labels: matched ETF event clocks, and
    # no-volume event clocks separately. Onset histories may reshape timing;
    # retain source-only events counts rather than claiming a simple subset.
    with np.load(OUT/'Nasdaq_scores_LOCAL.npz') as f:raw={k:f[k] for k in f.files}
    labels=[];stats=[]
    for n in selection['source_shortlist']:
        suffix=n[len('source__'):];source=mask_session_signals(raw[n],r.times,0,0,'event')
        for comparator in ('ETF__','no_volume__'):
            control=mask_session_signals(raw[comparator+suffix],r.times,0,0,'event')
            for a,b in DEV:
                for k in np.flatnonzero(np.any(control!=0,axis=1)):
                    if not pd.Timestamp(a,tz='UTC')<=r.times[k]<pd.Timestamp(b,tz='UTC'):continue
                    entry=k+1;end=min(entry+3,r.bounds(a,b)[1]-1)
                    while end>entry and r.days[end]!=r.days[entry]:end-=1
                    ci=np.flatnonzero(control[k]);si=np.flatnonzero(source[k]);cg=.15*np.sum(r.data.close[end,ci]/r.data.open[entry,ci]-1)-.15*len(ci)*.00046;sg=.15*np.sum(r.data.close[end,si]/r.data.open[entry,si]-1)-.15*len(si)*.00046
                    labels.append(dict(name=n,comparator=comparator,start=a,day=r.days[k],control_net=cg,source_net=sg,delta=sg-cg,retained=bool(np.array_equal(ci,si)),switched=bool(len(si) and not np.array_equal(ci,si)),removed=not bool(len(si))))
                q=pd.DataFrame([x for x in labels if x['name']==n and x['comparator']==comparator and x['start']==a]);days=sorted(set(r.days[(r.times>=pd.Timestamp(a,tz='UTC'))&(r.times<pd.Timestamp(b,tz='UTC'))]))
                if len(q):effect=paired_effect(q.delta.to_numpy(),q.day.to_numpy(),days)
                else:effect=paired_effect([],[],days)
                stats.append(dict(name=n,comparator=comparator,start=a,end_exclusive=b,**effect))
    pd.DataFrame(labels).to_csv(OUT/'fixed_opportunity_labels_LOCAL.csv',index=False);pd.DataFrame(stats).to_csv(OUT/'fixed_opportunity_statistics.csv',index=False)
    usage=[]
    for c in r.calls:
        log=r.readlog(c['call_id'])
        for symbol in r.data.symbols:usage.append(dict(call_id=c['call_id'],symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in log)))
    pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False)
    files=['scripts/source_activity_context_20261119.py','scripts/source_activity_signals_20261119.py','scripts/source_activity_retry_20261119.py','tests/test_source_activity.py','tests/test_source_activity_context.py','src/autogrid/engine.py','configs/win60_search.yaml']
    manifest=dict(status='COMPLETE_SOURCE_ACTIVITY_RESEARCH',engine_calls=len(r.calls),reset_actual_calls=sum(c['kind']=='reset_window' for c in r.calls),continuous_actual_calls=sum(c['kind']=='continuous_month' for c in r.calls),logical_reset_cells=len(r.rows),logical_month_segments=len(segments),source_candidates=32,matched_ETF_controls=32,nominal_grid_definitions=64,shortlisted_grid_definitions=selection['stressed_grid_definitions'],diagnostic_pool=pool,development_screen_pass=selection['development_screen_pass'],approved=[],engine_unchanged=True,source_BTC_volume_blocked=True,independent_validation=False,news_macro=False,orders=0,raw_upload='not attempted',hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files},cash_note='Nasdaqcash retainsfixedBitcoinpolicy,notwholecash; realizedcointradesalwaysrecomputed',risk='EachNasdaq/Bitcoinrole15%,two<=30%originalcap; notriskmatchedtopriorNasdaq15%audit')
    dump(OUT/'manifest.json',manifest);r.save();print(pd.DataFrame(wf).to_string(index=False));print('actual calls',len(r.calls),'pool',pool)

if __name__=='__main__':
    mode=sys.argv[1:]
    if mode==['prepare']:prepare_scores()
    elif mode in (['development'],['research']):
        fd=os.open(OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
        try:(development if mode==['development'] else research)()
        finally:(OUT/'RUNNING.lock').unlink()
    else:raise SystemExit('Use prepare/development/research; completed phases protected')
