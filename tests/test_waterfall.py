"""Hand-checkable waterfall tests. Remove the skip marks once allocate_losses exists."""
import pytest
from src.waterfall import Tranche, allocate_losses


def toy_structure():
    # Illustrative stack (NOT the real deal), senior -> junior
    return [
        Tranche("Senior", 900.0, offered=False),
        Tranche("M-1",     50.0, offered=True),
        Tranche("M-2",     30.0, offered=True),
        Tranche("B",       20.0, offered=False),
    ]


@pytest.mark.skip(reason="implement allocate_losses first")
def test_loss_wipes_b_and_half_of_m2():
    # Loss = all of B (20) + half of M-2 (15) = 35
    assert allocate_losses(toy_structure(), 35.0) == pytest.approx([900.0, 50.0, 15.0, 0.0])


@pytest.mark.skip(reason="implement allocate_losses first")
def test_zero_loss_changes_nothing():
    assert allocate_losses(toy_structure(), 0.0) == pytest.approx([900.0, 50.0, 30.0, 20.0])
