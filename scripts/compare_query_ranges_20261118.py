"""Within-day source query-range control; publish aggregates only."""
from pathlib import Path
import json
import numpy as np
from extended_snapshot_20261118 import raw_frame,OUT,OLD,VALUES

def compare(a,b):
    a=a.set_index(['timestamp','symbol']).sort_index();b=b.set_index(['timestamp','symbol']).sort_index();ix=a.index.intersection(b.index)
    mask=np.column_stack([~np.isclose(a.loc[ix,k],b.loc[ix,k],rtol=0 if k=='volume' else 1e-9,atol=0 if k=='volume' else 1e-8) for k in VALUES])
    by_symbol={s:{k:int(mask[np.asarray(ix.get_level_values('symbol')==s),i].sum()) for i,k in enumerate(VALUES)} for s in ('TQQQ','SQQQ','IBIT','BITI')}
    return dict(shared_keys=len(ix),revised_rows=int(mask.any(axis=1).sum()),changed_fields={k:int(mask[:,i].sum()) for i,k in enumerate(VALUES)},per_symbol=by_symbol,added_keys=len(b.index.difference(a.index)),dropped_keys=len(a.index.difference(b.index)))

def main():
    target=OUT/'query_range_control.json'
    if target.exists():raise SystemExit('Control already frozen')
    old=raw_frame(OLD);extended=raw_frame(OUT);now=raw_frame(OUT/'same_day_one_month')
    result=dict(old_month_vs_new_month=compare(old,now),same_day_month_vs_60d=compare(now,extended),old_month_vs_60d=compare(old,extended))
    target.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
