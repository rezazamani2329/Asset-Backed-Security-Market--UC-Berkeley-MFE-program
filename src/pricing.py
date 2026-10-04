"""Present-value and discount-margin utilities for monthly STACR cash flows.

Rates are decimal annual rates: ``0.04`` means 4%.  Cash flows passed to
``price`` are amounts per 100 face, so the result is a full (dirty) price per
100, including interest accrued since the last payment date.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _arrays(cashflows, sofr, day_counts=None):
    cf = np.asarray(cashflows, dtype=float)
    rates = np.asarray(sofr, dtype=float)
    if cf.ndim != 1 or rates.ndim != 1 or len(cf) != len(rates) or len(cf) == 0:
        raise ValueError("cashflows and sofr must be non-empty one-dimensional arrays of equal length")
    if not np.isfinite(cf).all() or not np.isfinite(rates).all():
        raise ValueError("cashflows and sofr must be finite")
    if ((rates < -0.10) | (rates > 1.0)).any():
        raise ValueError("sofr must be supplied as a decimal annual rate")
    days = np.full(len(cf), 30.0) if day_counts is None else np.asarray(day_counts, dtype=float)
    if days.shape != cf.shape or not np.isfinite(days).all() or (days <= 0).any():
        raise ValueError("day_counts must contain one positive value per cash flow")
    return cf, rates, days


def discount_factors(sofr, dm_bps: float, day_counts=None) -> np.ndarray:
    """Cumulative money-market discount factors for SOFR plus discount margin."""
    _, rates, days = _arrays(np.zeros(len(sofr)), sofr, day_counts)
    dm = float(dm_bps) / 10_000.0
    period_rates = 1.0 + (rates + dm) * days / 360.0
    if (period_rates <= 0).any():
        raise ValueError("SOFR plus discount margin produces a non-positive discount factor")
    return 1.0 / np.cumprod(period_rates)


def price(cashflows: np.ndarray, sofr: np.ndarray, dm_bps: float, day_counts=None) -> float:
    """Return full price per 100 for monthly cash flows already expressed per 100 face."""
    cf, rates, days = _arrays(cashflows, sofr, day_counts)
    return float(np.dot(cf, discount_factors(rates, dm_bps, days)))


def discount_margin(
    cashflows: np.ndarray, sofr: np.ndarray, market_price: float, day_counts=None,
    *, lower_bps: float = -5_000.0, upper_bps: float = 20_000.0,
    tolerance: float = 1e-8, max_iterations: int = 250,
) -> float:
    """Solve the discount margin in basis points that matches ``market_price``.

    Uses deterministic bisection so the core calculation does not depend on a
    SciPy optimizer.  A clear error is raised if the chosen bracket has no root.
    """
    target = float(market_price)
    if not np.isfinite(target) or target < 0:
        raise ValueError("market_price must be finite and non-negative")
    cf, rates, days = _arrays(cashflows, sofr, day_counts)

    def objective(dm):
        return price(cf, rates, dm, days) - target

    lo, hi = float(lower_bps), float(upper_bps)
    f_lo, f_hi = objective(lo), objective(hi)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if f_lo * f_hi > 0:
        raise ValueError("Discount-margin root is not bracketed")
    for _ in range(max_iterations):
        mid = (lo + hi) / 2.0
        f_mid = objective(mid)
        if abs(f_mid) <= tolerance or abs(hi - lo) <= tolerance:
            return mid
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    raise RuntimeError("Discount-margin solver did not converge")


def weighted_average_life(principal, day_counts=None) -> float:
    """Principal-weighted average payment time in years."""
    p = np.asarray(principal, dtype=float)
    if p.ndim != 1 or len(p) == 0 or not np.isfinite(p).all() or (p < -1e-10).any():
        raise ValueError("principal must be a non-negative one-dimensional array")
    total = p.sum()
    if total <= 0:
        return float("nan")
    days = np.full(len(p), 30.0) if day_counts is None else np.asarray(day_counts, dtype=float)
    if days.shape != p.shape or (days <= 0).any():
        raise ValueError("day_counts must contain one positive value per principal payment")
    years = np.cumsum(days) / 365.0
    return float(np.dot(p, years) / total)


def class_metrics(
    cashflows: pd.DataFrame, original_face: float, sofr, *, market_price: float | None = None,
    day_counts=None,
) -> dict[str, float]:
    """Summarize one offered class waterfall output.

    ``cashflows`` must contain ``interest``, ``principal`` and ``writedown``.
    Price/DM is only solved when ``market_price`` is provided; no market level is
    fabricated by the model.
    """
    required = {"interest", "principal", "writedown"}
    missing = required - set(cashflows.columns)
    if missing:
        raise ValueError(f"Class cash flow is missing columns: {sorted(missing)}")
    face = float(original_face)
    if face <= 0:
        raise ValueError("original_face must be positive")
    interest = cashflows["interest"].to_numpy(float)
    principal = cashflows["principal"].to_numpy(float)
    writedown = cashflows["writedown"].to_numpy(float)
    total_cf_per_100 = (interest + principal) / face * 100.0
    result = {
        "weighted_average_life_years": weighted_average_life(principal, day_counts),
        "principal_paid_pct": float(principal.sum() / face),
        "writedown_pct": float(writedown.sum() / face),
        "interest_paid_per_100": float(interest.sum() / face * 100.0),
    }
    if market_price is not None:
        dm = discount_margin(total_cf_per_100, np.asarray(sofr, dtype=float), market_price, day_counts)
        result["market_price"] = float(market_price)
        result["discount_margin_bps"] = dm
    return result
