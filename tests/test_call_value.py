"""Checks for the call value and cost of risk transfer (src/call_value.py)."""
import pandas as pd
import pytest

from src import call_value as cv
from src import duration as du
from src import lockin as lk
from tests.test_duration import slow_pool


@pytest.fixture(scope="module")
def result():
    r = pd.read_csv(lk.PRICING_RATES)
    return cv.compare_call(slow_pool(), du.extend_rates(r[r.scenario == "base"])).set_index("tranche")


def test_call_shortens_and_helps_discount_notes(result):
    assert (result["wal_no_call"] >= result["wal_call"] - 1e-9).all()
    # M-2B trades below par: being paid par early in 2031 is worth something to the investor
    assert result.loc["M-2B", "call_value_per_100"] > 0
    assert result.loc["M-2B", "dm_no_call_bps"] < result.loc["M-2B", "dm_call_bps"]


def test_freddie_cost_without_losses(result):
    assert (result[["protection_call_usd", "protection_no_call_usd"]] == 0).all().all()
    assert (result["spread_cost_call_usd"] > 0).all()
    assert (result["extra_cost_no_call_usd"] >= -1e-6).all()
    assert result.loc["M-2B", "extra_cost_no_call_usd"] > 0


def test_spread_cost_matches_simple_formula():
    # one note, balance 100 for 12 months of 30 days, spread 100bp, SOFR 0: cost = 12 * 100 * 0.01 * 30/360
    n = {"balance": pd.Series([100.0] * 12).to_numpy(), "spread_bps": 100.0,
         "accrual_days": pd.Series([30.0] * 12).to_numpy(), "sofr": pd.Series([0.0] * 12).to_numpy(),
         "days": pd.Series([30.0] * 12).to_numpy(), "writedowns": pd.Series([0.0] * 12).to_numpy()}
    assert cv.freddie_cost(n)["spread_cost"] == pytest.approx(1.0)
