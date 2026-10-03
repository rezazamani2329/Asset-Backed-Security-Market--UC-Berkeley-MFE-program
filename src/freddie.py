"""Load the Freddie Mac Single-Family Loan-Level Dataset (sample files) for calibration.

Files (NOT committed, licensed): data/raw/freddie_sf/sample_orig_YYYY.txt and
sample_perf_YYYY.txt, pipe-delimited, no header. Column positions follow Freddie's
"Single-Family Loan-Level Dataset General User Guide" file layout.

Only 30-year fixed-rate loans are kept, to match the STACR reference pool.
compact_panel() writes one small parquet per vintage to data/processed/freddie/.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "freddie_sf"
OUT = ROOT / "data" / "processed" / "freddie"
VINTAGES = range(2000, 2027)

# Origination file: 0-based position -> name
ORIG_COLS = {
    0: "fico", 1: "first_pay", 5: "mi_pct", 7: "occupancy", 9: "dti", 10: "orig_upb",
    11: "orig_ltv", 12: "orig_rate", 15: "amort_type", 16: "state", 19: "loan_id",
    20: "purpose", 21: "orig_term",
}

# Monthly performance file
PERF_COLS = {
    0: "loan_id", 1: "period", 2: "upb", 3: "dq", 4: "age", 5: "rem", 7: "mod_flag",
    8: "zb_code", 10: "rate", 13: "mi_rec", 14: "net_sale", 15: "non_mi_rec",
    16: "expenses", 21: "actual_loss", 25: "eltv", 26: "zb_upb", 27: "dq_interest",
}

# Zero-balance codes: 01 prepaid / matured; credit events: 02 third-party sale,
# 03 short sale, 09 REO disposition, 15 non-performing note sale
CREDIT_ZB = {"02", "03", "09", "15"}


def load_orig(year: int) -> pd.DataFrame:
    df = pd.read_csv(RAW / f"sample_orig_{year}.txt", sep="|", header=None,
                     usecols=list(ORIG_COLS), dtype=str)
    df = df.rename(columns=ORIG_COLS)
    for c in ["fico", "first_pay", "mi_pct", "dti", "orig_upb", "orig_ltv", "orig_rate", "orig_term"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.loc[df["fico"] > 850, "fico"] = np.nan          # 9999 = not available
    df.loc[df["dti"] > 65, "dti"] = np.nan             # 999 = not available
    df.loc[df["orig_ltv"] > 200, "orig_ltv"] = np.nan
    df.loc[df["mi_pct"] > 100, "mi_pct"] = np.nan
    df["vintage"] = year
    return df[(df["amort_type"] == "FRM") & (df["orig_term"] == 360)].drop(columns="amort_type")


def load_all_orig() -> pd.DataFrame:
    return pd.concat([load_orig(y) for y in VINTAGES], ignore_index=True)


def market_rate_proxy(orig: pd.DataFrame) -> pd.Series:
    """Monthly 30y market mortgage rate proxy: mean note rate of new 30y FRM loans.

    A loan's rate is locked roughly two months before its first payment, so the
    series is indexed by first payment date minus 2 months. Index: period (YYYYMM int).
    """
    lock = to_month_index(orig["first_pay"]) - 2
    s = orig.groupby(lock.to_numpy())["orig_rate"].mean().sort_index()
    s = s.reindex(np.arange(s.index.min(), s.index.max() + 1)).interpolate()
    s.index = from_month_index(s.index)
    return s.rolling(3, center=True, min_periods=1).mean().rename("market_rate")


def to_month_index(yyyymm) -> pd.Series:
    """YYYYMM -> months since year 0 (integer math; avoids pandas datetimes)."""
    x = pd.Series(yyyymm).astype("int64")
    return (x // 100) * 12 + (x % 100) - 1


def from_month_index(m) -> np.ndarray:
    m = np.asarray(m, dtype="int64")
    return (m // 12) * 100 + (m % 12) + 1


def load_perf(year: int) -> pd.DataFrame:
    df = pd.read_csv(RAW / f"sample_perf_{year}.txt", sep="|", header=None,
                     usecols=list(PERF_COLS), dtype=str)
    df = df.rename(columns=PERF_COLS)
    df["dq"] = df["dq"].replace({"RA": "99"})
    df["dq"] = pd.to_numeric(df["dq"], errors="coerce").fillna(0).astype("int16")
    for c in ["period", "age", "rem"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int32")
    for c in ["upb", "rate", "mi_rec", "net_sale", "non_mi_rec", "expenses", "actual_loss",
              "eltv", "zb_upb", "dq_interest"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    df.loc[df["eltv"] >= 999, "eltv"] = np.nan
    df["modified"] = df["mod_flag"].isin(["Y", "P"])
    df["zb_code"] = df["zb_code"].fillna("")
    return df.drop(columns="mod_flag")


def compact_panel(year: int, overwrite: bool = False) -> Path:
    """Perf rows of 30y FRM loans for one vintage, merged with origination fields."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"panel_{year}.parquet"
    if path.exists() and not overwrite:
        return path
    orig = load_orig(year)
    perf = load_perf(year)
    perf = perf[perf["loan_id"].isin(orig["loan_id"])]
    keep = ["loan_id", "fico", "dti", "orig_ltv", "orig_upb", "orig_rate", "mi_pct",
            "occupancy", "first_pay", "state", "vintage"]
    perf = perf.merge(orig[keep], on="loan_id", how="left")
    perf = perf.sort_values(["loan_id", "period"])
    perf.to_parquet(path, index=False)
    return path


def load_panel(year: int) -> pd.DataFrame:
    return pd.read_parquet(compact_panel(year))


def load_fred(series: str) -> pd.Series:
    """Monthly average of a FRED CSV in data/raw/ (e.g. HPIPONM226S, MORTGAGE30US), by YYYYMM."""
    df = pd.read_csv(ROOT / "data" / "raw" / f"{series}.csv", dtype=str)
    month = (df.iloc[:, 0].str[:4] + df.iloc[:, 0].str[5:7]).astype(int)
    val = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    return val.groupby(month.to_numpy()).mean().dropna().rename(series)
