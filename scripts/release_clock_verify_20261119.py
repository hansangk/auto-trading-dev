"""Independent ledger, source-release, exact-horizon and rejection verification."""
from pathlib import Path
import json,hashlib,re
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from inverse_etf_retry_20261116 import CFG
OUT=Path('runs/release_clock_audit_20261119_0630')

def main():
    m=json.loads((OUT/'manifest.json').read_text());plan=json.loads((OUT/'preregistered_plan.json').read_text())
    for p,h in {**m['hashes'],**plan['prepared_hashes']}.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
    data=load_market_data(OUT/'five_minute_overlap_LOCAL.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
    with np.load(OUT/'scores_LOCAL.npz') as f:scores={k:f[k] for k in f.files}
    rows=pd.read_csv(OUT/'all_evaluations.csv');ledger=[json.loads(x) for x in (OUT/'ledger_LOCAL.jsonl').read_text().splitlines() if x]
    trace=pd.read_csv(OUT/'source_trace_LOCAL.csv');ctx=np.load(OUT/'context_LOCAL.npz');checks=0;phase_ambiguous=0
    assert len(rows)==m['engine_calls']==32 and set(rows.cost)=={1} and set(rows.delay_bars)=={0}
    for row in rows.itertuples():
        group=[t for t in ledger if t['call_id']==row.call_id];equity=CFG.capital;peak=equity;dd=0;costs=0
        assert len(group)==row.rounds
        for t in group:
            sig=int(t['signal_index']);entry=int(times.get_loc(pd.Timestamp(t['entry'])));end=int(times.get_loc(pd.Timestamp(t['end'])))
            assert entry==sig+1 and entry<=end
            assert len(t['bought_symbols'])==1 and t['execution_type']=='buy_two_etfs'
            symbol=t['bought_symbols'][0];j=data.symbols.index(symbol)
            assert scores[row.name][sig,j]!=0 and np.count_nonzero(scores[row.name][sig])==1
            assert t['bought_weights']==[.15]
            assert times[sig].tz_convert('America/New_York').date()==times[entry].tz_convert('America/New_York').date()==times[end].tz_convert('America/New_York').date()
            decision=times[sig]+pd.Timedelta(minutes=5)
            assert decision==times[entry]
            source=trace.iloc[sig]
            used=['btc_end']+(['qqq_end'] if row.policy in ('nasdaq_source','qqq_parent') else [])
            for key in used:
                src=pd.Timestamp(source[key]);assert src+pd.Timedelta(minutes=5)<=decision and decision-src<=pd.Timedelta(minutes=65)
            if row.policy=='btc_acceptance':
                assert np.isfinite(ctx['same_day_first_ibit'][sig])
                assert decision.tz_convert('America/New_York')>=decision.tz_convert('America/New_York').normalize()+pd.Timedelta(hours=10,minutes=35)
            reserved=entry+row.hold_minutes//5-1
            assert times[reserved]+pd.Timedelta(minutes=5)-times[entry]==pd.Timedelta(minutes=row.hold_minutes)
            assert times[reserved].tz_convert('America/New_York').date()==times[entry].tz_convert('America/New_York').date()
            gross=[.15*(getattr(data,f)[end,j]/data.open[entry,j]-1) for f in ('open','close')]
            match=[bool(np.isclose(v,t['gross_return'],rtol=1e-6,atol=1e-10)) for v in gross]
            assert any(match);phase_ambiguous+=all(match)
            cost=.15*2*(CFG.execution.commission_bps+CFG.execution.slippage_bps)/10000
            assert np.isclose(cost,t['cost_return']) and np.isclose(t['gross_return']-t['cost_return'],t['net_return'])
            # pandas JSON export retained ten decimal places for fractional
            # returns. Its maximum half-unit rounding error is5e-11, about
            # .005currency units on1e8capital. Currency PnL retains10decimals:
            # reconcile via that amount, with an explicit serialization bound.
            assert abs(equity*t['net_return']-t['pnl'])<=equity*5.1e-11+1e-6
            costs+=equity*t['cost_return'];equity+=t['pnl'];assert np.isclose(equity,t['equity'],rtol=1e-12,atol=1e-5)
            peak=max(peak,equity);dd=max(dd,1-equity/peak);checks+=1
        assert np.isclose(equity/CFG.capital-1,row.total_return) and np.isclose(costs,row.costs)
        assert np.isclose(dd,row.max_drawdown)
        assert np.isclose(np.mean([t['net_return']>0 for t in group]) if group else 0,row.win_rate)
    usage=pd.read_csv(OUT/'ticker_usage.csv');assert int(usage.buys.sum())==checks
    pairs=pd.read_csv(OUT/'paired_events_LOCAL.csv');support=pd.read_csv(OUT/'returnblind_support.csv');labels=pd.read_csv(OUT/'paired_path_labels_LOCAL.csv')
    for r in pairs.itertuples():
        a,b=int(r.coarse_entry_index),int(r.release_entry_index);h=r.hold_minutes//5
        for k in (a,b):assert times[k+h-1]+pd.Timedelta(minutes=5)-times[k]==pd.Timedelta(minutes=r.hold_minutes)
        assert times[a]>=times[b]
    for r in support.itertuples():
        q=pairs[(pairs.policy==r.policy)&(pairs.hold_minutes==r.hold_minutes)&(pairs.day>=r.start)&(pairs.day<r.end_exclusive)]
        assert len(q)==r.matched_events
    ranking=pd.read_csv(OUT/'ranking.csv');selection=json.loads((OUT/'selection.json').read_text());assert not ranking.sample_eligible.any() and selection['shortlist']==[] and selection['approved']==[]
    stats=pd.read_csv(OUT/'paired_path_statistics.csv');assert not stats.support_pass.any() and stats.block_lower.isna().all()
    testlog=(OUT/'tests.log').read_text();testcount=int(re.search(r'Ran (\d+) tests',testlog).group(1));assert '\nOK\n' in testlog
    result=dict(status='PASS',engine_calls=len(rows),trade_records=checks,paired_event_records=len(pairs),exact_horizon_checks=len(pairs)*2,all_stress_skipped_by_sample_gate=True,tests_passed=testcount,source_release_checked_for_each_trade=True,account_return_cost_win_drawdown_reconciled=True,engine_unchanged=True,exit_price_phase_ambiguous=phase_ambiguous,ledger_fractional_precision_decimals=10,maximum_fractional_rounding_error=5e-11,prior_verifier_failures=1,orders=0,independent_validation=False,verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));print(usage.groupby('symbol').buys.sum().to_string())

if __name__=='__main__':main()
