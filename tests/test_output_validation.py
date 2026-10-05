"""Final output-level validation for the STACR 2026-DNA1 pipeline.

These tests intentionally validate persisted team outputs independently of the
waterfall/pricing unit tests.  They are designed to catch integration problems
such as stale snapshots, broken balance roll-forwards, negative tranche
balances, or unexpected writedowns to the offered notes.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("good", "base", "moderate", "severe")
OFFERED_CLASSES = {"A-1", "M-1", "M-2A", "M-2B"}
EXPECTED_STARTING_POOL = 19_254_307_537.76
EXPECTED_M1_BALANCE = 157_810_518.32
MINIMUM_CE = 0.03525


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_pool_cashflow_rollforward_reconciles(scenario):
    pool = pd.read_csv(ROOT / "outputs" / "tables" / f"pool_cf_{scenario}.csv")

    expected_ending = (
        pool["beginning_balance"]
        - pool["scheduled_principal"]
        - pool["prepayments"]
        - pool["defaults"]
    )
    np.testing.assert_allclose(pool["ending_balance"], expected_ending, atol=0.02)

    np.testing.assert_allclose(
        pool["beginning_balance"].iloc[1:].to_numpy(),
        pool["ending_balance"].iloc[:-1].to_numpy(),
        atol=0.02,
    )

    assert pool.loc[0, "beginning_balance"] == pytest.approx(EXPECTED_STARTING_POOL, abs=0.02)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_persisted_waterfall_outputs_reconcile(scenario):
    wf = pd.read_csv(ROOT / "outputs" / "tables" / f"waterfall_cf_{scenario}.csv")

    expected_ending = (
        wf["beginning_balance"]
        - wf["principal"]
        - wf["writedown"]
        + wf["writeup"]
    )
    np.testing.assert_allclose(wf["ending_balance"], expected_ending, atol=0.02)
    assert (wf["ending_balance"] >= -1e-8).all()

    offered = wf[wf["tranche"].isin(OFFERED_CLASSES)]
    assert offered["writedown"].sum() == pytest.approx(0.0, abs=0.01)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_current_snapshot_and_month_one_trigger_are_aligned(scenario):
    wf = pd.read_csv(ROOT / "outputs" / "tables" / f"waterfall_cf_{scenario}.csv")
    month1 = wf[wf["month"] == 1]

    m1 = month1[month1["tranche"] == "M-1"]
    assert len(m1) == 1
    assert m1.iloc[0]["beginning_balance"] == pytest.approx(EXPECTED_M1_BALANCE, abs=0.02)

    assert month1["minimum_ce_test"].all()

    summary = pd.read_csv(ROOT / "outputs" / "tables" / "tranche_pricing_summary.csv")
    starting_sub = summary.loc[summary["scenario"] == scenario, "starting_subordinate_pct"]
    assert len(starting_sub) == len(OFFERED_CLASSES)
    assert (starting_sub >= MINIMUM_CE).all()


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_pricing_summary_is_monotone_in_discount_margin(scenario):
    summary = pd.read_csv(ROOT / "outputs" / "tables" / "tranche_pricing_summary.csv")
    block = summary[summary["scenario"] == scenario]

    assert set(block["tranche"]) == OFFERED_CLASSES
    assert (block["price_at_0bp_dm"] > block["price_at_100bp_dm"]).all()
    assert (block["price_at_100bp_dm"] > block["price_at_200bp_dm"]).all()
    assert block["wal_years"].between(0.0, 5.0).all()
