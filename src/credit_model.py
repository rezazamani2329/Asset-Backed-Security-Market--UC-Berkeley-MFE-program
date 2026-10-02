"""Credit model: credit events (defaults), loss severity, modification losses.

Owner: Reza. Inputs: clean pool (src/clean.py) + house-price path (src/scenarios.py).

STACR 2026-DNA1 is an ACTUAL-LOSS deal (PPM p. 172, 184): loss = credit event UPB
+ delinquent interest + prior forgiveness - net liquidation proceeds (incl. MI).
See docs/cashflows.md.

Default model (proportional hazard, per loan, per month):

    MDR_t = cdr_to_mdr(BASE_CDR) * exp(b_ltv(MTM LTV_t - 80)) * exp(-B_FICO (FICO - 750))
            * exp(B_DTI (DTI - 38)) * investor multiplier  [+ extra hazard if 30 days dq]

    MTM LTV_t = HPI-adjusted LTV on the tape / HPI_t   (HPI_0 = 1 on the tape date).
    b_ltv is steeper above 80 LTV: negative equity drives strategic and forced default.

Here "default" means a loan goes seriously delinquent and enters the liquidation pipeline.
The credit event (and the loss) comes LIQ_LAG months later; see collateral_projection.py.
MOD_SHARE of new defaults are modified instead of liquidated, and the rate cut is a
modification loss (PPM p. 84-85).

Severity (actual loss as a fraction of UPB):

    loss = UPB * (1 + LIQ_LAG * coupon / 1200 + COSTS)        UPB + missed interest + costs
           - property value * HPI * (1 - REO_DISCOUNT)        distressed sale proceeds
           - MI proceeds                                     only if original LTV > 80 (CAS)

ALL PARAMS ARE PLACEHOLDERS until calibrated (docs/reza_plan.md, Step 2).
"""
import numpy as np
import pandas as pd

PARAMS = {
    "base_cdr": 0.0020,        # annual CDR at MTM LTV 80, FICO 750, DTI 38   PLACEHOLDER
    "b_ltv_low": 0.04,         # log-hazard per LTV point below 80            PLACEHOLDER
    "b_ltv_high": 0.10,        # log-hazard per LTV point above 80            PLACEHOLDER
    "b_fico": 0.012,           # log-hazard per FICO point (higher = safer)   PLACEHOLDER
    "b_dti": 0.02,             # log-hazard per DTI point                     PLACEHOLDER
    "investor_mult": 1.5,      # investment property multiplier               PLACEHOLDER
    "dq30_extra_mdr": 0.01,    # extra monthly hazard for loans 30 dq on tape PLACEHOLDER
    "dq30_months": 12,         # ...for this many months                      PLACEHOLDER
    "liq_lag": 12,             # months from default to credit event          PLACEHOLDER
    "costs": 0.10,             # foreclosure / REO costs, fraction of UPB     PLACEHOLDER
    "reo_discount": 0.20,      # distressed sale discount to market value     PLACEHOLDER
    "mi_coverage": 0.25,       # MI pays this share of the claim if LTV > 80  PLACEHOLDER
    "mod_share": 0.25,         # share of new defaults modified, not sold     PLACEHOLDER
    "mod_rate_cut": 2.0,       # coupon cut on modified loans, pp             PLACEHOLDER
}


def cdr_to_mdr(cdr: np.ndarray) -> np.ndarray:
    """Annual CDR -> monthly default rate: 1 - CDR = (1 - MDR)^12."""
    cdr = np.asarray(cdr, dtype=float)
    return 1.0 - (1.0 - cdr) ** (1.0 / 12.0)


def _current_ltv(loans: pd.DataFrame) -> np.ndarray:
    """HPI-adjusted LTV on the tape, falling back to original LTV when missing."""
    ltv = pd.to_numeric(loans["HPI Adjusted LTV"], errors="coerce")
    if "Original LTV" in loans:
        ltv = ltv.fillna(pd.to_numeric(loans["Original LTV"], errors="coerce"))
    return ltv.fillna(ltv.median()).to_numpy(dtype=float)


def mark_to_market_ltv(loans: pd.DataFrame, hpi_path: np.ndarray) -> np.ndarray:
    """Current LTV per loan per month, shape (n_loans, n_months).

    hpi_path has n_months + 1 points starting at 1.0 (the tape date). Amortization is
    ignored, which slightly overstates LTV (conservative).
    """
    hpi = np.asarray(hpi_path, dtype=float)
    return _current_ltv(loans)[:, None] / hpi[None, 1:]


def default_rate(loans: pd.DataFrame, hpi_path: np.ndarray, params: dict = PARAMS) -> np.ndarray:
    """Monthly default probability per loan per month, shape (n_loans, n_months)."""
    p = params
    ltv = mark_to_market_ltv(loans, hpi_path)
    fico = pd.to_numeric(loans["Credit Score"], errors="coerce")
    fico = fico.fillna(fico.median()).to_numpy(dtype=float)
    dti = pd.to_numeric(loans.get("Current Debt to Income", pd.Series(38.0, index=loans.index)),
                        errors="coerce").fillna(38.0).to_numpy(dtype=float)

    ltv_term = np.where(ltv > 80, p["b_ltv_high"] * (ltv - 80), p["b_ltv_low"] * (ltv - 80))
    mult = (np.exp(ltv_term)
            * np.exp(-p["b_fico"] * (fico - 750))[:, None]
            * np.exp(p["b_dti"] * (dti - 38))[:, None])
    if "Occupancy" in loans:
        investor = (loans["Occupancy"] == "Investment Property").to_numpy()
        mult = mult * np.where(investor, p["investor_mult"], 1.0)[:, None]

    mdr = cdr_to_mdr(p["base_cdr"]) * mult
    if "dq_bucket" in loans:
        dq30 = (loans["dq_bucket"] == 1).to_numpy()
        months = np.arange(mdr.shape[1])[None, :] < p["dq30_months"]
        mdr = mdr + p["dq30_extra_mdr"] * (dq30[:, None] & months)
    return np.clip(mdr, 0.0, 1.0)


def severity(loans: pd.DataFrame, hpi_at_default: np.ndarray, params: dict = PARAMS) -> np.ndarray:
    """Actual loss given a credit event, as a fraction of defaulted UPB, per loan.

    hpi_at_default: HPI level (tape date = 1.0) at liquidation, scalar or one per loan.
    No fixed deal severity: it is built from the liquidation, so it moves with scenarios.
    """
    p = params
    coupon = loans["Gross Coupon"].to_numpy(dtype=float)
    ltv = _current_ltv(loans) / 100.0
    value = 1.0 / ltv                                    # property value per $1 of UPB
    claim = 1.0 + p["liq_lag"] * coupon / 1200.0 + p["costs"]
    proceeds = value * np.asarray(hpi_at_default, dtype=float) * (1.0 - p["reo_discount"])

    mi = np.zeros_like(coupon)
    if "Original LTV" in loans:
        has_mi = pd.to_numeric(loans["Original LTV"], errors="coerce").to_numpy() > 80
        mi = np.where(has_mi, p["mi_coverage"] * claim, 0.0)

    return np.clip(claim - proceeds - mi, 0.0, None)


def modification_loss(modified_balance: np.ndarray, params: dict = PARAMS) -> np.ndarray:
    """Monthly modification loss ($): interest lost from the rate cut on modified loans."""
    return np.asarray(modified_balance, dtype=float) * params["mod_rate_cut"] / 1200.0
