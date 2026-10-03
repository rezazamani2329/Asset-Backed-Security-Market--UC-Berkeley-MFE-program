import numpy as np
import pandas as pd
import pytest

from src.pricing import class_metrics, discount_margin, price, weighted_average_life


def test_zero_rate_price_is_sum_of_cashflows():
    assert price(np.array([2.0, 102.0]), np.zeros(2), 0.0) == pytest.approx(104.0)


def test_higher_discount_margin_reduces_price():
    cf = np.array([1.0] * 11 + [101.0])
    sofr = np.full(12, 0.04)
    assert price(cf, sofr, 300.0) < price(cf, sofr, 100.0)


def test_discount_margin_inverts_price():
    cf = np.array([1.0] * 11 + [101.0])
    sofr = np.full(12, 0.04)
    market = price(cf, sofr, 275.0)
    assert discount_margin(cf, sofr, market) == pytest.approx(275.0, abs=1e-5)


def test_rates_must_be_decimal():
    with pytest.raises(ValueError, match="decimal"):
        price(np.array([100.0]), np.array([4.0]), 0.0)


def test_weighted_average_life():
    assert weighted_average_life(np.array([50.0, 50.0]), [365.0, 365.0]) == pytest.approx(1.5)


def test_class_metrics_do_not_invent_market_price():
    frame = pd.DataFrame({"interest": [1.0, 1.0], "principal": [0.0, 100.0], "writedown": [0.0, 0.0]})
    metrics = class_metrics(frame, 100.0, np.array([0.04, 0.04]))
    assert metrics["principal_paid_pct"] == pytest.approx(1.0)
    assert metrics["writedown_pct"] == 0.0
    assert "discount_margin_bps" not in metrics
