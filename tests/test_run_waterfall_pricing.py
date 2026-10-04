from pathlib import Path

import numpy as np
import pytest

from src.run_waterfall_pricing import OFFERED_CLASSES, SCENARIOS, run_all


ROOT = Path(__file__).resolve().parents[1]


def test_team_scenarios_run_end_to_end_without_writedown_to_offered_notes():
    cashflows, summary = run_all(ROOT, write_outputs=False)
    assert set(cashflows) == set(SCENARIOS)
    assert len(summary) == len(SCENARIOS) * len(OFFERED_CLASSES)
    assert set(summary["tranche"]) == set(OFFERED_CLASSES)
    assert (summary["total_writedown"] == 0.0).all()
    np.testing.assert_allclose(summary["total_principal"], summary["starting_balance"], atol=0.02)
    assert summary["wal_years"].between(0.0, 5.0).all()

    for frame in cashflows.values():
        assert frame["called"].any()
        identity = (
            frame["beginning_balance"] - frame["principal"]
            - frame["writedown"] + frame["writeup"]
        )
        assert identity.to_numpy() == pytest.approx(frame["ending_balance"].to_numpy(), abs=0.02)


def test_price_falls_as_discount_margin_rises():
    _, summary = run_all(ROOT, write_outputs=False)
    assert (summary["price_at_0bp_dm"] > summary["price_at_100bp_dm"]).all()
    assert (summary["price_at_100bp_dm"] > summary["price_at_200bp_dm"]).all()


def test_current_state_passes_minimum_credit_enhancement_from_month_one():
    _, summary = run_all(ROOT, write_outputs=False)
    assert (summary["starting_subordinate_pct"] >= 0.03525).all()
    for frame in run_all(ROOT, write_outputs=False)[0].values():
        assert frame.loc[frame["month"] == 1, "minimum_ce_test"].all()
