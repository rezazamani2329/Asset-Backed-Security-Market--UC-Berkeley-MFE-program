"""Hand-checkable tests for the STACR waterfall primitives."""
import numpy as np
import pandas as pd
import pytest

from src.waterfall import (
    CUTOFF_BALANCE, CURRENT_BALANCES, CURRENT_POOL_BALANCE, TRANCHES, Tranche, a1_scheduled_reduction,
    allocate_losses, allocate_principal, allocate_writeups, copy_tranches,
    cumulative_loss_limit, current_tranches, run, trigger_results,
)


def toy_structure():
    return [
        Tranche("Senior", 900.0, offered=False),
        Tranche("M-1", 50.0, offered=True),
        Tranche("M-2", 30.0, offered=True),
        Tranche("B", 20.0, offered=False),
    ]


def test_loss_wipes_b_and_half_of_m2():
    assert allocate_losses(toy_structure(), 35.0) == pytest.approx([900.0, 50.0, 15.0, 0.0])


def test_zero_loss_changes_nothing_and_does_not_mutate():
    tranches = toy_structure()
    assert allocate_losses(tranches, 0.0) == pytest.approx([900.0, 50.0, 30.0, 20.0])
    assert [t.balance for t in tranches] == pytest.approx([900.0, 50.0, 30.0, 20.0])


def test_negative_loss_rejected():
    with pytest.raises(ValueError):
        allocate_losses(toy_structure(), -1.0)


def test_real_pair_shares_loss_pro_rata():
    tranches = copy_tranches(TRANCHES)
    b3 = next(t.balance for t in tranches if t.name == "B-3H")
    b2 = next(t.balance for t in tranches if t.name == "B-2H")
    b1 = next(t.balance for t in tranches if t.name == "B-1H")
    pair_loss = 10_000_000.0
    result = allocate_losses(tranches, b3 + b2 + b1 + pair_loss)
    by_name = {t.name: result[i] for i, t in enumerate(tranches)}
    m2b = next(t for t in tranches if t.name == "M-2B")
    m2bh = next(t for t in tranches if t.name == "M-2BH")
    pair_total = m2b.balance + m2bh.balance
    assert m2b.balance - by_name["M-2B"] == pytest.approx(pair_loss * m2b.balance / pair_total)
    assert m2bh.balance - by_name["M-2BH"] == pytest.approx(pair_loss * m2bh.balance / pair_total)


def test_writeup_is_top_down_and_capped():
    tranches = [
        Tranche("Senior", 80.0, False, original_balance=100.0, cumulative_writedown=20.0),
        Tranche("Junior", 40.0, False, original_balance=50.0, cumulative_writedown=10.0),
    ]
    balances, writeups, unused = allocate_writeups(tranches, 25.0)
    assert balances == pytest.approx([100.0, 45.0])
    assert writeups == pytest.approx([20.0, 5.0])
    assert unused == pytest.approx(0.0)


def test_generic_principal_direction_depends_on_trigger():
    assert allocate_principal(toy_structure(), 25.0, True) == pytest.approx([0, 0, 5, 20])
    assert allocate_principal(toy_structure(), 25.0, False) == pytest.approx([25, 0, 0, 0])


def test_cumulative_loss_schedule():
    assert cumulative_loss_limit(1) == pytest.approx(0.001)
    assert cumulative_loss_limit(13) == pytest.approx(0.002)
    assert cumulative_loss_limit(145) == pytest.approx(0.013)
    assert cumulative_loss_limit(300) == pytest.approx(0.013)


def test_a1_reduction_schedule():
    assert a1_scheduled_reduction(1, 100.0) == pytest.approx(3.75)
    assert a1_scheduled_reduction(12, 100.0) == pytest.approx(3.75)
    assert a1_scheduled_reduction(13, 100.0) == pytest.approx(1.5)
    assert a1_scheduled_reduction(36, 100.0) == pytest.approx(1.5)
    assert a1_scheduled_reduction(37, 100.0) == 0.0


def test_initial_trigger_state_passes_with_zero_distress():
    result = trigger_results(TRANCHES, CUTOFF_BALANCE, 0.0, [0.0], 0.0, 1)
    assert result["minimum_ce"]
    assert result["cumulative_loss"]
    assert result["delinquency"]
    assert result["all_pass"]


def test_current_balances_reconcile_and_use_september_m1_factor():
    assert sum(CURRENT_BALANCES.values()) == pytest.approx(CURRENT_POOL_BALANCE, abs=0.02)
    state = current_tranches()
    assert sum(t.balance for t in state) == pytest.approx(CURRENT_POOL_BALANCE, abs=0.02)
    m1 = next(t for t in state if t.name == "M-1")
    m1h = next(t for t in state if t.name == "M-1H")
    assert m1.balance / m1.original_balance == pytest.approx(0.571984481, abs=1e-10)
    assert m1h.balance / m1h.original_balance == pytest.approx(0.571984481, abs=1e-9)


def test_real_principal_split_and_pairing_when_triggers_pass():
    paid = allocate_principal(
        copy_tranches(TRANCHES), 100_000_000.0, True,
        pool_balance=CUTOFF_BALANCE,
    )
    by_name = {t.name: paid[i] for i, t in enumerate(TRANCHES)}
    assert sum(paid) == pytest.approx(100_000_000.0)
    # Initial senior percentage is 96.475%; subordinate principal starts at M-1.
    senior_balance = sum(t.balance for t in TRANCHES if t.name in ("A-H", "A-1", "A-1H"))
    senior_amount = 100_000_000.0 * senior_balance / CUTOFF_BALANCE
    assert by_name["A-H"] == pytest.approx(senior_amount)
    assert by_name["M-1"] + by_name["M-1H"] == pytest.approx(100_000_000.0 - senior_amount)
    assert by_name["M-1"] / by_name["M-1H"] == pytest.approx(
        TRANCHES[3].balance / TRANCHES[4].balance
    )


def test_run_refuses_current_pool_with_original_tranches():
    pool = pd.DataFrame({
        "month": [1], "beginning_balance": [19_443_046_983.78],
        "scheduled_principal": [10.0], "prepayments": [20.0], "losses": [0.0],
        "recoveries": [0.0], "ending_balance": [19_443_046_953.78],
        "modification_losses": [0.0], "distressed_balance": [0.0],
    })
    with pytest.raises(ValueError, match="current class balances"):
        run(TRANCHES, pool)


def test_run_one_consistent_toy_month_reconciles():
    tranches = toy_structure()
    pool = pd.DataFrame({
        "month": [1], "beginning_balance": [1000.0],
        "scheduled_principal": [5.0], "prepayments": [5.0], "losses": [35.0],
        "defaults": [35.0],
        "recoveries": [0.0], "ending_balance": [955.0],
        "modification_losses": [0.0], "distressed_balance": [0.0],
    })
    out = run(tranches, pool, sofr=[0.04], dates=["2026-10-25"], call_date=None)
    assert out["B"].loc[0, "writedown"] == pytest.approx(20.0)
    assert out["M-2"].loc[0, "writedown"] == pytest.approx(15.0)
    # Generic trigger-pass principal pays junior first.
    assert sum(frame.loc[0, "principal"] for frame in out.values()) == pytest.approx(10.0)


def test_nonzero_modification_losses_are_not_silently_misallocated():
    pool = pd.DataFrame({
        "month": [1], "beginning_balance": [1000.0],
        "scheduled_principal": [0.0], "prepayments": [0.0], "losses": [0.0],
        "recoveries": [0.0], "ending_balance": [1000.0],
        "modification_losses": [1.0], "distressed_balance": [0.0],
    })
    with pytest.raises(NotImplementedError, match="modification losses"):
        run(toy_structure(), pool)


def test_pool_balance_must_reconcile():
    pool = pd.DataFrame({
        "month": [1], "beginning_balance": [1000.0],
        "scheduled_principal": [10.0], "prepayments": [20.0], "defaults": [30.0],
        "losses": [5.0], "recoveries": [0.0], "ending_balance": [999.0],
        "modification_losses": [0.0], "distressed_balance": [0.0],
    })
    with pytest.raises(ValueError, match="roll-forward"):
        run(toy_structure(), pool)
