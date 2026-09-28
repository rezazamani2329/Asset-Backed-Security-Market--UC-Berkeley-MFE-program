# Project Plan

This plan defines ownership and the interfaces between the five workstreams for the STACR 2026-DNA1 analysis. Dates and review assignments should be added after the team agrees on its working schedule.

## Analytical scope

The integrated analysis will cover:

- STACR 2026-DNA1 organizational and cash-flow structure
- Reference-pool composition and loan-level data quality
- Default, prepayment, loss-severity, and recovery assumptions
- Interest-rate and home-price scenarios
- Tranche waterfall and pricing
- Modeled-versus-market spread comparison
- Sensitivity analysis and combined macro stress tests
- Investment advantages, disadvantages, and final recommendation

Fannie Mae CAS 2026-R01 will be used as a comparison transaction where useful.

## Ownership and outputs

### Reza Zamani - Deal structure

- Summarize the transaction parties and legal structure.
- Explain the reference pool and credit-protection mechanics.
- Translate the priority of payments and loss allocation into implementable rules.
- Identify credit enhancement, attachment and detachment points, triggers, and write-down or recovery rules.
- Complete `docs/structure.md` and the structural sections of `docs/cashflows.md`.

### Haocheng Sun - Loan-data pipeline

- Profile the raw STACR loan-level dataset.
- Resolve missing values, data types, duplicates, and inconsistent categories.
- Document every filter and transformation.
- Produce collateral stratifications and pool summary statistics.
- Implement and document the pipeline in `src/clean.py`.

### Al Yazid Bensaid - Default and prepayment model

- Define monthly default and voluntary-prepayment specifications.
- Incorporate borrower, loan, and macroeconomic drivers supported by the data.
- Specify loss severity and recovery timing.
- Calibrate a transparent base case and document limitations.
- Produce monthly pool cash flows and credit events for every scenario.

### Smarajit Paul Choudhury - Waterfall and pricing

- Convert offering-document rules into a tested cash-flow waterfall.
- Allocate interest, principal, prepayments, losses, and recoveries across tranches.
- Calculate prices, yields, spreads, weighted-average lives, and expected losses.
- Compare modeled spreads with available market spreads.
- Implement and test `src/waterfall.py` and `src/pricing.py`.

### Coco Ma - Economic scenarios

- Define base, upside, downside, and severe-stress paths.
- Produce interest-rate paths for discounting and refinancing incentives.
- Produce home-price paths for borrower equity and loss-severity effects.
- Document scenario sources and rationale.
- Implement scenario inputs in `src/scenarios.py` with a consistent monthly index.

## Model handoffs

| Producer | Consumer | Required handoff |
|---|---|---|
| Reza Zamani | Smarajit Paul Choudhury | Bond terms, triggers, payment priority, and loss-allocation rules |
| Haocheng Sun | Al Yazid Bensaid | Clean loan-level file, data dictionary, and validation summary |
| Haocheng Sun | Smarajit Paul Choudhury | Starting pool balance, coupon and maturity distributions, and aggregate checks |
| Coco Ma | Al Yazid Bensaid | Monthly rate and home-price paths by scenario |
| Coco Ma | Smarajit Paul Choudhury | Benchmark-rate inputs and consistent scenario labels |
| Al Yazid Bensaid | Smarajit Paul Choudhury | Monthly balance, interest, scheduled principal, prepayments, defaults, losses, and recoveries by scenario |
| Smarajit Paul Choudhury | Team | Tranche results, market comparison, sensitivities, and pricing conclusions |

## Shared interface standards

- Use a monthly date index and identical scenario names across modules.
- Keep licensed raw data outside Git; never overwrite source files.
- State units explicitly for rates, balances, prices, and spreads.
- Put assumptions in documented configuration or input files rather than unexplained notebook values.
- Include row-count, balance, and cash-flow reconciliation checks at every handoff.
- Add tests for each material waterfall rule and edge case.
- Require another team member to review each major component before integration.

## Macro scenarios

The scenarios should connect the economic narrative to mortgage and tranche outcomes:

| Scenario | Rates | Labor market | Home prices | Expected channel |
|---|---|---|---|---|
| Soft landing | Gradually lower | Stable | Modest growth | Low defaults and faster refinancing |
| Higher for longer | Persistently high | Stable | Flat | Slow prepayments and extension risk |
| Recession | Falling | Weaker | Declining | Higher defaults and severity, followed by refinancing |
| Stagflation | High | Weaker | Declining | Extension risk and credit deterioration together |
| Severe stress | Stressed path | Sharp unemployment increase | Large national decline | Nonlinear tranche losses |

The final recommendation should distinguish expected credit loss from the additional compensation investors require for systematic macroeconomic, liquidity, and model risk.

## Definition of done

The integrated model should produce:

1. Base-case collateral and tranche cash flows.
2. Default and prepayment sensitivities.
3. Interest-rate and home-price scenarios.
4. Combined downside and severe stress tests.
5. A modeled-versus-market spread comparison.
6. Advantages, disadvantages, and suitability by investor type.
7. A clear investment recommendation in non-technical language.

