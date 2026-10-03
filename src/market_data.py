"""Strict readers and reproducible downloads of public FRED CSV histories."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import pandas as pd
import numpy as np

SERIES = ('MORTGAGE30US','HPIPONM226S','DGS2','DGS10','SOFR','SOFR30DAYAVG','DFF')

def download(directory):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    records = []
    for name in SERIES:
        url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={name}'
        target = directory / f'{name}.csv'
        tmp = directory / f'{name}.download'
        subprocess.run(['curl.exe' if __import__('os').name=='nt' else 'curl', '-f','-sS','-L',
                        '--connect-timeout','15','--max-time','60','--retry','2',url,'-o',str(tmp)],check=True)
        read_series(tmp, name)
        tmp.replace(target)
        records.append({'series':name,'url':url,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                        'retrieved_utc':datetime.now(timezone.utc).isoformat()})
    (directory/'download_manifest.json').write_text(json.dumps(records,indent=2))

def read_series(path, name, as_of=None):
    raw = pd.read_csv(path, na_values=['.', ''])
    if name not in raw or len(raw.columns) != 2:
        raise ValueError(f'{path}: expected date and {name} columns')
    dates = pd.to_datetime(raw.iloc[:,0],errors='raise')
    if dates.duplicated().any() or dates.isna().any():
        raise ValueError(f'{path}: duplicate/missing dates')
    values = pd.to_numeric(raw[name],errors='raise')
    series = pd.Series(values.to_numpy(),index=dates,name=name).sort_index().dropna()
    if not np.isfinite(series).all() or series.empty:
        raise ValueError(f'{path}: empty or non-finite observations')
    if as_of is not None:
        series = series.loc[:pd.Timestamp(as_of)]
    if series.empty:
        raise ValueError(f'{name}: no data at valuation date')
    return series

def load_history(directory, as_of, snapshot_as_of):
    # Archived FRED files are latest-vintage histories, not real-time ALFRED histories.
    # Reject a different valuation cutoff rather than quietly introducing revision look-ahead.
    if pd.Timestamp(as_of).normalize() != pd.Timestamp(snapshot_as_of).normalize():
        raise ValueError('Valuation date must match snapshot_as_of; supply a matching archived vintage for a historical valuation')
    data, provenance = {}, []
    for name in SERIES:
        p = Path(directory)/f'{name}.csv'
        s = read_series(p,name,as_of)
        age = (pd.Timestamp(as_of)-s.index[-1]).days
        if age > (125 if name=='HPIPONM226S' else 14):
            raise ValueError(f'Stale {name}: last observation {s.index[-1].date()}')
        if name=='HPIPONM226S' and (s<=0).any():
            raise ValueError('HPI must be positive')
        data[name]=s
        provenance.append({'series':name,'url':f'https://fred.stlouisfed.org/series/{name}',
                           'file':f'{name}.csv','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                           'snapshot_as_of':snapshot_as_of,'first_date':str(s.index[0].date()),
                           'last_date':str(s.index[-1].date()),'last_value':float(s.iloc[-1]),'observations':len(s)})
    return data,pd.DataFrame(provenance)
