"""Statistical inference for the lock-in paper (Section IV.B and Appendix C).

Needs the licensed Freddie Mac files (data/raw/freddie_sf/), so run it on the computer that
has them, from the repo root:

    python notebooks/scripts/13_inference.py            # 500 bootstrap draws
    python notebooks/scripts/13_inference.py --boot 200 # faster

Writes only summary tables to outputs/tables/inference_*.csv (no loan-level data).
Caches the month buckets in data/processed/freddie/ (local, not committed).
"""
import argparse, sys, time, warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from src import calibration as cal, freddie as fr, lockin_inference as li, prepayment as pp

ap = argparse.ArgumentParser()
ap.add_argument("--boot", type=int, default=500)
ap.add_argument("--block", type=int, default=12)
args = ap.parse_args()
TABLES = ROOT / "outputs" / "tables"
t0 = time.time()

# 1. month buckets and default buckets by year (one pass over the vintages, then cached)
BM, DY = fr.OUT / "prepay_by_month.parquet", fr.OUT / "default_by_year.parquet"
if BM.exists() and DY.exists():
    bm, dy = pd.read_parquet(BM), pd.read_parquet(DY)
else:
    pmms, hpi = fr.load_fred("MORTGAGE30US"), fr.load_fred("HPIPONM226S")
    pb, db = [], []
    for y in fr.VINTAGES:
        panel = fr.load_panel(y)
        pb.append(li.prepay_buckets_by_month(panel, pmms))
        db.append(li.default_buckets_by_year(cal.default_rows(panel, hpi)))
        print(y, f"{time.time() - t0:.0f}s", flush=True)
    bm = pd.concat(pb).groupby(["month"] + cal.PREPAY_KEYS)[li.SUM_COLS].sum().reset_index()
    keys = ["year", "ltv_b", "fico_b", "dti_b", "investor", "pre2009", "dq30", "dq60"]
    d = pd.concat(db)
    d["wl"], d["wf"], d["wd"] = d["ltv"] * d["n"], d["fico"] * d["n"], d["dti"] * d["n"]
    dy = d.groupby(keys)[["n", "events", "wl", "wf", "wd"]].sum().reset_index()
    dy["ltv"], dy["fico"], dy["dti"] = dy["wl"] / dy["n"], dy["wf"] / dy["n"], dy["wd"] / dy["n"]
    bm.to_parquet(BM, index=False); dy.to_parquet(DY, index=False)

base = {k: pp.PARAMS[k] for k in cal.PREPAY_NAMES}
months = sorted(m for m in bm["month"].unique() if m >= 202201)
print(f"lock-in window: {months[0]}-{months[-1]}, {len(months)} months")

# 2. point estimates (should reproduce notebook 09's 0.025)
b = li.collapse(bm, months)
e, k = li.fit(b, base), li.fit(b, base, "kink")
point = {"gamma": e["g"][0], "g1": k["g"][0], "g2": k["g"][1]}
print("point:", {a: round(v, 4) for a, v in point.items()})

# 3. block bootstrap over calendar months
draws = li.bootstrap(bm, months, base, n_boot=args.boot, block=args.block)
draws.to_csv(TABLES / "inference_gamma_draws.csv", index=False)
summ = li.summarize(point, draws)
summ.to_csv(TABLES / "inference_gamma_summary.csv")
print(summ.round(4), f"\n{time.time() - t0:.0f}s", flush=True)

# 4. threshold (kink) statistic
kf = li.kink_f_stat(b, base)
pd.Series(kf).to_csv(TABLES / "inference_kink_test.csv")
print(kf)

# 5. pseudo out-of-sample forecast test: fit 2022-2024, forecast 2025-2026
ft = li.forecast_test(bm, base)
ft["forecasts"].to_csv(TABLES / "inference_forecasts_2025_2026.csv", index=False)
pd.DataFrame({"gamma_train": [ft["gamma_train"]], **{f"rmse_cpr_pp_{a}": [v] for a, v in ft["rmse_cpr_pp"].items()},
              **{f"{t}_{a}": [v] for t in ("dm_estimated_vs_none", "dm_estimated_vs_fhfa") for a, v in ft[t].items()}}
             ).T.to_csv(TABLES / "inference_forecast_test.csv")
print(ft["rmse_cpr_pp"], ft["dm_estimated_vs_none"], ft["dm_estimated_vs_fhfa"])

# 6. default regression with standard errors clustered by calendar year
dc = li.fit_default_clustered(dy)
dc.to_csv(TABLES / "inference_default_clustered.csv")
print(dc.round(4), f"\ndone in {time.time() - t0:.0f}s")
