#!/usr/bin/env python
# coding: utf-8

# # 01 · Data check: STACR 2026-DNA1 & CAS 2026-R01 reference pools
# 
# **Purpose.** Before modeling, make sure the loan-level data is clean and understand what drives this pool's prepayment and credit risk. This notebook is the input side of the pipeline:
# 
# ```
# data/raw (Bloomberg tapes) → src/clean.py → data/processed/*.parquet → 02 (behavior model) → 03 (pool projection) → waterfall
# ```
# 
# **Process.**
# 1. **Clean** (`src/clean.py`): skip Bloomberg's title row, keep the modeling fields (balance, coupon, FICO, LTV, DTI, age, term, status, occupancy, purpose, state), map account status to a delinquency bucket (C = current, 3/6/9 = 30/60/90+ days), flag loans ever delinquent, set impossible HPI-LTVs of 0 to missing, and add each loan's balance weight.
# 2. **Summarize** both pools with balance-weighted averages, the standard way to describe a mortgage pool.
# 3. **Plot** the distributions that drive the model: coupon (refinancing incentive), HPI-adjusted LTV (default and severity), and FICO (default).
# 4. **List status codes** still to resolve (`B`, `F`).
# 5. **Anchor** the base-case prepayment speed on the paydown since the Feb 2026 cut-off.
# 
# **Data is licensed: clear outputs before committing** (Kernel → Restart & Clear Output).

# In[1]:


import sys, warnings
from pathlib import Path

# Find the repo root (the folder that contains src/) so imports work from anywhere
ROOT = Path.cwd()
while not (ROOT / "src").is_dir() and ROOT != ROOT.parent:
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore", category=FutureWarning)  # pandas 2.2 + Python 3.14 noise

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
pd.set_option("display.float_format", "{:,.4f}".format)
print("repo root:", ROOT)


# ## 1. Clean the raw tapes → `data/processed/*.parquet`

# In[2]:


from src import clean
clean.main()


# In[3]:


pools = {name: pd.read_parquet(clean.PROCESSED / f"{name}.parquet") for name in clean.FILES}
pools['stacr_dna1'].head()


# **Result · Cleaning.** `clean.py` ran without errors and wrote both parquet files: **STACR 56,871 loans, $19.44bn** and **CAS 48,808 loans, $16.90bn**. Every Bloomberg row with a Loan ID was kept (no duplicates, no zero balances). The table preview shows the added fields: `dq_bucket` (0 = current), `ever_dq`, and `weight` (each loan's share of pool balance). The only cleaning issue flagged is **20 STACR loans with status codes the map does not cover** (see section 4). CAS has none.

# ## 2. Pool summary (balance-weighted)

# In[4]:


def summarize(df):
    w = df["Current Balance"]
    def wa(c):
        x = pd.to_numeric(df[c], errors="coerce"); m = x.notna()
        return (x[m] * w[m]).sum() / w[m].sum()
    return pd.Series({
        "loans": len(df),
        "current bal ($bn)": w.sum() / 1e9,
        "WA coupon": wa("Gross Coupon"),
        "WA FICO": wa("Credit Score"),
        "WA orig LTV": wa("Original LTV"),
        "WA HPI LTV": wa("HPI Adjusted LTV"),
        "WA DTI": wa("Current Debt to Income"),
        "WA age (mo)": wa("Age"),
        "% bal currently dq": w[df["dq_bucket"] > 0].sum() / w.sum() * 100,
        "loans w/ unmapped status": df["dq_bucket"].isna().sum(),
    })

pd.DataFrame({k: summarize(v) for k, v in pools.items()})


# **Result · Pool summary.**
# - **Credit quality is nearly identical**: WA FICO **759 vs 755** and WA DTI **38.5 vs 39.8**.
# - **LTV is the real difference**: original LTV **75.6 vs 92.5**, and HPI-adjusted LTV **70.5 vs 87.0**. The two deals sit in different LTV buckets (STACR DNA1 ≤ 80, CAS group 2 > 80), so they carry different loss risk even with the same borrowers' credit scores.
# - **Seasoning**: WA age **17.3 vs 15.4 months**. Both pools are young, but already past the fitted 6-month seasoning ramp (notebook 05), so they prepay at full speed.
# - **Coupons**: WA **6.76% vs 6.62%**. That was above the market rate earlier in 2026 (PMMS about 6.05–6.5% from February to June), which explains the fast paydown since cut-off. With PMMS now at **7.28%**, both pools are about 0.5–0.7 pp *out of the money*.
# - **Delinquency**: **0.62% vs 1.07%** of balance is 30+ days late. CAS is higher, consistent with its higher LTVs.

# ## 3. Distributions that drive your model
# 
# Coupon → refi incentive; HPI LTV → default & severity.

# In[5]:


fig, axes = plt.subplots(1, 3, figsize=(15, 4))
for name, df in pools.items():
    axes[0].hist(df["Gross Coupon"], bins=30, weights=df["weight"], alpha=0.5, label=name)
    axes[1].hist(df["HPI Adjusted LTV"].dropna(), bins=40, alpha=0.5, label=name)
    axes[2].hist(df["Credit Score"].dropna(), bins=40, alpha=0.5, label=name)
for ax, t in zip(axes, ["Gross coupon (bal-weighted)", "HPI-adjusted LTV", "FICO"]):
    ax.set_title(t); ax.legend()
plt.tight_layout()


# **Result · Distributions (balance-weighted coupon, LTV, FICO).**
# - **Coupon**: about **80% of balance** in both pools has a coupon between 6.25% and 7.5% (82% STACR, 79% CAS). Because coupons are bunched, a rate move shifts most of the pool along the S-curve together, which is why prepayment is so rate-sensitive. From today's 7.28% PMMS, rates would need to fall about 1 pp to put most of the pool on the steep part of the curve.
# - **HPI-adjusted LTV**: the two pools barely overlap. The middle 80% of STACR loans sit at **60–77** (max 88), while CAS sits at **80–93** (max 107, and **22 CAS loans are already underwater**). This is the single most important picture for severity.
# - **FICO**: the middle 80% is about **690–800** in both pools, with tails down to about 600. The default model's FICO term matters mainly for that low-FICO tail.

# ## 4. Status codes still to resolve
# 
# > Before mapping `B` and `F` in `STATUS_MAP`: what do you think they mean? What should `^` in Pay History mean?

# In[6]:


pools['stacr_dna1']['Account Status'].value_counts()


# **Result · Status codes.** STACR has **56,465 current** loans, **261** 30-day, **56** 60-day and **69** 90+-day delinquent, plus **16 `B`** and **4 `F`**. `B`/`F` most likely mean bankruptcy and foreclosure (confirm with the Bloomberg field legend). They are only 20 loans, but they are the most likely to become credit events soon. The model currently treats them as seriously delinquent and puts them straight into the liquidation pipeline.

# ## 5. Anchor for the base case
# 
# The pool was $22.78bn at the Feb 2026 cut-off and is $19.44bn on this tape.
# 
# > Using your `smm_to_cpr`, what CPR does that paydown imply? What else besides prepayment reduced the balance?

# **Result · Anchor.** The pool went from **$22.78bn** at the Feb 2026 cut-off to **$19.44bn** on this tape, a **14.7% paydown** in about 7 months (loan count 64,434 → 56,871, −11.7%). Taking out about 0.1% a month of scheduled principal leaves an SMM of about 2.1%, which is **CPR ≈ 23%**. The base-case prepayment model in notebook 02 should land in the 20–25% range.

# ## Results and takeaways
# 
# - **Size.** STACR DNA1 has **56,871 loans, $19.44bn** today (down from $22.78bn and 64,434 loans at the Feb 2026 cut-off). CAS R01 group 2 has 48,808 loans, $16.90bn. Every loan is a fixed-rate 30-year, about 15–17 months seasoned.
# - **Credit quality is strong and similar**: WA FICO is 759 (STACR) vs 755 (CAS), and WA DTI is 38.5 vs 39.8.
# - **The big difference is LTV**: STACR's original LTV is 61–80 (WA 75.6), while CAS group 2's is 81–97 (WA 92.5). On today's home prices the HPI-adjusted LTV is **70.5 vs 87.0**. STACR borrowers have about 30% equity, which lowers default rates, but calibration (notebook 05) shows liquidations still lose about 35–45% even at this LTV. CAS loans depend on mortgage insurance. **A direct STACR-vs-CAS spread comparison has to adjust for this.**
# - **Coupons** (WA 6.76% STACR, 6.62% CAS) were in the money earlier in 2026, when PMMS was 6.05–6.5%. At today's **7.28%** they are out of the money, so prepayment should slow sharply from the ~23% CPR seen since cut-off. Prepayment is still the dominant risk for timing.
# - **Delinquency is low**: 0.62% of STACR balance and 1.07% of CAS balance is currently 30+ days delinquent.
# - **To resolve**: 16 STACR loans coded `B` and 4 coded `F` (most likely bankruptcy and foreclosure; confirm with the Bloomberg legend). The model currently treats them as seriously delinquent.
# - **Prepayment anchor**: the paydown from $22.78bn to $19.44bn in about 7 months implies roughly **20–25% CPR**, which is the base-case target for notebook 02.
