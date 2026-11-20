"""What the February 2031 call is worth, and what the notes cost Freddie Mac.

Owner: Reza. Used by notebooks/11_call_value.ipynb. Builds on src/duration.py.

For each rate path and lock-in strength, the pool is projected once to the 2046 maturity and
the waterfall is run twice: with the 2031 call and without it.

Investor side (per 100 face, and in $ for the class's current balance):
- dm_call: discount margin that matches the Bloomberg ask if the call is exercised.
- call_value = P_call(dm_call) - P_no_call(dm_call): how much more the note is worth when
  Freddie Mac calls, at the same spread. Positive for notes bought below par (the call pays
  par early), negative for notes above par.
- dm_no_call: the DM the same ask price earns if there is no call.

Freddie Mac side (the cost of risk transfer):
- spread_cost = PV of the coupon spread Freddie Mac pays on the note
  (balance x spread x accrual days / 360), discounted at SOFR.
- protection = PV of the write-downs the note absorbs (the credit risk actually transferred).
- net_cost = spread_cost - protection. The extra net cost without the call is what Freddie
  Mac would pay for keeping the notes outstanding after 2031.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import duration as du
from src import lockin as lk
from src.pricing import discount_factors, discount_margin, price, weighted_average_life


def _pv(amounts: np.ndarray, sofr: np.ndarray, days: np.ndarray) -> float:
    return float(np.dot(amounts, discount_factors(sofr, 0.0, days)))


def freddie_cost(n: dict) -> dict:
    """PV (at SOFR) of the spread paid and of the write-downs absorbed by one note."""
    spread_paid = n["balance"] * n["spread_bps"] / 10_000 * n["accrual_days"] / 360
    return {"spread_cost": _pv(spread_paid, n["sofr"], n["days"]),
            "protection": _pv(n["writedowns"], n["sofr"], n["days"])}


def compare_call(pool_cf: pd.DataFrame, rates: pd.DataFrame) -> pd.DataFrame:
    """One row per offered class: investor value of the call and Freddie Mac's cost, call vs. no call."""
    called = du.note_cashflows(pool_cf, rates, du.CALL_DATE)
    open_ = du.note_cashflows(pool_cf, rates, du.MATURITY_DATE)
    rows = []
    for cls, c in called.items():
        o = open_[cls]
        full = lk.BLOOMBERG_ASK[cls] + c["accrued"]
        dm_call = discount_margin(c["cf"], c["sofr"], full, c["days"])
        dm_open = discount_margin(o["cf"], o["sofr"], full, o["days"])
        p_call = price(c["cf"], c["sofr"], dm_call, c["days"])
        p_open = price(o["cf"], o["sofr"], dm_call, o["days"])
        fc, fo = freddie_cost(c), freddie_cost(o)
        rows.append({
            "tranche": cls, "face": c["face"], "coupon_spread_bps": c["spread_bps"],
            "wal_call": weighted_average_life(c["principal"], c["days"]),
            "wal_no_call": weighted_average_life(o["principal"], o["days"]),
            "dm_call_bps": dm_call, "dm_no_call_bps": dm_open,
            "price_call": p_call, "price_no_call": p_open,
            "call_value_per_100": p_call - p_open,
            "call_value_usd": (p_call - p_open) / 100 * c["face"],
            "spread_cost_call_usd": fc["spread_cost"], "spread_cost_no_call_usd": fo["spread_cost"],
            "protection_call_usd": fc["protection"], "protection_no_call_usd": fo["protection"],
        })
    out = pd.DataFrame(rows)
    out["net_cost_call_usd"] = out.spread_cost_call_usd - out.protection_call_usd
    out["net_cost_no_call_usd"] = out.spread_cost_no_call_usd - out.protection_no_call_usd
    out["extra_cost_no_call_usd"] = out.net_cost_no_call_usd - out.net_cost_call_usd
    return out


def run_grid(pool: pd.DataFrame, paths: dict, rates_by_path: dict,
             lockins: dict = du.DURATION_CASES) -> pd.DataFrame:
    out = []
    for pname, path in paths.items():
        for lname, g in lockins.items():
            cf = lk.project(pool, path["hpi"], path["rate"], g)
            out.append(compare_call(cf, rates_by_path[pname]).assign(path=pname, lockin_case=lname, lockin=g))
    return pd.concat(out, ignore_index=True)
