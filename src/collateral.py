"""Reference-pool performance model: default, prepayment, loss severity.

Calibrate on HISTORICAL data (course data / Freddie Single-Family Loan-Level Dataset),
then apply to the current STACR / CAS pools. The Bloomberg snapshots alone have too
little performance history to estimate stress behavior.

Design decisions to make:
  - Loan-level hazard model vs. pool-level curves?
  - Drivers: current (mark-to-market) LTV, FICO, DTI, occupancy, purpose, age, rate incentive?
  - Severity: function of LTV at default? Mortgage insurance for LTV > 80 (CAS group 2)?
"""
import numpy as np
import pandas as pd


def default_hazard(loans: pd.DataFrame, hpi_path: np.ndarray) -> np.ndarray:
    """Monthly default probability per loan along one scenario path."""
    raise NotImplementedError


def prepay_hazard(loans: pd.DataFrame, rate_path: np.ndarray) -> np.ndarray:
    """Monthly prepayment probability per loan along one scenario path."""
    raise NotImplementedError


def severity(loans: pd.DataFrame, hpi_at_default: np.ndarray) -> np.ndarray:
    """Loss given default as a fraction of balance."""
    raise NotImplementedError


def project_pool(loans: pd.DataFrame, hpi_path, rate_path) -> pd.DataFrame:
    """Monthly pool cash flows for one path.

    Columns: beginning_balance, scheduled_principal, prepayments, defaults,
             losses, ending_balance
    """
    raise NotImplementedError
