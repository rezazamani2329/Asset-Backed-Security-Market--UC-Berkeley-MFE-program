"""Checks for the no-call run and duration measures (src/duration.py, run_waterfall_pricing)."""
import numpy as np
import pandas as pd
import pytest

from src import duration as du
from src import lockin as lk
from src import run_waterfall_pricing as rw
from src.waterfall import CALL_DATE, CURRENT_POOL_BALANCE


def slow_pool(n=du.N_TO_MATURITY, smm=0.004):
    """A loss-free pool that pays down slowly, so the notes are still outstanding in 2031."""
    rows, bal = [], CURRENT_POOL_BALANCE
    for m in range(1, n + 1):
        sched, prepay = bal * 0.0015, bal * smm
        rows.append({"month": m, "beginning_balance": bal, "scheduled_principal": sched,
                     "prepayments": prepay, "defaults": 0.0, "losses": 0.0, "recoveries": 0.0,
                     "ending_balance": bal - sched - prepay, "modification_losses": 0.0,
                     "distressed_balance": 0.0})
        bal -= sched + prepay
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def rates():
    r = pd.read_csv(lk.PRICING_RATES)
    return du.extend_rates(r[r.scenario == "base"])


def test_extend_rates(rates):
    base = pd.read_csv(lk.PRICING_RATES).query("scenario == 'base'").sort_values("month")
    assert len(rates) == du.N_TO_MATURITY
    assert rates["date"].iloc[-1] == du.MATURITY_DATE
    assert (rates["coupon_accrual_days"] > 0).all() and (rates["discount_days"] > 0).all()
    assert rates["sofr_coupon_decimal"].iloc[:53].to_numpy() == pytest.approx(base["sofr_coupon_decimal"].to_numpy())
    assert rates["sofr_coupon_decimal"].iloc[53:].nunique() == 1


def test_extend_path():
    path = {"hpi": np.linspace(1.0, 1.2, 54), "rate": np.full(53, 7.0)}
    ext = du.extend_path(path)
    assert len(ext["rate"]) == du.N_TO_MATURITY and len(ext["hpi"]) == du.N_TO_MATURITY + 1
    assert (ext["rate"][53:] == 7.0).all() and (np.diff(ext["hpi"]) > 0).all()


def test_default_still_calls_in_2031(rates):
    pool = slow_pool()
    _, default = rw.run_scenario(pool, rates)
    _, explicit = rw.run_scenario(pool, rates, call_date=CALL_DATE)
    pd.testing.assert_frame_equal(default, explicit)
    assert (default["final_payment_month"] <= 53).all()


def test_no_call_extends_the_notes(rates):
    pool = slow_pool()
    _, called = rw.run_scenario(pool, rates, call_date=CALL_DATE)
    _, no_call = rw.run_scenario(pool, rates, call_date=du.MATURITY_DATE)
    c, n = called.set_index("tranche"), no_call.set_index("tranche")
    assert (n["wal_years"] >= c["wal_years"] - 1e-9).all()
    assert n.loc["M-2B", "wal_years"] > c.loc["M-2B", "wal_years"] + 1.0
    assert n.loc["M-2B", "final_payment_month"] > 53
    assert n["total_principal"].to_numpy() == pytest.approx(n["starting_balance"].to_numpy())


def test_duration_measures(rates):
    pool = slow_pool()
    pools = {0.0: pool, du.SHIFT_BPS: pool, -du.SHIFT_BPS: pool}   # prepayments do not respond
    for call in (CALL_DATE, du.MATURITY_DATE):
        m = du.measures(pools, rates, call).set_index("tranche")
        assert (m["spread_duration"] > 0).all()
        assert (m["spread_duration"] < m["wal_years"] + 0.1).all()
        # a floater whose cash flows do not respond to rates has almost no rate duration
        assert (m["effective_duration"].abs() < 0.1).all()
