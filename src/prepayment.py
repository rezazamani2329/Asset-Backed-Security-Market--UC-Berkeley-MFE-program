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

PARAMS are FITTED on Freddie Mac Single-Family Loan-Level Dataset history (30y fixed,
vintages 2000-2026, about 48mm loan-months) against the PMMS 30y rate, by weighted least
squares on observed SMM by (incentive, age, burnout) bucket. See src/calibration.py and
notebooks/05_calibration_results.ipynb (weighted R^2 = 0.91).
"""
import numpy as np
import pandas as pd

PARAMS = {                 # FITTED, notebooks/05_calibration_results.ipynb
    "turnover": 0.055,     # CPR from home sales, no incentive
    "refi_max": 0.414,     # extra CPR when deep in the money
    "midpoint": 0.714,     # incentive (pp vs PMMS) at half of refi_max
    "slope": 2.736,        # steepness of the S-curve, per pp
    "burnout": 0.0076,     # decay per pp-month of past incentive
    "ramp_months": 6.2,    # seasoning ramp length (much faster than PSA's 30)
}


def calculate_smm(cpr: np.ndarray) -> np.ndarray:
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


def calculate_cpr(loans: pd.DataFrame, mortgage_rate: np.ndarray, params: dict = PARAMS) -> np.ndarray:
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


def calculate_prepayment(balance: np.ndarray, scheduled_principal: np.ndarray,
                         smm: np.ndarray) -> np.ndarray:
    """Unscheduled principal for one month: PP_t = SMM_t * (B_{t-1} - scheduled principal_t)."""
    return np.asarray(smm, dtype=float) * (np.asarray(balance, dtype=float)
                                           - np.asarray(scheduled_principal, dtype=float))


# Earlier names, kept so existing code keeps working
cpr_to_smm = calculate_smm
cpr = calculate_cpr
