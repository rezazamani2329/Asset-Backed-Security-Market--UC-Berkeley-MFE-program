# Pricing GSE Credit Risk Transfer Notes — STACR 2026-DNA1

UC Berkeley MFE · MFE230M Asset Securitization (ABSM) · Fall 2026 · Final Project, **Track 2**
**Instructor:** Professor Nancy Wallace, UC Berkeley Haas School of Business

**Team:** Reza Zamani, Al, HS, Coco, Samrajit

## Objective
Analyze and price Freddie Mac STACR 2026-DNA1 (classes A-1, M-1, M-2) from the
perspective of a consultant advising prospective investors.

| Class | Amount | Rule 144A CUSIP | Reg S CUSIP |
|---|---|---|---|
| A-1 | $275.9mm | 35564UCQ8 | U3202CCQ1 |
| M-1 | $275.9mm | 35564UCR6 | U3202CCR9 |
| M-2 | $75.7mm  | 35564UCS4 | U3202CCS7 |

## Project map (Track 2 requirements)
| Requirement | Where |
|---|---|
| 1. Organizational structure | `docs/structure.md` |
| 2. Cash flow structure (collateral + notes) | `docs/cashflows.md`, `src/waterfall.py` |
| 3a. Price the collateral (reference pool) | `src/collateral.py`, `src/scenarios.py` |
| 3b. Price the tranches | `src/waterfall.py`, `src/pricing.py` |
| 4. Recommendations | `report/` |

## Pipeline
```
data/raw → clean.py → collateral.py + scenarios.py → waterfall.py → pricing.py → report
```

## Data (NOT committed)
Bloomberg loan-level files and course historical data are licensed and must stay
local. Place them in `data/raw/`:
- `STACR_2026_DNA1_A1_Loan_Level.xlsx`
- historical performance data for model calibration

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.clean      # writes data/processed/*.parquet
pytest                   # run tests
```

## Deliverables
- Oral presentation: 5–8 slides (`report/slides/`)
- Written summary: 5–10 pages, slides in appendix (`report/`)
