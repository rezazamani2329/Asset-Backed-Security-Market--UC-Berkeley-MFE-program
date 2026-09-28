# Part 2: Cash Flow Structure (STACR 2026-DNA1)

Source: STACR 2026-DNA1 Private Placement Memorandum, dated February 12, 2026 (`docs/reference/stacr-2026-dna1-ppm.pdf`).
Page references are the printed page numbers in the PPM. For the main body, the PDF page is the printed page + 21.

## Key terms

| Item | Value | Source |
|---|---|---|
| Closing Date | February 17, 2026 | cover |
| First Payment Date | March 25, 2026, then the 25th of each month | p. 8 |
| Reference Pool (Cut-off Date Balance) | $22,781,151,551.84, 64,434 loans | p. 173, A-1 |
| Offered notes | $627,500,000 (A-1, M-1, M-2A, M-2B) | cover, p. x |
| Scheduled Maturity Date | Payment Date in February 2046 | p. 7 |
| Early redemption | Freddie Mac may redeem on or after the February 2031 Payment Date (5-year call), or when the pool falls to 10% or less of the Cut-off Date Balance | p. 185 |
| Coupon | 30-Day Average SOFR + spread, 0% floor, actual/360, paid monthly in arrears | p. x, p. 80 |
| First-period SOFR | 3.65786% | p. x |

## Reference tranche table (full stack, incl. retained pieces)

Losses and principal are calculated on a hypothetical stack of reference tranches that sums exactly to the Cut-off Date Balance (Table 3, p. 2). The notes only track their corresponding reference tranche. Freddie Mac keeps every piece ending in "H", plus A-H and all B tranches.

| Tranche | Balance ($) | Attach % | Detach % | Offered? | Coupon | Rating (S&P / DBRS) |
|---|---|---|---|---|---|---|
| A-H | 21,687,655,280.84 | 4.800 | 100.000 | No | n/a | n/a |
| A-1 | 275,900,000 | 3.525 | 4.800 | Yes | SOFR + 0.85% | A+ (sf) / A (low) (sf) |
| A-1H | 14,559,682 | 3.525 | 4.800 | No | n/a | n/a |
| M-1 | 275,900,000 | 2.250 | 3.525 | Yes | SOFR + 1.00% | BBB+ (sf) / BBB (high) (sf) |
| M-1H | 14,559,682 | 2.250 | 3.525 | No | n/a | n/a |
| M-2A | 37,850,000 | 2.075 | 2.250 | Yes | SOFR + 1.30% | BBB+ (sf) / BBB (sf) |
| M-2AH | 2,017,015 | 2.075 | 2.250 | No | n/a | n/a |
| M-2B | 37,850,000 | 1.900 | 2.075 | Yes | SOFR + 1.30% | BBB+ (sf) / BBB (low) (sf) |
| M-2BH | 2,017,015 | 1.900 | 2.075 | No | n/a | n/a |
| B-1H | 102,515,181 | 1.450 | 1.900 | No | SOFR + 1.80% (deemed) | n/a |
| B-2H | 273,373,818 | 0.250 | 1.450 | No | SOFR + 4.75% (deemed) | n/a |
| B-3H | 56,953,878 | 0.000 | 0.250 | No | n/a | n/a |

Notes on the table:
- Each offered class and its "H" twin share the same attach/detach band and take losses and principal **pro rata**. The H piece is about 5% of each band, which is Freddie Mac's risk retention (p. 3-4).
- Attach/detach points are computed from Table 3 balances divided by the Cut-off Date Balance. They match the initial credit enhancement in Table 1 (p. x).
- B-1H and B-2H coupons are deemed only to calculate modification loss allocations. They are not paid to anyone (p. x, footnote 10).
- M-2A and M-2B can be exchanged into a combined M-2 (SOFR + 1.30%) and into other MACR classes with different coupon/IO splits (Table 2, p. xii). Cash flows are the same as the underlying M-2A/M-2B.
- Expected WAL at pricing (10% CPR, no losses, called in Feb 2031): A-1 1.59 yr, M-1 1.75 yr, M-2A 4.11 yr, M-2B 4.79 yr (p. x).

## Loss allocation rules

**What counts as a loss.** A Credit Event is the first of: short sale, sale of a seriously delinquent note, third-party foreclosure sale, REO disposition, or charge-off (p. 171). The loss is the **actual** net loss: Credit Event UPB + prior principal forgiveness + delinquent accrued interest, minus Net Liquidation Proceeds, which include mortgage insurance proceeds (p. 172, 184). This is an actual-loss deal, not a fixed-severity deal.

**Principal Loss Amount** each month = credit event net losses + court-ordered principal reductions + later losses on prior credit events + principal-type modification losses + net gains on reversed credit events (p. 188). The **Tranche Write-down Amount** is the Principal Loss Amount minus recoveries (p. 196).

**Write-downs, bottom up** (p. 82): first any overcollateralization from prior write-up excess, then
1. B-3H
2. B-2H
3. B-1H
4. M-2B and M-2BH, pro rata
5. M-2A and M-2AH, pro rata
6. M-1 and M-1H, pro rata
7. A-1 and A-1H, pro rata
8. A-H, only for certain modification-related losses

A write-down cuts the note's principal with no payment, so it also cuts future interest (p. 8-9).

**Write-ups, top down** (p. 83): recoveries reverse prior write-downs in order A-H, A-1/A-1H, M-1/M-1H, M-2A/M-2AH, M-2B/M-2BH, B-1H, B-2H, B-3H. Each class is only written back up to what it lost.

**Modification losses** (p. 84-85): when a loan's rate is modified or balance forborne, the lost interest is allocated bottom up. For each band it first cuts that class's **interest payment** for the month, then its principal. Order: B-3H, B-2H (interest, then principal), B-1H (interest, then principal), M-2B interest, M-2A interest, M-2B principal, M-2A principal, M-1 interest, M-1 principal, A-1 interest, A-1 principal. Modification gains are paid back top down (p. 85).

## Principal allocation rules and triggers

Each month, **Stated Principal** (scheduled principal, prepayments, and non-credit removals from the pool; p. 194) plus **Recovery Principal** (p. 190) is split between a senior and a subordinate bucket.

**Senior Reduction Amount** (p. 193):
- If all three triggers pass: Senior Percentage x Stated Principal + 100% of Recovery Principal.
- If any trigger fails: 100% of Stated Principal and Recovery Principal. The subordinate bucket gets nothing.

**Senior Percentage** = (A-H + A-1 + A-1H balances) / pool UPB. At closing this is 95.2% (p. 193).
**Subordinate Reduction Amount** = total principal minus the Senior Reduction Amount (p. 195).

**Triggers for M-1, M-2A and M-2B** (all must pass):

| Test | Passes if | Source |
|---|---|---|
| Minimum Credit Enhancement Test | Subordinate Percentage (100% minus Senior Percentage) is at least 3.525% | p. 181 |
| Cumulative Net Loss Test | Cumulative net loss / Cut-off Date Balance is at or below a schedule: 0.10% in year 1, rising 0.10% a year to 1.30% from March 2038 | p. 173 |
| Delinquency Test | 6-month average Distressed Principal Balance (60+ days delinquent, in foreclosure, bankruptcy or REO, or modified in the last 12 months) is below 50% of (Subordinate Percentage x pool UPB minus current Principal Loss Amount) | p. 173-174 |

The Minimum Credit Enhancement Test starts at exactly 4.800% vs a 3.525% threshold, so it passes at closing. It fails if losses eat into the subordinate stack.

**Senior Reduction Amount order** (p. 86):
1. If the Class A-1 Cumulative Net Loss Test passes, up to the **Class A-1 Reduction Amount** to A-1/A-1H pro rata
2. A-H
3. A-1/A-1H, pro rata
4. M-1/M-1H, then M-2A/M-2AH, then M-2B/M-2BH (pro rata within each)
5. B-1H, B-2H, B-3H

**Class A-1 Reduction Amount** (p. 169, Appendix G): a fixed schedule for the first 36 payments. The A-1 band gets 3.75% of its original balance per month for months 1 to 12, then 1.50% per month for months 13 to 36. That is 81% of the band by month 36. After month 36, A-1 gets 100% of the Senior Reduction Amount (excluding Recovery Principal). The **Class A-1 Cumulative Net Loss Test** passes only if cumulative net loss has never exceeded 1.00% (p. 169). If it fails once, A-1 loses this fast-pay schedule for good.

**Subordinate Reduction Amount order** (p. 86-87): M-1/M-1H, M-2A/M-2AH, M-2B/M-2BH, B-1H, B-2H, B-3H, then A-1/A-1H, then A-H. So while triggers pass, the mezzanine notes amortize **sequentially** from the subordinate bucket.

**Supplemental Reduction Amount** (p. 87-88, 195): extra principal to the offered bands when the Offered Reference Tranche Percentage exceeds 5.50% of pool UPB, plus the **Class A-1 Additional Reduction Amount**. From payment 39 onward, if the Class A-1 Cumulative Net Loss Test passes, this pays off the entire remaining A-1/A-1H band (p. 169). Order: A-1 additional amount, then M-1, M-2A, M-2B, then A-1 (pro rata with H pieces).

**Cash priority on each Payment Date** (p. 79, 10): the Trust first pays Freddie Mac the Return Amount (equal to write-downs on the notes), then interest and principal to the notes. Among the notes: A-1 senior to M-1, M-1 senior to M-2A, M-2A senior to M-2B, except for the Subordinate Reduction Amount, which goes to M-1 before A-1.

## Interest: SOFR + spread by class

| Class | Spread | Initial coupon | Floor |
|---|---|---|---|
| A-1 | SOFR + 0.85% | 4.50786% | 0% |
| M-1 | SOFR + 1.00% | 4.65786% | 0% |
| M-2A | SOFR + 1.30% | 4.95786% | 0% |
| M-2B | SOFR + 1.30% | 4.95786% | 0% |

- Index: 30-Day Average SOFR, reset each month (p. 194).
- Day count: actual/360. Accrual period runs from the prior Payment Date to the day before the current one (p. 80).
- Interest is funded by earnings on the Eligible Investments (bought with note proceeds), plus Freddie Mac's Transfer Amount and Capital Contribution Amount (p. 5). Freddie Mac's payment obligation is the investor's main counterparty exposure. See `docs/structure.md`.
- Interest can be cut in a given month by modification losses (see above).

## Calls / legal final maturity

- **Scheduled maturity:** February 2046 Payment Date. All remaining note principal is due then (p. 7, 81).
- **Early Termination Date** (p. 174), earliest of:
  - Freddie Mac's optional call on or after the February 2031 Payment Date (Optional Termination Event 7, p. 185)
  - pool at or below 10% of the Cut-off Date Balance (clean-up call, Optional Termination Event 6, p. 185)
  - regulatory events: Investment Company Act or CPO registration, adverse capital or accounting changes (Optional Termination Events 1-5, p. 185)
  - a Freddie Mac Default under the transaction agreements (p. 178)
  - all Original Notes paid down to zero, or the last loan leaves the pool
- On early redemption, notes are repaid at their outstanding (written-down) principal balance. Any loss already written down is not restored.
- Pricing assumes the call is exercised in February 2031 (p. x, footnote 1).

## Comparison: CAS 2026-R01 (Group 2 is high-LTV, 81% to 97%)

| | STACR 2026-DNA1 | CAS 2026-R01 (Group 2) |
|---|---|---|
| Sponsor | Freddie Mac | Fannie Mae |
| Closing | Feb 17, 2026 | Feb 11, 2026 |
| Reference pool | $22.78bn, 64,434 loans | $18.82bn, 52,876 loans |
| Original LTV | 61% to 80% (WA 76%) | over 80% to 97% |
| WA credit score | 759 | 756 |
| WA DTI | 38% | 39.8% |
| Offered notes | $627.5mm | $661.7mm |
| Senior offered class | A-1, 3.525% to 4.800% | 2A-1, from 5.10% |
| Mezzanine | M-1 2.250% to 3.525%, M-2 1.900% to 2.250% | 2M-1 3.65% to 5.10%, 2M-2 2.85% to 3.65% |
| Retention | about 5% vertical slice of each offered band, plus all B tranches | 5% vertical slice, plus 2B tranches |
| Call | 5 years (Feb 2031) or 10% clean-up | after Jan 2031 or 10% clean-up |
| Maturity | Feb 2046 | Jan 2046 |

The CAS pool has higher LTVs, so it carries thicker credit enhancement at each rating level. Mortgage insurance on CAS loans above 80% LTV is a key driver of severity there.

CAS figures are from Fannie Mae's CAS 2026-R01 term sheet and KBRA's pre-sale release, not the STACR PPM. They should be checked against the CAS offering memorandum before use in the report.
