"""Independent accounting, literal-support attribution and resume validation."""
from pathlib import Path
import json,hashlib,copy,re
import numpy as np
import pandas as pd
from venue_isolation_retry_20261119 import Runner,OUT,PREV,DEV,CFG,load_context,candidates,pair,prior_name
from venue_flow_signals_20261119 import _prepare
from availability_runtime_20261119 import sha,clean,atomic_json
from availability_guarded_research_20261119 import verify_prefix
from session_signal_provenance import mask_session_signals
from latency_statistics_20261119 import paired_effect

def main():
    r=Runner();m=json.loads((OUT/'manifest.json').read_text())
    for p,h in m['hashes'].items():assert sha(Path(p))==h,p
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
            if is_btc:
                q=trace.loc[si];src=pd.Timestamp(q.source_end);decision=pd.Timestamp(q.decision);assert pd.Timestamp(q.source_start) in r.times and src+pd.Timedelta(minutes=5)<=decision and decision-src<=pd.Timedelta(minutes=65);source_checks+=1
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
            for z in r.data.symbols:usage.append(dict(call_ref=ref,symbol=z,buys=sum(z in t['bought_symbols'] for t in log),origin='new'))
        else:
            prior_trades+=len(log)
            for z in r.data.symbols:usage.append(dict(call_ref=ref,symbol=z,buys=sum(z in t['bought_symbols'] for t in log),origin='prior'))
        risk.append(dict(call_ref=ref,name=n,start=c['start'],scenario=scenario,postround_soft_threshold_touch_days=len(touch),minimum_daily_postround_return=minday,recorded_hard_halts=c['hard_halts'],recorded_mdd_halt=c['mdd_halt']))
    pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False);pd.DataFrame(risk).to_csv(OUT/'risk_threshold_audit_final.csv',index=False)
    attribution=[];labels=[];pool=json.loads((OUT/'selection.json').read_text())['diagnostic_pool']
    for c in candidates():
        if c['arm']!='source' or c['scope']!='coin':continue
        conf=dict(family='flow_trend',efficiency=c['body']/100,flow_threshold=.1,lookback=4)
        _,common,now,prior,mean=_prepare(r.data,r.times,r.ctx,conf);direction=np.sign(now['body']);predicate=(direction*now['flow']>=.1)&(direction*(now['flow']-mean)>0)
        for a,b in DEV:
            q=rows[(rows.name==pair(c['name']))&(rows.start==a)&(rows.end_exclusive==b)&(rows.scenario=='base')].iloc[0];local=[]
            for t in r.log(q.call_ref):
                si=int(t['signal_index']);admit=bool(common[si] and predicate[si]);symbol=t['bought_symbols'][0];onset=bool(r.score[c['name']][si,r.data.symbols.index(symbol)])
                local.append(dict(name=c['name'],start=a,signal_index=si,day=r.days[si],symbol=symbol,literal_admitted=admit,actual_same_source_onset=onset,net_label=t['net_return']))
            labels.extend(local);q=pd.DataFrame(local);ad=q[q.literal_admitted];rej=q[~q.literal_admitted];adequate=min(len(ad),len(rej))>=20 and min(ad.day.nunique(),rej.day.nunique())>=10
            effect=paired_effect(np.where(q.literal_admitted,q.net_label,0)-q.net_label,q.day.to_numpy(),sorted(set(r.days[(r.times>=pd.Timestamp(a,tz='UTC'))&(r.times<pd.Timestamp(b,tz='UTC'))]))) if adequate else dict(block_lower=None,block_upper=None)
            attribution.append(dict(name=c['name'],start=a,end_exclusive=b,control_frozen_rounds=len(q),literal_admitted=len(ad),literal_rejected=len(rej),actual_same_source_onset=int(q.actual_same_source_onset.sum()),admitted_mean_net=ad.net_label.mean(),rejected_mean_net=rej.net_label.mean(),baseline_sum_net=q.net_label.sum(),literal_sum_net=ad.net_label.sum(),adequate_sample=adequate,block_lower=effect['block_lower'],block_upper=effect['block_upper'],NOT_portfolio_return=True))
    pd.DataFrame(labels).to_csv(OUT/'fixed_price_opportunities_LOCAL.csv',index=False);pd.DataFrame(attribution).to_csv(OUT/'fixed_price_attribution.csv',index=False)
    frozen=[];leg=[]
    for c in candidates():
        if c['scope']!='full':continue
        for a,b in DEV:
            q=rows[(rows.name==c['name'])&(rows.start==a)&(rows.end_exclusive==b)&(rows.scenario=='base')].iloc[0];log=r.log(q.call_ref)
            for t in log:
                coin=any(z in ('IBIT','BITI') for z in t['bought_symbols']);nas=any(z in ('TQQQ','SQQQ') for z in t['bought_symbols']);coin_net=t['short_gross_return']-(.000069 if coin else 0)
                frozen.append(dict(name=c['name'],start=a,signal_index=t['signal_index'],coin=coin,nasdaq=nas,original_net=t['net_return'],literal_coin_only_net=coin_net,NOT_replay=True))
    f=pd.DataFrame(frozen);f.to_csv(OUT/'frozen_full_removal_LOCAL.csv',index=False)
    f.groupby(['name','start']).agg(rounds=('coin','size'),coin_rounds=('coin','sum'),Nasdaq_removed=('nasdaq','sum'),original_sum_net=('original_net','sum'),literal_coin_sum_net=('literal_coin_only_net','sum')).reset_index().to_csv(OUT/'frozen_full_removal_summary.csv',index=False)
    for x in r.ck['rows']:
        log=r.log(x['call_ref']);ng=bg=fees=0
        for t in log:
            initial=t['equity']-t['pnl'];ng+=initial*t['long_gross_return'];bg+=initial*t['short_gross_return'];fees+=initial*t['cost_return']
        assert np.isclose((ng+bg-fees)/CFG.capital,x['total_return'],atol=1e-12)
        leg.append(dict(name=x['name'],start=x['start'],end_exclusive=x['end_exclusive'],scenario=x['scenario'],call_ref=x['call_ref'],gross_Nasdaq=ng,gross_Bitcoin=bg,cost=fees,net=ng+bg-fees))
    pd.DataFrame(leg).to_csv(OUT/'leg_accounting.csv',index=False)
    choices=pd.read_csv(OUT/'monthly_choices.csv');assert len(choices)==22
    for t in choices.itertuples():assert t.training_end_exclusive==t.month and pd.Timestamp(t.training_start)==pd.Timestamp(t.month)-pd.DateOffset(months=t.months) and (t.selected in pool or t.selected=='cash')
    proof=json.loads((OUT/'resume_proof.json').read_text());call=calls[proof['call_id']-1];assert call['ledger_sha256']==proof['ledger_sha256']
    saved=r.ck['monthly'][proof['schedule_key']];assert saved['segments'][0]['state']==proof['state']
    assert sum(c['kind']=='continuous_month' and c['first_policy']==call['first_policy'] and c['start']==call['start'] and c['scenario']==call['scenario'] for c in calls)==1
    # Validate every prior result against pinned remote Gitblob checks and ledgerSHA.
    cache=json.loads((OUT/'cache_provenance.json').read_text())
    for p,h in cache['remote_git_blobs_verified'].items():
        data=Path(p).read_bytes();assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==h
    pre=pd.read_csv(OUT/'returnblind_preflight.csv');assert not any(x['name'].startswith(('sync__','async__')) for x in r.ck['rows'])
    assert not(OUT/'call_intent_LOCAL.json').exists() and not(OUT/'RUNNING.lock').exists()
    result=dict(status='PASS',new_actual_calls=len(calls),new_reset_calls=sum(c['kind']=='reset_window' for c in calls),continuous_actual_month_calls=physical_months,prior_unique_calls_reused=len(r.ck['prior']),prior_trade_records_checked=prior_trades,logical_reset_cells=len(rows),new_trade_records_checked=new_trades,new_Nasdaq_buy_rounds=new_nasdaq,new_Bitcoin_buy_rounds=new_btc,two_role_new_rounds=both,source_release_trade_checks=source_checks,ambiguous_price_phase=ambiguous,accounting_PIT_BUY_verified=True,full_month_state_verified=True,strict_prior_month_choices=22,resume_first_prefix_replayed=0,frozen_price_labels=len(labels),frozen_full_removal_labels=len(f),independent_validation=False,orders=0,verifier_sha256=sha(Path(__file__)))
    atomic_json(OUT/'verification.json',result);print(json.dumps(result,indent=2));print(pd.DataFrame(usage).groupby(['origin','symbol']).buys.sum().to_string())

if __name__=='__main__':main()
