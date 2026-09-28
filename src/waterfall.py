"""Allocate reference-pool principal and losses to the tranches.

TRANCHES below is filled from the PPM reference tranche table (Table 3).
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


# Ordered SENIOR -> JUNIOR. Source: STACR 2026-DNA1 PPM, Table 3 (p. 2) and Table 1 (p. x).
# Balances are initial Class Notional Amounts; they sum to the Cut-off Date Balance.
# See docs/cashflows.md for attach/detach points and the full allocation rules.
#
# IMPORTANT: each offered class and its "H" twin (A-1/A-1H, M-1/M-1H, M-2A/M-2AH,
# M-2B/M-2BH) share one attach/detach band and take write-downs, write-ups and
# principal PRO RATA (PPM p. 82-88). Do not write them down one after the other.
# A-H only absorbs certain modification-related losses (PPM p. 82).
# B-1H and B-2H spreads are "deemed" coupons used only for modification loss
# allocation; nobody is paid on them.
CUTOFF_BALANCE = 22_781_151_551.84

TRANCHES: list[Tranche] = [
    Tranche("A-H",   21_687_655_280.84, offered=False),
    Tranche("A-1",      275_900_000.00, offered=True,  spread_bps=85),
    Tranche("A-1H",      14_559_682.00, offered=False, spread_bps=85),
    Tranche("M-1",      275_900_000.00, offered=True,  spread_bps=100),
    Tranche("M-1H",      14_559_682.00, offered=False, spread_bps=100),
    Tranche("M-2A",      37_850_000.00, offered=True,  spread_bps=130),
    Tranche("M-2AH",      2_017_015.00, offered=False, spread_bps=130),
    Tranche("M-2B",      37_850_000.00, offered=True,  spread_bps=130),
    Tranche("M-2BH",      2_017_015.00, offered=False, spread_bps=130),
    Tranche("B-1H",     102_515_181.00, offered=False, spread_bps=180),
    Tranche("B-2H",     273_373_818.00, offered=False, spread_bps=475),
    Tranche("B-3H",      56_953_878.00, offered=False),
]

# Offered class -> retained twin that shares its band pro rata.
PRO_RATA_PAIRS = {"A-1": "A-1H", "M-1": "M-1H", "M-2A": "M-2AH", "M-2B": "M-2BH"}


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
