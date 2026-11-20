import numpy as np
import pandas as pd

from src import calibration as cal
from src import lockin_inference as li
from src import prepayment as pp

BASE = {k: pp.PARAMS[k] for k in cal.PREPAY_NAMES}


def synthetic_month_buckets(gamma=0.1, g2=None, months=None, seed=0, noise=0.0004):
    """Month buckets whose SMM follows the model with a known lock-in strength."""
    rng = np.random.default_rng(seed)
    months = months or [y * 100 + m for y in (2022, 2023, 2024, 2025) for m in range(1, 13)]
    theta0 = [BASE[k] for k in cal.PREPAY_NAMES]
    rows = []
    for t, month in enumerate(months):
        shock = rng.normal(0, noise)                     # common shock to the whole month
        for inc in np.arange(-3.4, 1.01, 0.4):
            for age in (12.0, 40.0, 100.0):
                g = [gamma] if g2 is None else [gamma, g2]
                smm = li.model_smm(theta0, g, np.array([inc]), np.array([age]), np.array([1.0]),
                                   "exp" if g2 is None else "kink")[0]
                smm = max(smm + shock + rng.normal(0, noise / 2), 0)
                w = 1e9
                rows.append({"month": month, "inc_b": round(inc, 1), "age_b": age, "burn_b": 0,
                             "w": w, "prepaid": smm * w, "wi": inc * w, "wa": age * w, "wb": 1.0 * w, "n": 5000})
    return pd.DataFrame(rows)


def test_point_estimate_recovers_gamma():
    bm = synthetic_month_buckets(gamma=0.10)
    est = li.fit(li.collapse(bm, bm["month"].unique()), BASE)["g"][0]
    assert abs(est - 0.10) < 0.02


def test_bootstrap_ci_covers_truth_and_rejects_fhfa():
    bm = synthetic_month_buckets(gamma=0.05, seed=1)
    months = bm["month"].unique()
    point_b = li.collapse(bm, months)
    e, k = li.fit(point_b, BASE), li.fit(point_b, BASE, "kink")
    draws = li.bootstrap(bm, months, BASE, n_boot=40, block=6, seed=3)
    s = li.summarize({"gamma": e["g"][0], "g1": k["g"][0], "g2": k["g"][1]}, draws)
    assert s.loc["gamma", "ci_low"] <= 0.05 <= s.loc["gamma", "ci_high"]
    assert s.loc["gamma", "p_gamma_ge_fhfa"] == 0.0


def test_kink_detected_when_present():
    bm = synthetic_month_buckets(gamma=0.0, g2=0.4, seed=2)
    b = li.collapse(bm, bm["month"].unique())
    k = li.fit(b, BASE, "kink")["g"]
    assert k[1] - k[0] > 0.2
    assert li.kink_f_stat(b, BASE)["F"] > 10


def test_block_draws_keep_length():
    months = list(range(1, 25))
    for wts in li.block_draws(months, 5, 6, 0):
        assert sum(wts.values()) == len(months)


def test_diebold_mariano_sign():
    rng = np.random.default_rng(0)
    good = rng.normal(0, 0.1, 60)
    bad = good + 0.3
    out = li.diebold_mariano(bad, good)
    assert out["dm_stat"] > 0 and out["p_two_sided"] < 0.01


def test_forecast_test_prefers_true_gamma():
    months = [y * 100 + m for y in (2022, 2023, 2024, 2025, 2026) for m in range(1, 13)]
    bm = synthetic_month_buckets(gamma=0.3, months=months, seed=4)
    out = li.forecast_test(bm, BASE)
    assert abs(out["gamma_train"] - 0.3) < 0.05
    assert out["rmse_cpr_pp"]["estimated"] < out["rmse_cpr_pp"]["none"]


def test_month_buckets_add_up_to_year_buckets():
    periods = [202211, 202212, 202301, 202302]
    rows = []
    for lid, rate in (("a", 3.0), ("b", 7.5)):
        upb = 300_000.0
        for k, per in enumerate(periods):
            zb = "01" if (lid == "b" and k == 3) else ""
            rows.append({"loan_id": lid, "period": per, "rate": rate, "upb": 0.0 if zb else upb,
                         "dq": 0, "rem": 340 - k, "age": 20 + k, "zb_code": zb})
            upb -= 2_000.0 if lid == "a" else 500.0
    panel = pd.DataFrame(rows)
    mrate = pd.Series(6.5, index=periods)
    bm = li.prepay_buckets_by_month(panel, mrate)
    by = cal.prepay_buckets_by_year(panel, mrate)
    assert set(bm["month"]) == {202212, 202301, 202302}
    assert np.isclose(bm["w"].sum(), by["w"].sum())
    assert np.isclose(bm["prepaid"].sum(), by["prepaid"].sum())
    assert bm.loc[bm["month"] == 202302, "prepaid"].sum() > 0
