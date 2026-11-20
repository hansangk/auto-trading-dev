"""Independent trade/source/account/selection/attribution reproducibility checks."""
from pathlib import Path
import json,hashlib,re
import numpy as np
import pandas as pd
from source_activity_context_20261119 import OUT,load_prepared
from inverse_etf_retry_20261116 import CFG
from session_signal_provenance import mask_session_signals

def main():
    plan=json.loads((OUT/'preregistered_plan.json').read_text());manifest=json.loads((OUT/'manifest.json').read_text())
    for p,h in {**plan['hashes'],**manifest['hashes']}.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
    data,times,ctx=load_prepared();days=times.tz_convert('America/New_York').strftime('%Y-%m-%d')
    with np.load(OUT/'scores_LOCAL.npz') as f:score={k:f[k] for k in f.files}
    trace=pd.read_csv(OUT/'source_trace_LOCAL.csv').set_index('index');calls=pd.read_csv(OUT/'actual_calls.csv');rows=pd.read_csv(OUT/'reset_window_results.csv')
    segments=json.loads((OUT/'monthly_state_checkpoints.json').read_text());starts={};initialpeaks={};statechecks=0
    for months in (3,6):
        for scenario in ('base','cost2','delay1'):
            equity=CFG.capital;peak=equity;killed=False
            group=[s for s in segments if s['trailing_months']==months and s['scenario']==scenario]
            assert len(group)==11
            for s in group:
                ident=s['call_id']
                if ident in starts:assert np.isclose(starts[ident],equity,rtol=1e-12) and np.isclose(initialpeaks[ident],peak,rtol=1e-12)
                starts[ident]=equity;initialpeaks[ident]=peak
                assert np.isclose(s['state']['equity'],equity*(1+s['total_return']),rtol=1e-12)
                assert s['state']['peak']>=peak and s['state']['peak']>=s['state']['equity']
                assert not killed or s['state']['killed'];equity=s['state']['equity'];peak=s['state']['peak'];killed=s['state']['killed'];statechecks+=1
    totaltrades=0;Nasdaqtrades=0;crypto=0;two=0;ambiguous=0;alllogs={};sourcechecks=0
    masked={}
    for c in calls.itertuples():
        log=[json.loads(x) for x in (OUT/f'call_{c.call_id}_ledger_LOCAL.jsonl').read_text().splitlines() if x];alllogs[c.call_id]=log
        delay=1 if c.scenario=='delay1' else 0;cost=2 if c.scenario=='cost2' else 1
        key=(c.first_policy,delay)
        if key not in masked:masked[key]=mask_session_signals(score[c.first_policy],times,delay,0,'event')
        signal=masked[key];equity=starts.get(c.call_id,CFG.capital);start_equity=equity;peak=initialpeaks.get(c.call_id,equity);dd=max(0,1-equity/peak);costs=0;nas=btc=one=both=0
        assert len(log)==c.rounds
        for t in log:
            si=int(t['signal_index']);entry=int(times.get_loc(pd.Timestamp(t['entry'])));end=int(times.get_loc(pd.Timestamp(t['end'])))
            assert entry==si+1+delay and days[si]==days[entry]==days[end]
            targets=[data.symbols.index(s) for s in t['bought_symbols']]
            assert set(targets)==set(np.flatnonzero(signal[si]))
            assert len(targets) in (1,2) and all(w==.15 for w in t['bought_weights']) and sum(t['bought_weights'])<=.300000001
            n=any(s in ('TQQQ','SQQQ') for s in t['bought_symbols']);b=any(s in ('IBIT','BITI') for s in t['bought_symbols']);nas+=n;btc+=b;one+=len(targets)==1;both+=len(targets)==2
            if n and (c.first_policy.startswith(('source__','ETF__','no_volume__'))):
                row=trace.loc[si];decision=pd.Timestamp(row.decision);srcend=pd.Timestamp(row.source_end)
                assert srcend==pd.Timestamp(row.ETF_matched_end) and srcend+pd.Timedelta(minutes=5)<=decision and decision-srcend<=pd.Timedelta(minutes=65);sourcechecks+=1
            gross=[sum(w*(getattr(data,f)[end,j]/data.open[entry,j]-1) for w,j in zip(t['bought_weights'],targets)) for f in ('open','close')]
            matches=[np.isclose(v,t['gross_return'],rtol=1e-9,atol=1e-12) for v in gross];assert any(matches);ambiguous+=all(matches)
            expectedcost=sum(t['bought_weights'])*2*(CFG.execution.commission_bps+CFG.execution.slippage_bps)/10000*cost
            assert np.isclose(expectedcost,t['cost_return'],rtol=1e-12)
            assert np.isclose(t['gross_return']-t['cost_return'],t['net_return'],rtol=1e-12,atol=1e-15)
            assert np.isclose(equity*t['net_return'],t['pnl'],rtol=1e-10,atol=1e-7)
            costs+=equity*t['cost_return'];equity*=1+t['net_return'];assert np.isclose(equity,t['equity'],rtol=1e-12)
            peak=max(peak,equity);dd=max(dd,1-equity/peak)
        assert np.isclose(equity/start_equity-1,c.total_return,atol=1e-12) and np.isclose(dd,c.max_drawdown,atol=1e-12)
        assert np.isclose(costs,c.costs,rtol=1e-12,atol=1e-6)
        assert nas==c.Nasdaq_rounds and btc==c.Bitcoin_rounds and one==c.one_role_rounds and both==c.two_role_rounds
        assert np.isclose(np.mean([t['net_return']>0 for t in log]) if log else 0,c.win_rate)
        totaltrades+=len(log);Nasdaqtrades+=nas;crypto+=btc;two+=both
    # Recompute every next-month decision using only the frozen prior windows.
    selection=json.loads((OUT/'selection.json').read_text());pool=selection['diagnostic_pool'];choices=pd.read_csv(OUT/'monthly_choices.csv');decisionchecks=0
    def cell(n,a,b,s):
        q=rows[(rows.name==n)&(rows.start==a)&(rows.end_exclusive==b)&(rows.scenario==s)];assert len(q)==1;return q.iloc[0]
    for d in choices.itertuples():
        month=pd.Timestamp(d.month);a=str((month-pd.DateOffset(months=d.trailing_months)).date());b=str(month.date());assert d.training_start==a and d.training_end_exclusive==b;eligible=[]
        background=[cell('coin_only',a,b,s) for s in ('base','cost2','delay1')]
        for n in pool:
            group=[cell(n,a,b,s) for s in ('base','cost2','delay1')]
            increment=all(x.total_return>y.total_return and x.max_drawdown<=y.max_drawdown for x,y in zip(group,background))
            if min(x.Nasdaq_rounds for x in group)>=20 and min(x.total_return for x in group)>0 and increment and not any(x.mdd_halt or x.hard_halts for x in group):eligible.append((min(x.total_return for x in group),np.mean([x.total_return for x in group]),n))
        expected=max(eligible)[2] if eligible else 'coin_only';assert d.selected==expected and d.eligible_count==len(eligible);decisionchecks+=1
    # Reconstruct exact same-opportunity provenance and publish ONLY aggregates.
    with np.load(OUT/'Nasdaq_scores_LOCAL.npz') as f:raw={k:f[k] for k in f.files}
    original=pd.read_csv(OUT/'fixed_opportunity_labels_LOCAL.csv');enhanced=[];partitions=[]
    for n in selection['source_shortlist']:
        suffix=n[len('source__'):];s=mask_session_signals(raw[n],times,0,0,'event')
        for prefix in ('ETF__','no_volume__'):
            c=mask_session_signals(raw[prefix+suffix],times,0,0,'event')
            for a,b in [('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01')]:
                period=(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'));sa=np.any(s!=0,axis=1)&period;ca=np.any(c!=0,axis=1)&period;same=np.all(s==c,axis=1)&sa&ca;switch=sa&ca&~same
                q=original[(original.name==n)&(original.comparator==prefix)&(original.start==a)].reset_index(drop=True);indices=np.flatnonzero(ca);assert len(q)==len(indices)
                for pos,k in enumerate(indices):
                    entry=k+1;end=min(entry+3,len(times)-1)
                    while end>entry and days[end]!=days[entry]:end-=1
                    ci=np.flatnonzero(c[k]);si=np.flatnonzero(s[k]);cg=.15*np.sum(data.close[end,ci]/data.open[entry,ci]-1)-.15*len(ci)*.00046;sg=.15*np.sum(data.close[end,si]/data.open[entry,si]-1)-.15*len(si)*.00046
                    assert np.isclose(q.iloc[pos].control_net,cg,atol=1e-12) and np.isclose(q.iloc[pos].source_net,sg,atol=1e-12)
                    enhanced.append(dict(**q.iloc[pos].to_dict(),signal_index=int(k),entry_index=int(entry),end_index=int(end)))
                partitions.append(dict(name=n,comparator=prefix,start=a,end_exclusive=b,source_only=int((sa&~ca).sum()),control_only=int((ca&~sa).sum()),retained_same_target=int(same.sum()),switched_target=int(switch.sum()),control_label_events=len(q),mean_control_net=float(q.control_net.mean()),mean_source_net=float(q.source_net.mean()),mean_delta=float(q.delta.mean())))
    pd.DataFrame(enhanced).to_csv(OUT/'fixed_opportunity_provenance_LOCAL.csv',index=False);pd.DataFrame(partitions).to_csv(OUT/'fixed_opportunity_partition.csv',index=False)
    # Policy cash choice differs from months that happened to have no trade.
    monthaudit=[]
    for trailing in (3,6):
        for scenario in ('base','cost2','delay1'):
            group=[s for s in segments if s['trailing_months']==trailing and s['scenario']==scenario]
            monthaudit.append(dict(trailing_months=trailing,scenario=scenario,explicit_whole_cash_policy_months=0,Nasdaq_cash_policy_months=sum(s['selected']=='coin_only' for s in group),actual_zero_trade_months=sum(s['rounds']==0 for s in group),actual_Nasdaq_zero_trade_months=sum(not any(any(x in ('TQQQ','SQQQ') for x in t['bought_symbols']) for t in alllogs[s['call_id']]) for s in group)))
    pd.DataFrame(monthaudit).to_csv(OUT/'monthly_execution_audit.csv',index=False)
    usage=pd.read_csv(OUT/'ticker_usage.csv');assert int(usage.buys.sum())==Nasdaqtrades+crypto
    tests=int(re.search(r'Ran (\d+) tests',(OUT/'tests.log').read_text()).group(1));guards=int(re.search(r'Ran (\d+) tests',(OUT/'resume_guard_tests.log').read_text()).group(1))
    result=dict(status='PASS',actual_engine_calls=len(calls),reset_actual_calls=int((calls.kind=='reset_window').sum()),continuous_actual_calls=int((calls.kind=='continuous_month').sum()),logical_reset_cells=len(rows),same_run_reset_reused_cells=len(rows)-int((calls.kind=='reset_window').sum()),logical_month_segments=len(segments),monthly_state_checks=statechecks,causal_selection_decisions_checked=decisionchecks,trade_records_checked=totaltrades,Nasdaq_buy_round_records=Nasdaqtrades,Bitcoin_buy_round_records=crypto,two_role_round_records=two,source_release_trade_checks=sourcechecks,exact_price_phase_ambiguous_records=ambiguous,fixed_opportunity_provenance_records=len(enhanced),base_suite_tests=tests,resume_guard_tests=guards,max_gross=float(calls.max_actual_gross.max()),engine_unchanged=True,orders=0,raw_upload='not attempted',independent_validation=False,verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));print(usage.groupby('symbol').buys.sum().to_string())

if __name__=='__main__':main()
