"""Load and clean the Bloomberg loan-level file for the STACR 2026-DNA1 reference pool.

Bloomberg exports have a title row (e.g. "STACR 26-DNA1 A1 Mtge") above the header,
mixed text/number status codes, and a pay-history string per loan.

Which tape: the original file STACR_2026_DNA1_A1_Loan_Level.xlsx is the post-August 2026
pool. A newer tape saved as STACR_2026_DNA1_A1_Loan_Level_YYYY-MM.xlsx (YYYY-MM = the
last payment month it reflects, e.g. _2026-09 for the post-September pool) is used
automatically; the newest one wins. main() records the tape's month in
data/processed/stacr_dna1_asof.json, and collateral_projection.load_pool() rolls the
tape forward only if it is older than the valuation snapshot.
"""
import json
import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

FILES = {
    "stacr_dna1": "STACR_2026_DNA1_A1_Loan_Level.xlsx",
}
DEFAULT_AS_OF = "2026-08"          # the original tape is the post-August 2026 pool
TAPE_PATTERN = re.compile(r"STACR_2026_DNA1_A1_Loan_Level_(\d{4}-\d{2})\.xlsx$")

KEEP = [
    "Loan ID", "Pay History", "Current Balance", "Original Balance", "Gross Coupon",
    "Payment Due", "Original LTV", "Amortized LTV", "HPI Adjusted LTV", "Credit Score",
    "Age", "Months to Maturity", "Loan Type", "Geographics", "Account Status",
    "Property Type", "Occupancy", "Loan Purpose", "MSA", "Current Debt to Income",
]

# Account status: C = current, 3/6/9 = 30/60/90+ days delinquent.
# B / F / other codes: CONFIRM against Bloomberg field legend before use.
STATUS_MAP = {"C": 0, "3": 1, "6": 2, "9": 3}


def latest_tape(raw: Path = RAW) -> tuple[Path, str]:
    """(path, as_of YYYY-MM) of the newest STACR tape in data/raw."""
    dated = sorted((m.group(1), f) for f in raw.glob("STACR_2026_DNA1_A1_Loan_Level_*.xlsx")
                   if (m := TAPE_PATTERN.search(f.name)))
    if dated:
        as_of, f = dated[-1]
        return f, as_of
    return raw / FILES["stacr_dna1"], DEFAULT_AS_OF


def load(name: str) -> pd.DataFrame:
    """Read one raw file, skipping Bloomberg's title row, and drop blank rows."""
    path = latest_tape()[0] if name == "stacr_dna1" else RAW / FILES[name]
    df = pd.read_excel(path, header=1)
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
        tape, as_of = latest_tape()
        (PROCESSED / f"{name}_asof.json").write_text(json.dumps({"tape": tape.name, "as_of": as_of}))
        print(f"{name}: {len(df):,} loans, ${df['Current Balance'].sum()/1e9:.2f}bn, "
              f"{unmapped} loans with unmapped status codes (tape {tape.name}, as of {as_of})")


if __name__ == "__main__":
    main()
