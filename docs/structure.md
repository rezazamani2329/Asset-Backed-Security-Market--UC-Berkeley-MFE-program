# Part 1: Organizational Structure (STACR 2026-DNA1)

Source: STACR 2026-DNA1 Private Placement Memorandum, dated February 12, 2026, and the Capital Contribution Agreement dated February 17, 2026 (both in `docs/reference/`).
Page references are the printed page numbers in the PPM. For the main body, the PDF page is the printed page + 21.

## In one paragraph

Investors do not buy mortgages. They buy notes issued by a Delaware trust. The trust invests the note proceeds in short-term government assets and sells credit protection to Freddie Mac on a $22.8bn reference pool of Freddie Mac loans. When loans in the pool suffer losses, the notes are written down and the trust hands that principal to Freddie Mac. In return, Freddie Mac tops up the notes' interest each month. Investors therefore take mortgage credit risk on the reference pool, plus a smaller counterparty risk on Freddie Mac's monthly payments (p. 1, 5, 72).

## Issuer / issuing vehicle

- **Issuer:** Freddie Mac STACR REMIC Trust 2026-DNA1, a Delaware statutory trust (p. 6, 71).
- **Sponsor and administrator:** Freddie Mac. It holds the Owner Certificate, the Residual Certificates and the X-IO interest, and pays the trust's fees and expenses (p. 12, 71).
- **Limited purpose:** the trust may only enter into the deal agreements, issue the notes and invest proceeds in Eligible Investments. It may not merge or sell substantially all its assets (p. 71, 104).
- **Tax form:** the trust elects REMIC status. Noteholders hold REMIC regular interests, which are taxed as debt (p. 13, 145).
- **Offered notes:** $627.5mm of A-1, M-1, M-2A and M-2B, sold only to qualified institutional buyers (Rule 144A) and offshore buyers (Reg S) (cover).

## Bankruptcy remoteness: how achieved

| Feature | What it does | Source |
|---|---|---|
| Separate legal entity | The trust, not Freddie Mac, owns the note proceeds and the Eligible Investments. Freddie Mac never owned the proceeds, so they should sit outside any Freddie Mac receivership estate. | p. 61 |
| Limited purpose and no mergers | The trust cannot take on other business or other creditors. | p. 71, 104 |
| Non-petition covenant | Noteholders and the Indenture Trustee agree not to put the trust into bankruptcy until one year and one day after the notes are paid in full. | p. 104 |
| Security interest | All trust assets are pledged to the Indenture Trustee for Freddie Mac and the noteholders. | p. 7, 92 |
| IO Q-REMIC interest contributed to the trust | Freddie Mac contributes an interest-only strip of the reference loans' interest to the trust. HERA's exceptions for mortgages held in a custodial capacity should keep it out of a receivership. | p. 60-61 |
| High-quality collateral | Proceeds go into U.S. government or agency debt, repo on that debt, or top-rated government money market funds, all with short maturities. | p. 175 |

Limits investors should know about (p. 60-62):
- FHFA as receiver could argue the IO Q-REMIC contribution was only a pledge and try to control it. That would delay payments.
- FHFA could ask a court to consolidate the trust with Freddie Mac. The GSE Act does not expressly allow this, and courts rarely do it, but it would delay payments.
- A successor to Freddie Mac could in some cases get a lien ranking ahead of the Indenture lien.

## How payments flow from Freddie Mac to noteholders

**At closing:** investors pay $627.5mm to the trust. The trust buys Eligible Investments, managed by BlackRock and held by BNY Mellon as custodian (p. 5-7).

**Each month (25th):**
1. **Interest.** The notes pay SOFR + spread. The SOFR part is covered by earnings on the Eligible Investments. If earnings fall short of SOFR on the note balance, Freddie Mac pays the gap (Index Component Contribution, under the Capital Contribution Agreement). The spread part is the **Transfer Amount**, paid by Freddie Mac under the Collateral Administration Agreement and funded first by the IO Q-REMIC interest (p. 5, 91, 179, 196).
2. **Losses.** If loans in the reference pool have credit events or modification losses that reach an offered note, the note is written down. The trust sells investments and pays that amount to Freddie Mac (the **Return Amount**) (p. 8-9, 192).
3. **Principal.** Principal collected on the reference pool is allocated to the notes under the rules in `docs/cashflows.md`. The trust sells investments to pay it (p. 10, 81).
4. **Investment losses.** If selling investments raises less than book value, Freddie Mac makes up the shortfall (Investment Liquidation Contribution) (p. 179, CCA s. 2).
5. **Netting.** All amounts are netted, so only one party pays the other each month (p. 11, CCA s. 2).

**Priority:** the trust pays Freddie Mac's Return Amount first, then interest and principal to the notes (p. 79, 80).

Important: noteholders never receive the mortgage cash flows themselves and have no claim on the loans or the homes (p. 55, 72).

## Investor exposure to Freddie Mac (conservatorship)

Investors take two separate risks:

1. **Credit risk on the reference pool.** This is the risk the deal is built to transfer. It drives almost all of the pricing.
2. **Counterparty risk on Freddie Mac.** Investors rely on Freddie Mac for the spread over SOFR, for any SOFR shortfall on the investments, and for investment liquidation losses. Principal is held in the trust, not at Freddie Mac.

Freddie Mac's status (p. xx, 59-62):
- Freddie Mac has been in conservatorship under FHFA since September 2008. It depends on Treasury's support under the Purchase Agreement to stay solvent. The PPM states this is ongoing as of February 2026. **To check before the presentation: whether conservatorship status has changed since then.**
- The notes are **not** guaranteed by Freddie Mac or the U.S. government (cover, p. 12).
- FHFA must place Freddie Mac into receivership if its assets fall below its obligations for 60 days. Treasury funding prevents this (p. 60).
- In receivership, FHFA could repudiate the Collateral Administration and Capital Contribution Agreements. The trust would then be an unsecured creditor for unpaid amounts, and payments could be frozen for up to 90 days (p. 61).
- A Freddie Mac payment default lets the trust designate an Early Termination Date, so the notes would be redeemed early from the trust's own assets (p. 51, 174, 178).

Plain-language takeaway for clients: the principal you invested sits in the trust in Treasury-type assets. What depends on Freddie Mac is mainly your monthly spread. A Freddie Mac failure would most likely end the deal early, not wipe out your principal.

## Trustee, servicers, other parties

| Role | Party | Source |
|---|---|---|
| Sponsor, Administrator | Freddie Mac | p. 6 |
| Indenture Trustee, Exchange Administrator | U.S. Bank Trust Company, N.A. | p. 6 |
| Owner Trustee | Wilmington Trust, N.A. | p. 6 |
| Custodian | The Bank of New York Mellon | p. 6 |
| Investment Manager | BlackRock Financial Management, Inc. | p. 6 |
| Lead managers | Wells Fargo Securities, Citigroup | cover |
| Rating agencies | S&P, Morningstar DBRS | p. x |
| Servicers | The existing servicers of the Freddie Mac loans, under Freddie Mac's Guide | p. 28 |

Notes on the parties:
- **Servicers** keep servicing the loans for Freddie Mac. Their decisions on modifications, forbearance and foreclosure timing drive losses, but noteholders have no direct rights against them (p. 28, 56).
- **Freddie Mac's quality control** can find underwriting defects after a loss. The loss is then reversed and the notes are written back up (p. 25, 83).
- **Conflicts of interest:** Freddie Mac is sponsor, administrator, guarantor of the underlying MBS and protection buyer. Some initial purchasers are affiliated with loan sellers and servicers (p. 12-13).
- **Risk retention:** Freddie Mac keeps at least 5% of each offered band, plus the first 1.9% of losses (B tranches), and commits not to hedge them (p. 3-4, xvii).

## Suitability assessment for investors

**Structural positives**
- Principal is ring-fenced in a bankruptcy-remote trust holding short-term government assets.
- Freddie Mac keeps the first-loss B tranches and a 5% slice of every offered band, so its incentives line up with investors.
- Floating rate (SOFR + spread) means little interest rate duration.
- Reference pool is prime: original LTV 61% to 80% (WA 76%), WA credit score 759, WA DTI 38% (p. A-1).
- Monthly loan-level disclosure through Freddie Mac's Clarity platform (p. A-1).

**Structural negatives**
- Investors have no claim on the mortgages and no control over servicing.
- Counterparty dependence on a GSE in conservatorship, whose future structure is uncertain.
- Loss definition includes modification losses, so interest can be cut even without a default.
- Freddie Mac holds a call from February 2031 and on several regulatory triggers. Upside is capped.
- Private placement with transfer restrictions, so liquidity is thinner than agency MBS (p. 69).

**By investor type** (legal and regulatory facts from the PPM; fit is our assessment)

| Investor | Can they buy? | Fit |
|---|---|---|
| Insurance companies | Yes, as QIBs. A-1 is A+ rated, M classes are BBB+/BBB. | Good for A-1 and M-1: investment-grade floating-rate credit with spread over similar-rated corporates. |
| Banks | Yes, as QIBs. The trust is structured not to be a Volcker "covered fund" (cover). | A-1 for spread with limited loss risk. Capital treatment should be checked by each bank. |
| Pension funds (ERISA plans) | Expected to be ERISA-eligible (p. 7, 156). | Suitable for A-1 and M-1 within credit allocations. |
| Money managers and credit funds | Yes. | M-2A/M-2B for higher spread and leverage to housing credit. |
| Hedge funds | Yes. | M-2 classes and the IO/MACR combinations for targeted exposures. |
| EU and UK investors | Freddie Mac's 5% retention and reporting are designed for EU/UK due diligence rules (p. xvii). | Can participate, subject to their own assessment. |
| Retail investors | No. QIB and Reg S only; EEA and UK retail sales prohibited (cover, p. xvii-xviii). | Not suitable. |
| Investors that need "mortgage related securities" | The notes are **not** SMMEA mortgage related securities (p. xiv). | Must check their own legal investment limits. |
