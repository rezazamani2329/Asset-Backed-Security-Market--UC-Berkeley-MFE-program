"""Monthly reference-pool projection: the handoff from the collateral model to the waterfall.

Owner: Reza. Consumer: src/waterfall.py (Smarajit) only needs the table returned by
project_pool; it does not need to know how CPR or defaults were modeled.

Design decisions to make:
  - Order within a month (chosen): defaults first (MDR x performing balance), then
    scheduled principal on what is left, then prepayments (SMM x balance after
    scheduled principal). Each dollar leaves the pool only once.
  - Defaulted loans sit in a liquidation pipeline for LIQ_LAG months (still in the
    reference pool, counted in distressed_balance), then become credit events with a loss.
    Loans 60+ dq or in bankruptcy/foreclosure on the tape start in the pipeline.
  - No cures from the pipeline (conservative simplification).
  - Loan-level projection vs. aggregating into rep lines (by coupon / LTV / FICO bucket)
  - Projection horizon: pricing assumes the Feb 2031 call (PPM p. x), so the base
    case runs ~5 years from today; maturity runs are for sensitivity only.
  - Starting balance: the Bloomberg tape is TODAY's pool ($19.44bn, 56,871 loans), not
    the $22.78bn cut-off (64,434 loans). Start from today and use the 22.78bn only for
    deal ratios (Senior Percentage, cumulative net loss tests).
"""
import numpy as np
import pandas as pd

from src import credit_model, prepayment

CUTOFF_BALANCE = 22_781_151_551.84   # PPM; same constant as src/waterfall.py
CALL_DATE = "2031-02-25"             # Freddie Mac optional call, pricing assumption

COLUMNS = [
    "month", "beginning_balance", "scheduled_principal", "prepayments",
    "defaults", "losses", "recoveries", "ending_balance",
    # Rate-modification / forbearance losses also count (PPM p. 84-85) and are
    # allocated differently (interest first), so keep them separate from losses.
    "modification_losses",
    # 60+ dq / FC / BK / REO / recently modified UPB: feeds the waterfall's
    # Delinquency Test (PPM p. 173-174). Agree names with src/waterfall.py.
    "distressed_balance",
]


def scheduled_principal(balance: np.ndarray, coupon: np.ndarray,
                        months_remaining: np.ndarray) -> np.ndarray:
    """Level-pay amortization principal for one month, per loan.

    payment = B r / (1 - (1 + r)^-n), interest = B r, principal = payment - interest,
    with r = coupon / 1200 (coupon in % per year). The last payment retires the balance.
    """
    b = np.asarray(balance, dtype=float)
    r = np.asarray(coupon, dtype=float) / 1200.0
    n = np.asarray(months_remaining, dtype=float)
    n_safe = np.maximum(n, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        payment = np.where(r > 0, b * r / (1.0 - (1.0 + r) ** -n_safe), b / n_safe)
    principal = np.where(n <= 1, b, payment - b * r)
    return np.clip(principal, 0.0, b)


def project_pool(loans: pd.DataFrame, hpi_path: np.ndarray, rate_path: np.ndarray,
                 n_months: int) -> pd.DataFrame:
    """Monthly pool cash flows ($) for one scenario path, with columns COLUMNS.

    hpi_path: n_months + 1 points, 1.0 on the tape date. rate_path: n_months mortgage
    rates in % per year. Uses prepayment.cpr, credit_model.default_rate / severity /
    modification_loss and their PARAMS.
    """
    cparams = credit_model.PARAMS
    lag, mod_share = int(cparams["liq_lag"]), cparams["mod_share"]
    hpi = np.asarray(hpi_path, dtype=float)

    bal = loans["Current Balance"].to_numpy(dtype=float)
    coupon = loans["Gross Coupon"].to_numpy(dtype=float)
    rem = loans["Months to Maturity"].to_numpy(dtype=float)
    smm = prepayment.cpr_to_smm(prepayment.cpr(loans, rate_path[:n_months]))
    mdr = credit_model.default_rate(loans, hpi[: n_months + 1])

    # Loans 60+ dq / bankruptcy / foreclosure on the tape (or unmapped codes) start in
    # the liquidation pipeline and are liquidated halfway through the lag.
    if "dq_bucket" in loans:
        dq = loans["dq_bucket"]
        serious = ((dq >= 2) | dq.isna()).to_numpy()
    else:
        serious = np.zeros(len(loans), dtype=bool)
    perf = np.where(serious, 0.0, bal)        # performing balance
    pipe = np.where(serious, bal, 0.0)        # defaulted, awaiting liquidation
    modified = np.zeros_like(bal)             # balance of modified loans (still performing)
    liq = np.zeros((len(loans), n_months))    # balance scheduled to liquidate each month
    if n_months:
        liq[:, min(max(lag // 2, 1), n_months) - 1] += pipe
    recent_mods = []

    rows = []
    for t in range(n_months):
        begin = perf.sum() + pipe.sum()
        mod_loss = credit_model.modification_loss(modified).sum()

        new_dq = mdr[:, t] * perf
        to_liq = (1.0 - mod_share) * new_dq
        to_mod = new_dq - to_liq
        after_dq = perf - to_liq
        sched = scheduled_principal(after_dq, coupon, rem - t)
        prepay = smm[:, t] * (after_dq - sched)
        perf_end = after_dq - sched - prepay

        with np.errstate(divide="ignore", invalid="ignore"):
            survival = np.where(after_dq > 0, perf_end / after_dq, 0.0)
        modified = (modified + to_mod) * survival
        recent_mods = (recent_mods + [to_mod.sum()])[-12:]

        pipe = pipe + to_liq
        if t + lag < n_months:
            liq[:, t + lag] += to_liq
        events = liq[:, t]
        pipe = pipe - events
        losses = (events * credit_model.severity(loans, hpi[t + 1])).sum()
        perf = perf_end

        rows.append({
            "month": t + 1,
            "beginning_balance": begin,
            "scheduled_principal": sched.sum(),
            "prepayments": prepay.sum(),
            "defaults": events.sum(),          # credit events: balance leaving the pool
            "losses": losses,
            "recoveries": 0.0,                 # later recoveries on credit events: not modeled
            "ending_balance": perf.sum() + pipe.sum(),
            "modification_losses": mod_loss,
            "distressed_balance": pipe.sum() + sum(recent_mods),
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def run_scenarios(loans: pd.DataFrame, scenarios: dict, n_months: int) -> dict:
    """{name: project_pool(...)} where scenarios = {name: {"hpi": path, "rate": path}}."""
    return {name: project_pool(loans, s["hpi"], s["rate"], n_months)
            for name, s in scenarios.items()}
