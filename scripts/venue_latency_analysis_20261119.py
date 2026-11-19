"""Completed-call factorial attribution; no engine calls or threshold fitting."""
from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np
from venue_latency_retry_20261119 import Runner,OUT,PREV,BASE,CFG,DEV,MDD_SCREEN,pair
from venue_latency_calendar_20261119 import common_mask
from availability_runtime_20261119 import atomic_json,sha

def main():
    r=Runner();rows=pd.DataFrame(r.ck['rows']);selection=json.loads((OUT/'selection.json').read_text());choices=pd.read_csv(OUT/'monthly_choices.csv');training=[]
    clarified=choices.rename(columns={'explicit_whole_cash_policy':'declared_fallback_is_whole_cash'}).copy();clarified['actual_selected_whole_cash']=clarified.selected=='cash';assert (clarified.actual_selected_whole_cash==clarified.Bitcoin_cash).all();clarified.to_csv(OUT/'monthly_choice_semantics.csv',index=False)
    for choice in choices.itertuples():
        count=0
        for n in selection['diagnostic_pool']:
            source=rows[(rows.name==n)&(rows.start==choice.training_start)&(rows.end_exclusive==choice.training_end_exclusive)].set_index('scenario');price=rows[(rows.name==pair(n))&(rows.start==choice.training_start)&(rows.end_exclusive==choice.training_end_exclusive)].set_index('scenario');assert len(source)==len(price)==3;both=pd.concat([source,price]);reason=[]
            if both.Bitcoin_rounds.min()<20:reason.append('COIN_ROUNDS_LT20')
            if both.max_drawdown.max()>MDD_SCREEN:reason.append('ABS_MDD_GT3PCT')
            if both.mdd_halt.any() or (both.hard_halts>0).any():reason.append('HALT')
            if source.total_return.min()<=0:reason.append('NONPOSITIVE_SOURCE_STRESS')
            if any(source.loc[s,'total_return']<=price.loc[s,'total_return'] for s in source.index):reason.append('NO_UNIFORM_FLOW_INCREMENT')
            if any(source.loc[s,'max_drawdown']>price.loc[s,'max_drawdown'] for s in source.index):reason.append('HIGHER_MDD_VS_SAME15PCT_PRICE')
            eligible=not reason;count+=eligible;training.append(dict(months=choice.months,month=choice.month,name=n,training_start=choice.training_start,training_end_exclusive=choice.training_end_exclusive,min_rounds=int(both.Bitcoin_rounds.min()),worst_stress_return=source.total_return.min(),eligible=eligible,selected=n==choice.selected,reasons='|'.join(reason)))
        assert count==choice.eligible_count
    pd.DataFrame(training).to_csv(OUT/'monthly_training_screens.csv',index=False)
    phase=pd.read_csv(OUT/'execution_phases_LOCAL.csv');contrasts=[];frozen=[];leg=[];cal=pd.read_csv(BASE/'calendar_schedule.csv',index_col='day')
    for x in ('open','close'):cal[x]=pd.to_datetime(cal[x],utc=True)
    def row(n,a,b,s):return rows[(rows.name==n)&(rows.start==a)&(rows.end_exclusive==b)&(rows.scenario==s)].iloc[0]
    for duration in (120,180):
        mask=common_mask(r.times,cal,duration)
        for arm in ('source','price'):
            for a,b in DEV:
                original=row('legacy__'+arm,a,b,'base');control=row(f'c{duration}__'+arm,a,b,'base');newlog=r.log(control.call_ref);newkeys={(int(t['signal_index']),tuple(t['bought_symbols'])) for t in newlog};local=[]
                for t in r.log(original.call_ref):
                    si=int(t['signal_index']);key=(si,tuple(t['bought_symbols']));local.append(dict(duration=duration,arm=arm,start=a,signal_index=si,day=r.days[si],literal_calendar_admitted=bool(mask[si]),actual_same_control_event=key in newkeys,parent_net=t['net_return'],literal_net=t['net_return'] if mask[si] else 0,NOT_portfolio_return=True))
                frozen.extend(local)
                for scenario in ('base','cost2','delay1'):
                    h=row(f'h{duration}__'+arm,a,b,scenario);c=row(f'c{duration}__'+arm,a,b,scenario)
                    def events(q):return {(int(t['signal_index']),tuple(t['bought_symbols'])):t for t in r.log(q.call_ref)}
                    hm,cm=events(h),events(c);common=set(hm)&set(cm);different=[]
                    for key in common:
                        hp=phase[(phase.call_ref==h.call_ref)&(phase.signal_index==key[0])].iloc[0];cp=phase[(phase.call_ref==c.call_ref)&(phase.signal_index==key[0])].iloc[0]
                        if hp.actual_exit!=cp.actual_exit or hp.phase!=cp.phase or not np.isclose(hm[key]['gross_return'],cm[key]['gross_return'],atol=1e-14):different.append(key)
                    changed_days=len({r.days[k[0]] for k in different})
                    contrasts.append(dict(duration=duration,arm=arm,start=a,end_exclusive=b,scenario=scenario,horizon_return=h.total_return,same_cohort_hold4_return=c.total_return,delta_pp=(h.total_return-c.total_return)*100,horizon_rounds=int(h.Bitcoin_rounds),control_rounds=int(c.Bitcoin_rounds),same_signal_target=len(common),changed_protected_exit=len(different),changed_exit_days=changed_days,changed_exit_min20_10days=len(different)>=20 and changed_days>=10,horizon_only=len(set(hm)-set(cm)),control_only=len(set(cm)-set(hm))))
    f=pd.DataFrame(frozen);f.to_csv(OUT/'frozen_calendar_labels_LOCAL.csv',index=False);f.groupby(['duration','arm','start']).agg(parent_rounds=('parent_net','size'),literal_admitted=('literal_calendar_admitted','sum'),actual_common_control=('actual_same_control_event','sum'),parent_sum_net=('parent_net','sum'),literal_sum_net=('literal_net','sum')).reset_index().to_csv(OUT/'frozen_calendar_attribution.csv',index=False);pd.DataFrame(contrasts).to_csv(OUT/'holding_factorial_contrasts.csv',index=False)
    for x in r.ck['rows']:
        ng=bg=fees=0
        for t in r.log(x['call_ref']):
            initial=t['equity']-t['pnl'];ng+=initial*t['long_gross_return'];bg+=initial*t['short_gross_return'];fees+=initial*t['cost_return']
        assert np.isclose((ng+bg-fees)/CFG.capital,x['total_return'],atol=1e-12);leg.append(dict(name=x['name'],start=x['start'],end_exclusive=x['end_exclusive'],scenario=x['scenario'],call_ref=x['call_ref'],gross_Nasdaq=ng,gross_Bitcoin=bg,cost=fees,net=ng+bg-fees))
    pd.DataFrame(leg).to_csv(OUT/'leg_accounting.csv',index=False)
    recent=pd.read_csv(OUT/'recent_fitted_ranks.csv');recent['minimum_rounds_pass']=recent.min_Bitcoin_rounds>=20;recent['fitted_reused_not_independent']=True;recent.to_csv(OUT/'recent_fit_sample_flags.csv',index=False)
    files=['scripts/venue_latency_calendar_20261119.py','scripts/venue_latency_retry_20261119.py','scripts/venue_latency_labels_20261119.py','scripts/venue_latency_verify_20261119.py','scripts/venue_latency_analysis_20261119.py','tests/test_venue_latency_calendar.py','src/autogrid/engine.py','configs/win60_search.yaml','scripts/availability_runtime_20261119.py','scripts/availability_guarded_research_20261119.py']
    atomic_json(OUT/'analysis_manifest.json',dict(status='COMPLETE_VERIFIED_ANALYSIS',analysis_engine_calls=0,nominal_definitions=12,new_protected_definitions=8,new_threshold_trials=0,prior_unique_cells=len(r.ck['prior']),hashes={p:sha(Path(p)) for p in files},checkpoint_sha256=sha(OUT/'checkpoint_LOCAL.json'),raw_ledger_sha256={c['call_id']:c['ledger_sha256'] for c in r.ck['calls']},original_input_hashes=r.plan['hashes'],independent_validation=False,orders=0))
    print(pd.DataFrame(contrasts).to_string(index=False));print(pd.Series([y for x in training for y in x['reasons'].split('|') if y]).value_counts().to_string())

if __name__=='__main__':main()
