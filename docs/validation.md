# Final Validation Notes

This note documents the final independent QA checks applied to the persisted
STACR 2026-DNA1 collateral, waterfall, and pricing outputs.

## Scope

The validation was performed at three levels:

1. **Automated code tests** — the existing waterfall, pricing, and integration
   tests were run with `pytest`.
2. **Independent output reconciliation** — the generated CSVs were checked
   directly for pool roll-forward identities, tranche balance identities,
   negative balances, offered-note writedowns, trigger state, and pricing
   monotonicity.
3. **External market sanity check** — current tranche factors/balances, WALs,
   bid/ask prices, and discount margins were cross-checked against Bloomberg
   as of 2026-10-02. Raw Bloomberg exports/screenshots are retained outside the
   public repository.

## Key validation findings

- The final collateral projection starts from the **September 2026** pool
  snapshot (~$19.2543bn), rather than the stale August snapshot (~$19.4430bn).
- M-1 starts from the September factor/balance: factor **0.571984481**, balance
  **$157.8105mm**.
- Starting subordinate percentage is approximately **3.525005%**, so the
  month-1 Minimum Credit Enhancement test passes.
- Across good/base/moderate/severe scenarios, pool and tranche balance
  identities reconcile to floating-point tolerance.
- No negative ending tranche balances were observed.
- No principal writedowns were observed on the offered classes A-1, M-1,
  M-2A, or M-2B in the four team scenarios.
- Persisted pricing results are monotone in discount margin: price at 0 bp DM
  > price at 100 bp DM > price at 200 bp DM.
- Bloomberg WAL observations fall within the model scenario ranges, providing
  an external reasonableness check on projected principal timing.

## Reproducible output-level tests

The integration checks above are encoded in:

```text
tests/test_output_validation.py
```

Run them with:

```bash
pytest -q tests/test_output_validation.py
```

## Caveats

- The first projection period is a short stub, while collateral prepayment and
  default behavior is modeled on a monthly basis.
- Licensed/raw loan-level and market data are intentionally excluded from the
  repository. Persisted outputs and execution evidence are used for team
  reproducibility.
- Pricing columns such as `price_at_100bp_dm` are sensitivity values under an
  assumed discount margin; they should not be described as observed market or
  fair prices. Market comparisons should use the separate Bloomberg quotes and
  discount-margin observations.
