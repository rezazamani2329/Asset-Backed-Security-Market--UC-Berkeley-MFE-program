"""Statistical inference for the lock-in estimates (paper Section IV.B and Appendix C).

The point estimates in notebook 09 are weighted least squares fits on bucketed prepayment
rates. Loans observed in the same calendar month share the same market rate, so their
prepayment shocks are correlated: treating buckets as independent overstates precision.
This module resamples calendar months instead.

1. Month buckets: the notebook 05/09 prepayment buckets, split by calendar month (YYYYMM).
2. Moving-block bootstrap over calendar months (blocks of consecutive months, so serial
   correlation within a block is kept). Each draw collapses the resampled months into fit
   buckets and refits, exactly like the point estimate.
3. Tests: percentile confidence interval for gamma, bootstrap p-values for gamma = 0 and
   gamma = 0.20 (FHFA).
4. Threshold: a two-slope lock-in curve, slope g1 up to a kink at k pp below market and g2
   beyond it. Bootstrap CI for g2 - g1 and a weighted F-type statistic.
5. Pseudo out-of-sample forecast test: fit gamma on 2022-2024, forecast monthly CPR in
   2025-2026 with gamma-hat, gamma = 0 and gamma = 0.20, and compare with a Diebold-Mariano
   test (Newey-West variance).
6. Default regression with standard errors clustered by calendar year.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import least_squares

from src import calibration as cal

SUM_COLS = ["w", "prepaid", "wi", "wa", "wb", "n"]
KINK = 2.0
FHFA = 0.20


# ----------------------------------------------------------------------------- data
def prepay_buckets_by_month(panel: pd.DataFrame, mrate: pd.Series) -> pd.DataFrame:
    """Prepayment bucket sums split by calendar month (column `month`, YYYYMM)."""
    rows = cal._prepay_rows(panel, mrate)
    p = panel["period"].astype("int64")
    # _prepay_rows keeps the panel index of the rows it uses, so the period lines up
    rows = rows.assign(month=p.loc[rows.index].to_numpy()).drop(columns="year")
    return rows.groupby(["month"] + cal.PREPAY_KEYS)[SUM_COLS].sum().reset_index()


def collapse(bm: pd.DataFrame, months, weights=None) -> pd.DataFrame:
    """Fit buckets from the chosen months; `weights` = how often each month is drawn."""
    sel = bm[bm["month"].isin(list(months))]
    if weights is not None:
        k = sel["month"].map(weights).to_numpy()
        sel = sel.copy()
        sel[SUM_COLS] = sel[SUM_COLS].to_numpy() * k[:, None]
    return cal.combine_prepay(sel.drop(columns="month"))


# ----------------------------------------------------------------------------- estimators
def _resid_fn(b: pd.DataFrame, base: dict, curve):
    sw = np.sqrt(b["w"].to_numpy() / b["w"].sum())
    theta0 = [base[k] for k in cal.PREPAY_NAMES]
    inc, age, burn, smm = (b[c].to_numpy() for c in ("inc", "age", "burn", "smm"))

    def resid(x):
        return sw * (model_smm(theta0, x, inc, age, burn, curve) - smm)
    return resid


def model_smm(theta0, g, inc, age, burn, curve="exp"):
    """Bucket SMM with lock-in curve `exp` (one slope) or `kink` (g = [g1, g2])."""
    turnover, refi_max, midpoint, slope, burnout, ramp = theta0
    gap = np.clip(-np.asarray(inc, float), 0, None)
    if curve == "exp":
        lock = np.exp(-g[0] * gap)
    else:
        lock = np.exp(-g[0] * np.minimum(gap, KINK) - g[1] * np.clip(gap - KINK, 0, None))
    s = 1.0 / (1.0 + np.exp(-slope * (inc - midpoint)))
    cpr = np.minimum(1.0, age / ramp) * (turnover * lock + refi_max * s * np.exp(-burnout * burn))
    return 1.0 - (1.0 - np.clip(cpr, 0, 0.99)) ** (1 / 12)


def fit(b: pd.DataFrame, base: dict, curve="exp", min_loans: int = 200) -> dict:
    b = b[b["n"] >= min_loans]
    r = _resid_fn(b, base, curve)
    if curve == "exp":
        out = least_squares(r, [0.2], bounds=([0.0], [3.0]))
    else:
        out = least_squares(r, [0.05, 0.1], bounds=([-1.0, -1.0], [3.0, 3.0]))
    return {"g": out.x.astype(float), "ssr": float(np.sum(out.fun ** 2)), "n_buckets": len(b)}


# ----------------------------------------------------------------------------- bootstrap
def block_draws(months, n_boot: int, block: int, seed: int):
    """Circular moving-block bootstrap over an ordered list of months -> list of {month: count}."""
    months = sorted(months)
    T = len(months)
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(T / block))
    for _ in range(n_boot):
        starts = rng.integers(0, T, n_blocks)
        idx = ((starts[:, None] + np.arange(block)[None, :]) % T).ravel()[:T]
        yield pd.Series([months[i] for i in idx]).value_counts().to_dict()


def bootstrap(bm: pd.DataFrame, months, base: dict, n_boot=500, block=12, seed=2026) -> pd.DataFrame:
    """Bootstrap draws of the one-slope gamma and of the kinked curve (g1, g2)."""
    rows = []
    for k, wts in enumerate(block_draws(months, n_boot, block, seed)):
        b = collapse(bm, wts.keys(), wts)
        e, kk = fit(b, base, "exp"), fit(b, base, "kink")
        rows.append({"draw": k, "gamma": e["g"][0], "g1": kk["g"][0], "g2": kk["g"][1]})
    return pd.DataFrame(rows)


def summarize(point: dict, draws: pd.DataFrame, alpha=0.05) -> pd.DataFrame:
    """Point estimates, bootstrap standard errors, percentile CIs and p-values."""
    q = [alpha / 2, 1 - alpha / 2]
    g, d = draws["gamma"], draws["g2"] - draws["g1"]
    out = {
        "gamma": {"estimate": point["gamma"], "se": g.std(ddof=1),
                  "ci_low": g.quantile(q[0]), "ci_high": g.quantile(q[1]),
                  # one-sided bootstrap p-values (gamma is bounded at 0)
                  "p_gamma_le_0": float((g <= 1e-6).mean()),
                  "p_gamma_ge_fhfa": float((g >= FHFA).mean())},
        "g1 (gap up to 2pp)": {"estimate": point["g1"], "se": draws["g1"].std(ddof=1),
                               "ci_low": draws["g1"].quantile(q[0]), "ci_high": draws["g1"].quantile(q[1])},
        "g2 (gap beyond 2pp)": {"estimate": point["g2"], "se": draws["g2"].std(ddof=1),
                                "ci_low": draws["g2"].quantile(q[0]), "ci_high": draws["g2"].quantile(q[1])},
        "g2 - g1": {"estimate": point["g2"] - point["g1"], "se": d.std(ddof=1),
                    "ci_low": d.quantile(q[0]), "ci_high": d.quantile(q[1]),
                    "p_g2_le_g1": float((d <= 0).mean())},
    }
    return pd.DataFrame(out).T


def kink_f_stat(b: pd.DataFrame, base: dict) -> dict:
    """Weighted SSR of the one- and two-slope curves and the F-type statistic (1 restriction).

    Buckets are not independent, so the F p-value is indicative only; the bootstrap CI of
    g2 - g1 is the main test.
    """
    e, k = fit(b, base, "exp"), fit(b, base, "kink")
    n = k["n_buckets"]
    F = (e["ssr"] - k["ssr"]) / (k["ssr"] / (n - 2))
    return {"ssr_exp": e["ssr"], "ssr_kink": k["ssr"], "n_buckets": n, "F": F,
            "p_F_naive": float(stats.f.sf(F, 1, n - 2))}


# ----------------------------------------------------------------------------- forecasts
def monthly_forecast_errors(bm: pd.DataFrame, test_months, base: dict, gammas: dict,
                            min_loans: int = 200) -> pd.DataFrame:
    """Exposure-weighted observed vs. predicted SMM each test month, for each gamma."""
    t = bm[bm["month"].isin(list(test_months))]
    t = cal.combine_prepay(t, ["month"] + cal.PREPAY_KEYS)
    t = t[t["n"] >= min_loans]
    theta0 = [base[k] for k in cal.PREPAY_NAMES]
    rows = []
    for m, g in t.groupby("month"):
        w = g["w"].to_numpy()
        r = {"month": m, "observed": np.average(g["smm"], weights=w)}
        for name, gam in gammas.items():
            pred = model_smm(theta0, [gam], g["inc"].to_numpy(), g["age"].to_numpy(),
                             g["burn"].to_numpy())
            r[name] = np.average(pred, weights=w)
        rows.append(r)
    return pd.DataFrame(rows)


def diebold_mariano(e1, e2, lags: int | None = None) -> dict:
    """DM test of equal squared-error loss; positive stat = model 2 more accurate."""
    d = np.asarray(e1) ** 2 - np.asarray(e2) ** 2
    T = len(d)
    lags = int(np.floor(T ** (1 / 3))) if lags is None else lags
    dc = d - d.mean()
    v = np.sum(dc ** 2) / T
    for L in range(1, lags + 1):
        v += 2 * (1 - L / (lags + 1)) * np.sum(dc[L:] * dc[:-L]) / T
    stat = d.mean() / np.sqrt(v / T)
    return {"mean_loss_diff": float(d.mean()), "dm_stat": float(stat),
            "p_two_sided": float(2 * stats.norm.sf(abs(stat))), "T": T, "lags": lags}


def forecast_test(bm: pd.DataFrame, base: dict, train=(202201, 202412), test=(202501, 202612)) -> dict:
    months = sorted(bm["month"].unique())
    tr = [m for m in months if train[0] <= m <= train[1]]
    te = [m for m in months if test[0] <= m <= test[1]]
    g_hat = fit(collapse(bm, tr), base)["g"][0]
    f = monthly_forecast_errors(bm, te, base, {"estimated": g_hat, "none": 0.0, "fhfa": FHFA})
    err = {k: f[k] - f["observed"] for k in ("estimated", "none", "fhfa")}
    return {"gamma_train": g_hat, "forecasts": f,
            "rmse_cpr_pp": {k: float(np.sqrt(np.mean(((1 - (1 - f[k]) ** 12) - (1 - (1 - f["observed"]) ** 12)) ** 2)) * 100)
                            for k in err},
            "dm_estimated_vs_none": diebold_mariano(err["none"], err["estimated"]),
            "dm_estimated_vs_fhfa": diebold_mariano(err["fhfa"], err["estimated"])}


# ----------------------------------------------------------------------------- default
def default_buckets_by_year(rows: pd.DataFrame) -> pd.DataFrame:
    r = rows.assign(year=rows["period"] // 100)
    parts = [cal.default_buckets(g).assign(year=y) for y, g in r.groupby("year")]
    return pd.concat(parts, ignore_index=True)


def fit_default_clustered(b: pd.DataFrame) -> pd.DataFrame:
    """The notebook 05 Poisson GLM with standard errors clustered by calendar year."""
    import statsmodels.api as sm
    c = b[(b["dq30"] == 0) & (b["dq60"] == 0)]
    X = pd.DataFrame({
        "const": 1.0,
        "ltv_low": np.minimum(c["ltv"] - 80, 0), "ltv_high": np.maximum(c["ltv"] - 80, 0),
        "fico": c["fico"] - 750, "dti": c["dti"] - 38,
        "investor": c["investor"], "pre2009": c["pre2009"],
    })
    m = sm.GLM(c["events"], X, family=sm.families.Poisson(), offset=np.log(c["n"]))
    naive, clus = m.fit(), m.fit(cov_type="cluster", cov_kwds={"groups": c["year"].to_numpy()})
    return pd.DataFrame({"coef": naive.params, "se_naive": naive.bse, "se_cluster_year": clus.bse,
                         "z_cluster": clus.params / clus.bse})
