"""Discount tranche cash flows to price / discount margin.

STACR notes pay SOFR + spread on outstanding balance.
Decide and justify: risk-neutral vs. physical default assumptions, and how
model output is compared to Bloomberg market discount margins.
"""
import numpy as np


def price(cashflows: np.ndarray, sofr: np.ndarray, dm_bps: float) -> float:
    """Price per 100 face given monthly cash flows, projected SOFR, and a discount margin."""
    raise NotImplementedError


def discount_margin(cashflows: np.ndarray, sofr: np.ndarray, market_price: float) -> float:
    """Solve for the DM (bps) that equates model PV with the market price."""
    raise NotImplementedError
