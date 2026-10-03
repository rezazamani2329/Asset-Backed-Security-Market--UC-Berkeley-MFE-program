#!/usr/bin/env python
# coding: utf-8

# # 07 · Walkthrough: `src/calibration.py`, fitting the model to Freddie history
# 
# **Purpose.** Run each calibration function on its own, see what it produces, and follow how the fitted `PARAMS` in `src/prepayment.py` and `src/credit_model.py` were obtained. `05_calibration_results` runs the whole thing at once and shows the fit charts; this one opens the box.
# 
# | # | Function | Output |
# |---|---|---|
# | 1 | `_mtm_ltv` | each loan-month's mark-to-market LTV |
# | 2 | `prepay_buckets` | observed SMM by incentive / age / burnout bucket, one vintage |
# | 3 | `prepay_model_smm` | the S-curve formula on bucket averages |
# | 4 | `run_all` → `combine_prepay` → `fit_prepay` | all vintages, then the least-squares fit |
# | 5 | `default_rows` | loan-months at risk of starting a default spell |
# | 6 | `default_buckets` → `fit_default` | Poisson GLM |
# | 7 | `liquidations` / `clean_liquidations` | loss components of each credit event |
# | 8 | `pipeline_outcomes` | what happens after a loan reaches 90+ days late |
# | 9 | `dq30_roll` | how often 30-day-late loans reach 90+ |
# | 10 | `severity_model` / `fit_severity` | the severity formula and its fit |
# | 11 | `calibrate` | every fitted parameter in one place |
# 
# Run `06_freddie_walkthrough` (or `05_calibration_results`) first so the panels in `data/processed/freddie/` exist.
# 
# **Process.** Calibration turns the Freddie panels into the numbers in `PARAMS`. Each model piece is fitted on the data that best identifies it: prepayment on every current loan-month (S-curve by incentive, age and burnout); defaults on current loan-months with a Poisson GLM; liquidation timing, cure share and rate cuts on post-2013 default spells; severity on 17k liquidations. Sections 1–3 show the building blocks on two vintages; sections 4–11 run all vintages and fit.

# **What this code does.** Sets up imports, then loads the FHFA HPI and PMMS series from `data/raw/` and the 2007 and 2015 panels built by notebook 06.

# In[1]:


import sys, warnings
from pathlib import Path

ROOT = Path.cwd()
while not (ROOT / "src").is_dir() and ROOT != ROOT.parent:
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
pd.set_option("display.float_format", "{:,.4f}".format)
pd.set_option("display.max_columns", 30)

from src import freddie as fr, calibration as cal, prepayment as pp, credit_model as cm
hpi = fr.load_fred("HPIPONM226S")
pmms = fr.load_fred("MORTGAGE30US")
p07, p15 = fr.load_panel(2007), fr.load_panel(2015)
print(f"2007 panel: {len(p07):,} loan-months | 2015 panel: {len(p15):,} loan-months")


# **What the output shows.** The 2007 panel has 2,605,770 loan-months and the 2015 panel 2,421,244, both 30-year fixed loans only.

# **Q&A · Setup**
# 
# **Q: Why does the first cell search upward for `src/`?**
# A: So `from src import ...` works whether Jupyter was started in the repo root or in `notebooks/`. It walks up the folders until it finds `src/` and adds that folder to the import path.
# 
# **Q: Why are warnings hidden?**
# A: pandas 2.2 on Python 3.14 prints harmless compatibility warnings. Only warnings are hidden; real errors still stop the cell.
# 
# **Q: Why load only the 2007 and 2015 panels here?**
# A: They're two contrasting vintages, one through the crash and one through a calm market, so each function's output is easy to interpret. Section 4 then runs all 27 vintages.

# ---
# ## 1 · `_mtm_ltv`: mark-to-market LTV
# 
# $$LTV_t = \text{orig LTV} \times \frac{\text{UPB}_t}{\text{orig UPB}} \times \frac{HPI_{\text{origination}}}{HPI_t}$$
# 
# Amortization lowers LTV; home-price changes since origination move it up or down.

# **What this code does.** Computes every 2007 loan-month's mark-to-market LTV with `_mtm_ltv` (original LTV × balance paydown × HPI at origination / HPI now), then takes the median by calendar year.

# In[2]:


ltv = cal._mtm_ltv(p07, p07["upb"], hpi)
by = pd.DataFrame({"period": p07["period"].astype(int), "ltv": ltv}).dropna()
by = by[by["ltv"] > 0].groupby(by["period"] // 100)["ltv"].median()
print("median MTM LTV of 2007 loans still outstanding, by year:")
print(by.loc[2007:2016].round(1).to_dict())


# **Result · `_mtm_ltv`.** For 2007 loans still outstanding, median mark-to-market LTV rises from **79 (2007)** to **93 (2011)** as prices fell, then drops back to **71 (2015)** and **66 (2016)** as prices recovered and loans amortized.

# **Q&A · `_mtm_ltv`**
# 
# **Q: Why does LTV peak in 2011, not 2008?**
# A: National prices kept falling until May 2011 (HPI trough). Amortization only lowers LTV slowly, so LTV follows the house-price path.
# 
# **Q: Why is this the key covariate for default and severity?**
# A: Equity decides whether a borrower in trouble can sell instead of defaulting, and how much a liquidation recovers. Using LTV at origination would miss the crash entirely.

# ---
# ## 2 · `prepay_buckets`: observed SMM for one vintage
# 
# For every loan current last month: exposure = last month's balance − scheduled principal; prepaid = full payoffs (code 01) plus partial curtailments. Then sum by bucket of incentive (vs PMMS), loan age and accumulated past incentive (burnout).

# **What this code does.** Runs `prepay_buckets` on the 2015 panel: for loans current last month, exposure = balance − scheduled principal, prepaid = payoffs + curtailments, summed by incentive (vs PMMS), age and burnout bucket. `combine_prepay` turns the sums into bucket averages and SMM. The table re-groups by incentive and converts SMM to CPR.

# In[3]:


b15 = cal.combine_prepay(cal.prepay_buckets(p15, pmms))
print(f"2015 vintage: {len(b15)} buckets, {b15['n'].sum():,.0f} loan-months, ${b15['w'].sum()/1e9:,.1f}bn of exposure-months")
inc = b15.assign(o=b15.prepaid).groupby("inc_b")[["o", "w", "wi", "n"]].sum()
inc = pd.DataFrame({"incentive": inc.wi / inc.w, "loan-months": inc.n, "CPR": pp.smm_to_cpr(inc.o / inc.w)})
inc[inc["loan-months"] > 2000].round(3)


# **Result · `prepay_buckets` (2015 vintage).** 1,190 buckets from **2.34 million loan-months**. By incentive, the CPR traces an S-curve: about **6–9%** when out of the money, 10.6% at +0.13 pp, **21%** at +0.61, **34%** at +1.11, a peak of **37%** at +1.36, then lower (31–34%) at the deepest incentives, where burnout and fewer loans pull it down.

# **Q&A · `prepay_buckets`**
# 
# **Q: What counts as "prepaid"?**
# A: Full payoffs (code 01, before maturity) plus curtailments, i.e. any principal paid beyond the scheduled amount. Both are unscheduled principal, which is what SMM measures.
# 
# **Q: Why only loans that were current last month?**
# A: Delinquent loans rarely refinance, and their missed payments would look like negative prepayment. The prepayment model applies to performing loans; delinquent ones are handled by the credit model.

# ---
# ## 3 · `prepay_model_smm`: the S-curve formula
# 
# The same formula as `prepayment.calculate_cpr`, evaluated on bucket averages so it can be fitted. Here it uses the *placeholder* parameters, to show the starting point of the fit.

# **What this code does.** Evaluates the S-curve formula `prepay_model_smm` with the old placeholder parameters on the 2015 buckets, and compares predicted CPR with observed CPR by incentive.

# In[4]:


placeholder = [0.06, 0.55, 0.75, 3.5, 0.02, 30]
b15 = b15.assign(model=cal.prepay_model_smm(placeholder, b15.inc, b15.age, b15.burn))
g = b15.assign(o=b15.smm * b15.w, f=b15.model * b15.w).groupby("inc_b")[["o", "f", "w", "wi", "n"]].sum()
cmp_ = pd.DataFrame({"incentive": g.wi / g.w, "observed CPR": pp.smm_to_cpr(g.o / g.w), "placeholder CPR": pp.smm_to_cpr(g.f / g.w), "n": g.n})
cmp_[cmp_.n > 2000].drop(columns="n").round(3)


# **Result · `prepay_model_smm` (placeholder parameters).** The placeholder curve **underpredicts almost everywhere** for 2015 loans: about 6% vs 8.5–8.8% observed when out of the money, and 15% vs 21% at +0.61 pp. It only gets close at the deepest incentives. This is why the fit lowers `refi_max` but also changes the shape, seasoning and burnout.

# **Q&A · `prepay_model_smm`**
# 
# **Q: Why evaluate the formula on bucket averages rather than loan by loan?**
# A: Each bucket's average incentive, age and burnout stand in for its loans. This turns 48 million loan-months into a few thousand points, so the least-squares fit runs in seconds, and it's the same formula `calculate_cpr` uses loan by loan.
# 
# **Q: Why does the placeholder underpredict out-of-the-money speeds?**
# A: Its 30-month seasoning ramp slows down young loans a lot, while the data says loans reach full speed in about 6 months.

# ---
# ## 4 · `run_all` → `combine_prepay` → `fit_prepay`: all vintages
# 
# `run_all` processes all 27 vintages (about 30 seconds) and returns every table the fits need. `fit_prepay` then minimizes the exposure-weighted squared gap between model and observed SMM.

# **What this code does.** Runs `run_all` on all 27 vintages (about 30 seconds): prepayment buckets, default rows, liquidations, pipeline outcomes and 30-day rolls. Then `fit_prepay` fits the six S-curve parameters by exposure-weighted least squares. The table compares placeholder and fitted values.

# In[5]:


r = cal.run_all(hpi, pmms)
theta = cal.fit_prepay(r["prepay"])
pd.DataFrame({"placeholder": dict(zip(theta, placeholder)), "fitted": theta}).round(4)


# **What the output shows.** turnover 5.5% (was 6%), refi_max 41% (was 55%), midpoint 0.71 pp (was 0.75), slope 2.74 (was 3.5), burnout 0.0076 (was 0.02), seasoning ramp 6.2 months (was 30).

# **What this code does.** Measures fit quality: the exposure-weighted R² of placeholder vs fitted parameters across all buckets with at least 200 loan-months, and plots both S-curves for a seasoned loan with no burnout.

# In[6]:


b = r["prepay"]; b = b[b.n >= 200]
for name, t in [("placeholder", placeholder), ("fitted", list(theta.values()))]:
    pred = cal.prepay_model_smm(t, b.inc, b.age, b.burn)
    r2 = 1 - np.average((b.smm - pred) ** 2, weights=b.w) / np.average((b.smm - np.average(b.smm, weights=b.w)) ** 2, weights=b.w)
    print(f"{name:12s} weighted R^2 = {r2:.3f}")
x = np.linspace(-2, 3, 101)
for name, t in [("placeholder", placeholder), ("fitted", list(theta.values()))]:
    plt.plot(x, pp.smm_to_cpr(cal.prepay_model_smm(t, x, 60, 0)), label=name)
plt.xlabel("incentive vs PMMS (pp)"); plt.ylabel("CPR"); plt.title("S-curve, seasoned loan, no burnout"); plt.legend()


# **Result · `run_all` → `fit_prepay`.** Fitted on all vintages: turnover **5.5%**, refi_max **41%**, midpoint **+0.71 pp**, slope **2.74**, burnout **0.0076**, seasoning **6.2 months**. The weighted R² rises from **0.54 with the placeholders to 0.91** with the fitted values. The chart shows the fitted curve is lower at the top (about 47% vs 61%) and less steep.

# **Q&A · `fit_prepay`**
# 
# **Q: Why weight buckets by exposure in the fit?**
# A: A bucket with $50bn of exposure tells you much more than one with $50mm, and the model's job is to get dollar cash flows right. Exposure weighting makes the fit match dollars, not bucket counts.
# 
# **Q: Why do buckets with fewer than 200 loan-months get dropped?**
# A: Their observed SMM is too noisy (a single payoff can swing it), so they'd add noise without information.

# ---
# ## 5 · `default_rows`: who is at risk of defaulting
# 
# Rows are loan-months where the loan was **current last month**. The event is the first missed payment of a spell that reaches 90+ days late (or a credit event). COVID-forbearance months are dropped.

# **What this code does.** Builds `default_rows` for the 2007 and 2015 vintages: current loan-months at risk, with an event flag for the first missed payment of a spell that reaches 90+, and covariates from the month before. Prints counts, annualized rates and median LTV.

# In[7]:


d07 = cal.default_rows(p07, hpi); d15 = cal.default_rows(p15, hpi)
for y, d in [(2007, d07), (2015, d15)]:
    print(f"{y}: {len(d):,} loan-months at risk, {d.event.sum():,} default spells, "
          f"{d.event.mean()*1200:.2f}% a year, median MTM LTV {d.ltv.median():.1f}")
d07.head()


# **Result · `default_rows`.** 2007 loans: **2.04 million** current loan-months at risk, **4,222** default spells, **2.49% a year**, median MTM LTV 82. 2015 loans: 1.95 million, only **392** spells, **0.24% a year**, median LTV 61. A ten-fold difference driven by underwriting, the crash and equity.

# **Q&A · `default_rows`**
# 
# **Q: Why define the event as the *start* of a default spell?**
# A: The model's MDR applies to performing loans and puts defaulted loans into a liquidation pipeline. A loan can't go from current to 90+ days late in one month, so the event is the first missed payment of a spell that eventually reaches 90+ (two months before it gets there).
# 
# **Q: Why are COVID-forbearance months dropped?**
# A: In 2020–21 many borrowers in forbearance were reported as delinquent but later resumed paying without a loss. Counting them would double the fitted default rate.

# ---
# ## 6 · `default_buckets` → `fit_default`: Poisson GLM
# 
# Rows are grouped by LTV (5-pt), FICO (20-pt), DTI (5-pt), investor and pre-2009 buckets; the GLM fits log(monthly default rate) on those traits.

# **What this code does.** Fits the Poisson GLM with `fit_default` on the bucketed default rows from all vintages: log(monthly default rate) on LTV below/above 80, FICO, DTI, investor and pre-2009 vintage. Prints the coefficient table and the converted parameters.

# In[8]:


f = cal.fit_default(r["default"])
print(f["_glm"].summary().tables[1])
pd.Series({k: v for k, v in f.items() if not k.startswith("_")}).round(4).to_frame("fitted")


# **What the output shows.** All coefficients have the expected signs (higher LTV and DTI raise defaults, higher FICO lowers them) with large z-statistics. Converted: base 0.40% a year, LTV slopes 0.021 / 0.040, FICO 0.0091, DTI 0.0226, investor 1.22×, pre-2009 2.51×.

# **What this code does.** Turns the GLM coefficients into multipliers for typical comparisons, using exp(coefficient × difference).

# In[9]:


print("default-rate multipliers implied by the fit:")
print(f"  LTV 70 vs 80:  {np.exp(-10 * f['b_ltv_low']):.2f}x   LTV 100 vs 80: {np.exp(20 * f['b_ltv_high']):.2f}x")
print(f"  FICO 700 vs 750: {np.exp(50 * f['b_fico']):.2f}x   DTI 45 vs 38: {np.exp(7 * f['b_dti']):.2f}x   investor: {f['investor_mult']:.2f}x")
print(f"  pre-2009 vintage: {f['pre2009_mult']:.2f}x")


# **Result · `fit_default`.** The Poisson GLM gives (relative to LTV 80, FICO 750, DTI 38): LTV 70 → **0.81×**, LTV 100 → **2.22×**, FICO 700 → **1.58×**, DTI 45 → **1.17×**, investor **1.22×**, pre-2009 vintage **2.51×**. The base rate for post-2008 loans is **0.40% a year**.

# **Q&A · `fit_default`**
# 
# **Q: Why do the multipliers multiply together?**
# A: The GLM models log(default rate) as a sum of effects, so each effect multiplies the rate. An investor loan at LTV 100 with FICO 700 has 1.22 × 2.22 × 1.58 ≈ 4.3× the base rate.
# 
# **Q: Why is the LTV effect split at 80?**
# A: Below 80 a borrower has plenty of equity, so extra LTV matters little (2.1% per point). Above 80 equity disappears, and each point matters about twice as much (4.0% per point).

# ---
# ## 7 · `liquidations` / `clean_liquidations`: each credit event's loss
# 
# Per $1 of UPB at liquidation: loss = 1 + missed interest + costs − sale proceeds − MI. `clean_liquidations` drops tiny balances and impossible severities and adds the month the default spell started.

# **What this code does.** Cleans the liquidation records (drops tiny balances and impossible severities, adds the spell start month), checks the loss identity, and compares median loss components for spells before and after 2013.

# In[10]:


liq = cal.clean_liquidations(r["liquidations"])
print(f"{len(liq):,} usable liquidations")
liq["check"] = 1 + liq.missed_int + liq.costs - liq.proceeds - liq.mi - liq.severity
print("identity check (should be ~0):", liq["check"].abs().median().round(4))
liq["era"] = np.where(liq.start >= 201301, "spell 2013+", "spell <2013")
liq.groupby("era")[["severity", "missed_int", "costs", "proceeds", "mi", "ltv", "months_90_to_liq"]].median().round(3)


# **Result · `liquidations` / `clean_liquidations`.** **17,389** usable liquidations, and the loss identity (1 + missed interest + costs − proceeds − MI − severity) is exactly **0**. By era:
# - **Spells before 2013**: median severity **48.7%**, LTV 83.5, proceeds 64% of balance
# - **Spells from 2013**: median severity **29.4%**, LTV 63.5, proceeds 83%, costs 10.6%, 17 months from 90+ to liquidation

# **Q&A · `liquidations`**
# 
# **Q: Why is post-2013 severity lower?**
# A: Mostly because LTV at liquidation is lower (63 vs 84): prices were rising, so homes sold for more relative to the loan. Faster, more organized loss mitigation also helped.
# 
# **Q: Why drop liquidations under $10,000 or with severity outside −100% to 300%?**
# A: Tiny balances make the ratio explode (a $500 balance with $5,000 of costs is 1,000%). Those records would dominate a ratio-based fit without telling us anything.

# ---
# ## 8 · `pipeline_outcomes`: what happens after 90+ days late

# **What this code does.** Takes `pipeline_outcomes` for every 90+ spell with enough follow-up and compares liquidation, modification and "neither" shares, and the average rate cut, before and after 2013.

# In[11]:


po = r["pipeline"]
po = po.assign(era=np.where(po.first90 >= 201301, "90+ in 2013+", "90+ before 2013"))
out = po.groupby("era").agg(spells=("liquidated", "size"), liquidated=("liquidated", "mean"), modified=("modified", "mean"))
out["neither"] = 1 - out.liquidated - (po.groupby("era").apply(lambda d: (d.modified & ~d.liquidated).mean()))
print("average rate cut when modified:", po.loc[po.modified, "rate_cut"].groupby(po.era).mean().round(2).to_dict())
out.round(3)


# **Result · `pipeline_outcomes`.** Before 2013: 23,571 spells, **64.5% liquidated**, 34% modified (average cut **2.39 pp**). From 2013: 7,970 spells, **43% liquidated**, 37% modified (average cut **0.88 pp**), and 24% cured or paid off without either. Servicing has shifted away from foreclosure.

# **Q&A · `pipeline_outcomes`**
# 
# **Q: Why use only spells with at least 36 months of follow-up?**
# A: A recent spell may still be in progress. Including it as "not liquidated" would understate the liquidation share.
# 
# **Q: Why did rate cuts shrink from 2.39 pp to 0.88 pp?**
# A: Crisis-era modifications cut rates from 6–7% to as low as 2%. In the low-rate 2013–2021 period loans already had low coupons, so modifications relied more on term extensions and forbearance than rate cuts.

# ---
# ## 9 · `dq30_roll`: from 30 days late to 90+

# **What this code does.** Reads the totals from `dq30_roll`: loan-months 30 days late, and how many reached 90+ within 12 months. Converts the share to a monthly hazard.

# In[12]:


n30, hit = r["dq30_roll"]
p12 = hit / n30
print(f"{n30:,} loan-months 30 days late; {hit:,} reached 90+ within 12 months = {p12:.1%}")
print(f"equivalent monthly hazard: {1 - (1 - p12) ** (1/12):.2%}")


# **Result · `dq30_roll`.** Of **478,782** loan-months 30 days late, **117,216** reached 90+ within 12 months: **24.5%**, or about **2.31% a month**. (The model uses 2.28% after subtracting the base default rate.)

# **Q&A · `dq30_roll`**
# 
# **Q: Why does this matter for STACR?**
# A: 261 STACR loans are 30 days late on the tape. With a 24.5% roll rate, about a quarter of them will become default spells within a year, so they start with a much higher hazard than current loans.
# 
# **Q: Why convert 24.5% a year to a monthly hazard?**
# A: The projection runs monthly. 1 − (1 − 0.245)^(1/12) = 2.31% a month gives the same 12-month probability.

# ---
# ## 10 · `severity_model` / `fit_severity`
# 
# Only the distressed-sale discount is fitted; costs and MI come straight from the data, missed interest from the 19-month lag.

# **What this code does.** Runs `fit_severity` with the 19-month lag (costs and MI observed, sale discount fitted), then evaluates `severity_model` at LTVs 50–100 for a 6.76% coupon with the placeholder 20% and fitted 48% discounts.

# In[13]:


sev = cal.fit_severity(r["liquidations"], 19)
print({k: round(v, 3) for k, v in sev.items()})
grid = pd.DataFrame({"LTV": [50, 60, 70, 80, 90, 100]})
for d in [0.20, sev["reo_discount"]]:
    grid[f"severity, discount {d:.0%}"] = cal.severity_model(grid.LTV.values, 6.76, False, sev["costs"], d, 19, sev["mi_coverage"])
grid.round(3)


# **Result · `fit_severity`.** Costs **10%**, MI **18.5%** of the claim, fitted distressed-sale discount **48%**. The grid shows why the discount matters: at LTV 70, severity is **6%** with the placeholder 20% discount but **46%** with 48%. At LTV 50 it's 0% vs 17%.

# **Q&A · `fit_severity`**
# 
# **Q: Why fit only the discount?**
# A: Costs and MI are measured directly in the liquidation records, and missed interest comes from the fitted 19-month lag. The discount is the one piece that can't be observed without each home's market value, so it's chosen to make average model severity match the data.
# 
# **Q: Isn't 48% implausibly large?**
# A: It's large because it absorbs everything the national HPI misses: local price falls, property damage, vacancy and forced-sale pricing. The fit says these together cut recoveries about in half relative to an HPI-indexed value.

# ---
# ## 11 · `calibrate`: everything at once

# **What this code does.** Runs `calibrate`, which calls every fit above and returns all parameters, and compares them with the `PARAMS` dicts the model actually uses.

# In[14]:


fit = cal.calibrate(r)
allp = {**{f"prepay.{k}": v for k, v in fit["prepayment"].items()}, **{f"credit.{k}": v for k, v in fit["credit"].items()}}
now = {**{f"prepay.{k}": v for k, v in pp.PARAMS.items()}, **{f"credit.{k}": v for k, v in cm.PARAMS.items()}}
pd.DataFrame({"calibrate()": allp, "in PARAMS (rounded)": now}).round(4)


# **Result · `calibrate`.** Every parameter from `calibrate()` matches the value in `PARAMS` to rounding (for example turnover 0.0551 → 0.055, discount 0.4797 → 0.48). So the numbers the model runs on are exactly the ones fitted here.

# **Q&A · `calibrate`**
# 
# **Q: Why are the fitted values written into `PARAMS` instead of being recalculated each run?**
# A: So the model runs without the Freddie data (which teammates may not have) and so results don't change silently. Re-running notebook 05 or this one re-checks them.
# 
# **Q: When should the calibration be redone?**
# A: When new performance data arrives, when the model's form changes (for example adding a negative-equity block on refinancing), or for a sensitivity check (such as fitting only post-2013 data).

# ---
# ## Results and takeaways
# 
# - **Mark-to-market LTV** captures the crash: 2007 loans went from LTV 79 to 93 (2011) and back to 66 (2016).
# - **Prepayment**: observed speeds trace an S-curve, about 6–9% out of the money and up to 37% around +1.4 pp. The placeholder curve explained 54% of the variation; the fitted one explains **91%** (turnover 5.5%, refi max 41%, midpoint 0.71 pp, 6-month ramp).
# - **Defaults**: 2007 loans started default spells at 2.5% a year vs 0.24% for 2015 loans. The GLM explains this with LTV (LTV 100 = 2.2× LTV 80), FICO (700 = 1.6× 750), DTI, investor status, and a 2.5× pre-2009 underwriting effect. The base rate for today's loans is **0.40% a year**.
# - **Pipeline**: since 2013, only 43% of 90+ spells liquidate (vs 65% before), it takes about 19 months from first missed payment, and 24.5% of 30-day-late loans reach 90+ within a year.
# - **Severity**: median 29% for post-2013 spells and 49% before. With costs of 10% and a fitted **48%** distressed-sale discount, the model matches average losses and gives about 46% severity at LTV 70.
# - **Consistency**: every value from `calibrate()` matches `PARAMS` to rounding, so notebooks 02–05 run on exactly these fits.
