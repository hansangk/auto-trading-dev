"""Independent accounting, literal-support attribution and resume validation."""
from pathlib import Path
import json,hashlib,copy,re
import numpy as np
import pandas as pd
from venue_latency_retry_20261119 import Runner,OUT,PREV,GRAND,BASE,DEV,CFG,load_context,candidates,pair,hold
from venue_flow_signals_20261119 import _prepare
from availability_runtime_20261119 import sha,clean,atomic_json
from availability_guarded_research_20261119 import verify_prefix
from session_signal_provenance import mask_session_signals
from latency_statistics_20261119 import paired_effect

def main():
    r=Runner();m=json.loads((OUT/'manifest.json').read_text());phase_records=[];calendar=pd.read_csv(BASE/'calendar_schedule.csv',index_col='day');calendar['close']=pd.to_datetime(calendar['close'],utc=True)
    for p,h in m['hashes'].items():assert sha(Path(p))==h,p
    calls=r.ck['calls'];rows=pd.DataFrame(r.ck['rows']);starts={};peaks={};physical_months=0
    for saved in r.ck['monthly'].values():
        verify_prefix(saved,OUT,calls,CFG.capital);equity=CFG.capital;peak=equity
        for seg in saved['segments']:
            starts[seg['call_ref']]=equity;peaks[seg['call_ref']]=peak;equity=seg['state']['equity'];peak=seg['state']['peak'];physical_months+=1
    references={**{'new:'+str(c['call_id']):c for c in calls},**r.ck['prior']};new_trades=prior_trades=new_nasdaq=new_btc=both=ambiguous=source_checks=0;usage=[];risk=[];masked={};trace=pd.read_csv(GRAND/'source_trace_LOCAL.csv').set_index('index')
    for ref,c in references.items():
        log=r.log(ref);assert sha(OUT/f'call_{ref.split(":")[1]}_ledger_LOCAL.jsonl' if ref.startswith('new:') else Path(c['ledger_path']))==c['ledger_sha256']
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
            if is_btc:
                q=trace.loc[si];src=pd.Timestamp(q.source_end);decision=pd.Timestamp(q.decision);assert pd.Timestamp(q.source_start) in r.times and src+pd.Timedelta(minutes=5)<=decision and decision-src<=pd.Timedelta(minutes=65);source_checks+=1
            gross=[sum(w*(getattr(r.data,f)[end,j]/r.data.open[entry,j]-1) for w,j in zip(weights,targets)) for f in ('open','close')];matches=[np.isclose(v,t['gross_return'],rtol=1e-9,atol=1e-12) for v in gross];assert any(matches);ambiguous+=all(matches)
            lo,hi=r.bounds(c['start'],c['end_exclusive']);scheduled=min(hi-1,entry+hold(n)-1)
            while scheduled>entry and r.days[scheduled]!=r.days[entry]:scheduled-=1
            expected=scheduled;phase='CLOSE';gross_weight=sum(weights)
            for j in range(entry,scheduled):
                move=sum(w*(r.data.close[j,k]/r.data.open[entry,k]-1) for w,k in zip(weights,targets))/gross_weight
                if move<=-.006 or move>=.018:expected=j+1;phase='OPEN';break
            assert expected==end
            price=getattr(r.data,'open' if phase=='OPEN' else 'close')[end]
            assert np.isclose(sum(w*(price[k]/r.data.open[entry,k]-1) for w,k in zip(weights,targets)),t['gross_return'],atol=1e-14)
            actual_exit=r.times[end] if phase=='OPEN' else min(r.times[end]+pd.Timedelta(hours=1),calendar.loc[r.days[end],'close'])
            planned_exit=min(r.times[scheduled]+pd.Timedelta(hours=1),calendar.loc[r.days[scheduled],'close'])
            actual_minutes=(actual_exit-r.times[entry]).total_seconds()/60;planned_minutes=(planned_exit-r.times[entry]).total_seconds()/60
            if ref.startswith('new:') and n.startswith(('h120__','h180__')):assert planned_minutes==int(n.split('__')[0][1:]) and actual_minutes<=planned_minutes
            phase_records.append(dict(call_ref=ref,name=n,start=c['start'],end_exclusive=c['end_exclusive'],scenario=scenario,signal_index=si,day=r.days[si],symbols='|'.join(t['bought_symbols']),entry=str(r.times[entry]),scheduled_close=str(planned_exit),actual_exit=str(actual_exit),phase=phase,scheduled_minutes=planned_minutes,actual_minutes=actual_minutes,origin='new' if ref.startswith('new:') else 'prior'))
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
            for z in r.data.symbols:usage.append(dict(call_ref=ref,symbol=z,buys=sum(z in t['bought_symbols'] for t in log),origin='new'))
        else:
            prior_trades+=len(log)
            for z in r.data.symbols:usage.append(dict(call_ref=ref,symbol=z,buys=sum(z in t['bought_symbols'] for t in log),origin='prior'))
        risk.append(dict(call_ref=ref,name=n,start=c['start'],scenario=scenario,postround_soft_threshold_touch_days=len(touch),minimum_daily_postround_return=minday,recorded_hard_halts=c['hard_halts'],recorded_mdd_halt=c['mdd_halt']))
    pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False);pd.DataFrame(risk).to_csv(OUT/'risk_threshold_audit_final.csv',index=False)
    phase=pd.DataFrame(phase_records);phase.to_csv(OUT/'execution_phases_LOCAL.csv',index=False)
    phase.groupby(['origin','name','start','end_exclusive','scenario','phase']).agg(rounds=('actual_minutes','size'),min_actual_minutes=('actual_minutes','min'),max_actual_minutes=('actual_minutes','max'),mean_actual_minutes=('actual_minutes','mean'),min_scheduled_minutes=('scheduled_minutes','min'),max_scheduled_minutes=('scheduled_minutes','max')).reset_index().to_csv(OUT/'execution_phase_summary.csv',index=False)
    prepared=json.loads((OUT/'prepared_manifest.json').read_text());assert not any(x['name'].startswith('h60__') for x in r.ck['rows'])
    choices=pd.read_csv(OUT/'monthly_choices.csv');pool=json.loads((OUT/'selection.json').read_text())['diagnostic_pool'];assert len(choices)==22
    for t in choices.itertuples():assert t.training_end_exclusive==t.month and pd.Timestamp(t.training_start)==pd.Timestamp(t.month)-pd.DateOffset(months=t.months) and (t.selected in pool or t.selected=='cash')
    proof=json.loads((OUT/'resume_proof.json').read_text());call=calls[proof['call_id']-1];assert call['ledger_sha256']==proof['ledger_sha256']
    saved=r.ck['monthly'][proof['schedule_key']];assert saved['segments'][0]['state']==proof['state']
    assert sum(c['kind']=='continuous_month' and c['first_policy']==call['first_policy'] and c['start']==call['start'] and c['scenario']==call['scenario'] for c in calls)==1
    cache=json.loads((OUT/'cache_provenance.json').read_text())
    for p,h in cache['remote_git_blobs_verified'].items():
        raw=Path(p).read_bytes();assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==h
    # Identical h/c signals have distinct holding definitions and references.
    for d in (120,180):
        for arm in ('source','price'):
            np.testing.assert_array_equal(r.score[f'h{d}__{arm}'],r.score[f'c{d}__{arm}'])
            for a,b in DEV:
                g=rows[(rows.name.isin([f'h{d}__{arm}',f'c{d}__{arm}']))&(rows.start==a)&(rows.end_exclusive==b)&(rows.scenario=='base')]
                assert len(g)==2 and g.call_ref.nunique()==2
    assert not(OUT/'call_intent_LOCAL.json').exists() and not(OUT/'RUNNING.lock').exists()
    result=dict(status='PASS',new_actual_calls=len(calls),new_reset_calls=sum(c['kind']=='reset_window' for c in calls),continuous_actual_month_calls=physical_months,prior_unique_calls_reused=len(r.ck['prior']),prior_trade_records_checked=prior_trades,logical_reset_cells=len(rows),new_trade_records_checked=new_trades,new_Nasdaq_buy_rounds=new_nasdaq,new_Bitcoin_buy_rounds=new_btc,new_two_role_rounds=both,source_release_trade_checks=source_checks,phase_price_equal_ambiguous_before_policy_reconstruction=ambiguous,all_exit_phases_reconstructed_from_protective_rule=True,hold_aware_cache_verified=True,exact_scheduled_durations_verified=True,full_month_state_verified=True,strict_prior_month_choices=22,resume_first_prefix_replayed=0,independent_validation=False,orders=0,verifier_sha256=sha(Path(__file__)))
    atomic_json(OUT/'verification.json',result);print(json.dumps(result,indent=2));print(pd.DataFrame(usage).groupby(['origin','symbol']).buys.sum().to_string())

if __name__=='__main__':main()
