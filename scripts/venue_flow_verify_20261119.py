"""Independent accounting, literal-support attribution and resume validation."""
from pathlib import Path
import json,hashlib,copy,re
import numpy as np
import pandas as pd
from venue_flow_retry_20261119 import Runner,OUT,DEV,CFG,load_context,candidates
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
    references={**{'new:'+str(c['call_id']):c for c in calls},**r.ck['prior']};new_trades=prior_trades=new_nasdaq=new_btc=both=ambiguous=source_checks=0;usage=[];risk=[];masked={};trace=pd.read_csv(OUT/'source_trace_LOCAL.csv').set_index('index')
    for ref,c in references.items():
        log=r.log(ref);assert sha(OUT/f'call_{ref.split(":")[1]}_ledger_LOCAL.jsonl')==c['ledger_sha256']
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
            if is_btc and n.startswith(('source__','price__')):
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
            for z in r.data.symbols:usage.append(dict(call_ref=ref,symbol=z,buys=sum(z in t['bought_symbols'] for t in log)))
        else:prior_trades+=len(log)
        risk.append(dict(call_ref=ref,name=n,start=c['start'],scenario=scenario,postround_soft_threshold_touch_days=len(touch),minimum_daily_postround_return=minday,recorded_hard_halts=c['hard_halts'],recorded_mdd_halt=c['mdd_halt']))
    pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False);pd.DataFrame(risk).to_csv(OUT/'risk_threshold_audit_final.csv',index=False)
    with np.load(OUT/'crypto_scores_LOCAL.npz') as f:raw={k:f[k] for k in f.files}
    attribution=[];labels=[];pool=json.loads((OUT/'selection.json').read_text())['diagnostic_pool']
    for c in candidates():
        if c['arm']!='source':continue
        conf={k:v for k,v in c.items() if k not in ('alpha','arm')};_,common,now,prior,mean=_prepare(r.data,r.times,r.ctx,conf);direction=np.sign(now['body']);fam=c['family']
        if fam=='flow_trend':predicate=(direction*now['flow']>=c['flow_threshold'])&(direction*(now['flow']-mean)>0)
        elif fam=='absorption_release':predicate=(-direction*prior['flow']>=c['flow_threshold'])&(direction*now['flow']>0)
        elif fam=='flow_flip':predicate=(direction*now['flow']>=c['flow_threshold'])&(direction*prior['flow']<=c['prior_ceiling'])
        else:
            direction=np.sign(prior['body']);predicate=(direction*prior['flow']>=c['flow_threshold'])&(direction*now['flow']>0)
        for a,b in DEV:
            q=rows[(rows.name=='price__'+c['alpha'])&(rows.start==a)&(rows.end_exclusive==b)&(rows.scenario=='base')].iloc[0];log=r.log(q.call_ref);local=[]
            for t in log:
                coin=[z for z in t['bought_symbols'] if z in ('IBIT','BITI')]
                if not coin:continue
                si=int(t['signal_index']);admit=bool(common[si] and predicate[si]);onset=bool(raw[c['name']][si,r.data.symbols.index(coin[0])])
                coin_net=t['short_gross_return']-.15*2*(CFG.execution.commission_bps+CFG.execution.slippage_bps)/10000
                local.append(dict(source=c['name'],start=a,signal_index=si,day=r.days[si],symbol=coin[0],literal_flow_admitted=admit,actual_source_same_onset=onset,frozen_coin_net=coin_net,frozen_round_net=t['net_return']))
            labels.extend(local);q=pd.DataFrame(local);ad=q[q.literal_flow_admitted] if len(q) else q;rej=q[~q.literal_flow_admitted] if len(q) else q
            adequate=len(ad)>=20 and len(rej)>=20 and ad.day.nunique()>=10 and rej.day.nunique()>=10
            effect=paired_effect(np.where(q.literal_flow_admitted,q.frozen_coin_net,0)-q.frozen_coin_net,q.day.to_numpy(),sorted(set(r.days[(r.times>=pd.Timestamp(a,tz='UTC'))&(r.times<pd.Timestamp(b,tz='UTC'))]))) if adequate else dict(block_lower=None,block_upper=None)
            attribution.append(dict(source=c['name'],start=a,end_exclusive=b,price_control_executed_coin_rounds=len(local),literal_admitted=len(ad),literal_rejected=len(rej),actual_source_same_onset=int(q.actual_source_same_onset.sum()) if len(q) else 0,admitted_mean_coin_net=float(ad.frozen_coin_net.mean()) if len(ad) else None,rejected_mean_coin_net=float(rej.frozen_coin_net.mean()) if len(rej) else None,baseline_sum_coin_net=float(q.frozen_coin_net.sum()) if len(q) else 0,literal_admitted_sum_coin_net=float(ad.frozen_coin_net.sum()) if len(ad) else 0,adequate_conditional_sample=adequate,block_lower=effect['block_lower'],block_upper=effect['block_upper'],NOT_portfolio_return=True))
    pd.DataFrame(labels).to_csv(OUT/'frozen_control_opportunities_LOCAL.csv',index=False);pd.DataFrame(attribution).to_csv(OUT/'frozen_control_attribution.csv',index=False)
    assert not(OUT/'call_intent_LOCAL.json').exists() and not(OUT/'RUNNING.lock').exists()
    choices=pd.read_csv(OUT/'monthly_choices.csv');assert len(choices)==22
    for t in choices.itertuples():assert t.training_end_exclusive==t.month and pd.Timestamp(t.training_start)==pd.Timestamp(t.month)-pd.DateOffset(months=t.months) and (t.selected in pool or t.selected=='nasdaq_only')
    # Reconcile pause prefix and show no old prefix was repeated.
    proof=json.loads((OUT/'resume_proof.json').read_text());call=calls[proof['call_id']-1];assert call['ledger_sha256']==proof['ledger_sha256']
    saved=r.ck['monthly'][proof['schedule_key']];assert saved['segments'][0]['state']==proof['state']
    assert sum(c['kind']=='continuous_month' and c['first_policy']==call['first_policy'] and c['start']==call['start'] and c['scenario']==call['scenario'] for c in calls)==1
    result=dict(status='PASS',new_actual_calls=len(calls),new_reset_calls=sum(c['kind']=='reset_window' for c in calls),continuous_actual_month_calls=physical_months,logical_reset_cells=len(rows),new_trade_records_checked=new_trades,new_Nasdaq_buy_rounds=new_nasdaq,new_Bitcoin_buy_rounds=new_btc,two_role_rounds=both,source_release_trade_checks=source_checks,ambiguous_open_close_matches=ambiguous,all_equity_fee_risk_buy_reconciled=True,full_month_state_verified=True,strict_prior_month_choices=22,resume_first_prefix_replayed=0,frozen_control_labels=len(labels),frozen_attribution_definitions=32,independent_validation=False,news_macro=False,orders=0,verifier_sha256=sha(Path(__file__)))
    atomic_json(OUT/'verification.json',result);print(json.dumps(result,indent=2));print(pd.DataFrame(usage).groupby('symbol').buys.sum().to_string())

if __name__=='__main__':main()
