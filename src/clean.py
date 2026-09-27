"""Load and clean Bloomberg loan-level files for the STACR / CAS reference pools.

Bloomberg exports have a title row (e.g. "STACR 26-DNA1 A1 Mtge") above the header,
mixed text/number status codes, and a pay-history string per loan.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

FILES = {
    "stacr_dna1": "STACR_2026_DNA1_A1_Loan_Level.xlsx",
    "cas_r01_g2": "CAS_2026_R01_2A1_Loan_level.xlsx",
}

KEEP = [
    "Loan ID", "Pay History", "Current Balance", "Original Balance", "Gross Coupon",
    "Payment Due", "Original LTV", "Amortized LTV", "HPI Adjusted LTV", "Credit Score",
    "Age", "Months to Maturity", "Loan Type", "Geographics", "Account Status",
    "Property Type", "Occupancy", "Loan Purpose", "MSA", "Current Debt to Income",
]

# Account status: C = current, 3/6/9 = 30/60/90+ days delinquent.
# B / F / other codes: CONFIRM against Bloomberg field legend before use.
STATUS_MAP = {"C": 0, "3": 1, "6": 2, "9": 3}


def load(name: str) -> pd.DataFrame:
    """Read one raw file, skipping Bloomberg's title row, and drop blank rows."""
    df = pd.read_excel(RAW / FILES[name], header=1)
    df = df[df["Loan ID"].notna()]
    return df[[c for c in KEEP if c in df.columns]].copy()


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Loan ID"] = df["Loan ID"].astype(str)
    df["Account Status"] = df["Account Status"].astype(str).str.strip()
    df["dq_bucket"] = df["Account Status"].map(STATUS_MAP)  # NaN = code needs review
    df["Pay History"] = df["Pay History"].fillna("").astype(str)
    df["ever_dq"] = df["Pay History"].str.contains(r"[369]")
    for c in ["Credit Score", "HPI Adjusted LTV"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # HPI-adjusted LTV of 0 is a data error, not a zero-LTV loan
    df.loc[df["HPI Adjusted LTV"] <= 0, "HPI Adjusted LTV"] = float("nan")
    df["weight"] = df["Current Balance"] / df["Current Balance"].sum()
    return df


def main():
    PROCESSED.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        df = clean(load(name))
        df.to_parquet(PROCESSED / f"{name}.parquet", index=False)
        unmapped = df["dq_bucket"].isna().sum()
        print(f"{name}: {len(df):,} loans, ${df['Current Balance'].sum()/1e9:.2f}bn, "
              f"{unmapped} loans with unmapped status codes")


if __name__ == "__main__":
    main()
