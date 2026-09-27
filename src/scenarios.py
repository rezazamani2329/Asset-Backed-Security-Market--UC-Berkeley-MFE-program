"""House-price and interest-rate scenario generation.

Design decisions to make (and justify in the report):
  - Deterministic stress scenarios (base / adverse / severe) vs. Monte Carlo paths?
  - HPA model: national vs. state/MSA level? Drift and volatility calibrated to what?
  - Rate paths: needed for prepayment incentive and for SOFR coupon projection.
"""
import numpy as np


def hpa_paths(n_paths: int, n_months: int, seed: int = 0) -> np.ndarray:
    """Cumulative house-price index paths, shape (n_paths, n_months + 1), starting at 1.0."""
    raise NotImplementedError


def rate_paths(n_paths: int, n_months: int, seed: int = 0) -> dict:
    """Return {'mortgage_rate': ..., 'sofr': ...}, each shape (n_paths, n_months)."""
    raise NotImplementedError
