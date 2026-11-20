"""Duration of the STACR 2026-DNA1 notes with and without the 2031 call, and with lock-in.

Owner: Reza. Used by notebooks/10_no_call_duration.ipynb.

Two questions:
1. How far do the notes extend if Freddie Mac does NOT exercise the February 2031 optional
   call? The notes then run until the pool pays them down, or until the scheduled maturity
   (February 2046 payment date, PPM p. 7), when any remaining principal is due.
2. What are the notes' effective duration and spread duration under each lock-in strength?

Definitions (P = full price per 100 at the discount margin earned at the Bloomberg ask):
- Spread duration  = (P(DM - d) - P(DM + d)) / (2 * P * d): price sensitivity to the
  note's own spread, holding cash flows fixed.
- Effective duration = (P(rates - d) - P(rates + d)) / (2 * P * d), where "rates" shifts the
  mortgage-rate path AND the SOFR path by d, the pool is re-projected (so prepayments
  respond), and the DM is held fixed. Because the notes float, this is close to zero unless
  prepayments respond to rates and the note trades away from par.

Paths are extended beyond the Feb 2031 call for the no-call run:
- mortgage rate: held at its last value;
- HPI: grows at its last-12-month pace;
- SOFR: held at its last value; payment dates on the 25th of each month.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import lockin as lk
from src import run_waterfall_pricing as rw
from src.pricing import discount_margin, price, weighted_average_life
from src.waterfall import CALL_DATE

MATURITY_DATE = pd.Timestamp("2046-02-25")     # scheduled maturity, PPM p. 7
FIRST_PAYMENT = pd.Timestamp("2026-10-25")
N_TO_MATURITY = (MATURITY_DATE.year - FIRST_PAYMENT.year) * 12 + MATURITY_DATE.month - FIRST_PAYMENT.month + 1
SHIFT_BPS = 25.0
ESTIMATED_LOCKIN = 0.025                       # notebook 09, lock-in only fit on 2022-2026
DURATION_CASES = {"no lock-in": 0.0, "lock-in (estimated)": ESTIMATED_LOCKIN,
                  "lock-in (FHFA)": lk.pp.LOCKIN_FHFA}
CALL_CASES = {"call 2031": CALL_DATE, "no call": MATURITY_DATE}


def extend_path(path: dict, n_months: int = N_TO_MATURITY) -> dict:
    """Extend a {"hpi", "rate"} path to n_months (rate flat, HPI at its last-year growth)."""
    hpi = np.asarray(path["hpi"], float)
    rate = np.asarray(path["rate"], float)
    extra = n_months - len(rate)
    if extra <= 0:
        return {"hpi": hpi[: n_months + 1], "rate": rate[:n_months]}
    growth = (hpi[-1] / hpi[-13]) ** (1 / 12) if len(hpi) > 12 else 1.0
    return {"hpi": np.concatenate([hpi, hpi[-1] * growth ** np.arange(1, extra + 1)]),
            "rate": np.concatenate([rate, np.full(extra, rate[-1])])}


def extend_rates(rates: pd.DataFrame, n_months: int = N_TO_MATURITY) -> pd.DataFrame:
    """Extend one scenario's pricing-rate rows to n_months (SOFR flat, actual day counts)."""
    r = rates.sort_values("month").reset_index(drop=True).copy()
    r["date"] = pd.to_datetime(r["date"])
    extra = n_months - len(r)
    if extra <= 0:
        return r.iloc[:n_months].copy()
    last = r.iloc[-1]
    dates = pd.DatetimeIndex([last["date"] + pd.DateOffset(months=k) for k in range(1, extra + 1)])
    days = pd.Series(dates.insert(0, last["date"])).diff().dt.days.to_numpy(float)[1:]
    ext = pd.DataFrame({"scenario": last["scenario"], "month": np.arange(len(r) + 1, n_months + 1),
                        "date": dates, "coupon_accrual_days": days, "discount_days": days,
                        "sofr_coupon_decimal": last["sofr_coupon_decimal"], "fixing_source": "extended flat"})
    return pd.concat([r, ext], ignore_index=True)


def shift_rates(rates: pd.DataFrame, bps: float) -> pd.DataFrame:
    out = rates.copy()
    out["sofr_coupon_decimal"] = out["sofr_coupon_decimal"] + bps / 10_000
    return out


def note_cashflows(pool_cf: pd.DataFrame, rates: pd.DataFrame, call_date) -> dict:
    """{class: (cash flow per 100, principal, sofr, discount days)} for the offered classes."""
    n = len(pool_cf)
    rates = rates.iloc[:n]
    cashflows, summary = rw.run_scenario(pool_cf, rates, call_date=call_date)
    out = {}
    for _, row in summary.iterrows():
        cls = row["tranche"]
        f = cashflows[cashflows["tranche"] == cls]
        m = len(f)
        per_100 = (f["interest"] + f["principal"]).to_numpy(float) / row["starting_balance"] * 100
        out[cls] = {"cf": per_100, "principal": f["principal"].to_numpy(float),
                    "sofr": rates["sofr_coupon_decimal"].to_numpy(float)[:m],
                    "days": rates["discount_days"].to_numpy(float)[:m],
                    "accrued": row["price_at_coupon_spread_dm"] - 100.0,
                    "final_month": row["final_payment_month"], "writedown": row["total_writedown"]}
    return out


def project_shifts(pool: pd.DataFrame, path: dict, lockin: float, shift_bps: float = SHIFT_BPS) -> dict:
    """Pool cash flows for the path and for the mortgage rate shifted by +/- shift_bps."""
    return {s: lk.project(pool, path["hpi"], path["rate"] + s / 100, lockin)
            for s in (0.0, shift_bps, -shift_bps)}


def measures(pools: dict, rates: pd.DataFrame, call_date, shift_bps: float = SHIFT_BPS) -> pd.DataFrame:
    """WAL, final month, DM at the ask, spread and effective duration for one case.

    pools: output of project_shifts. SOFR is shifted together with the mortgage rate.
    """
    d = shift_bps / 10_000
    base = note_cashflows(pools[0.0], rates, call_date)
    up = note_cashflows(pools[shift_bps], shift_rates(rates, shift_bps), call_date)
    dn = note_cashflows(pools[-shift_bps], shift_rates(rates, -shift_bps), call_date)
    rows = []
    for cls, b in base.items():
        full = lk.BLOOMBERG_ASK[cls] + b["accrued"]
        dm = discount_margin(b["cf"], b["sofr"], full, b["days"])
        p0 = price(b["cf"], b["sofr"], dm, b["days"])
        p_sm = price(b["cf"], b["sofr"], dm - shift_bps, b["days"])
        p_sp = price(b["cf"], b["sofr"], dm + shift_bps, b["days"])
        p_up = price(up[cls]["cf"], up[cls]["sofr"], dm, up[cls]["days"])
        p_dn = price(dn[cls]["cf"], dn[cls]["sofr"], dm, dn[cls]["days"])
        rows.append({
            "tranche": cls,
            "wal_years": weighted_average_life(b["principal"], b["days"]),
            "wal_up_years": weighted_average_life(up[cls]["principal"], up[cls]["days"]),
            "wal_down_years": weighted_average_life(dn[cls]["principal"], dn[cls]["days"]),
            "final_payment_month": b["final_month"],
            "writedown": b["writedown"],
            "dm_at_ask_bps": dm,
            "spread_duration": (p_sm - p_sp) / (2 * p0 * d),
            "effective_duration": (p_dn - p_up) / (2 * p0 * d),
        })
    return pd.DataFrame(rows)


def run_grid(pool: pd.DataFrame, paths: dict, rates_by_path: dict,
             lockins: dict = DURATION_CASES, calls: dict = CALL_CASES) -> pd.DataFrame:
    """Every path x lock-in x call case. Paths and rates must already be extended."""
    out = []
    for pname, path in paths.items():
        for lname, g in lockins.items():
            pools = project_shifts(pool, path, g)
            for cname, cdate in calls.items():
                out.append(measures(pools, rates_by_path[pname], cdate)
                           .assign(path=pname, lockin_case=lname, lockin=g, call=cname))
    return pd.concat(out, ignore_index=True)
