#!/usr/bin/env python
# coding: utf-8

# # 06 · Walkthrough: `src/freddie.py`, loading the Freddie Mac data
# 
# **Purpose.** See, one function at a time, how the raw Freddie Mac Single-Family Loan-Level files become the clean monthly panels that the calibration (notebooks 05 and 07) uses.
# 
# | # | Function | What it does |
# |---|---|---|
# | 1 | `load_orig` | reads one origination file (one row per loan) |
# | 2 | `load_all_orig` | all 27 vintages stacked |
# | 3 | `to_month_index` / `from_month_index` | YYYYMM ↔ month counter |
# | 4 | `market_rate_proxy` | market rate built from new loans' note rates |
# | 5 | `load_fred` | PMMS rate and FHFA HPI from FRED |
# | 6 | `load_perf` | reads one monthly performance file |
# | 7 | `compact_panel` / `load_panel` | merged, saved panel per vintage |
# | 8 | `CREDIT_ZB` | which loan exits count as credit events |
# 
# The Freddie files are licensed: clear outputs before committing this notebook.
# 
# **Process.** Freddie publishes two pipe-delimited text files per origination year: an *origination* file (one row per loan, fixed at closing) and a *performance* file (one row per loan per month until the loan leaves). `freddie.py` reads both with Freddie's column layout, keeps 30-year fixed loans, cleans "not available" codes, merges the loan's origination traits onto every month, and saves a compact parquet panel per vintage. It also builds a market-rate proxy from the loans and reads PMMS and the HPI from FRED. Each section below runs one step and explains what it produced.

# **What this code does.** Finds the repo root, makes `src/` importable, hides harmless pandas warnings, imports numpy / pandas / matplotlib, then imports `src.freddie` and prints where the raw files live and which vintages are expected.

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

from src import freddie as fr
print("raw folder:", fr.RAW)
print("vintages:", fr.VINTAGES.start, "to", fr.VINTAGES.stop - 1)


# **What the output shows.** The raw Freddie folder is `data/raw/freddie_sf/`, and the code expects vintages **2000 to 2026**.

# **Q&A · Setup**
# 
# **Q: Why does the first cell search upward for `src/`?**
# A: So `from src import ...` works whether Jupyter was started in the repo root or in `notebooks/`. It walks up the folders until it finds `src/` and adds that folder to the import path.
# 
# **Q: Why are warnings hidden?**
# A: pandas 2.2 on Python 3.14 prints harmless compatibility warnings. Only warnings are hidden; real errors still stop the cell.

# ---
# ## 1 · `load_orig`: one origination file
# 
# One row per loan, fixed at origination: FICO, DTI, LTV, balance, note rate, occupancy, purpose, state. The function keeps only **30-year fixed-rate** loans and turns Freddie's "not available" codes (FICO 9999, DTI 999) into missing values.

# **What this code does.** Counts the lines in the raw 2007 origination file, then calls `fr.load_orig(2007)`. That reads the pipe-delimited file with the column positions from Freddie's layout, converts numbers, marks "not available" codes as missing, and keeps only 30-year fixed-rate loans. `.head()` shows the first five loans.

# In[2]:


raw_rows = sum(1 for _ in open(fr.RAW / "sample_orig_2007.txt"))
o07 = fr.load_orig(2007)
print(f"2007 file: {raw_rows:,} loans in the file, {len(o07):,} kept (30-year fixed)")
o07.head()


# **What the output shows.** 50,000 loans in the file, 43,121 kept. Each row is one loan with its FICO, first payment month, MI %, occupancy, DTI, original balance, LTV, note rate, state, loan ID, purpose and term.

# **What this code does.** Summarizes the numeric origination fields of the 2007 loans with `describe()`: count, mean, spread and percentiles.

# In[3]:


o07[["fico", "dti", "orig_ltv", "orig_upb", "orig_rate", "mi_pct"]].describe().round(2)


# **What the output shows.** FICO averages 724 (middle half 681–773), DTI 37, original LTV 73 (median 79, max 100), balance $188k, note rate 6.40%. MI is 0% for at least three quarters of loans.

# **What this code does.** Counts loans by occupancy and purpose code, and counts missing FICO and DTI values.

# In[4]:


print("occupancy:", o07["occupancy"].value_counts().to_dict())
print("purpose:  ", o07["purpose"].value_counts().to_dict())
print("missing FICO / DTI:", o07["fico"].isna().sum(), "/", o07["dti"].isna().sum())


# **Result · `load_orig`.** The 2007 file has **50,000 loans**; **43,121 (86%)** are 30-year fixed and kept. Averages: FICO 724, DTI 37, original LTV 73 (median 79), loan size $188k, note rate 6.40%. Most loans have no mortgage insurance (75% have MI 0%), since MI is only required above 80 LTV. 87% are owner-occupied, 8% investor and 5% second homes. 48% are purchases, 34% cash-out refinances and 18% rate/term refinances. Only 35 loans are missing FICO and 961 missing DTI.

# **Q&A · `load_orig`**
# 
# **Q: Why drop the 14% of loans that aren't 30-year fixed?**
# A: STACR DNA1 is a pool of 30-year fixed-rate loans. 15- and 20-year loans prepay faster and default less, and ARMs reset, so mixing them in would bias every fitted parameter.
# 
# **Q: What do the occupancy and purpose codes mean?**
# A: Occupancy: P = primary residence, I = investment property, S = second home. Purpose: P = purchase, C = cash-out refinance, N = no-cash-out (rate/term) refinance. The model uses occupancy (investor ×1.22 default rate); purpose isn't in the model yet but could be added.
# 
# **Q: Why turn FICO 9999 and DTI 999 into missing values?**
# A: Those are Freddie's codes for "not available". Left as numbers, a FICO of 9999 would look like an extremely safe borrower and distort the default fit.

# ---
# ## 2 · `load_all_orig`: every vintage

# **What this code does.** Calls `fr.load_all_orig()`, which runs `load_orig` for every vintage 2000–2026 and stacks the results, then averages FICO, LTV, DTI and note rate by vintage.

# In[5]:


orig = fr.load_all_orig()
summary = orig.groupby("vintage").agg(loans=("loan_id", "size"), fico=("fico", "mean"), ltv=("orig_ltv", "mean"),
                                      dti=("dti", "mean"), rate=("orig_rate", "mean"))
print(f"{len(orig):,} 30-year fixed loans across {orig.vintage.nunique()} vintages")
summary.round(2)


# **What the output shows.** 977,577 30-year fixed loans in total. The table shows each vintage's size and average credit profile, which the next cell plots.

# **What this code does.** Plots the vintage averages from the previous table: note rate, FICO and original LTV.

# In[6]:


fig, ax = plt.subplots(1, 3, figsize=(16, 4))
summary["rate"].plot(ax=ax[0], marker="o", title="Average note rate by vintage (%)")
summary["fico"].plot(ax=ax[1], marker="o", title="Average FICO by vintage")
summary["ltv"].plot(ax=ax[2], marker="o", title="Average original LTV by vintage")
plt.tight_layout()


# **Result · `load_all_orig`.** **977,577** 30-year fixed loans across 27 vintages (about 24,000–47,000 per full year after the filter; 2026 is a partial year). The charts show three regimes:
# - **Note rates** fall from **8.2% (2000)** to **3.1% (2021)**, then jump to about **6.7–6.8% (2023–25)**. STACR's 2024–25 loans come from this high-rate period.
# - **FICO** is about 714–724 before the crisis, jumps to about **757–760 in 2009–11** as underwriting tightened, and settles around 745–756 since.
# - **Original LTV** stays between 69 and 81; DTI rises from about 32–34 to about **38** in recent vintages.

# **Q&A · `load_all_orig`**
# 
# **Q: Why does FICO jump after 2008?**
# A: After the crisis Freddie and lenders tightened credit standards: fewer low-FICO and low-documentation loans. That's why the default fit includes a pre-2009 indicator: older loans default 2.5× more even at the same FICO, LTV and DTI.
# 
# **Q: Why do recent vintages matter most for STACR?**
# A: STACR 2026-DNA1's loans were made in 2024–25 at 6.5–7%+ rates, with DTIs near 38. Their behavior is closest to recent vintages, but those have little history yet, so older vintages are needed to see a full rate cycle and a house-price crash.

# ---
# ## 3 · `to_month_index` / `from_month_index`: month arithmetic
# 
# Dates are stored as YYYYMM integers. Converting them to a running month count makes differences like "months from default to liquidation" simple subtraction. (Plain integer math is used because pandas date functions crash on this Python 3.14 install.)

# **What this code does.** Converts four YYYYMM dates to a running month count with `to_month_index`, converts them back with `from_month_index`, and checks the gap between Dec 2007 and Jan 2008.

# In[7]:


x = pd.Series([200701, 200712, 200801, 202602])
m = fr.to_month_index(x)
print(pd.DataFrame({"YYYYMM": x, "month index": m, "back": fr.from_month_index(m)}))
print("months from 2007-12 to 2008-01:", int(m[2] - m[1]))


# **Result · month arithmetic.** 200712 → 24,095 and 200801 → 24,096, so December 2007 to January 2008 is exactly **1 month**, and converting back returns the original YYYYMM.

# **Q&A · month arithmetic**
# 
# **Q: Why not just subtract YYYYMM numbers?**
# A: 200801 − 200712 = 89, not 1. Converting to a running month count (year × 12 + month − 1) makes every gap a simple subtraction, which the calibration needs for "months from default to liquidation" and the 12-month roll window.
# 
# **Q: Why not use pandas dates?**
# A: On this Python 3.14 install, pandas' date parser crashes (a segmentation fault), so the code uses integer math, which is also faster.

# ---
# ## 4 · `market_rate_proxy`: market rate from the loans themselves
# 
# For each month, the average note rate of new 30-year loans locked that month (first payment date minus 2 months), smoothed over 3 months.

# **What this code does.** Builds the market-rate proxy: for every month, the average note rate of new 30-year loans locked that month (first payment minus 2 months), with gaps filled and a centered 3-month average. Prints it at a few dates.

# In[8]:


proxy = fr.market_rate_proxy(orig)
print(proxy.loc[[200001, 200301, 200607, 200812, 201212, 202101, 202310, 202601]].round(2))


# **Result · `market_rate_proxy`.** The proxy follows the familiar history of 30-year rates: **8.18%** in Jan 2000, 6.06% in 2003, 6.68% in mid-2006, 5.64% in Dec 2008, **3.71%** in Dec 2012, **2.86%** in Jan 2021, **7.29%** in Oct 2023 and 6.16% in Jan 2026.

# **Q&A · `market_rate_proxy`**
# 
# **Q: Why subtract 2 months from the first payment date?**
# A: A borrower locks the rate roughly a month before closing, and the first payment is due about a month after closing. So a loan with its first payment in March reflects market rates from around January.
# 
# **Q: Why smooth over 3 months?**
# A: Each month's average comes from a few thousand loans in a 50,000-loan sample, so it's noisy. A centered 3-month average removes noise without shifting the timing.

# ---
# ## 5 · `load_fred`: PMMS and HPI from FRED
# 
# Reads the two CSVs downloaded into `data/raw/` and averages them by month.

# **What this code does.** Loads the PMMS 30-year rate and the FHFA HPI with `load_fred` (monthly averages by YYYYMM), lines up the proxy with PMMS, and prints the date ranges, the HPI peak and trough, and how closely the proxy tracks PMMS.

# In[9]:


pmms = fr.load_fred("MORTGAGE30US")
hpi = fr.load_fred("HPIPONM226S")
both = pd.concat([pmms, proxy], axis=1).dropna()
print(f"PMMS: {pmms.index.min()}–{pmms.index.max()}, latest {pmms.iloc[-1]:.2f}%")
print(f"HPI:  {hpi.index.min()}–{hpi.index.max()}, peak {hpi.loc[200001:201212].max():.1f} ({hpi.loc[200001:201212].idxmax()}), "
      f"trough {hpi.loc[200701:201312].min():.1f} ({hpi.loc[200701:201312].idxmin()})")
print(f"proxy − PMMS: mean {(both.market_rate - both.MORTGAGE30US).mean():.2f} pp, corr {both.corr().iloc[0, 1]:.3f}")


# **What the output shows.** PMMS covers Apr 1971 – Oct 2026 (latest 7.28%). The HPI peaked at 224.5 in Apr 2007 and bottomed at 176.7 in May 2011. Proxy − PMMS averages 0.14 pp with correlation 0.992.

# **What this code does.** Plots PMMS against the proxy (left) and the HPI since 2000 (right).

# In[10]:


fig, ax = plt.subplots(1, 2, figsize=(14, 4))
k = np.arange(len(both)); ax[0].plot(k, both.MORTGAGE30US, label="PMMS"); ax[0].plot(k, both.market_rate, label="proxy", alpha=0.7)
ax[0].set_xticks(k[::36], [str(p)[:4] for p in both.index[::36]]); ax[0].legend(); ax[0].set_title("30-year rate (%)")
h = hpi.loc[200001:]; k = np.arange(len(h)); ax[1].plot(k, h.values); ax[1].set_xticks(k[::36], [str(p)[:4] for p in h.index[::36]])
ax[1].set_title("FHFA purchase-only HPI"); plt.tight_layout()


# **Result · `load_fred`.** PMMS runs from Apr 1971 to Oct 2026, latest **7.28%**. The HPI peaks at **224.5 in Apr 2007** and bottoms at **176.7 in May 2011**, a **21% national decline**, then more than doubles to about 443 today. The proxy tracks PMMS closely (**corr 0.992**, proxy about 0.14 pp higher).

# **Q&A · `load_fred`**
# 
# **Q: Why use PMMS rather than the proxy in the calibration?**
# A: Scenario paths (Coco's work) will be expressed as market mortgage rates like PMMS. Calibrating against PMMS means the fitted S-curve can be fed those paths directly. The proxy confirms PMMS is the right measure.
# 
# **Q: Why does a 21% national decline matter so much?**
# A: It's the only big price decline in the data, so it's what identifies how defaults and severity react to negative equity. Local declines were much larger (30–50% in parts of CA, FL, NV and AZ), which a national index understates.

# ---
# ## 6 · `load_perf`: one monthly performance file
# 
# One row per loan per month: balance, delinquency status, age, rate, modification flag, and, when the loan leaves, the zero-balance code and loss details. `RA` (REO acquisition) is recoded as 99.

# **What this code does.** Reads the 2007 monthly performance file with `load_perf`: one row per loan per month, with balance, delinquency status (REO coded 99), age, remaining term, rate, modification flag and, at exit, the zero-balance code and loss details.

# In[11]:


perf07 = fr.load_perf(2007)
print(f"{len(perf07):,} loan-months for the 2007 vintage, {perf07.loan_id.nunique():,} loans")
perf07.head()


# **What the output shows.** 3,012,061 loan-months for 50,000 loans (all products, before the 30-year filter). The first rows follow one loan month by month.

# **What this code does.** Picks the first 2007 loan that ended in an REO sale (code 09) and shows its last 8 months, including the loss fields on the final row.

# In[12]:


one = perf07[perf07.zb_code == "09"].loan_id.iloc[0]
path = perf07[perf07.loan_id == one]
print("one 2007 loan that ended in an REO sale (ID not shown)")
path[["period", "upb", "dq", "age", "rate", "modified", "zb_code", "zb_upb", "dq_interest", "expenses", "net_sale", "actual_loss"]].tail(8)


# **What the output shows.** The loan was 27 months late in Jul 2015, became REO in Aug 2015 and was sold in Feb 2016 with a $71,677 loss on a $60,182 balance.

# **What this code does.** Counts loan-months by delinquency status (months late) and counts how loans left the data, by zero-balance code.

# In[13]:


print("delinquency status counts (months late; 99 = REO):")
print(perf07.dq.value_counts().sort_index().head(12).to_dict())
print("zero-balance codes:", perf07.loc[perf07.zb_code != "", "zb_code"].value_counts().to_dict())


# **Result · `load_perf`.** The 2007 performance file has **3,012,061 loan-months** for its 50,000 loans (all products, before the 30-year filter).
# - **One REO loan, step by step**: one 2007 loan was 27 months late in Jul 2015, became REO (status 99) in Aug 2015, and was sold in Feb 2016. Removed balance $60,182; missed interest $10,274; expenses $17,881; net sale proceeds $15,897 (stored as a negative number, a recovery). **Actual loss $71,677, about 119% of the balance**, an extreme case after a nine-year timeline.
# - **Status counts**: 2.72 million current months, 94k one month late, 34k two months late, then a long tail of seriously delinquent months.
# - **How loans left**: 42,554 paid off (01), and credit events of 2,525 REO (09), 1,197 short sales (03), 539 third-party sales (02) and 223 note sales (15).

# **Q&A · `load_perf`**
# 
# **Q: How is the actual loss calculated?**
# A: Loss = removed balance + delinquent interest + expenses − sale proceeds − other recoveries − MI. For the example: 60,182 + 10,274 + 17,881 − 15,897 − 763 = 71,677. This identity holds for the liquidations used in the fit to within a few cents.
# 
# **Q: Why are recoveries stored as negative numbers?**
# A: Freddie reports them as credits that reduce the loss. The code flips the sign when it computes proceeds per dollar of balance.
# 
# **Q: What does status 99 (`RA`) mean?**
# A: REO acquisition: the lender took the home through foreclosure and owns it while trying to sell it. The loan's final row then carries the sale's loss details.

# ---
# ## 7 · `compact_panel` / `load_panel`: the saved panel
# 
# Keeps 30-year fixed loans only, adds origination fields (FICO, DTI, LTV, MI, occupancy...) to every month, sorts by loan and month, and saves `data/processed/freddie/panel_YYYY.parquet`. Later loads take a second.

# **What this code does.** Times `fr.load_panel(2007)`, which loads the saved parquet panel (built once by `compact_panel`), adds up the size of all 27 panels on disk, and shows the first rows with the merged origination fields.

# In[14]:


import time
t = time.time(); p07 = fr.load_panel(2007); secs = time.time() - t
print(f"panel 2007: {p07.shape[0]:,} rows × {p07.shape[1]} columns, loaded in {secs:.1f}s")
sizes = {y: (fr.OUT / f"panel_{y}.parquet").stat().st_size / 1e6 for y in fr.VINTAGES}
print(f"all panels: {sum(sizes.values()):,.0f} MB on disk (raw text: about 9 GB)")
p07[["loan_id", "period", "upb", "dq", "fico", "dti", "orig_ltv", "orig_upb", "occupancy", "first_pay"]].head()


# **Result · `compact_panel` / `load_panel`.** The 2007 panel has **2,605,770 rows × 27 columns** (30-year fixed only) and loads in about **0.1 seconds**. All 27 panels take **310 MB** on disk, vs about 9 GB of raw text. Each row now carries the loan's FICO, DTI, original LTV, original balance and occupancy next to its monthly status.

# **Q&A · `compact_panel`**
# 
# **Q: Why build a panel instead of reading the raw files every time?**
# A: The raw files are 9 GB of text, and parsing them takes minutes. The parquet panels hold only the needed columns in compact types, so every later step (and notebooks 05 and 07) loads a vintage in a fraction of a second.
# 
# **Q: Why merge origination fields into every month?**
# A: The calibration needs each loan-month's covariates (FICO, DTI, original LTV for the mark-to-market LTV) next to its outcome. Merging once avoids repeating the join for every fit.
# 
# **Q: Are the panels committed to GitHub?**
# A: No. They're in `data/processed/`, which is gitignored, because they're built from the licensed Freddie files.

# ---
# ## 8 · `CREDIT_ZB`: which exits are credit events
# 
# A loan leaves the data with a zero-balance code. `01` is a payoff (prepayment or maturity). `02`, `03`, `09` and `15` are **credit events**, which is what STACR counts as losses.

# **What this code does.** Loads four vintages (2005, 2007, 2015, 2020) and tabulates how their loans left the data, by zero-balance code, using readable names. Prints which codes count as credit events.

# In[15]:


names = {"01": "prepaid / matured", "02": "third-party sale", "03": "short sale", "09": "REO disposition",
         "15": "non-performing note sale", "16": "re-performing loan sale", "96": "removed (other)", "06": "repurchase"}
rows = []
for y in [2005, 2007, 2015, 2020]:
    p = fr.load_panel(y); z = p.loc[p.zb_code != "", "zb_code"].value_counts()
    rows.append({"vintage": y, "loans": p.loan_id.nunique(), **{names.get(k, k): v for k, v in z.items()}})
t = pd.DataFrame(rows).set_index("vintage").fillna(0).astype(int)
print("credit-event codes:", sorted(fr.CREDIT_ZB))
t


# **Result · `CREDIT_ZB`.** Credit events are codes **02, 03, 09 and 15**. The contrast between vintages is the whole story of the crisis:
# - **2005**: 1,437 REO sales and 622 short sales out of 38,124 loans
# - **2007**: 2,401 REO, 1,154 short sales, 500 third-party sales and 210 note sales out of 43,121 loans, about **9.9%** of loans ending in a credit event
# - **2015**: only 45 REO and 18 short sales out of 36,501 loans, about **0.3%**
# - **2020**: 10 REO and no short sales so far
# 
# Most loans of every vintage end by paying off (code 01).

# **Q&A · `CREDIT_ZB`**
# 
# **Q: Why are re-performing loan sales (16) not counted as credit events?**
# A: These are loans that went delinquent, recovered and kept paying, then were sold as a package. They don't produce a liquidation loss in the reference pool. STACR's credit events (PPM p. 171) are short sales, sales of seriously delinquent notes, third-party foreclosure sales, REO dispositions and charge-offs, which map to codes 02, 03, 09 and 15.
# 
# **Q: Why do 2015 and 2020 loans have so few credit events?**
# A: Better underwriting, and above all rising home prices: borrowers who got into trouble could usually sell at a profit instead of defaulting. Pandemic forbearance also kept many 2020 loans out of foreclosure.

# ---
# ## Results and takeaways
# 
# - **Coverage**: 977,577 thirty-year fixed loans from 27 vintages (2000–2026), with monthly performance through 2026. The 2007 vintage alone has about 2.6 million loan-months after the filter.
# - **Three eras** show in the origination data: high rates and weaker credit before 2008, tight credit (FICO ~757–760) and falling rates in 2009–2021, and a return to 6.5–7% rates with DTIs near 38 in 2023–25, the era of STACR's loans.
# - **Market inputs are sound**: the proxy built from the loans tracks PMMS with correlation 0.992, and the HPI shows the 21% national decline from Apr 2007 to May 2011 that identifies the credit model.
# - **Loss detail is complete**: each liquidation carries balance, missed interest, expenses, sale proceeds, MI and the actual loss, and they add up exactly (the REO example lost $71,677 on $60,182).
# - **Credit events depend on the era**: about 9.9% of 2007 loans ended in a credit event vs about 0.3% of 2015 loans.
# - **Saved panels** (310 MB, gitignored) load in a fraction of a second and feed notebooks 05 and 07.
