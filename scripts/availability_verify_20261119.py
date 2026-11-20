"""Independent accounting, literal-support attribution and resume validation."""
from pathlib import Path
import json,hashlib,copy,re
import numpy as np
import pandas as pd
from availability_retry_20261119 import Runner,OUT,PREV,DEV,CFG,load_context
from availability_signals_20261119 import support
from availability_runtime_20261119 import sha,clean,atomic_json
from availability_guarded_research_20261119 import verify_prefix
from session_signal_provenance import mask_session_signals
from latency_statistics_20261119 import paired_effect

def main():
    r=Runner();m=json.loads((OUT/'manifest.json').read_text());amend=json.loads((OUT/'runtime_amendment.json').read_text())
    for p,h in {**m['hashes'],**amend['files']}.items():assert sha(Path(p))==h,p
    cache=json.loads((OUT/'cache_provenance.json').read_text())
    for p,h in cache['remote_git_blobs_verified'].items():
        b=Path(p).read_bytes();assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==h
    calls=r.ck['calls'];rows=pd.DataFrame(r.ck['rows']);starts={};peaks={};physical_months=0
    for saved in r.ck['monthly'].values():
        verify_prefix(saved,OUT,calls,CFG.capital);equity=CFG.capital;peak=equity
        for seg in saved['segments']:
            starts[seg['call_ref']]=equity;peaks[seg['call_ref']]=peak;equity=seg['state']['equity'];peak=seg['state']['peak'];physical_months+=1
    references={**{'new:'+str(c['call_id']):c for c in calls},**r.ck['prior']};new_trades=prior_trades=new_nasdaq=new_btc=both=ambiguous=source_checks=0;usage=[];risk=[];masked={};trace=pd.read_csv(PREV/'source_trace_LOCAL.csv').set_index('index')
    for ref,c in references.items():
        log=r.log(ref);assert sha((OUT if ref.startswith('new:') else PREV)/f'call_{ref.split(":")[1]}_ledger_LOCAL.jsonl')==c['ledger_sha256']
        selected=rows[rows.call_ref==ref]
        n=selected.iloc[0]['name'] if len(selected) else c['first_policy'];scenario=c['scenario'];delay=1 if scenario=='delay1' else 0;cost=2 if scenario=='cost2' else 1
        key=(n,delay)
        if key not in masked:masked[key]=mask_session_signals(r.score[n],r.times,delay,0,'event')
        s=masked[key];equity=starts.get(ref,CFG.capital);initial=equity;peak=peaks.get(ref,equity);dd=max(0,1-equity/peak);fees=0;nas=btc=0;day=None;daily_start=equity;touch=set();minday=0
        assert len(log)==c['rounds']
        for t in log:
            si=int(t['signal_index']);entry=int(r.times.get_loc(pd.Timestamp(t['entry'])));end=int(r.times.get_loc(pd.Timestamp(t['end'])))
            assert entry==si+1+delay and r.days[si]==r.days[entry]==r.days[end]
            targets=[r.data.symbols.index(z) for z in t['bought_symbols']];weights=t['bought_weights'];assert set(targets)==set(np.flatnonzero(s[si])) and all(w==.15 for w in weights) and sum(weights)<=.300000001
            is_nas=any(z in ('TQQQ','SQQQ') for z in t['bought_symbols']);is_btc=any(z in ('IBIT','BITI') for z in t['bought_symbols']);nas+=is_nas;btc+=is_btc
            if is_nas and n.startswith(('source__','ETF__')):
                q=trace.loc[si];src=pd.Timestamp(q.source_end);decision=pd.Timestamp(q.decision);assert src==pd.Timestamp(q.ETF_matched_end) and src+pd.Timedelta(minutes=5)<=decision and decision-src<=pd.Timedelta(minutes=65);source_checks+=1
            gross=[sum(w*(getattr(r.data,f)[end,j]/r.data.open[entry,j]-1) for w,j in zip(weights,targets)) for f in ('open','close')];matches=[np.isclose(v,t['gross_return'],rtol=1e-9,atol=1e-12) for v in gross];assert any(matches);ambiguous+=all(matches)
            expected_cost=sum(weights)*2*(CFG.execution.commission_bps+CFG.execution.slippage_bps)/10000*cost;assert np.isclose(expected_cost,t['cost_return'],rtol=1e-12)
            assert np.isclose(t['gross_return']-t['cost_return'],t['net_return'],atol=1e-15) and np.isclose(equity*t['net_return'],t['pnl'],rtol=1e-10,atol=1e-6)
            if r.days[entry]!=day:day=r.days[entry];daily_start=equity
            fees+=equity*t['cost_return'];equity*=1+t['net_return'];assert np.isclose(equity,t['equity'],rtol=1e-12);peak=max(peak,equity);dd=max(dd,1-equity/peak);minday=min(minday,equity/daily_start-1)
            if equity/daily_start-1<=-CFG.risk.daily_soft_loss:touch.add(day)
            if ref.startswith('new:'):both+=len(targets)==2
        assert np.isclose(equity/initial-1,c['total_return'],atol=1e-12) and np.isclose(dd,c['max_drawdown'],atol=1e-12) and np.isclose(fees,c['costs'],rtol=1e-12,atol=1e-6)
        assert nas==c['Nasdaq_rounds'] and btc==c['Bitcoin_rounds'] and np.isclose(np.mean([t['net_return']>0 for t in log]) if log else 0,c['win_rate'])
        if ref.startswith('new:'):
            new_trades+=len(log);new_nasdaq+=nas;new_btc+=btc
            for z in r.data.symbols:usage.append(dict(call_ref=ref,symbol=z,buys=sum(z in t['bought_symbols'] for t in log)))
        else:prior_trades+=len(log)
        risk.append(dict(call_ref=ref,name=n,start=c['start'],scenario=scenario,postround_soft_threshold_touch_days=len(touch),minimum_daily_postround_return=minday,recorded_hard_halts=c['hard_halts'],recorded_mdd_halt=c['mdd_halt']))
    pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False);pd.DataFrame(risk).to_csv(OUT/'risk_threshold_audit_final.csv',index=False)
    # Literal mask admission on NONE's frozen events differs from the actual
    # gated onset stream. Save both; neither label average is account return.
    with np.load(OUT/'Nasdaq_scores_LOCAL.npz') as f:raw={k:f[k] for k in f.files}
    labels=[];summary=[]
    for feed in ('source','ETF'):
        parent=mask_session_signals(raw[feed+'__none'],r.times,0,0,'event')
        for gate in ('current','L20','L40'):
            gated=mask_session_signals(raw[feed+'__'+gate],r.times,0,0,'event');mask=support(r.data,r.times,r.ctx,gate)
            for a,b in DEV:
                period=(r.times>=pd.Timestamp(a,tz='UTC'))&(r.times<pd.Timestamp(b,tz='UTC'));pa=np.any(parent,axis=1)&period;ga=np.any(gated,axis=1)&period;same=np.all(parent==gated,axis=1)&pa&ga;switch=pa&ga&~same;records=[]
                for k in np.flatnonzero(pa):
                    entry=k+1;end=min(entry+3,len(r.times)-1)
                    while end>entry and r.days[end]!=r.days[entry]:end-=1
                    j=int(np.flatnonzero(parent[k])[0]);net=.15*(r.data.close[end,j]/r.data.open[entry,j]-1-.00046);admit=bool(mask[k]);actual=np.flatnonzero(gated[k]);onsetnet=.15*np.sum(r.data.close[end,actual]/r.data.open[entry,actual]-1)-.15*len(actual)*.00046
                    records.append(dict(feed=feed,gate=gate,start=a,day=r.days[k],signal_index=int(k),entry_index=int(entry),end_index=int(end),admitted=admit,parent_net=net,literal_net=net if admit else 0,onset_net=onsetnet))
                labels.extend(records);q=pd.DataFrame(records);ad=q[q.admitted];rej=q[~q.admitted];adequate=len(ad)>=20 and len(rej)>=20 and ad.day.nunique()>=10 and rej.day.nunique()>=10
                days=sorted(set(r.days[period]));effect=paired_effect((q.literal_net-q.parent_net).to_numpy(),q.day.to_numpy(),days) if adequate else dict(block_lower=None,block_upper=None)
                summary.append(dict(feed=feed,gate=gate,start=a,end_exclusive=b,parent_events=int(pa.sum()),gated_events=int(ga.sum()),literal_admitted=len(ad),literal_rejected=len(rej),source_only=int((ga&~pa).sum()),control_only=int((pa&~ga).sum()),same_target=int(same.sum()),switched_target=int(switch.sum()),mean_parent_net=float(q.parent_net.mean()),mean_literal_net=float(q.literal_net.mean()),mean_literal_delta=float((q.literal_net-q.parent_net).mean()),mean_onset_net=float(q.onset_net.mean()),admitted_mean=float(ad.parent_net.mean()) if len(ad) else None,rejected_mean=float(rej.parent_net.mean()) if len(rej) else None,intervention_support_pass=adequate,block_lower=effect['block_lower'],block_upper=effect['block_upper']))
    pd.DataFrame(labels).to_csv(OUT/'fixed_opportunity_labels_LOCAL.csv',index=False);pd.DataFrame(summary).to_csv(OUT/'fixed_opportunity_summary.csv',index=False)
    proof=json.loads((OUT/'resume_regression_proof.json').read_text());reconstructed=copy.deepcopy(r.ck);reconstructed['calls']=reconstructed['calls'][:proof['new_calls_at_pause']]
    first_key=next(iter(reconstructed['monthly']));first=copy.deepcopy(reconstructed['monthly'][first_key]);first['segments']=first['segments'][:1];reconstructed['monthly']={first_key:first}
    serialized=json.dumps(clean(reconstructed),indent=2,allow_nan=False)+'\n';assert hashlib.sha256(serialized.encode()).hexdigest()==proof['checkpoint_sha256']
    assert first['segments'][0]['state']==proof['carried_state'] and first['segments'][0]['call_ref']==proof['prefix_call_ref']
    assert sum(c['kind']=='continuous_month' and c['start']=='2026-01-01' and c['scenario']=='base' for c in calls)==1
    assert not(OUT/'call_intent_LOCAL.json').exists() and not(OUT/'RUNNING.lock').exists()
    selection=json.loads((OUT/'selection.json').read_text());assert selection['diagnostic_pool']==[]
    assert pd.read_csv(OUT/'recent_fitted_ranks.csv').empty
    assert not any(x['name'].startswith(('source__','ETF__')) and x['start']>='2026-01-01' for x in r.ck['rows'])
    choices=pd.read_csv(OUT/'monthly_choices.csv');assert len(choices)==22 and (choices.selected=='coin_only').all() and (choices.eligible_count==0).all()
    wf=pd.read_csv(OUT/'continuous_walkforward.csv');oldwf=pd.read_csv(PREV/'continuous_walkforward.csv')
    for row in wf.itertuples():
        old=oldwf[(oldwf.trailing_months==row.months)&(oldwf.scenario==row.scenario)].iloc[0]
        for k in ('total_return','rounds','win_rate','max_drawdown'):assert np.isclose(getattr(row,k),old[k],atol=1e-12)
    suite=int(re.search(r'Ran (\d+) tests',(OUT/'tests.log').read_text()).group(1));guard=int(re.search(r'Ran (\d+) tests',(OUT/'prefix_guard_tests.log').read_text()).group(1))
    result=dict(status='PASS',new_actual_calls=len(calls),new_research_reset_calls=sum(c['kind']=='reset_window' for c in calls),new_storage_regression_month_calls=physical_months,prior_unique_calls_reused=len(r.ck['prior']),prior_logical_cells_reused=sum(x['call_ref'].startswith('old:') for x in r.ck['rows']),logical_reset_cells=len(r.ck['rows']),new_trade_records_checked=new_trades,prior_trade_records_checked=prior_trades,new_Nasdaq_buy_rounds=new_nasdaq,new_Bitcoin_buy_rounds=new_btc,new_two_role_rounds=both,source_release_trade_checks=source_checks,price_phase_ambiguous_records_new_plus_prior=ambiguous,physical_month_state_checks=physical_months,logical_month_segments=66,causal_cash_decisions_checked=22,fixed_opportunity_label_records=len(labels),prepause_checkpoint_reconstructed_hash_matches=True,first_month_replay_count=0,old_frozen_background_path_regression_pass=True,base_suite_tests=suite,prefix_guard_tests=guard,diagnostic_candidates=0,new_independent_validation=False,engine_unchanged=True,orders=0,raw_upload='not attempted',verifier_sha256=sha(Path(__file__)))
    atomic_json(OUT/'verification.json',result);print(json.dumps(result,indent=2));print(pd.DataFrame(usage).groupby('symbol').buys.sum().to_string())

if __name__=='__main__':main()
