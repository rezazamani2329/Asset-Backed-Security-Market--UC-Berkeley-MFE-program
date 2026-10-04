# Waterfall and Pricing Implementation Status

This note documents the implemented STACR 2026-DNA1 waterfall/pricing core, its input contract, and the items still required for a current-date valuation.

## Implemented

- Full original reference-tranche stack and offered/H pair definitions
- Bottom-up ordinary-loss allocation
- Pro-rata allocation inside A-1/A-1H, M-1/M-1H, M-2A/M-2AH and M-2B/M-2BH
- Top-down recoveries/write-ups capped by cumulative prior write-downs, netted against same-month losses (PPM p. 196)
- Recovery Principal = defaulted UPB (`defaults`) in excess of the Tranche Write-down Amount, plus any write-up, paid 100% senior (PPM p. 190)
- Cumulative Net Loss counts credit-event losses and principal-type modification losses only (PPM pp. 172, 188)
- Minimum credit-enhancement, cumulative-net-loss and delinquency tests
- Senior Percentage calculated as (A-H + A-1 + A-1H) / pool UPB (96.475% at closing)
- Separate A-1 cumulative-net-loss state
- Senior/subordinate principal split and sequential allocation
- A-1 scheduled reduction for payments 1 through 36
- A-1 senior-principal priority after payment 36
- Interest-first modification-loss allocation, including retained/deemed-interest pieces
- Floating-rate interest using decimal SOFR, class spread and actual-day input
- Optional-call payoff of remaining written-down balance
- Present value, discount margin, weighted-average life and class-level risk metrics
- Input validation for units, missing columns, monthly balance continuity and inconsistent starting state

## Required monthly collateral input

The waterfall accepts the existing pool cash-flow schema:

| Column | Unit | Meaning |
|---|---:|---|
| `month` | integer | Scenario month number |
| `beginning_balance` | dollars | Beginning reference-pool UPB |
| `scheduled_principal` | dollars | Contractual amortization |
| `prepayments` | dollars | Voluntary early principal |
| `defaults` | dollars | Defaulted balance leaving performing pool |
| `losses` | dollars | Actual net credit-event loss |
| `recoveries` | dollars | Qualifying recoveries/write-ups |
| `ending_balance` | dollars | Ending reference-pool UPB |
| `modification_losses` | dollars | Current-month interest lost from rate modifications |
| `distressed_balance` | dollars | Balance used by delinquency test |

The engine validates:

```text
beginning balance - scheduled principal - prepayments - defaults = ending balance
```

It also verifies that each month's beginning balance equals the previous month's ending balance.

## Current-state inputs

The scenario projections begin with the current $19.443bn pool. Offered-class balances after the September 2026 payment have now been validated against Bloomberg PDI and are stored in `CURRENT_BALANCES`; H twins use the matching offered-class factor and A-H is the residual needed to reconcile the stack. The September M-1 factor is 0.571984481. A current-date run should use `current_tranches()` and retain:

```text
name
current_balance
original_balance
cumulative_writedown
```

It also needs:

- Cumulative net loss through the valuation date
- Six months of distressed principal balances before the first projected month
- Whether the A-1 cumulative-net-loss test has ever failed
- Current payment number
- Prior modification gains/loss state if applicable

The engine refuses to combine the current pool with original tranche balances unless a caller deliberately overrides the guard for a clearly labeled demonstration.

## Explicit limitations

### Modification data

The current collateral output defines `modification_losses` specifically as interest lost from rate cuts, so the engine can allocate it through the PPM interest-first priority. The handoff does not contain principal-forbearance losses or modification gains; those would need separate fields before they could be modeled.

### Pool snapshot date

The $19,443,046,983.78 Bloomberg pool balance reconciles to the post-August (payment 6) state: the August M-1 factor implies exactly 3.525% of the pool paydown since cut-off. `CURRENT_BALANCES` correctly uses the September (payment 7) class factors validated by Haocheng Sun. Because the A-H residual forces the stack to equal the August pool, the starting Subordinate Percentage is 3.4908% and the Minimum Credit Enhancement Test fails in the first projected months. `run_waterfall_pricing` warns when this happens. Fix: start the collateral projection from the post-September reference pool balance (Freddie Mac monthly STACR disclosure) and rerun `python -m src.export_results`.

### Starting trigger history

The runner starts cumulative net loss and the distressed-balance history at zero. Actual values through September 2026 should be supplied via `initial_cumulative_loss` and `initial_distressed_history`.

### Supplemental reduction

The payment-37 A-1 senior-principal priority is implemented. The separate Offered Reference Tranche Percentage test and full Supplemental Reduction Amount are not; they are not reached by the offered classes in the four supplied scenarios before payoff/call, but should be added for a general-purpose engine.

### Market comparison

Prices are full (dirty) prices per 100 of current face, including accrued interest since September 25 (about 0.10 at valuation). Pricing utilities do not invent a market price. Bloomberg clean price, settlement date and/or observed discount margin are required before computing relative value.

## Run the team scenarios

From the repository root:

```bash
python -m src.run_waterfall_pricing
```

This joins `outputs/tables/pool_cf_<scenario>.csv` to Coco's `data/scenarios/pricing_rates.csv`, starts at deal payment 8, and writes:

- `outputs/tables/waterfall_cf_<scenario>.csv`: auditable monthly cash flows for every reference tranche
- `outputs/tables/waterfall_cashflows_all.csv`: the four waterfall files combined into one table
- `outputs/tables/tranche_pricing_summary.csv`: offered-class WAL, interest, principal, losses and scenario PVs at explicitly labeled 0/100/200 bp and class-coupon-spread discount margins

The scenario PV columns are sensitivity outputs, not Bloomberg market prices.

## Tests

`tests/test_waterfall.py` covers:

- Zero, negative, boundary and multi-band losses
- Offered/H pair allocation
- Top-down capped write-ups
- Trigger-dependent principal direction
- Cumulative-loss and A-1 schedules
- Initial trigger state
- Current-pool/original-tranche mismatch guard
- One-month waterfall reconciliation
- Modification-loss priority and principal/interest split
- Post-payment-36 A-1 priority
- Pool cash-flow roll-forward validation
- Recovery Principal sources = uses and senior allocation
- Same-month netting of recoveries against losses

`tests/test_pricing.py` covers:

- Zero-rate present value
- Price sensitivity to discount margin
- Discount-margin inversion
- Decimal-rate validation
- Weighted-average life
- Class metrics without fabricated market inputs
