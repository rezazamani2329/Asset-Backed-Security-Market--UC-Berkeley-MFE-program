"""Robustness and validation runs for the paper (Section IV.D-E). Run from the repo root:
    python notebooks/scripts/12_robustness.py outputs/tables/robustness_828.csv
"""
import sys, time, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from src import collateral_projection as cp, lockin as lk, duration as du
pool = cp.load_pool(); team = cp.get_scenarios(None)
all_rates = pd.read_csv(lk.PRICING_RATES)
rates = du.extend_rates(all_rates[all_rates.scenario == "base"])
const = lk.constant_rate_paths(team["base"]["hpi"], {"8.28": 8.28})
p828 = du.extend_path(const["8.28"]); pbase = du.extend_path(team["base"])
t=time.time()
# 1. model speeds in first months vs Bloomberg actual
b = lk.project(pool, pbase["hpi"], pbase["rate"], 0.025)
smm = (b.prepayments/(b.beginning_balance-b.scheduled_principal)).to_numpy()
cpr = 1-(1-smm)**12
print("model CPR m1-3:", np.round(cpr[:3]*100,2), "avg yr1", round(cpr[:12].mean()*100,2), time.time()-t, flush=True)
out=[]
# 2. lock-in strengths, 8.28 no call and call
for g in [0.0, 0.025, 0.037, 0.089, 0.20, 0.40]:
    pools = du.project_shifts(pool, p828, g)
    for cname, cd in du.CALL_CASES.items():
        m = du.measures(pools, rates, cd)
        m = m.assign(lockin=g, call=cname, test="lockin"); out.append(m)
    print("g", g, time.time()-t, flush=True)
    pd.concat(out).to_csv(sys.argv[1], index=False)
# 3. shift size at 8.28 no call, estimated lock-in
for s in [10.0, 50.0]:
    pools = du.project_shifts(pool, p828, 0.025, s)
    m = du.measures(pools, rates, du.MATURITY_DATE, s).assign(lockin=0.025, call="no call", test=f"shift{int(s)}")
    out.append(m); print("s", s, time.time()-t, flush=True)
# 4. house-price crash: HPI -30% over 24 months then flat, 8.28 no call
h = np.asarray(p828["hpi"], float).copy(); n=len(h)
drop = np.ones(n); drop[1:25] = np.linspace(1,0.70,25)[1:]; drop[25:] = 0.70
crash = {"hpi": h[0]*drop, "rate": p828["rate"]}
for d, label in [(0.70, "crash30")]:
    dr = np.ones(n); dr[1:25]=np.linspace(1,d,25)[1:]; dr[25:]=d
    pools = du.project_shifts(pool, {"hpi": h[0]*dr, "rate": p828["rate"]}, 0.025)
    for cname, cd in du.CALL_CASES.items():
        m = du.measures(pools, rates, cd).assign(lockin=0.025, call=cname, test=label)
        m["pool_loss_pct"] = pools[0.0].losses.sum()/pool["Current Balance"].sum()*100
        out.append(m)
    print(label, time.time()-t, flush=True)
    pd.concat(out).to_csv(sys.argv[1], index=False)
pd.concat(out).to_csv(sys.argv[1], index=False)

