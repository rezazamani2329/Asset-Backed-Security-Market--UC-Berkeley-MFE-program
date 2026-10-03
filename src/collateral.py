"""Reference-pool performance model (kept as the entry point named in the README pipeline).

The model is split into:
  - src/prepayment.py            CPR / SMM, refi incentive
  - src/credit_model.py          credit events (defaults) and severity
  - src/collateral_projection.py monthly pool table handed to the waterfall

Calibrate on HISTORICAL data (course data / Freddie Single-Family Loan-Level Dataset),
then apply to the current STACR pool. The Bloomberg snapshots alone have too
little performance history to estimate stress behavior.
"""
from src.prepayment import calculate_cpr, calculate_smm, calculate_prepayment  # noqa: F401
from src.credit_model import (calculate_credit_event_rate, calculate_credit_events,  # noqa: F401
                              calculate_loss_severity)
from src.collateral_projection import project_collateral, run_scenarios  # noqa: F401
