"""Confidence bands for the paper's model outputs from the bootstrap draws of gamma.

Reads outputs/tables/inference_gamma_draws.csv (from 13_inference.py, run where the Freddie
data is), takes n evenly spaced quantiles of the gamma draws, and for each one reruns the
pool projection, the waterfall and pricing on the constant 8.28% path with and without the
call. Reports the 2.5/50/97.5 percentiles of M-2B WAL, M-2B spread duration and the cost of
risk transfer of the four offered notes. Runs without the Freddie data.

    python notebooks/scripts/14_bands.py --n 41
"""
import argparse, sys, warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from src import call_value as cv, collateral_projection as cp, duration as du, lockin as lk

ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=41)
ap.add_argument("--draws", default=str(ROOT / "outputs/tables/inference_gamma_draws.csv"))
args = ap.parse_args()
TABLES = ROOT / "outputs" / "tables"

g = pd.read_csv(args.draws)["gamma"].to_numpy()
grid = np.quantile(g, np.linspace(0.0, 1.0, args.n))   # quantiles carry equal probability
pool = cp.load_pool(); team = cp.get_scenarios(None)
rates = du.extend_rates(pd.read_csv(lk.PRICING_RATES).query("scenario == 'base'"))
path = du.extend_path(lk.constant_rate_paths(team["base"]["hpi"], {"x": 8.28})["x"])
cache, rows = {}, []
for gam in grid:
    key = round(float(gam), 5)
    if key not in cache:
        pools = du.project_shifts(pool, path, key)
        out = {}
        for cname, cdate in du.CALL_CASES.items():
            m = du.measures(pools, rates, cdate).set_index("tranche")
            nc = du.note_cashflows(pools[0.0], rates, cdate)
            costs = {c: cv.freddie_cost(n) for c, n in nc.items()}
            cost = sum(v["spread_cost"] - v["protection"] for v in costs.values()) / 1e6
            out[cname] = {"m2b_wal": m.loc["M-2B", "wal_years"], "m2b_spread_duration": m.loc["M-2B", "spread_duration"],
                          "offered_cost_mm": cost}
        cache[key] = out
    for cname, v in cache[key].items():
        rows.append({"gamma": gam, "call": cname, **v})
    print(f"gamma {gam:.4f}", flush=True)
d = pd.DataFrame(rows); d.to_csv(TABLES / "inference_bands_draws.csv", index=False)
band = d.groupby("call")[["m2b_wal", "m2b_spread_duration", "offered_cost_mm"]].quantile([0.025, 0.5, 0.975]).unstack()
band.to_csv(TABLES / "inference_bands.csv"); print(band.round(3))
