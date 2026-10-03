# Handoff: collateral cash flows for the waterfall (Reza → Smarajit)

## Files

| What | Where |
|---|---|
| Monthly pool cash flows, one file per scenario | `outputs/tables/pool_cf_{good,base,moderate,severe}.csv` (same data as `outputs/pool_cf_*.parquet`) |
| Scenario summary (CPR, end balance, losses) | `outputs/tables/scenario_summary.csv` |
| SOFR coupons and discount factors (Coco) | `data/scenarios/pricing_rates.csv` |
| Scenario paths (Coco) | `data/scenarios/scenarios.csv` |
| How the numbers are produced | `notebooks/03_collateral_projection.ipynb`, `notebooks/08_export_results.ipynb` |

Regenerate everything with `python -m src.export_results` after any input changes.

## `pool_cf_<scenario>.csv` columns (all amounts in $, reference pool level)

| Column | Meaning | Use in the waterfall |
|---|---|---|
| `month` | 1–53; month *t* is the payment date in row *t* of `pricing_rates.csv` (month 1 = 2026-10-25, month 53 = 2031-02-25 call) | join key with `pricing_rates.csv` |
| `beginning_balance` / `ending_balance` | reference pool UPB (performing + loans in the liquidation pipeline) | Senior Percentage, 10% clean-up test |
| `scheduled_principal` | contractual amortization | part of Stated Principal |
| `prepayments` | voluntary prepayments (payoffs + curtailments) | part of Stated Principal |
| `defaults` | UPB removed by **credit events** this month | not principal to the notes |
| `losses` | actual loss on those credit events (UPB + missed interest + costs − proceeds − MI) | Principal Loss Amount → write-downs, bottom up |
| `recoveries` | always 0 (not modeled) | write-ups |
| `modification_losses` | interest lost on modified loans | modification loss allocation (interest first, PPM p. 84-85) |
| `distressed_balance` | 60+ dq / FC / REO in the pipeline + loans modified in the last 12 months | Delinquency Test (6-month average) |

Identity each month: `ending = beginning − scheduled_principal − prepayments − defaults`.
Cumulative net loss for the triggers = cumulative `losses` / cut-off balance **$22,781,151,551.84**.

## Scenarios (Coco, as of 2026-10-03)

| | mortgage rate month 12 → 53 | HPI by 2031 | loss % of cut-off |
|---|---|---|---|
| good | 6.70% → 5.67% | +32% | 0.193% |
| base | 6.74% → 5.79% | +22% | 0.210% |
| moderate | 7.14% → 5.90% | −14% | 0.289% |
| severe | 7.09% → 5.39% | −21% | 0.358% |

Losses reach B-2H only in moderate and severe; A-1, M-1 and M-2 take no write-downs in any scenario.

## Watch out for

1. **SOFR falls to 0% in moderate and severe.** Those paths replay 2006–2011, so `sofr_coupon_decimal` in `pricing_rates.csv` is zero from month 21 (severe) and month 37 (moderate) onward. Note coupons (SOFR + spread, 0% floor on SOFR) drop to roughly the spread.
2. **Month 1 is a 22-day stub** (2026-10-03 → 2026-10-25). `pricing_rates.csv` uses 22 discount days for month 1 (coupon accrual is the full 30 days from 2026-09-25). The collateral model treats month 1 as a full month, so month-1 prepayments and defaults are about 8 days' worth too high.
3. **Pool balance vs cut-off.** Projections start from today's tape ($19.44bn); deal ratios (attachment points, cumulative loss tests) use the $22.78bn cut-off balance.
4. **Discount factors** are the scenario's own SOFR path with no credit spread (`physical_scenario_overnight_no_credit_spread`). Add the tranche spread or solve for the discount margin on top.
