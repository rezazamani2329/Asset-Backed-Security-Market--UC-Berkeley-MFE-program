"""Mortgage rate lock-in: how much it lengthens the STACR 2026-DNA1 notes.

Owner: Reza. Used by notebooks/09_lockin.ipynb.

Lock-in lives in src/prepayment.py (PARAMS["lockin"], off by default). This module runs the
existing pipeline (collateral projection -> waterfall -> pricing) for several lock-in
strengths and rate paths, and collects pool speeds, note WALs and the discount margin earned
at the Bloomberg ask price, so "with vs. without lock-in" can be compared side by side.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src import collateral_projection as cp, prepayment as pp
from src import run_waterfall_pricing as rw
from src.pricing import discount_margin

ROOT = Path(__file__).resolve().parents[1]
PRICING_RATES = ROOT / "data" / "scenarios" / "pricing_rates.csv"

# Bloomberg, October 2, 2026 (data/bloomberg_validation/, README section 8.3)
BLOOMBERG_ASK = {"A-1": 99.978, "M-1": 100.027, "M-2A": 99.720, "M-2B": 99.148}
BLOOMBERG_WAL = {"A-1": 1.39, "M-1": 1.23, "M-2A": 2.78, "M-2B": 3.48}
PMMS_VALUATION = 7.28   # Freddie PMMS 30y on 2026-10-01 (FRED MORTGAGE30US)

LOCKIN_CASES = {"no lock-in": 0.0, "lock-in (FHFA)": pp.LOCKIN_FHFA, "strong lock-in": 2 * pp.LOCKIN_FHFA}


def rate_gap_table(pool: pd.DataFrame, market_rate: float = PMMS_VALUATION,
                   edges=(-np.inf, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, np.inf)) -> pd.DataFrame:
    """Loans and balance share by rate gap (market rate - coupon, pp) on the valuation date."""
    gap = market_rate - pool["Gross Coupon"].to_numpy(float)
    bal = pool["Current Balance"].to_numpy(float)
    group = pd.cut(gap, list(edges))
    out = pd.DataFrame({"gap": group, "balance": bal}).groupby("gap", observed=False).agg(
        loans=("balance", "size"), balance=("balance", "sum"))
    out["balance_share"] = out["balance"] / bal.sum()
    # share of normal turnover kept at the middle of each gap group, FHFA lock-in strength
    out["turnover_kept_fhfa"] = pp.lockin_multiplier(_mid(out.index), pp.LOCKIN_FHFA)
    return out


def _mid(index) -> np.ndarray:
    mids = []
    for iv in index:
        lo, hi = iv.left, iv.right
        mids.append(hi - 0.5 if not np.isfinite(lo) else lo + 0.5 if not np.isfinite(hi) else (lo + hi) / 2)
    return np.array(mids)


def project(pool: pd.DataFrame, hpi: np.ndarray, rate: np.ndarray, lockin: float) -> pd.DataFrame:
    """Monthly pool cash flows with the given lock-in strength (other PARAMS unchanged)."""
    saved = dict(pp.PARAMS)
    try:
        pp.PARAMS["lockin"] = float(lockin)
        return cp.project_collateral(pool, hpi, rate, len(rate))
    finally:
        pp.PARAMS.clear()
        pp.PARAMS.update(saved)


def pool_summary(df: pd.DataFrame) -> dict:
    smm = (df.prepayments / (df.beginning_balance - df.scheduled_principal)).to_numpy()
    return {"cpr_year1_pct": pp.smm_to_cpr(smm[:12]).mean() * 100,
            "cpr_avg_pct": pp.smm_to_cpr(smm).mean() * 100,
            "pool_at_call_bn": df.ending_balance.iloc[-1] / 1e9,
            "losses_mm": df.losses.sum() / 1e6}


def price_notes(pool_cf: pd.DataFrame, rates: pd.DataFrame) -> pd.DataFrame:
    """Waterfall + pricing for one pool path: WAL, final month, write-down and DM at the ask."""
    cashflows, summary = rw.run_scenario(pool_cf, rates)
    sofr = rates["sofr_coupon_decimal"].to_numpy(float)
    days = rates["discount_days"].to_numpy(float)
    rows = []
    for _, r in summary.iterrows():
        cls = r["tranche"]
        frame = cashflows[cashflows["tranche"] == cls]
        per_100 = (frame["interest"] + frame["principal"]).to_numpy(float) / r["starting_balance"] * 100
        accrued = r["price_at_coupon_spread_dm"] - 100.0      # full price at own spread = par + accrued
        rows.append({"tranche": cls, "wal_years": r["wal_years"],
                     "final_payment_month": r["final_payment_month"],
                     "writedown": r["total_writedown"],
                     "dm_at_ask_bps": discount_margin(per_100, sofr, BLOOMBERG_ASK[cls] + accrued, days),
                     "bloomberg_wal": BLOOMBERG_WAL[cls]})
    return pd.DataFrame(rows)


def run_cases(pool: pd.DataFrame, paths: dict, cases: dict = LOCKIN_CASES,
              rates_scenario: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every rate path x lock-in case. paths = {name: {"hpi": ..., "rate": ...}}.

    rates_scenario maps a path name to the pricing_rates.csv scenario used for SOFR and
    discounting (default: the same name, else "base").
    Returns (pool table, note table).
    """
    all_rates = pd.read_csv(PRICING_RATES)
    pools, notes = [], []
    for pname, path in paths.items():
        sc = (rates_scenario or {}).get(pname, pname if pname in set(all_rates.scenario) else "base")
        rates = all_rates[all_rates.scenario == sc].sort_values("month")
        for cname, g in cases.items():
            cf = project(pool, path["hpi"], path["rate"], g)
            pools.append({"path": pname, "case": cname, "lockin": g, **pool_summary(cf)})
            notes.append(price_notes(cf, rates).assign(path=pname, case=cname, lockin=g))
    return pd.DataFrame(pools), pd.concat(notes, ignore_index=True)


def constant_rate_paths(hpi: np.ndarray, levels: dict) -> dict:
    """Paths that hold the mortgage rate flat at each level (pp), with the given HPI path."""
    n = len(hpi) - 1
    return {name: {"hpi": hpi, "rate": np.full(n, float(level))} for name, level in levels.items()}
