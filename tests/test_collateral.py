"""Sanity checks for the default/prepay model. Remove the skip marks as each piece exists."""
import numpy as np
import pandas as pd
import pytest

from src.prepayment import calculate_cpr, calculate_smm, calculate_prepayment, smm_to_cpr
from src.credit_model import calculate_credit_event_rate, calculate_loss_severity
from src.collateral_projection import project_collateral, project_pool


def toy_pool():
    # Illustrative loans (NOT the real pool)
    return pd.DataFrame({
        "Loan ID": ["a", "b"],
        "Current Balance": [300_000.0, 500_000.0],
        "Gross Coupon": [6.75, 7.25],
        "Credit Score": [760, 700],
        "HPI Adjusted LTV": [70.0, 78.0],
        "Age": [18, 18],
        "Months to Maturity": [342, 342],
        "dq_bucket": [0, 0],
    })


def test_cpr_smm_round_trip():
    x = np.array([0.0, 0.06, 0.25, 0.60])
    assert smm_to_cpr(calculate_smm(x)) == pytest.approx(x)


def test_lower_rates_mean_faster_prepay():
    n = 12
    low, high = np.full(n, 5.0), np.full(n, 8.0)
    assert (calculate_cpr(toy_pool(), low) > calculate_cpr(toy_pool(), high)).all()


def test_falling_home_prices_mean_more_defaults():
    n = 12
    up, down = np.linspace(1.0, 1.05, n), np.linspace(1.0, 0.80, n)
    assert calculate_credit_event_rate(toy_pool(), down).sum() > calculate_credit_event_rate(toy_pool(), up).sum()


def test_falling_home_prices_mean_higher_severity():
    assert (calculate_loss_severity(toy_pool(), np.full(2, 0.80)) > calculate_loss_severity(toy_pool(), np.full(2, 1.05))).all()


def test_balance_conserved():
    n = 24
    cf = project_collateral(toy_pool(), np.ones(n + 1), np.full(n, 6.5), n)
    out = cf["scheduled_principal"] + cf["prepayments"] + cf["defaults"]
    assert (cf["beginning_balance"] - out).to_numpy() == pytest.approx(cf["ending_balance"].to_numpy())
    assert cf["beginning_balance"].iloc[0] == pytest.approx(800_000.0)


def test_prepayment_uses_balance_after_scheduled_principal():
    assert calculate_prepayment(1000.0, 100.0, 0.02) == pytest.approx(18.0)


def test_old_names_still_work():
    assert project_pool is project_collateral


def test_good_scenario_prepays_faster_and_loses_less():
    from src.collateral_projection import placeholder_scenarios, run_scenarios
    res = run_scenarios(toy_pool(), placeholder_scenarios(24), 24)
    assert res["good"]["prepayments"].sum() > res["base"]["prepayments"].sum()
    assert res["good"]["losses"].sum() <= res["base"]["losses"].sum()


def test_load_scenarios_reads_coco_format(tmp_path):
    from src.collateral_projection import load_scenarios
    n = 3
    rows = [("base", m, 7.0 + 0.1 * m, 200.0 * (1 + 0.01 * m)) for m in range(n + 1)]
    f = tmp_path / "s.csv"
    pd.DataFrame(rows, columns=["scenario", "month", "mortgage_rate", "hpi_index"]).to_csv(f, index=False)
    s = load_scenarios(f, n)["base"]
    assert s["hpi"][0] == pytest.approx(1.0) and len(s["hpi"]) == n + 1
    assert s["rate"] == pytest.approx([7.1, 7.2, 7.3])
