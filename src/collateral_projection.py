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
from pathlib import Path

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


def project_collateral(loans: pd.DataFrame, hpi_path: np.ndarray, rate_path: np.ndarray,
                       n_months: int) -> pd.DataFrame:
    """Monthly pool cash flows ($) for one scenario path, with columns COLUMNS.

    hpi_path: n_months + 1 points, 1.0 on the tape date. rate_path: n_months mortgage
    rates in % per year. Uses prepayment.calculate_cpr / calculate_smm / calculate_prepayment
    and credit_model.calculate_credit_event_rate / calculate_credit_events /
    calculate_loss_severity / modification_loss, with their PARAMS.
    """
    cparams = credit_model.PARAMS
    lag, mod_share = int(cparams["liq_lag"]), cparams["mod_share"]
    hpi = np.asarray(hpi_path, dtype=float)

    bal = loans["Current Balance"].to_numpy(dtype=float)
    coupon = loans["Gross Coupon"].to_numpy(dtype=float)
    rem = loans["Months to Maturity"].to_numpy(dtype=float)
    smm = prepayment.calculate_smm(prepayment.calculate_cpr(loans, rate_path[:n_months]))
    mdr = credit_model.calculate_credit_event_rate(loans, hpi[: n_months + 1])

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

        new_dq = credit_model.calculate_credit_events(perf, mdr[:, t])
        to_liq = (1.0 - mod_share) * new_dq
        to_mod = new_dq - to_liq
        after_dq = perf - to_liq
        sched = scheduled_principal(after_dq, coupon, rem - t)
        prepay = prepayment.calculate_prepayment(after_dq, sched, smm[:, t])
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
        losses = (events * credit_model.calculate_loss_severity(loans, hpi[t + 1])).sum()
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
    """{name: project_collateral(...)} where scenarios = {name: {"hpi": path, "rate": path}}."""
    return {name: project_collateral(loans, s["hpi"], s["rate"], n_months)
            for name, s in scenarios.items()}


SCENARIO_CSV = Path(__file__).resolve().parents[1] / "data" / "scenarios" / "scenarios.csv"
PMMS_TODAY = 7.28   # Freddie PMMS 30y, Oct 2026 (FRED MORTGAGE30US); interim base rate


def placeholder_scenarios(n_months: int = 53) -> dict:
    """INTERIM paths until Coco's scenario file arrives: flat mortgage rate, HPI growing at
    a constant monthly rate to its end level. Base starts from today's PMMS."""
    paths = {               # (HPI at end of horizon, 30y mortgage rate %)
        "good":     (1.25, PMMS_TODAY - 1.00),   # rally and strong prices: fast prepay, few losses
        "base":     (1.13, PMMS_TODAY),          # rates stay put, HPI about +3% a year
        "moderate": (0.90, PMMS_TODAY - 0.25),   # mild recession: prices -10%, little rate relief
        "severe":   (0.75, PMMS_TODAY - 0.50),   # deep recession: prices -25%, rates fall only a bit
    }
    return {name: {"hpi": np.geomspace(1.0, h, n_months + 1), "rate": np.full(n_months, r)}
            for name, (h, r) in paths.items()}


def load_scenarios(path: Path = SCENARIO_CSV, n_months: int = None) -> dict:
    """Read scenario paths from a CSV (Coco's file) in the format

        scenario,month,mortgage_rate,hpi_index
        base,0,7.28,100.0
        base,1,7.25,100.3
        ...

    month runs 0..n_months; mortgage_rate is the 30y market rate in % (PMMS-type), used for
    months 1..n_months; hpi_index can be on any base and is rescaled to 1.0 at month 0.
    """
    df = pd.read_csv(path).sort_values(["scenario", "month"])
    if df.empty or df.duplicated(["scenario", "month"]).any():
        raise ValueError("Empty scenarios or duplicate scenario/month rows")
    if not set(df.scenario).issubset({"good", "base", "moderate", "severe"}):
        raise ValueError("Expected good, base, moderate, severe scenarios")
    if not np.isfinite(df.month).all() or not (df.month == df.month.astype(int)).all():
        raise ValueError("Months must be finite integers")
    actual = int(df.month.max())
    if n_months is None:
        n_months = actual
    if n_months < 1 or actual != n_months or (df.month < 0).any():
        raise ValueError("Scenario horizon does not match requested projection")
    if "date" in df:
        # ISO "YYYY-MM-DD" strings compare in date order, so no datetime parsing is needed
        # (pandas date parsing crashes on some Python 3.14 installs).
        dates_by_scenario = [g.sort_values("month").date.astype(str).str[:10].tolist()
                             for _, g in df.groupby("scenario")]
        if any(d != dates_by_scenario[0] for d in dates_by_scenario[1:]):
            raise ValueError("Scenario dates must agree")
        dates = dates_by_scenario[0]
        iso = pd.Series(dates).str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()
        if not iso or dates != sorted(set(dates)):
            raise ValueError("Invalid scenario dates")
        if dates[-1] != CALL_DATE[:10]:
            raise ValueError("Scenario endpoint must equal call date")
    out = {}
    for name, g in df.groupby("scenario", sort=False):
        g = g.set_index("month").reindex(range(n_months + 1))
        if g[["mortgage_rate", "hpi_index"]].isna().any().any():
            raise ValueError(f"scenario {name!r} needs months 0..{n_months} with no gaps")
        values = g[["mortgage_rate", "hpi_index"]].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("Mortgage rates and HPI must be finite and positive")
        hpi = g["hpi_index"].to_numpy(dtype=float)
        out[name] = {"hpi": hpi / hpi[0], "rate": g["mortgage_rate"].to_numpy(dtype=float)[1:]}
    return out


def get_scenarios(n_months: int = None) -> dict:
    """Coco's scenarios from data/scenarios/scenarios.csv if present, else the interim paths."""
    if SCENARIO_CSV.exists():
        paths = load_scenarios(SCENARIO_CSV, n_months)
        if set(paths) != {"good", "base", "moderate", "severe"}:
            raise ValueError("Production scenario file requires all four scenarios")
        return paths
    return placeholder_scenarios(53 if n_months is None else n_months)


# Earlier name, kept so existing code keeps working
project_pool = project_collateral
