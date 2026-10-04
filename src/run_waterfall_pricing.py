"""Run the STACR waterfall and pricing handoff for every team scenario.

Usage from the repository root::

    python -m src.run_waterfall_pricing

The command reads Haocheng's pool cash flows and Coco's rate paths, writes one
long-form tranche cash-flow file per scenario, and creates a compact offered-
class summary. Prices are scenario PVs at explicit discount-margin assumptions;
they are not represented as observed market prices.
"""
from __future__ import annotations

from pathlib import Path
import warnings

import pandas as pd

from src.pricing import price, weighted_average_life
from src.waterfall import MIN_SUBORDINATE_PCT, current_tranches, run


SCENARIOS = ("good", "base", "moderate", "severe")
OFFERED_CLASSES = ("A-1", "M-1", "M-2A", "M-2B")
VALUATION_DATE = pd.Timestamp("2026-10-03")
STARTING_PAYMENT_NUMBER = 8
DM_GRID_BPS = (0.0, 100.0, 200.0)

# Deal history through the September 2026 payment, from Bloomberg CLP
# (STACR_2026-DNA1_Bloomberg_CLP_2026-10-02.xlsx). Cumulative defaults are 0%, so no
# losses have been allocated. Distressed Principal Balance is approximated as the
# "Delinq. 60+ %" row (which includes bankruptcy, foreclosure and REO) times the pool
# balance; recently modified loans are reported only as counts and are omitted.
INITIAL_CUMULATIVE_LOSS = 0.0
CLP_HISTORY = (  # (payment month, pool balance in $, 60+ delinquent share)
    ("2026-04", 20_711_669_000.0, 0.0009),
    ("2026-05", 20_242_474_000.0, 0.0012),
    ("2026-06", 19_937_098_000.0, 0.0015),
    ("2026-07", 19_675_126_000.0, 0.0021),
    ("2026-08", 19_443_047_000.0, 0.0025),
    ("2026-09", 19_254_308_000.0, 0.0029),
)
INITIAL_DISTRESSED_HISTORY = tuple(balance * share for _, balance, share in CLP_HISTORY)


def _load_inputs(pool_path: Path, rates_path: Path, scenario: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    pool = pd.read_csv(pool_path)
    rates = pd.read_csv(rates_path)
    rates = rates.loc[rates["scenario"] == scenario].copy().sort_values("month")
    if rates.empty:
        raise ValueError(f"No pricing-rate rows found for scenario {scenario!r}")
    if pool["month"].tolist() != rates["month"].tolist():
        raise ValueError(f"Pool and pricing months do not align for scenario {scenario!r}")
    return pool, rates


def run_scenario(pool: pd.DataFrame, rates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return long-form tranche cash flows and offered-class metrics."""
    scenario = str(rates["scenario"].iloc[0])
    state = current_tranches()
    starting_face = {t.name: t.balance for t in state}
    spreads = {t.name: t.spread_bps for t in state}
    senior = sum(starting_face[n] for n in ("A-H", "A-1", "A-1H"))
    starting_subordinate_pct = 1.0 - senior / float(pool["beginning_balance"].iloc[0])
    if starting_subordinate_pct < MIN_SUBORDINATE_PCT:
        # The Bloomberg pool tape and the Bloomberg PDI class factors must
        # describe the same payment date; otherwise the A-H residual distorts
        # the Minimum Credit Enhancement Test from the first projected month.
        warnings.warn(
            f"{scenario}: starting Subordinate Percentage {starting_subordinate_pct:.4%} "
            f"is below {MIN_SUBORDINATE_PCT:.3%}; check that the pool balance and "
            "class balances are as of the same payment date",
            stacklevel=2,
        )
    outputs = run(
        state,
        pool,
        sofr=rates["sofr_coupon_decimal"].to_numpy(float),
        dates=pd.to_datetime(rates["date"]),
        accrual_days=rates["coupon_accrual_days"].to_numpy(float),
        starting_payment_number=STARTING_PAYMENT_NUMBER,
        initial_cumulative_loss=INITIAL_CUMULATIVE_LOSS,
        initial_distressed_history=INITIAL_DISTRESSED_HISTORY,
    )

    cashflows = pd.concat(
        [frame.assign(tranche=name) for name, frame in outputs.items()],
        ignore_index=True,
    )
    cashflows.insert(0, "scenario", scenario)

    summary_rows = []
    discount_days = rates["discount_days"].to_numpy(float)
    sofr = rates["sofr_coupon_decimal"].to_numpy(float)
    for name in OFFERED_CLASSES:
        frame = outputs[name]
        face = starting_face[name]
        total_per_100 = (frame["interest"] + frame["principal"]).to_numpy(float) / face * 100.0
        principal = frame["principal"].to_numpy(float)
        row = {
            "scenario": scenario,
            "tranche": name,
            "starting_balance": face,
            "coupon_spread_bps": spreads[name],
            "starting_subordinate_pct": starting_subordinate_pct,
            "total_interest": frame["interest"].sum(),
            "total_principal": principal.sum(),
            "total_writedown": frame["writedown"].sum(),
            "wal_years": weighted_average_life(principal, discount_days),
            "first_trigger_failure_month": (
                int(frame.loc[~frame["all_triggers_pass"], "month"].iloc[0])
                if (~frame["all_triggers_pass"]).any() else pd.NA
            ),
            "final_payment_month": int(frame.loc[frame["principal"] > 0, "month"].iloc[-1]),
        }
        for dm in DM_GRID_BPS:
            row[f"price_at_{int(dm)}bp_dm"] = price(total_per_100, sofr, dm, discount_days)
        row["price_at_coupon_spread_dm"] = price(
            total_per_100, sofr, spreads[name], discount_days
        )
        summary_rows.append(row)
    return cashflows, pd.DataFrame(summary_rows)


def run_all(
    project_root: Path | str = Path("."), *, write_outputs: bool = True,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Run all four scenarios using the repository's agreed input locations."""
    root = Path(project_root)
    rates_path = root / "data/scenarios/pricing_rates.csv"
    cashflow_outputs: dict[str, pd.DataFrame] = {}
    summaries = []
    for scenario in SCENARIOS:
        pool_path = root / f"outputs/tables/pool_cf_{scenario}.csv"
        pool, rates = _load_inputs(pool_path, rates_path, scenario)
        cashflows, summary = run_scenario(pool, rates)
        cashflow_outputs[scenario] = cashflows
        summaries.append(summary)

    summary_all = pd.concat(summaries, ignore_index=True)
    if write_outputs:
        output_dir = root / "outputs/tables"
        output_dir.mkdir(parents=True, exist_ok=True)
        for scenario, frame in cashflow_outputs.items():
            frame.to_csv(output_dir / f"waterfall_cf_{scenario}.csv", index=False)
        pd.concat(cashflow_outputs.values(), ignore_index=True).to_csv(
            output_dir / "waterfall_cashflows_all.csv", index=False
        )
        summary_all.to_csv(output_dir / "tranche_pricing_summary.csv", index=False)
    return cashflow_outputs, summary_all


def main() -> None:
    _, summary = run_all()
    display = summary[
        ["scenario", "tranche", "wal_years", "coupon_spread_bps",
         "price_at_coupon_spread_dm", "total_writedown"]
    ].copy()
    print(display.to_string(index=False, float_format=lambda value: f"{value:,.4f}"))
    print("\nWrote scenario and consolidated waterfall cash flows plus tranche_pricing_summary.csv to outputs/tables/")


if __name__ == "__main__":
    main()
