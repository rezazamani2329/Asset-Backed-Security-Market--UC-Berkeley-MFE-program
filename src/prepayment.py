"""Voluntary prepayment model: CPR as a function of refinancing incentive and seasoning.

Owner: Reza. Inputs: clean pool (src/clean.py) + mortgage-rate path (src/scenarios.py).

Model (per loan, per month t):

    CPR_t = ramp(age_t) * [ TURNOVER + REFI_MAX * S(incentive_t) * burnout_t ]

    incentive_t = loan coupon - market mortgage rate_t           (percentage points)
    S(x)        = 1 / (1 + exp(-SLOPE * (x - MIDPOINT)))          logistic "S-curve"
    burnout_t   = exp(-BURNOUT * sum of past positive incentive)  in-the-money loans that
                  have not refinanced yet are the less rate-sensitive ones
    ramp(age)   = min(1, age / RAMP_MONTHS)                       PSA-style seasoning

TURNOVER is the floor from home sales when there is no refi incentive.

PARAMS are PLACEHOLDERS until calibrated on historical data (docs/reza_plan.md, Step 2).
Rough check: the pool paid down from $22.78bn (Feb 2026) to $19.44bn on the tape, which
is roughly a 20-25% CPR, and these values give about that at a 6.25% market rate.
"""
import numpy as np
import pandas as pd

PARAMS = {
    "turnover": 0.06,      # CPR from home sales, no incentive          PLACEHOLDER
    "refi_max": 0.55,      # extra CPR when deep in the money            PLACEHOLDER
    "midpoint": 0.75,      # incentive (pp) at half of refi_max          PLACEHOLDER
    "slope": 3.5,          # steepness of the S-curve, per pp            PLACEHOLDER
    "burnout": 0.02,       # decay per pp-month of past incentive        PLACEHOLDER
    "ramp_months": 30,     # seasoning ramp length (PSA uses 30)         PLACEHOLDER
}


def cpr_to_smm(cpr: np.ndarray) -> np.ndarray:
    """Annual CPR -> single monthly mortality: 1 - CPR = (1 - SMM)^12."""
    cpr = np.asarray(cpr, dtype=float)
    return 1.0 - (1.0 - cpr) ** (1.0 / 12.0)


def smm_to_cpr(smm: np.ndarray) -> np.ndarray:
    """Single monthly mortality -> annual CPR."""
    smm = np.asarray(smm, dtype=float)
    return 1.0 - (1.0 - smm) ** 12


def refi_incentive(loans: pd.DataFrame, mortgage_rate: np.ndarray) -> np.ndarray:
    """Coupon minus market mortgage rate (pp), shape (n_loans, n_months)."""
    coupon = loans["Gross Coupon"].to_numpy(dtype=float)
    return coupon[:, None] - np.asarray(mortgage_rate, dtype=float)[None, :]


def cpr(loans: pd.DataFrame, mortgage_rate: np.ndarray, params: dict = PARAMS) -> np.ndarray:
    """Annual CPR per loan per month, shape (n_loans, n_months)."""
    p = params
    inc = refi_incentive(loans, mortgage_rate)
    n_months = inc.shape[1]

    s_curve = 1.0 / (1.0 + np.exp(-p["slope"] * (inc - p["midpoint"])))
    # burnout uses incentive accumulated BEFORE month t
    past = np.cumsum(np.clip(inc, 0, None), axis=1) - np.clip(inc, 0, None)
    burnout = np.exp(-p["burnout"] * past)

    age = loans["Age"].to_numpy(dtype=float)[:, None] + np.arange(1, n_months + 1)[None, :]
    ramp = np.minimum(1.0, age / p["ramp_months"])

    return np.clip(ramp * (p["turnover"] + p["refi_max"] * s_curve * burnout), 0.0, 0.99)
