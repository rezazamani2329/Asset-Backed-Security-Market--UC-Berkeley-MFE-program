"""Sanity checks for the default/prepay model. Remove the skip marks as each piece exists."""
import numpy as np
import pandas as pd
import pytest

from src.prepayment import cpr, cpr_to_smm, smm_to_cpr
from src.credit_model import default_rate, severity
from src.collateral_projection import project_pool


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
    assert smm_to_cpr(cpr_to_smm(x)) == pytest.approx(x)


def test_lower_rates_mean_faster_prepay():
    n = 12
    low, high = np.full(n, 5.0), np.full(n, 8.0)
    assert (cpr(toy_pool(), low) > cpr(toy_pool(), high)).all()


def test_falling_home_prices_mean_more_defaults():
    n = 12
    up, down = np.linspace(1.0, 1.05, n), np.linspace(1.0, 0.80, n)
    assert default_rate(toy_pool(), down).sum() > default_rate(toy_pool(), up).sum()


def test_falling_home_prices_mean_higher_severity():
    assert (severity(toy_pool(), np.full(2, 0.80)) > severity(toy_pool(), np.full(2, 1.05))).all()


def test_balance_conserved():
    n = 24
    cf = project_pool(toy_pool(), np.ones(n + 1), np.full(n, 6.5), n)
    out = cf["scheduled_principal"] + cf["prepayments"] + cf["defaults"]
    assert (cf["beginning_balance"] - out).to_numpy() == pytest.approx(cf["ending_balance"].to_numpy())
    assert cf["beginning_balance"].iloc[0] == pytest.approx(800_000.0)
