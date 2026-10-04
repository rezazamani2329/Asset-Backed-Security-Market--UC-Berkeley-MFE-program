"""STACR 2026-DNA1 tranche waterfall primitives and monthly engine.

The implementation separates immutable tranche terms from monthly balances.  It
implements the deal's ordinary loss/write-up order, offered/H pro-rata pairs,
trigger gate, senior/subordinate principal buckets, A-1 scheduled reduction and
the February 2031 call.  Defaulted UPB not written down is paid as Recovery
Principal.  Supplemental reduction remains unsupported.

Sources: ``docs/cashflows.md`` and the cited PPM pages in that document.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


CUTOFF_BALANCE = 22_781_151_551.84
A1_CNL_LIMIT = 0.01
MIN_SUBORDINATE_PCT = 0.03525
CALL_DATE = pd.Timestamp("2031-02-25")


@dataclass
class Tranche:
    """One reference tranche or note class.

    ``balance`` is mutable state supplied for the valuation date.  For a
    closing-date run it equals ``original_balance``.  For a current valuation,
    current class factors must be used instead of silently scaling the stack.
    """

    name: str
    balance: float
    offered: bool
    spread_bps: float = 0.0
    original_balance: float | None = None
    cumulative_writedown: float = 0.0

    def __post_init__(self) -> None:
        if self.original_balance is None:
            self.original_balance = float(self.balance)
        for field in ("balance", "original_balance", "cumulative_writedown"):
            if getattr(self, field) < -1e-8:
                raise ValueError(f"{self.name}: {field} cannot be negative")


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

PRO_RATA_PAIRS = {
    "A-1": "A-1H", "M-1": "M-1H", "M-2A": "M-2AH", "M-2B": "M-2BH"
}
PAIR_BY_MEMBER = {member: pair for pair in PRO_RATA_PAIRS.items() for member in pair}

# Ordinary losses exclude A-H.  The PPM permits A-H only for certain
# modification-related losses, which are deliberately not folded into this path.
LOSS_BANDS: tuple[tuple[str, ...], ...] = (
    ("B-3H",), ("B-2H",), ("B-1H",), ("M-2B", "M-2BH"),
    ("M-2A", "M-2AH"), ("M-1", "M-1H"), ("A-1", "A-1H"),
)
WRITEUP_BANDS: tuple[tuple[str, ...], ...] = (
    ("A-H",), ("A-1", "A-1H"), ("M-1", "M-1H"),
    ("M-2A", "M-2AH"), ("M-2B", "M-2BH"),
    ("B-1H",), ("B-2H",), ("B-3H",),
)
SUBORDINATE_PRINCIPAL_BANDS: tuple[tuple[str, ...], ...] = (
    ("M-1", "M-1H"), ("M-2A", "M-2AH"), ("M-2B", "M-2BH"),
    ("B-1H",), ("B-2H",), ("B-3H",), ("A-1", "A-1H"), ("A-H",),
)
POST_36_SENIOR_PRINCIPAL_BANDS: tuple[tuple[str, ...], ...] = (
    ("A-1", "A-1H"), ("A-H",), ("M-1", "M-1H"),
    ("M-2A", "M-2AH"), ("M-2B", "M-2BH"),
    ("B-1H",), ("B-2H",), ("B-3H",),
)

# PPM pp. 84-85. Each tuple is (amount type, reference-tranche band).
# B-3H has no deemed coupon, so its modification allocation is principal.
MODIFICATION_LOSS_PRIORITY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("principal", ("B-3H",)),
    ("interest", ("B-2H",)), ("principal", ("B-2H",)),
    ("interest", ("B-1H",)), ("principal", ("B-1H",)),
    ("interest", ("M-2B", "M-2BH")),
    ("interest", ("M-2A", "M-2AH")),
    ("principal", ("M-2B", "M-2BH")),
    ("principal", ("M-2A", "M-2AH")),
    ("interest", ("M-1", "M-1H")),
    ("principal", ("M-1", "M-1H")),
    ("interest", ("A-1", "A-1H")),
    ("principal", ("A-1", "A-1H")),
)
SENIOR_PRINCIPAL_BANDS: tuple[tuple[str, ...], ...] = (
    ("A-H",), ("A-1", "A-1H"), ("M-1", "M-1H"),
    ("M-2A", "M-2AH"), ("M-2B", "M-2BH"),
    ("B-1H",), ("B-2H",), ("B-3H",),
)


def copy_tranches(tranches: Sequence[Tranche]) -> list[Tranche]:
    return [replace(t) for t in tranches]


def current_tranches() -> list[Tranche]:
    """Return the estimated post-September-2026 tranche state.

    Current balances are supplied by the team handoff and retain the original
    legal balances for A-1 scheduling and loss-history caps.
    """
    return [replace(t, balance=CURRENT_BALANCES[t.name]) for t in TRANCHES]


def _index(tranches: Sequence[Tranche]) -> dict[str, int]:
    names = [t.name for t in tranches]
    if len(names) != len(set(names)):
        raise ValueError("Tranche names must be unique")
    return {name: i for i, name in enumerate(names)}


def _validate_amount(amount: float, label: str) -> float:
    value = float(amount)
    if not np.isfinite(value) or value < -1e-8:
        raise ValueError(f"{label} must be finite and non-negative")
    return max(value, 0.0)


def _deal_bands_or_generic(
    tranches: Sequence[Tranche], deal_bands: Sequence[tuple[str, ...]], *, reverse: bool
) -> tuple[tuple[str, ...], ...]:
    names = set(_index(tranches))
    required = {name for band in deal_bands for name in band}
    if required.issubset(names):
        return tuple(deal_bands)
    ordered = [t.name for t in tranches]
    if reverse:
        ordered.reverse()
    return tuple((name,) for name in ordered)


def _allocate_reduction(
    tranches: Sequence[Tranche], amount: float, bands: Sequence[tuple[str, ...]]
) -> tuple[list[float], list[float], float]:
    """Reduce balances through ordered bands, pro rata inside each band."""
    remaining = _validate_amount(amount, "amount")
    balances = [float(t.balance) for t in tranches]
    allocated = [0.0] * len(tranches)
    by_name = _index(tranches)
    for band in bands:
        ids = [by_name[name] for name in band if name in by_name]
        capacity = sum(balances[i] for i in ids)
        take = min(remaining, capacity)
        if take > 0 and capacity > 0:
            for i in ids:
                share = take * balances[i] / capacity
                balances[i] -= share
                allocated[i] += share
        remaining -= take
        if remaining <= 1e-7:
            remaining = 0.0
            break
    return balances, allocated, remaining

# Balances after the Sep 2026 Payment Date (7th payment), to start the waterfall
# from the post-September pool. Offered-class factors were validated against
# Bloomberg PDI by Haocheng Sun. H twins use the same factor as their offered
# class; A-H is the residual that makes the full stack equal the current pool.
# In particular, M-1 uses the Sep factor 0.571984481, not the Aug factor
# 0.594889779 that appeared in the earlier estimate.
CURRENT_BALANCES = {
    "A-H":   18_361_378_647.06,
    "A-1":      203_476_250.00,   # factor 0.737500
    "A-1H":      10_737_765.47,
    "M-1":      157_810_518.32,   # Bloomberg balance; displayed factor is rounded
    "M-1H":       8_327_912.15,   # same factor as M-1
    "M-2A":      37_850_000.00,   # factor 1.000000
    "M-2AH":      2_017_015.00,
    "M-2B":      37_850_000.00,   # factor 1.000000
    "M-2BH":      2_017_015.00,
    "B-1H":     102_515_181.00,
    "B-2H":     273_373_818.00,
    "B-3H":      56_953_878.00,
}
# Post-September pool from Bloomberg CLP (reported in $000s). The loan-level tape
# is post-August ($19,443,046,983.78); src.export_results rolls it forward to this.
CURRENT_POOL_BALANCE = 19_254_308_000.00


def allocate_losses(tranches: list[Tranche], loss: float) -> list[float]:
    """Return balances after ordinary losses are allocated bottom-up.

    Real STACR offered/H pairs are treated as one band and share the write-down
    pro rata.  A generic senior-to-junior list is supported for toy tests.
    Inputs are not mutated.
    """
    bands = _deal_bands_or_generic(tranches, LOSS_BANDS, reverse=True)
    balances, _, excess = _allocate_reduction(tranches, loss, bands)
    if excess > 1e-6:
        raise ValueError(f"Ordinary loss exceeds eligible tranche capacity by {excess:,.2f}")
    return balances


def allocate_writeups(tranches: list[Tranche], recovery: float) -> tuple[list[float], list[float], float]:
    """Restore prior write-downs top-down, capped by each class's loss history.

    Returns ``(new_balances, writeups, unused_recovery)``.  The caller supplies
    cumulative write-down state; recovery that exceeds prior write-downs remains
    unused rather than inflating a class above its original/current entitlement.
    """
    remaining = _validate_amount(recovery, "recovery")
    balances = [float(t.balance) for t in tranches]
    writeups = [0.0] * len(tranches)
    by_name = _index(tranches)
    bands = _deal_bands_or_generic(tranches, WRITEUP_BANDS, reverse=False)
    for band in bands:
        ids = [by_name[name] for name in band if name in by_name]
        capacity = sum(float(tranches[i].cumulative_writedown) for i in ids)
        give = min(remaining, capacity)
        if give > 0 and capacity > 0:
            for i in ids:
                share = give * tranches[i].cumulative_writedown / capacity
                balances[i] += share
                writeups[i] += share
        remaining -= give
        if remaining <= 1e-7:
            remaining = 0.0
            break
    return balances, writeups, remaining


def _allocate_principal_bands(
    tranches: Sequence[Tranche], amount: float, bands: Sequence[tuple[str, ...]]
) -> tuple[list[float], float]:
    _, paid, remaining = _allocate_reduction(tranches, amount, bands)
    return paid, remaining


def allocate_principal(
    tranches: list[Tranche], principal: float, triggers_pass: bool,
    *, pool_balance: float | None = None, recovery_principal: float = 0.0,
    a1_priority: bool = False, a1_scheduled_amount: float = 0.0,
) -> list[float]:
    """Allocate principal using the senior/subordinate trigger gate.

    When ``pool_balance`` is supplied, the senior percentage is calculated from
    A-H and the A-1 pair.  If triggers fail, all principal is senior.  This
    primitive excludes A-1 scheduled/supplemental reductions; ``run`` applies
    the scheduled A-1 amount before the remaining senior bucket.
    """
    stated = _validate_amount(principal, "principal")
    recovery = _validate_amount(recovery_principal, "recovery_principal")
    by_name = _index(tranches)
    real_deal = {"A-H", "A-1", "A-1H"}.issubset(by_name)
    if not real_deal:
        bands = tuple((t.name,) for t in (tranches if not triggers_pass else reversed(tranches)))
        paid, excess = _allocate_principal_bands(tranches, stated + recovery, bands)
        if excess > 1e-6:
            raise ValueError("Principal exceeds outstanding tranche balance")
        return paid

    if pool_balance is None or pool_balance <= 0:
        raise ValueError("pool_balance is required for the STACR principal split")
    # The PPM Senior Percentage includes A-H and the A-1/A-1H band.
    # At closing it is 96.475%, leaving the 3.525% subordinate percentage.
    senior_balance = sum(tranches[by_name[n]].balance for n in ("A-H", "A-1", "A-1H"))
    senior_pct = min(max(senior_balance / float(pool_balance), 0.0), 1.0)
    senior_amount = stated + recovery if not triggers_pass else senior_pct * stated + recovery
    subordinate_amount = stated + recovery - senior_amount

    # The fixed A-1 amount is the first use of the Senior Reduction Amount; it
    # must not be removed from total principal before the senior/sub split.
    scheduled_request = _validate_amount(a1_scheduled_amount, "a1_scheduled_amount")
    scheduled_amount = min(scheduled_request, senior_amount)
    scheduled_paid, scheduled_excess = _allocate_principal_bands(
        tranches, scheduled_amount, (("A-1", "A-1H"),)
    )
    scheduled_used = scheduled_amount - scheduled_excess
    after_schedule = [
        replace(t, balance=t.balance - scheduled_paid[i]) for i, t in enumerate(tranches)
    ]

    senior_bands = POST_36_SENIOR_PRINCIPAL_BANDS if a1_priority else SENIOR_PRINCIPAL_BANDS
    senior_paid, senior_excess = _allocate_principal_bands(
        after_schedule, senior_amount - scheduled_used, senior_bands
    )
    senior_paid = [a + b for a, b in zip(scheduled_paid, senior_paid)]
    interim = [replace(t, balance=t.balance - senior_paid[i]) for i, t in enumerate(tranches)]
    sub_paid, sub_excess = _allocate_principal_bands(
        interim, subordinate_amount, SUBORDINATE_PRINCIPAL_BANDS
    )
    if senior_excess + sub_excess > 1e-5:
        raise ValueError("Principal exceeds outstanding tranche balance")
    return [a + b for a, b in zip(senior_paid, sub_paid)]


def allocate_modification_loss(
    tranches: Sequence[Tranche], gross_interest: Sequence[float], amount: float,
) -> tuple[list[float], list[float], list[float], float]:
    """Allocate an aggregate rate-modification loss under the PPM priority.

    The collateral model's ``modification_losses`` field is specifically the
    current-month interest lost from rate cuts. The PPM nevertheless lets that
    amount exhaust deemed/current interest and then principal in a prescribed
    order. Interest capacity includes Freddie's H pieces and B-1H/B-2H deemed
    interest; only offered-note reductions affect investor cash interest.

    Returns ``(interest_reductions, principal_reductions, balances, excess)``.
    """
    remaining = _validate_amount(amount, "modification_loss")
    interest_capacity = np.asarray(gross_interest, dtype=float).copy()
    if interest_capacity.shape != (len(tranches),) or not np.isfinite(interest_capacity).all():
        raise ValueError("gross_interest must contain one finite amount per tranche")
    if (interest_capacity < -1e-8).any():
        raise ValueError("gross_interest cannot be negative")
    interest_capacity = np.maximum(interest_capacity, 0.0)
    balances = np.asarray([t.balance for t in tranches], dtype=float)
    interest_reduction = np.zeros(len(tranches))
    principal_reduction = np.zeros(len(tranches))
    by_name = _index(tranches)

    for amount_type, band in MODIFICATION_LOSS_PRIORITY:
        ids = [by_name[name] for name in band if name in by_name]
        capacity_vector = interest_capacity if amount_type == "interest" else balances
        capacity = float(capacity_vector[ids].sum())
        take = min(remaining, capacity)
        if take > 0 and capacity > 0:
            allocation = take * capacity_vector[ids] / capacity
            capacity_vector[ids] -= allocation
            target = interest_reduction if amount_type == "interest" else principal_reduction
            target[ids] += allocation
        remaining -= take
        if remaining <= 1e-7:
            remaining = 0.0
            break
    return (
        interest_reduction.tolist(), principal_reduction.tolist(),
        balances.tolist(), remaining,
    )


def cumulative_loss_limit(payment_number: int) -> float:
    """PPM cumulative-net-loss schedule as a fraction of cut-off balance."""
    if payment_number < 1:
        raise ValueError("payment_number must be positive")
    # 0.10% in year 1, +0.10% each deal year, capped at 1.30%.
    deal_year = (payment_number - 1) // 12 + 1
    return min(deal_year * 0.001, 0.013)


def trigger_results(
    tranches: Sequence[Tranche], pool_balance: float, cumulative_net_loss: float,
    distressed_history: Sequence[float], current_principal_loss: float,
    payment_number: int,
) -> dict[str, bool | float]:
    """Calculate the three subordinate-principal tests and A-1 CNL test."""
    by_name = _index(tranches)
    senior = sum(tranches[by_name[n]].balance for n in ("A-H", "A-1", "A-1H"))
    if pool_balance <= 0:
        raise ValueError("pool_balance must be positive")
    subordinate_pct = max(0.0, 1.0 - senior / pool_balance)
    history = list(distressed_history)[-6:]
    avg_distressed = float(np.mean(history)) if history else 0.0
    delinquency_threshold = 0.5 * max(subordinate_pct * pool_balance - current_principal_loss, 0.0)
    minimum_ce = subordinate_pct + 1e-12 >= MIN_SUBORDINATE_PCT
    cnl = cumulative_net_loss / CUTOFF_BALANCE <= cumulative_loss_limit(payment_number) + 1e-12
    delinquency = avg_distressed < delinquency_threshold if delinquency_threshold > 0 else avg_distressed == 0
    return {
        "minimum_ce": minimum_ce,
        "cumulative_loss": cnl,
        "delinquency": delinquency,
        "all_pass": minimum_ce and cnl and delinquency,
        "a1_cnl": cumulative_net_loss / CUTOFF_BALANCE <= A1_CNL_LIMIT + 1e-12,
        "subordinate_pct": subordinate_pct,
        "six_month_avg_distressed": avg_distressed,
        "delinquency_threshold": delinquency_threshold,
    }


def a1_scheduled_reduction(payment_number: int, original_band_balance: float) -> float:
    """Scheduled A-1/A-1H fast-pay amount before other senior allocation."""
    if 1 <= payment_number <= 12:
        return 0.0375 * original_band_balance
    if 13 <= payment_number <= 36:
        return 0.015 * original_band_balance
    return 0.0


def _apply_state(
    tranches: list[Tranche], balances: Sequence[float],
    *, writedowns: Sequence[float] | None = None, writeups: Sequence[float] | None = None,
) -> list[Tranche]:
    result: list[Tranche] = []
    for i, tranche in enumerate(tranches):
        cumulative = tranche.cumulative_writedown
        if writedowns is not None:
            cumulative += writedowns[i]
        if writeups is not None:
            cumulative = max(0.0, cumulative - writeups[i])
        result.append(replace(tranche, balance=max(0.0, balances[i]), cumulative_writedown=cumulative))
    return result


def _coerce_pool_cf(pool_cf: pd.DataFrame) -> pd.DataFrame:
    required = {
        "beginning_balance", "scheduled_principal", "prepayments", "losses",
        "recoveries", "ending_balance", "modification_losses", "distressed_balance",
    }
    missing = required - set(pool_cf.columns)
    if missing:
        raise ValueError(f"Pool cash flow is missing columns: {sorted(missing)}")
    frame = pool_cf.copy().reset_index(drop=True)
    if "defaults" not in frame:
        frame["defaults"] = 0.0
    if "month" not in frame:
        frame["month"] = np.arange(1, len(frame) + 1)
    if "date" in frame:
        frame["date"] = pd.to_datetime(frame["date"])
    numeric = required | {"defaults"}
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if (~np.isfinite(frame[column]) | (frame[column] < -1e-8)).any():
            raise ValueError(f"Pool cash-flow column {column!r} must be finite and non-negative")
    expected_ending = (
        frame["beginning_balance"] - frame["scheduled_principal"]
        - frame["prepayments"] - frame["defaults"]
    )
    tolerance = np.maximum(1.0, frame["beginning_balance"].to_numpy() * 1e-9)
    if (np.abs(expected_ending - frame["ending_balance"]) > tolerance).any():
        raise ValueError("Pool cash-flow balance roll-forward does not reconcile")
    if len(frame) > 1:
        prior_ending = frame["ending_balance"].iloc[:-1].to_numpy()
        next_beginning = frame["beginning_balance"].iloc[1:].to_numpy()
        if (np.abs(prior_ending - next_beginning) > np.maximum(1.0, prior_ending * 1e-9)).any():
            raise ValueError("Pool cash-flow months do not link beginning to prior ending balance")
    return frame


def run(
    tranches: list[Tranche], pool_cf: pd.DataFrame, *,
    sofr: Sequence[float] | None = None, dates: Sequence[pd.Timestamp] | None = None,
    accrual_days: Sequence[float] | None = None, call_date: pd.Timestamp | None = CALL_DATE,
    starting_payment_number: int = 1, allow_inconsistent_initial_state: bool = False,
    initial_cumulative_loss: float = 0.0,
    initial_distressed_history: Sequence[float] = (),
    a1_cnl_ever_failed: bool = False,
) -> dict[str, pd.DataFrame]:
    """Run pool cash flows through the implemented monthly waterfall.

    ``sofr`` must be decimal (0.04 means 4%).  The function deliberately raises
    when the first pool balance does not match the supplied tranche state, unless
    the caller explicitly overrides the guard for a labeled demonstration.

    The upstream ``modification_losses`` field is defined as current-month
    interest lost from rate modifications and is allocated through the PPM's
    special interest-first priority. Principal forbearance and modification
    gains would require separate inputs and are not present in this handoff.
    """
    cf = _coerce_pool_cf(pool_cf)
    state = copy_tranches(tranches)
    n = len(cf)
    first_pool = float(cf.loc[0, "beginning_balance"]) if n else 0.0
    state_total = sum(t.balance for t in state)
    if n and not allow_inconsistent_initial_state and abs(first_pool - state_total) > max(1.0, first_pool * 1e-8):
        raise ValueError(
            "Pool beginning balance does not match supplied tranche state. "
            "Provide current class balances or run a consistent closing-date demonstration."
        )
    sofr_values = np.zeros(n) if sofr is None else np.asarray(sofr, dtype=float)
    if len(sofr_values) != n or ((sofr_values < -0.10) | (sofr_values > 1.0)).any():
        raise ValueError("sofr must contain one decimal rate per pool-cash-flow row")
    if dates is None:
        date_values = pd.date_range("2000-01-01", periods=n, freq="MS") + pd.Timedelta(days=24)
    else:
        date_values = pd.DatetimeIndex(pd.to_datetime(dates))
        if len(date_values) != n:
            raise ValueError("dates length must match pool cash flows")
    days = np.full(n, 30.0) if accrual_days is None else np.asarray(accrual_days, dtype=float)
    if len(days) != n or (days <= 0).any():
        raise ValueError("accrual_days must contain one positive value per month")

    outputs = {t.name: [] for t in state}
    distressed_history = [
        _validate_amount(value, "initial_distressed_history")
        for value in initial_distressed_history
    ][-6:]
    cumulative_loss = _validate_amount(initial_cumulative_loss, "initial_cumulative_loss")
    a1_failed = bool(a1_cnl_ever_failed)
    original_a1_band = sum(t.original_balance for t in state if t.name in ("A-1", "A-1H"))

    for row_number, row in cf.iterrows():
        payment_number = starting_payment_number + row_number
        beginning = [t.balance for t in state]
        interest_entitlement = [
            t.balance * max(sofr_values[row_number] + t.spread_bps / 10_000, 0.0)
            * days[row_number] / 360 if t.spread_bps else 0.0
            for t in state
        ]
        gross_interest = [amount if t.offered else 0.0 for amount, t in zip(interest_entitlement, state)]
        loss = _validate_amount(row.losses, "losses")
        modification_loss = _validate_amount(row.modification_losses, "modification_losses")
        recovery = _validate_amount(row.recoveries, "recoveries")
        credit_event_amount = _validate_amount(row.defaults, "defaults")
        distressed_history.append(_validate_amount(row.distressed_balance, "distressed_balance"))

        # PPM p. 196: write-down and write-up amounts are the net of the
        # Principal Loss Amount and the Principal Recovery Amount.
        net_writedown = max(loss - recovery, 0.0)
        net_writeup = max(recovery - loss, 0.0)
        loss_bands = _deal_bands_or_generic(state, LOSS_BANDS, reverse=True)
        loss_balances, writedowns, excess_loss = _allocate_reduction(state, net_writedown, loss_bands)
        if excess_loss > 1e-5:
            raise ValueError("Ordinary loss exhausted all eligible tranches")
        state = _apply_state(state, loss_balances, writedowns=writedowns)

        modification_interest, modification_principal, modification_balances, excess_modification = (
            allocate_modification_loss(state, interest_entitlement, modification_loss)
        )
        if excess_modification > 1e-5:
            raise ValueError("Modification loss exhausted all eligible interest and principal")
        state = _apply_state(state, modification_balances, writedowns=modification_principal)
        total_writedowns = [a + b for a, b in zip(writedowns, modification_principal)]
        interest = [
            max(0.0, gross_interest[i] - modification_interest[i])
            for i in range(len(state))
        ]

        writeup_balances, writeups, _ = allocate_writeups(state, net_writeup)
        state = _apply_state(state, writeup_balances, writeups=writeups)

        # Cumulative Net Loss Percentage (PPM p. 172) counts the Principal Loss
        # Amount, which includes only the principal-type modification priorities.
        cumulative_loss = max(
            0.0, cumulative_loss + loss + sum(modification_principal) - recovery
        )

        if {"A-H", "A-1", "A-1H"}.issubset(_index(state)):
            triggers = trigger_results(
                state, float(row.beginning_balance), cumulative_loss, distressed_history,
                current_principal_loss=loss, payment_number=payment_number,
            )
        else:
            # Toy structures exercise generic allocation primitives without
            # pretending to reproduce STACR-specific trigger definitions.
            triggers = {
                "minimum_ce": True, "cumulative_loss": True,
                "delinquency": True, "all_pass": True, "a1_cnl": True,
            }
        a1_failed = a1_failed or not bool(triggers["a1_cnl"])

        stated_principal = _validate_amount(row.scheduled_principal, "scheduled_principal") + _validate_amount(row.prepayments, "prepayments")
        # PPM p. 190: Recovery Principal is the Credit Event Amount (defaulted
        # UPB) in excess of the Tranche Write-down Amount, plus any write-up.
        recovery_principal = max(credit_event_amount - net_writedown, 0.0) + net_writeup
        principal_paid = [0.0] * len(state)
        if stated_principal + recovery_principal > 1e-8:
            scheduled = (
                a1_scheduled_reduction(payment_number, original_a1_band)
                if not a1_failed else 0.0
            )
            residual_paid = allocate_principal(
                state, stated_principal, bool(triggers["all_pass"]),
                pool_balance=float(row.beginning_balance), recovery_principal=recovery_principal,
                a1_priority=payment_number >= 37 and not a1_failed,
                a1_scheduled_amount=scheduled,
            )
            principal_paid = [a + b for a, b in zip(principal_paid, residual_paid)]
            state = [replace(t, balance=max(0.0, t.balance - residual_paid[i])) for i, t in enumerate(state)]

        called = bool(call_date is not None and date_values[row_number] >= pd.Timestamp(call_date))
        if called:
            for i, tranche in enumerate(state):
                principal_paid[i] += tranche.balance
                state[i] = replace(tranche, balance=0.0)

        for i, tranche in enumerate(state):
            outputs[tranche.name].append({
                "month": int(row.month), "date": date_values[row_number],
                "beginning_balance": beginning[i], "gross_interest": gross_interest[i],
                "modification_interest_loss": modification_interest[i], "interest": interest[i],
                "principal": principal_paid[i], "ordinary_writedown": writedowns[i],
                "modification_principal_loss": modification_principal[i],
                "writedown": total_writedowns[i],
                "writeup": writeups[i], "ending_balance": tranche.balance,
                "minimum_ce_test": bool(triggers["minimum_ce"]),
                "cumulative_loss_test": bool(triggers["cumulative_loss"]),
                "delinquency_test": bool(triggers["delinquency"]),
                "all_triggers_pass": bool(triggers["all_pass"]),
                "a1_cnl_test": not a1_failed, "called": called,
            })
        if called:
            break

    return {name: pd.DataFrame(rows) for name, rows in outputs.items()}
