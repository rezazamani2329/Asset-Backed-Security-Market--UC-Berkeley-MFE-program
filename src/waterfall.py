"""Allocate reference-pool principal and losses to the tranches.

Fill in TRANCHES from the offering circular's reference tranche table.
The offered classes (A-1, M-1, M-2) are only part of the structure;
Freddie Mac retains other pieces (senior, vertical slice, subordinate).

Rules to extract from the offering circular:
  - Loss allocation order (bottom up?)
  - Principal allocation: sequential vs. pro rata; triggers (minimum credit
    enhancement test, delinquency test) that switch between them
  - Clean-up call / optional redemption
"""
from dataclasses import dataclass


@dataclass
class Tranche:
    name: str
    balance: float
    offered: bool          # sold to investors vs. retained by Freddie Mac
    spread_bps: float = 0.0


# Ordered SENIOR -> JUNIOR. TODO: populate from the offering circular.
TRANCHES: list[Tranche] = []


def allocate_losses(tranches: list[Tranche], loss: float) -> list[float]:
    """Write down `loss` from the most junior tranche upward. Return new balances."""
    raise NotImplementedError


def allocate_principal(tranches: list[Tranche], principal: float,
                       triggers_pass: bool) -> list[float]:
    """Distribute principal per the deal's rules. Return principal paid to each tranche."""
    raise NotImplementedError


def run(tranches: list[Tranche], pool_cf) -> dict:
    """Run a pool cash-flow projection through the waterfall.

    Returns {tranche_name: DataFrame(month, balance, principal, writedown, interest)}.
    """
    raise NotImplementedError
