"""Calibrate the prepayment and credit PARAMS on Freddie Mac loan-level history.

Data: src/freddie.py panels (30y fixed-rate loans, vintages 2000-2026, monthly performance).
Each vintage is reduced to small bucketed tables, then the models' functional forms from
src/prepayment.py and src/credit_model.py are fitted to them:

  prepayment  CPR = ramp(age) * [turnover + refi_max * S(incentive) * burnout]
              fitted by weighted least squares on observed SMM by
              (incentive, age, burnout) bucket
  default     monthly hazard of first reaching 90+ days delinquent (or a credit event),
              Poisson GLM on (MTM LTV, FICO, DTI, investor, pre-2009 vintage)
  severity    actual loss components on liquidated loans: costs, missed interest,
              distressed-sale discount vs. HPI-implied value, MI coverage
  pipeline    months from first 90+ to liquidation; share of 90+ loans never liquidated

Market rate: Freddie PMMS 30y (FRED MORTGAGE30US). freddie.market_rate_proxy (mean note
rate of new loans in the sample) tracks it closely (corr 0.99) and is a cross-check.
Mark-to-market LTV uses the FHFA purchase-only national HPI (FRED HPIPONM226S).
"""
import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from src import freddie as fr
from src.collateral_projection import scheduled_principal

INC_EDGES = np.r_[-np.inf, np.arange(-2.0, 3.01, 0.25), np.inf]
AGE_EDGES = np.r_[0, 3, 6, 9, 12, 18, 24, 30, 36, 48, 60, 90, 120, np.inf]
BURN_EDGES = np.r_[-0.01, 0.5, 2, 5, 10, 20, 40, 80, np.inf]

# COVID forbearance: 90+ "delinquency" in these months was mostly forbearance that cured,
# not credit default, so these months are left out of the default and pipeline fits.
FORBEARANCE = (202003, 202112)


def _in_forbearance(period) -> np.ndarray:
    period = np.asarray(period)
    return (period >= FORBEARANCE[0]) & (period <= FORBEARANCE[1])


def _lagged(panel: pd.DataFrame, cols) -> pd.DataFrame:
    g = panel.groupby("loan_id", sort=False)
    return pd.DataFrame({f"prev_{c}": g[c].shift(1) for c in cols}, index=panel.index)


def _mtm_ltv(panel: pd.DataFrame, upb: pd.Series, hpi: pd.Series | None) -> pd.Series:
    """Current LTV: original LTV x amortization x house-price change since origination."""
    amort = upb / panel["orig_upb"]
    if hpi is None:
        return (panel["orig_ltv"] * amort).where(panel["eltv"].isna(), panel["eltv"])
    orig_month = fr.from_month_index(fr.to_month_index(panel["first_pay"]) - 2)
    h0 = hpi.reindex(orig_month).to_numpy()
    ht = hpi.reindex(panel["period"].astype("int64").to_numpy()).to_numpy()
    return pd.Series(panel["orig_ltv"].to_numpy() * amort.to_numpy() * h0 / ht, index=panel.index)


# ----------------------------------------------------------------------------- prepayment
def prepay_buckets(panel: pd.DataFrame, mrate: pd.Series) -> pd.DataFrame:
    """Observed SMM by (incentive, age, burnout) bucket for loans current last month."""
    p = panel
    inc = p["rate"].to_numpy() - mrate.reindex(p["period"].astype("int64").to_numpy()).to_numpy()
    p = p.assign(inc=inc, pos=np.clip(inc, 0, None))
    g = p.groupby("loan_id", sort=False)
    p["burn"] = g["pos"].cumsum() - p["pos"]                    # incentive accumulated before
    lag = _lagged(p, ["upb", "dq", "rate", "rem", "age", "inc", "burn"])
    ok = (lag["prev_upb"] > 0) & (lag["prev_dq"] == 0) & lag["prev_inc"].notna()
    ok &= p["zb_code"].isin(["", "01"]) & (p["dq"] <= 1)
    p, lag = p[ok], lag[ok]

    sched = scheduled_principal(lag["prev_upb"].to_numpy(), lag["prev_rate"].to_numpy(),
                                lag["prev_rem"].astype(float).to_numpy())
    exposure = lag["prev_upb"].to_numpy() - sched
    payoff = (p["zb_code"] == "01").to_numpy() & (lag["prev_rem"].to_numpy() > 1)
    curtail = np.clip(lag["prev_upb"].to_numpy() - p["upb"].to_numpy() - sched, 0, None)
    prepaid = np.where(payoff, exposure, np.where(p["zb_code"] == "", curtail, 0.0))
    prepaid = np.minimum(prepaid, exposure)

    d = pd.DataFrame({
        "inc_b": pd.cut(lag["prev_inc"], INC_EDGES, labels=False),
        "age_b": pd.cut(lag["prev_age"].astype(float) + 1, AGE_EDGES, labels=False, right=False),
        "burn_b": pd.cut(lag["prev_burn"].fillna(0), BURN_EDGES, labels=False),
        "w": exposure, "prepaid": prepaid,
        "wi": exposure * lag["prev_inc"], "wa": exposure * (lag["prev_age"].astype(float) + 1),
        "wb": exposure * lag["prev_burn"].fillna(0), "n": 1,
    })
    return d.groupby(["inc_b", "age_b", "burn_b"]).sum().reset_index()


def combine_prepay(b: pd.DataFrame) -> pd.DataFrame:
    b = b.groupby(["inc_b", "age_b", "burn_b"]).sum().reset_index()
    b = b[b["w"] > 0].copy()
    b["inc"], b["age"], b["burn"] = b["wi"] / b["w"], b["wa"] / b["w"], b["wb"] / b["w"]
    b["smm"] = b["prepaid"] / b["w"]
    return b


def prepay_model_smm(theta, inc, age, burn):
    turnover, refi_max, midpoint, slope, burnout, ramp = theta
    s = 1.0 / (1.0 + np.exp(-slope * (inc - midpoint)))
    cpr = np.minimum(1.0, age / ramp) * (turnover + refi_max * s * np.exp(-burnout * burn))
    return 1.0 - (1.0 - np.clip(cpr, 0, 0.99)) ** (1 / 12)


def fit_prepay(b: pd.DataFrame, min_loans: int = 200) -> dict:
    b = b[b["n"] >= min_loans]
    sw = np.sqrt(b["w"].to_numpy() / b["w"].sum())

    def resid(theta):
        return sw * (prepay_model_smm(theta, b["inc"], b["age"], b["burn"]) - b["smm"]).to_numpy()

    x0 = [0.06, 0.55, 0.75, 3.5, 0.02, 30]
    lo, hi = [0.0, 0.05, -1.0, 0.5, 0.0, 3], [0.3, 1.0, 3.0, 15.0, 0.5, 72]
    r = least_squares(resid, x0, bounds=(lo, hi))
    names = ["turnover", "refi_max", "midpoint", "slope", "burnout", "ramp_months"]
    return {k: float(v) for k, v in zip(names, r.x)}


# ----------------------------------------------------------------------------- default
def default_rows(panel: pd.DataFrame, hpi: pd.Series | None) -> pd.DataFrame:
    """Loan-months of current loans at risk of starting a default spell.

    A loan that first reaches 90+ days delinquent (or a credit event) in month F started
    defaulting when it first missed a payment, two months earlier (S = F - 2). The model's
    MDR is the monthly probability that a performing loan starts such a spell; the loan then
    sits in the liquidation pipeline. Covariates are measured in the month before.
    """
    p = panel
    m = fr.to_month_index(p["period"]).to_numpy()
    is90 = ((p["dq"] >= 3) | p["zb_code"].isin(fr.CREDIT_ZB)).to_numpy()
    first90 = pd.Series(m[is90]).groupby(p["loan_id"].to_numpy()[is90]).min()
    start = first90.reindex(p["loan_id"]).to_numpy() - 2          # NaN if never defaulted
    lag = _lagged(p, ["upb", "dq"])
    ok = (lag["prev_upb"] > 0).to_numpy() & (lag["prev_dq"] == 0).to_numpy()
    ok &= ~(m > start)                                            # stop once the spell starts
    ok &= ~p["zb_code"].isin(["01", "96", "06", "16"]).to_numpy()
    ok &= ~_in_forbearance(p["period"].astype("int64").to_numpy())
    event = (m == start)
    p, lag = p[ok], lag[ok]
    ltv = _mtm_ltv(p, lag["prev_upb"], hpi)
    return pd.DataFrame({
        "event": event[ok].astype(int),
        "ltv": ltv.to_numpy(), "fico": p["fico"].to_numpy(), "dti": p["dti"].to_numpy(),
        "investor": (p["occupancy"] == "I").to_numpy().astype(int),
        "dq30": 0, "dq60": 0,
        "pre2009": (p["vintage"] < 2009).to_numpy().astype(int),
        "period": p["period"].astype("int64").to_numpy(),
    })


def default_buckets(rows: pd.DataFrame) -> pd.DataFrame:
    r = rows.dropna(subset=["ltv", "fico", "dti"])
    r = r.assign(ltv_b=np.clip(np.floor(r["ltv"] / 5) * 5, 20, 160),
                 fico_b=np.clip(np.floor(r["fico"] / 20) * 20, 580, 820),
                 dti_b=np.clip(np.floor(r["dti"] / 5) * 5, 10, 55), n=1)
    keys = ["ltv_b", "fico_b", "dti_b", "investor", "pre2009", "dq30", "dq60"]
    agg = r.groupby(keys).agg(n=("n", "sum"), events=("event", "sum"),
                              ltv=("ltv", "mean"), fico=("fico", "mean"), dti=("dti", "mean"))
    return agg.reset_index()


def fit_default(b: pd.DataFrame) -> dict:
    """Poisson GLM: log MDR = a + slopes. a is for post-2008 vintages (today's underwriting)."""
    import statsmodels.api as sm
    c = b[(b["dq30"] == 0) & (b["dq60"] == 0)]
    X = pd.DataFrame({
        "const": 1.0,
        "ltv_low": np.minimum(c["ltv"] - 80, 0), "ltv_high": np.maximum(c["ltv"] - 80, 0),
        "fico": c["fico"] - 750, "dti": c["dti"] - 38,
        "investor": c["investor"], "pre2009": c["pre2009"],
    })
    m = sm.GLM(c["events"], X, family=sm.families.Poisson(), offset=np.log(c["n"])).fit()
    mdr0 = float(np.exp(m.params["const"]))
    return {
        "base_cdr": 1 - (1 - mdr0) ** 12,
        "b_ltv_low": float(m.params["ltv_low"]), "b_ltv_high": float(m.params["ltv_high"]),
        "b_fico": float(-m.params["fico"]), "b_dti": float(m.params["dti"]),
        "investor_mult": float(np.exp(m.params["investor"])),
        "pre2009_mult": float(np.exp(m.params["pre2009"])),
        "_glm": m,
    }


# ----------------------------------------------------------------------------- liquidation
def liquidations(panel: pd.DataFrame, hpi: pd.Series | None) -> pd.DataFrame:
    """One row per credit event: loss components per $ of removed UPB, LTV, timing."""
    p = panel
    first90 = p[(p["dq"] >= 3) | p["zb_code"].isin(fr.CREDIT_ZB)].groupby("loan_id")["period"].min()
    ce = p[p["zb_code"].isin(fr.CREDIT_ZB) & (p["zb_upb"] > 0) & p["actual_loss"].notna()]
    upb = ce["zb_upb"]
    out = pd.DataFrame({
        "loan_id": ce["loan_id"].to_numpy(), "vintage": ce["vintage"].to_numpy(),
        "period": ce["period"].astype("int64").to_numpy(), "zb_code": ce["zb_code"].to_numpy(),
        "upb": upb.to_numpy(), "rate": ce["rate"].to_numpy(),
        "severity": (ce["actual_loss"] / upb).to_numpy(),
        "costs": (ce["expenses"].fillna(0) / upb).to_numpy(),
        "missed_int": (ce["dq_interest"].fillna(0) / upb).to_numpy(),
        "proceeds": (-(ce["net_sale"].fillna(0) + ce["non_mi_rec"].fillna(0)) / upb).to_numpy(),
        "mi": (-ce["mi_rec"].fillna(0) / upb).to_numpy(),
        "has_mi": (ce["mi_pct"] > 0).to_numpy(), "orig_ltv": ce["orig_ltv"].to_numpy(),
        "ltv": _mtm_ltv(ce, upb, hpi).to_numpy(),
    })
    f90 = fr.to_month_index(first90.reindex(out["loan_id"]).to_numpy())
    out["months_90_to_liq"] = fr.to_month_index(out["period"]).to_numpy() - f90.to_numpy()
    return out


def pipeline_outcomes(panel: pd.DataFrame, min_follow: int = 36) -> pd.DataFrame:
    """For loans that first hit 90+: did they liquidate, and how big was any rate cut?"""
    p = panel
    is90 = (p["dq"] >= 3) | p["zb_code"].isin(fr.CREDIT_ZB)
    first = p[is90].groupby("loan_id")["period"].min()
    last = p.groupby("loan_id")["period"].max()
    liq = p[p["zb_code"].isin(fr.CREDIT_ZB)].groupby("loan_id").size() > 0
    mod_rate = p[p["modified"]].groupby("loan_id")["rate"].min()
    o = pd.DataFrame({"first90": first})
    o["follow"] = (fr.to_month_index(last.reindex(o.index).to_numpy())
                   - fr.to_month_index(o["first90"].to_numpy())).to_numpy()
    o["liquidated"] = liq.reindex(o.index).fillna(False).astype(bool)
    o["modified"] = o.index.isin(mod_rate.index)
    orig_rate = p.groupby("loan_id")["orig_rate"].first()
    o["rate_cut"] = (orig_rate.reindex(o.index) - mod_rate.reindex(o.index)).clip(lower=0)
    o["vintage"] = p.groupby("loan_id")["vintage"].first().reindex(o.index)
    o = o[~_in_forbearance(o["first90"].astype("int64").to_numpy())]
    return o[(o["follow"] >= min_follow) | o["liquidated"]]


def dq30_roll(panel: pd.DataFrame, horizon: int = 12) -> tuple[int, int]:
    """(# loan-months 30 days dq and not yet 90+, # of those reaching 90+ within horizon)."""
    p = panel[["loan_id", "period", "dq", "zb_code"]].copy()
    p["m"] = fr.to_month_index(p["period"]).to_numpy()
    is90 = (p["dq"] >= 3) | p["zb_code"].isin(fr.CREDIT_ZB)
    first = p[is90].groupby("loan_id")["m"].min()
    d30 = p[(p["dq"] == 1) & ~_in_forbearance(p["period"].astype("int64").to_numpy())]
    f = first.reindex(d30["loan_id"]).to_numpy()
    at_risk = ~(f <= d30["m"].to_numpy())
    hit = (f > d30["m"].to_numpy()) & (f <= d30["m"].to_numpy() + horizon)
    return int(at_risk.sum()), int(hit[at_risk].sum())


def run_all(hpi: pd.Series | None, mrate: pd.Series, vintages=fr.VINTAGES,
            sample_frac: float = 1.0) -> dict:
    """Process every vintage once; returns the bucketed tables used by the fits.

    hpi: national HPI by YYYYMM (FHFA purchase-only, FRED HPIPONM226S).
    mrate: market 30y mortgage rate by YYYYMM (Freddie PMMS, FRED MORTGAGE30US), the same
    kind of rate a scenario path supplies to prepayment.calculate_cpr.
    """
    pre, dflt, liq, pipe, rolls = [], [], [], [], []
    for y in vintages:
        panel = fr.load_panel(y)
        if sample_frac < 1:
            ids = panel["loan_id"].drop_duplicates().sample(frac=sample_frac, random_state=y)
            panel = panel[panel["loan_id"].isin(ids)]
        pre.append(prepay_buckets(panel, mrate))
        dflt.append(default_buckets(default_rows(panel, hpi)))
        liq.append(liquidations(panel, hpi))
        pipe.append(pipeline_outcomes(panel))
        rolls.append(dq30_roll(panel))
    keys = ["ltv_b", "fico_b", "dti_b", "investor", "pre2009", "dq30", "dq60"]
    d = pd.concat(dflt)
    d["wl"], d["wf"], d["wd"] = d["ltv"] * d["n"], d["fico"] * d["n"], d["dti"] * d["n"]
    d = d.groupby(keys)[["n", "events", "wl", "wf", "wd"]].sum().reset_index()
    d["ltv"], d["fico"], d["dti"] = d["wl"] / d["n"], d["wf"] / d["n"], d["wd"] / d["n"]
    return {
        "prepay": combine_prepay(pd.concat(pre)), "default": d,
        "liquidations": pd.concat(liq, ignore_index=True),
        "pipeline": pd.concat(pipe), "dq30_roll": tuple(np.sum(rolls, axis=0)),
        "mrate": mrate,
    }


# ----------------------------------------------------------------------------- severity fit
def severity_model(ltv, coupon, has_mi, costs, reo_discount, liq_lag, mi_coverage):
    """Same formula as credit_model.calculate_loss_severity, on arrays (ltv in %)."""
    claim = 1.0 + liq_lag * coupon / 1200.0 + costs
    proceeds = (100.0 / ltv) * (1.0 - reo_discount)
    mi = np.where(has_mi, mi_coverage * claim, 0.0)
    return np.clip(claim - proceeds - mi, 0.0, None)


def clean_liquidations(liq: pd.DataFrame) -> pd.DataFrame:
    l = liq[(liq["upb"] > 10_000) & liq["severity"].between(-1, 3) & (liq["ltv"] > 0)].copy()
    l["start"] = fr.from_month_index(fr.to_month_index(l["period"]).to_numpy()
                                     - l["months_90_to_liq"].to_numpy() - 2)
    return l


def fit_severity(liq: pd.DataFrame, liq_lag: float) -> dict:
    """costs and MI coverage observed directly; distressed-sale discount fitted so the
    model's severity matches observed severity (UPB-weighted least squares)."""
    l = clean_liquidations(liq)
    w = l["upb"].to_numpy()
    costs = float(np.average(l["costs"].clip(0, 1), weights=w))
    mi = l[l["has_mi"]]
    mi_cov = float(np.average((mi["mi"] / (1 + mi["missed_int"] + mi["costs"])).clip(0, 1),
                              weights=mi["upb"]))

    def resid(x):
        pred = severity_model(l["ltv"].to_numpy(), l["rate"].to_numpy(), l["has_mi"].to_numpy(),
                              costs, x[0], liq_lag, mi_cov)
        return np.sqrt(w / w.sum()) * (pred - l["severity"].to_numpy())

    d = float(least_squares(resid, [0.2], bounds=([0.0], [0.9])).x[0])
    return {"costs": costs, "reo_discount": d, "mi_coverage": mi_cov}


def calibrate(r: dict, recent_from: int = 201301) -> dict:
    """All fitted PARAMS from run_all() output. Pipeline timing / outcomes use default
    spells starting from `recent_from` (post-crisis servicing and foreclosure practice)."""
    prepay = fit_prepay(r["prepay"])
    default = fit_default(r["default"])

    l = clean_liquidations(r["liquidations"])
    rec = l[l["start"] >= recent_from]
    liq_lag = float(np.median(rec["months_90_to_liq"] + 2))
    sev = fit_severity(r["liquidations"], liq_lag)

    pipe = r["pipeline"]
    pipe = pipe[pipe["first90"] >= recent_from]
    p_liq = float(pipe["liquidated"].mean())
    p_mod = float(pipe["modified"].mean())
    cut = float(pipe.loc[pipe["modified"], "rate_cut"].mean())
    mod_share = 1 - p_liq
    n30, hit = r["dq30_roll"]
    p12 = hit / n30

    credit = {k: v for k, v in default.items() if not k.startswith("_") and k != "pre2009_mult"}
    credit.update({
        "dq30_extra_mdr": float(1 - (1 - p12) ** (1 / 12) - (1 - (1 - credit["base_cdr"]) ** (1 / 12))),
        "dq30_months": 12,
        "liq_lag": round(liq_lag),
        **sev,
        "mod_share": mod_share,
        # only modified loans lose interest; spread their cut over all non-liquidated spells
        "mod_rate_cut": cut * p_mod / mod_share,
    })
    return {"prepayment": prepay, "credit": credit,
            "diagnostics": {"pre2009_mult": default["pre2009_mult"], "p_liquidated": p_liq,
                            "p_modified": p_mod, "rate_cut_if_modified": cut, "dq30_12m_roll": p12,
                            "n_default_events": int(r["default"]["events"].sum()),
                            "n_liquidations": len(l), "glm": default["_glm"]}}
