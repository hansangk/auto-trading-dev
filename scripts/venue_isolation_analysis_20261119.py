"""Post-run descriptions and training failures; zero engine calls."""
from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np
from venue_isolation_retry_20261119 import Runner,OUT,CFG,DEV,MDD_SCREEN,pair
from availability_runtime_20261119 import atomic_json,sha

def main():
    r=Runner();rows=pd.DataFrame(r.ck['rows']);selection=json.loads((OUT/'selection.json').read_text());choices=pd.read_csv(OUT/'monthly_choices.csv');failures=[]
    for choice in choices.itertuples():
        for n in selection['diagnostic_pool']:
            source=rows[(rows.name==n)&(rows.start==choice.training_start)&(rows.end_exclusive==choice.training_end_exclusive)].set_index('scenario');price=rows[(rows.name==pair(n))&(rows.start==choice.training_start)&(rows.end_exclusive==choice.training_end_exclusive)].set_index('scenario');assert len(source)==len(price)==3
            both=pd.concat([source,price]);reason=[]
            if both.Bitcoin_rounds.min()<20:reason.append('COIN_ROUNDS_LT20')
            if both.max_drawdown.max()>MDD_SCREEN:reason.append('ABS_MDD_GT3PCT')
            if both.mdd_halt.any() or (both.hard_halts>0).any():reason.append('HALT')
            if source.total_return.min()<=0:reason.append('NONPOSITIVE_SOURCE_STRESS')
            if any(source.loc[s,'total_return']<=price.loc[s,'total_return'] for s in source.index):reason.append('NO_UNIFORM_FLOW_INCREMENT')
            if any(source.loc[s,'max_drawdown']>price.loc[s,'max_drawdown'] for s in source.index):reason.append('HIGHER_MDD_VS_SAME15PCT_PRICE')
            assert bool(reason)==(choice.eligible_count==0)
            failures.append(dict(months=choice.months,month=choice.month,name=n,training_start=choice.training_start,training_end_exclusive=choice.training_end_exclusive,min_rounds=int(both.Bitcoin_rounds.min()),worst_stress_return=source.total_return.min(),reasons='|'.join(reason)))
    pd.DataFrame(failures).to_csv(OUT/'monthly_training_rejections.csv',index=False)
    paired=[]
    for n in selection['diagnostic_pool']:
        for a,b in DEV:
            for scenario in ('base','cost2','delay1'):
                src=rows[(rows.name==n)&(rows.start==a)&(rows.end_exclusive==b)&(rows.scenario==scenario)].iloc[0]
                full=rows[(rows.name==n.replace('coin__','full__',1))&(rows.start==a)&(rows.end_exclusive==b)&(rows.scenario==scenario)].iloc[0]
                labels=[]
                slog=r.log(src.call_ref);flog=r.log(full.call_ref);fm={(t['signal_index'],tuple(z for z in t['bought_symbols'] if z in ('IBIT','BITI'))):t for t in flog if any(z in ('IBIT','BITI') for z in t['bought_symbols'])};sm={(t['signal_index'],tuple(t['bought_symbols'])):t for t in slog}
                common=set(fm)&set(sm);exit_changed=sum((sm[k]['end']!=fm[k]['end']) or not np.isclose(sm[k]['short_gross_return'],fm[k]['short_gross_return'],atol=1e-14) for k in common)
                paired.append(dict(name=n,start=a,end_exclusive=b,scenario=scenario,full_return=full.total_return,isolation_return=src.total_return,delta_pp=(src.total_return-full.total_return)*100,full_coin_rounds=int(full.Bitcoin_rounds),isolation_coin_rounds=int(src.Bitcoin_rounds),same_signal_target_rounds=len(common),common_changed_exit_or_price=exit_changed,full_only=len(set(fm)-set(sm)),isolation_only=len(set(sm)-set(fm)),NOT_riskmatched=True))
    pd.DataFrame(paired).to_csv(OUT/'full_vs_isolation_replay.csv',index=False)
    files=['scripts/venue_isolation_signals_20261119.py','scripts/venue_isolation_retry_20261119.py','scripts/venue_isolation_verify_20261119.py','scripts/venue_isolation_analysis_20261119.py','tests/test_venue_isolation_signals.py','src/autogrid/engine.py','configs/win60_search.yaml','scripts/availability_runtime_20261119.py','scripts/availability_guarded_research_20261119.py']
    atomic_json(OUT/'analysis_manifest.json',dict(status='COMPLETE_VERIFIED_ANALYSIS',analysis_engine_calls=0,nominal_definitions=16,new_eligible_definitions=4,new_alpha_thresholds=0,prior_unique_cells=len(r.ck['prior']),hashes={p:sha(Path(p)) for p in files},checkpoint_sha256=sha(OUT/'checkpoint_LOCAL.json'),raw_ledger_sha256={c['call_id']:c['ledger_sha256'] for c in r.ck['calls']},original_input_hashes=r.plan['hashes'],independent_validation=False,orders=0))
    print(pd.Series([y for x in failures for y in x['reasons'].split('|')]).value_counts().to_string());print(pd.DataFrame(paired).to_string(index=False))

if __name__=='__main__':main()
