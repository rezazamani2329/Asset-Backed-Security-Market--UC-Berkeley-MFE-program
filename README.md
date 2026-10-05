# Pricing GSE Credit Risk Transfer Notes — STACR 2026-DNA1

UC Berkeley MFE · MFE230M Asset Securitization (ABSM) · Fall 2026 · Final Project, **Track 2**
**Instructor:** Professor Nancy Wallace, UC Berkeley Haas School of Business

## Objective
Analyze and price Freddie Mac STACR 2026-DNA1 (classes A-1, M-1, M-2) from the
perspective of a consultant advising prospective investors.

| Class | Original | Current (Sept 2026) | Spread (SOFR +) | Rule 144A CUSIP | Reg S CUSIP |
|---|---|---|---|---|---|
| A-1  | $275.9mm | $203.5mm | 85 bp  | 35564UCQ8 | U3202CCQ1 |
| M-1  | $275.9mm | $157.8mm | 100 bp | 35564UCR6 | U3202CCR9 |
| M-2 (M-2A + M-2B) | $75.7mm | $75.7mm | 130 bp | 35564UCS4 | U3202CCS7 |

## Findings in brief

- **Losses are small.** The model projects reference-pool losses of 0.20% to 0.37% of the
  cut-off balance across four scenarios, from a good economy to a 2008-style house-price fall.
- **The offered notes are not touched.** M-2B, the lowest offered class, starts taking losses
  only once pool losses pass 1.90% of cut-off (the B-1H, B-2H and B-3H layers Freddie Mac
  retains), about five times the worst case.
- **Timing is the real risk.** Market mortgage rates sit above most borrowers' note rates, so
  few refinance and the pool pays down slowly. M-1 and M-2 extend when rates stay high.
- A plain-language walk-through of the deal and the model is in the team's beginner guide
  (shared separately).

## Team

| Member | Part | Main files |
|---|---|---|
| Al Yazid Bensaid | Deal structure | `docs/structure.md`, `docs/cashflows.md` |
| Haocheng Sun | Loan data cleaning, class factors | `src/clean.py`, `notebooks/01_clean.ipynb` |
| Reza Zamani | Default and prepayment model, collateral projection | `src/prepayment.py`, `src/credit_model.py`, `src/collateral_projection.py`, `src/calibration.py`, notebooks 02–08 |
| Coco Ma | Interest-rate and house-price scenarios | `src/scenarios.py`, `src/market_data.py`, `data/scenarios/` |
| Smarajit Paul Choudhury | Waterfall and pricing | `src/waterfall.py`, `src/pricing.py`, `src/run_waterfall_pricing.py`, `docs/waterfall_pricing.md` |

## Project map (Track 2 requirements)
| Requirement | Where |
|---|---|
| 1. Organizational structure | `docs/structure.md` |
| 2. Cash flow structure (collateral + notes) | `docs/cashflows.md`, `src/waterfall.py`, `docs/waterfall_pricing.md` |
| 3a. Price the collateral (reference pool) | `src/collateral_projection.py`, `src/scenarios.py`, `outputs/tables/pool_cf_*.csv` |
| 3b. Price the tranches | `src/waterfall.py`, `src/pricing.py`, `outputs/tables/tranche_pricing_summary.csv` |
| 4. Recommendations | `report/` |

## Pipeline

```
data/raw (STACR tape, Freddie SF sample files, FRED)
   │
   ├─ src/clean.py ─────────────► data/processed/*.parquet         (current pool)
   ├─ src/calibration.py ───────► outputs/tables/fitted_params.csv  (prepay, default, severity)
   ├─ src/scenarios.py ─────────► data/scenarios/scenarios.csv, pricing_rates.csv
   │
   └─ src/export_results.py ────► outputs/tables/pool_cf_<scenario>.csv   (monthly collateral table)
                                        │
        src/run_waterfall_pricing.py ◄──┘
                                        └─► waterfall_cf_<scenario>.csv, tranche_pricing_summary.csv
```

**Projection start.** The pool is the post-September 2026 (payment 7) loan tape:
56,433 loans, $19.25bn, matching Bloomberg CLP and the M-1 September factor.
Projections run monthly from the October 2026 payment (month 1) to the February
2031 optional call (month 53).

**Collateral model.** Prepayment is an S-curve in refinance incentive with burnout and
seasoning ramp. Credit events are a Poisson GLM on mark-to-market LTV, FICO, DTI,
investor status and delinquency. Severity builds the loss from mark-to-market LTV,
costs, missed interest, REO discount and mortgage insurance. All three are calibrated on 27 vintages of the Freddie Mac
Single-Family Loan-Level sample plus FRED HPI and PMMS. Each scenario produces
beginning balance, scheduled principal, prepayments, credit events, losses,
modification losses, distressed balance and ending balance by month
(see `outputs/HANDOFF_SMARAJIT.md` for the column definitions).

## Notebooks

Every code cell has a markdown note above (what it does) and below (what it shows),
plus Q&A. Matching `.py` versions are in `notebooks/scripts/`.

| Notebook | Content |
|---|---|
| `01_clean` | Load and clean the STACR loan tape |
| `02_prepayment_and_credit_model` | CPR/SMM, credit-event rate and severity functions |
| `03_collateral_projection` | Monthly pool projection by scenario |
| `04_model_functions_walkthrough` | Each model function step by step |
| `05_calibration_results` | Fitted prepayment, default and severity parameters |
| `06_freddie` | Freddie Mac loan-level calibration data |
| `07_calibration_step_by_step` | Calibration walked through one step at a time |
| `08_export_results` | Run all scenarios and export tables and figures |

## Results (September 2026 tape)

Scenarios (Coco): good, base, moderate and severe mortgage-rate and house-price paths.

| Scenario | Year-1 CPR | Pool at call | Losses (% of cut-off) | A-1 WAL | M-1 WAL | M-2A WAL | M-2B WAL |
|---|---|---|---|---|---|---|---|
| good     | 10.9% | $6.83bn | 0.20% | 1.40 | 1.16 | 2.28 | 2.70 |
| base     | 10.6% | $7.33bn | 0.22% | 1.40 | 1.20 | 2.43 | 2.82 |
| moderate |  7.6% | $9.30bn | 0.30% | 1.40 | 1.87 | 3.47 | 3.84 |
| severe   |  8.0% | $7.17bn | 0.37% | 1.40 | 1.54 | 2.74 | 3.16 |
| *PPM at issue* | | | | *1.59* | *1.75* | *4.11* | *4.79* |

WALs are in years from the September 2026 payment, so they are shorter than the PPM's
issue-date WALs. A-1 follows a fixed fast-pay schedule and is retired by month 30 in every scenario.

- No offered class is written down in any scenario. Losses stay inside the B-tranches
  and the main risk to investors is timing: slower prepayment in the moderate case
  extends M-1 and M-2 by about a year.
- Prices at a discount margin equal to the coupon spread are about 100.10 per 100 for every
  class (par plus about 0.10 of accrued interest). Prices at 0, 100 and 200 bp discount
  margins are in `outputs/tables/tranche_pricing_summary.csv`. These are sensitivities,
  not a comparison against market prices.

## Data (not committed)

Bloomberg loan-level files, Freddie Mac loan-level data and the course handout are
licensed or course-only and stay local. Place them in `data/raw/`:

- `STACR_2026_DNA1_A1_Loan_Level_YYYY-MM.xlsx`: the STACR loan tape (the newest dated tape is used)
- `freddie_sf/sample_orig_YYYY.txt`, `freddie_sf/sample_perf_YYYY.txt`: Freddie Mac SF Loan-Level sample files
- FRED CSVs (`HPIPONM226S.csv`, `MORTGAGE30US.csv`; `python -m src.scenarios --download` refreshes the scenario inputs)

Result tables, figures and the pool cash flows in `outputs/` are committed. Loan-level rows are not.

## Setup and run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m src.clean                   # clean the loan tape -> data/processed/
python -m src.scenarios               # Coco's rate and HPI scenarios -> data/scenarios/
python -m src.export_results          # pool cash flows, tables and figures -> outputs/
python -m src.run_waterfall_pricing   # waterfall and offered-class pricing -> outputs/tables/
pytest                                # tests
```

## Open items

- Supplemental Reduction Amount and the Offered Reference Tranche Percentage test are not
  implemented. None of the four scenarios reaches them before payoff or the call.
- Relative value needs a Bloomberg market price or discount margin to compare against.

## Deliverables
- Oral presentation: 5–8 slides (`report/slides/`)
- Written summary: 5–10 pages, slides in appendix (`report/`, outline in `report/outline.md`)
