# Default & Prepayment Model: Plan (Reza)

**Job:** turn the clean pool (HS) + rate/HPI scenarios (Coco) into a monthly reference-pool
table that Smarajit's waterfall consumes. The base case runs from today's $19.44bn pool to
the Feb 2031 call (about 53 months).

```
clean.py (HS) ─┐
               ├─► prepayment.py ─┐
scenarios.py ──┤                  ├─► collateral_projection.project_collateral ─► waterfall.py
   (Coco)      └─► credit_model.py┘
```

## Step 0: Interfaces (this week, before any modeling)

- **With Coco:** agree on the shape of the scenario inputs: `mortgage_rate` (n_months, % per year)
  and `hpi` (n_months + 1, starts at 1.0), plus scenario names: base / rates −100 / rates +100 /
  moderate stress / severe stress. Until Coco delivers, use flat placeholder paths.
- **With Smarajit:** agree on the column names in `COLUMNS` (`src/collateral_projection.py`),
  especially `losses`, `modification_losses` and `distressed_balance`, plus units ($, not %).
- **With HS:** confirm the cleaned fields you need: balance, coupon, FICO, HPI-adjusted LTV,
  DTI, age, remaining term, occupancy, purpose, state, dq_bucket. Also confirm how the B/F
  status codes are handled.

## Step 1: Plumbing with constant rates (get the table right first)

Implement these in order. Each one has a test in `tests/test_collateral.py`:

1. `calculate_smm`, `smm_to_cpr`, `cdr_to_mdr`: unit conversions
2. `scheduled_principal`: level-pay amortization
3. `project_collateral` using **constant** CPR / CDR / severity (e.g. 10% CPR to match the PPM pricing
   speed, 0.2% CDR, 25% severity)
4. Test: the balance is conserved every month, and the starting balance is $19.44bn

**★ Next step: do item 1, then item 2.** With constant assumptions you can hand Smarajit a
real table within days, and he can build the waterfall while you build the behavioral model.

> Think: within a month, which balance does the SMM apply to, and which balance does the MDR
> apply to? Write out B_t before coding.

## Step 2: Calibration data

- Get the **Freddie Mac Single-Family Loan-Level Dataset** (free registration). It has monthly
  performance for each loan. Use a sample of vintages, including a stressed one (2006–08)
  and a recent one. Keep it in `data/raw/` (it's gitignored).
- Also check with Prof. Wallace whether the course's historical data is meant for this.

> Think: with ~5 years of runway and a 2024–25 vintage pool, which history is most
> representative for base vs. stress? Why is 2007 useful even though underwriting differs?

## Step 3: Prepayment (`src/prepayment.py`)

- `refi_incentive`: loan coupon − market mortgage rate along the path
- `calculate_cpr`: S-curve in incentive × seasoning ramp × burnout, with a turnover floor
- Fit it to the historical data: bucket loans by incentive and compute the empirical CPR

> Think: should the S-curve be logistic or piecewise linear? Does 50 bp of incentive
> matter the same for a $1.9mm loan as for a $150k loan?

## Step 4: Credit (`src/credit_model.py`)

- `mark_to_market_ltv`: current LTV rolled forward along the HPI path
- `calculate_credit_event_rate`: a monthly hazard driven by MTM LTV, FICO, DTI, occupancy, and current dq status
- `calculate_loss_severity`: actual loss = UPB + delinquent interest + costs − sale proceeds − MI
- `modification_loss`: modification frequency × size of the rate cut
- A liquidation lag (default → credit event), which also produces `distressed_balance`

> Think: loans already 60/90+ days delinquent today: should they get a separate roll rate
> rather than the hazard model? What severity do you get at LTV 70 with 10% HPI down?

## Step 5: Scenarios and validation

- `run_scenarios` runs good / base / moderate / severe on all paths
- Sanity checks (these are the skipped tests): rates ↓ ⇒ CPR ↑; HPI ↓ ⇒ defaults ↑ and severity ↑
- Backtest: does the model reproduce the pool's observed CPR and dq since cut-off
  ($22.78bn → $19.44bn)?

> Think: what CPR is implied by $22.78bn → $19.44bn over the months since Feb 2026?

## Step 6: The three figures for the presentation

1. CPR vs. refinancing incentive (model S-curve over the historical data points)
2. Credit event rate by scenario over time
3. Projected pool balance for base / moderate / severe on one chart

## Files

| File | Functions |
|---|---|
| `src/prepayment.py` | calculate_smm, smm_to_cpr, refi_incentive, calculate_cpr, calculate_prepayment |
| `src/credit_model.py` | cdr_to_mdr, mark_to_market_ltv, calculate_credit_event_rate, calculate_credit_events, calculate_loss_severity, modification_loss |
| `src/collateral_projection.py` | scheduled_principal, project_collateral, run_scenarios, placeholder_scenarios |
| `tests/test_collateral.py` | conversions, economic direction, balance conservation |
| `notebooks/` | calibration + the three figures |
