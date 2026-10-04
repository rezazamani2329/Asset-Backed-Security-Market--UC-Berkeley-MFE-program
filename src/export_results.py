"""Export shareable results: CSV tables in outputs/tables/ and notebook charts in outputs/figures/.

Only pooled results are written (no loan-level rows).
    python -m src.export_results            # tables + figures
Calibration tables need the Freddie data (run notebook 05 or 07 first); they are skipped
if data/processed/freddie/ is missing.
"""
import base64
import re
from pathlib import Path

import nbformat
import numpy as np
import pandas as pd

from src import collateral_projection as cp, credit_model as cm, prepayment as pp

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
FIGURES = ROOT / "outputs" / "figures"
N_MONTHS = 53

# Valuation state is after the September 2026 payment, but the loan-level tape is the
# post-August pool. Bloomberg CLP (STACR_2026-DNA1_Bloomberg_CLP_2026-10-02.xlsx,
# "Balance (M)" row, reported in $000s) gives the September pool balance.
SNAPSHOT_POOL_BALANCE = cp.SNAPSHOT_POOL_BALANCE   # kept for older imports; see cp.load_pool

PLACEHOLDER = {
    "prepayment": {"turnover": 0.06, "refi_max": 0.55, "midpoint": 0.75, "slope": 3.5,
                   "burnout": 0.02, "ramp_months": 30},
    "credit": {"base_cdr": 0.0020, "b_ltv_low": 0.04, "b_ltv_high": 0.10, "b_fico": 0.012,
               "b_dti": 0.02, "investor_mult": 1.5, "dq30_extra_mdr": 0.01, "dq30_months": 12,
               "liq_lag": 12, "costs": 0.10, "reo_discount": 0.20, "mi_coverage": 0.25,
               "mod_share": 0.25, "mod_rate_cut": 2.0},
}


def scenario_tables(pool: pd.DataFrame) -> None:
    paths = cp.get_scenarios(None)
    n_months = len(next(iter(paths.values()))["rate"])
    res = cp.run_scenarios(pool, paths, n_months)
    rows = {}
    for name, df in res.items():
        df.to_csv(TABLES / f"pool_cf_{name}.csv", index=False)
        smm = (df.prepayments / (df.beginning_balance - df.scheduled_principal)).to_numpy()
        rows[name] = {
            "cpr_year1_pct": pp.smm_to_cpr(smm[:12]).mean() * 100,
            "start_balance_bn": df.beginning_balance.iloc[0] / 1e9,
            "end_balance_bn": df.ending_balance.iloc[-1] / 1e9,
            "prepayments_mm": df.prepayments.sum() / 1e6,
            "scheduled_principal_mm": df.scheduled_principal.sum() / 1e6,
            "credit_events_mm": df.defaults.sum() / 1e6,
            "losses_mm": df.losses.sum() / 1e6,
            "loss_pct_of_cutoff": df.losses.sum() / cp.CUTOFF_BALANCE * 100,
            "avg_severity_pct": df.losses.sum() / max(df.defaults.sum(), 1) * 100,
            "modification_losses_mm": df.modification_losses.sum() / 1e6,
            "peak_distressed_balance_mm": df.distressed_balance.max() / 1e6,
        }
    pd.DataFrame(rows).T.rename_axis("scenario").round(4).to_csv(TABLES / "scenario_summary.csv")
    pd.DataFrame({"scenario": list(paths), "hpi_end": [p["hpi"][-1] for p in paths.values()],
                  "mortgage_rate_pct": [p["rate"][0] for p in paths.values()]}).to_csv(
        TABLES / "scenario_paths_used.csv", index=False)


def params_table() -> None:
    rows = []
    for model, fitted in [("prepayment", pp.PARAMS), ("credit", cm.PARAMS)]:
        for k, v in fitted.items():
            rows.append({"model": model, "parameter": k, "placeholder": PLACEHOLDER[model].get(k), "fitted": v})
    pd.DataFrame(rows).to_csv(TABLES / "fitted_params.csv", index=False)


def calibration_tables() -> None:
    from src import calibration as cal, freddie as fr
    if not (fr.OUT / "panel_2007.parquet").exists():
        print("Freddie panels not found; skipping calibration tables")
        return
    r = cal.run_all(fr.load_fred("HPIPONM226S"), fr.load_fred("MORTGAGE30US"))
    fit = cal.calibrate(r)

    b = r["prepay"]; b = b[b.n >= 200].copy()
    b["fit"] = cal.prepay_model_smm(list(fit["prepayment"].values()), b.inc, b.age, b.burn)
    g = b.assign(o=b.smm * b.w, f=b.fit * b.w).groupby("inc_b")[["o", "f", "w", "wi", "n"]].sum()
    pd.DataFrame({"incentive_pp": g.wi / g.w, "loan_months": g.n,
                  "observed_cpr": pp.smm_to_cpr(g.o / g.w), "fitted_cpr": pp.smm_to_cpr(g.f / g.w)}
                 ).round(4).to_csv(TABLES / "calibration_prepay_by_incentive.csv", index=False)

    d = r["default"]
    X = pd.DataFrame({"const": 1.0, "ltv_low": np.minimum(d.ltv - 80, 0), "ltv_high": np.maximum(d.ltv - 80, 0),
                      "fico": d.fico - 750, "dti": d.dti - 38, "investor": d.investor, "pre2009": d.pre2009})
    d = d.assign(fit=fit["diagnostics"]["glm"].predict(X, offset=np.log(d.n)))
    for key, name in [("ltv_b", "ltv"), ("fico_b", "fico"), ("dti_b", "dti")]:
        t = d.groupby(key)[["n", "events", "fit"]].sum()
        t = t.assign(observed_annual_pct=t.events / t.n * 1200, fitted_annual_pct=t.fit / t.n * 1200)
        t.rename_axis(f"{name}_bucket").round(4).to_csv(TABLES / f"calibration_default_by_{name}.csv")
    glm = fit["diagnostics"]["glm"]
    pd.DataFrame({"coef": glm.params, "std_err": glm.bse, "z": glm.tvalues}).round(5).to_csv(
        TABLES / "calibration_default_glm.csv")

    c = fit["credit"]
    liq = cal.clean_liquidations(r["liquidations"])
    liq = liq.assign(model=cal.severity_model(liq.ltv.values, liq.rate.values, liq.has_mi.values,
                                              c["costs"], c["reo_discount"], c["liq_lag"], c["mi_coverage"]),
                     ltv_bucket=pd.cut(liq.ltv, [0, 50, 60, 70, 80, 90, 100, 120, 300]))
    liq.groupby("ltv_bucket", observed=True).agg(liquidations=("upb", "size"), observed_median=("severity", "median"),
                                              model_median=("model", "median")).round(4).to_csv(
        TABLES / "calibration_severity_by_ltv.csv")

    diag = fit["diagnostics"]
    rec = liq[liq.start >= 201301]
    pd.Series({
        "default_spells": diag["n_default_events"], "liquidations": diag["n_liquidations"],
        "median_months_to_credit_event_2013plus": float(np.median(rec.months_90_to_liq + 2)),
        "share_90plus_liquidated_2013plus": diag["p_liquidated"],
        "share_90plus_modified_2013plus": diag["p_modified"],
        "rate_cut_if_modified_pp": diag["rate_cut_if_modified"],
        "dq30_reach_90plus_in_12m": diag["dq30_12m_roll"],
        "pre2009_default_multiplier": diag["pre2009_mult"],
    }, name="value").round(4).to_csv(TABLES / "calibration_pipeline_summary.csv")


def figures() -> int:
    """Save every chart embedded in notebooks/0*.ipynb as a PNG, named after its section."""
    n = 0
    for path in sorted((ROOT / "notebooks").glob("0*.ipynb")):
        nb = nbformat.read(path, 4)
        section, k = "intro", 0
        for cell in nb.cells:
            if cell.cell_type == "markdown":
                m = re.search(r"^#{2,3}\s+(.+)$", cell.source, re.M)
                if m:
                    section, k = m.group(1), 0
                continue
            for out in cell.get("outputs", []):
                png = out.get("data", {}).get("image/png")
                if not png:
                    continue
                k += 1
                slug = re.sub(r"[^a-z0-9]+", "_", section.lower()).strip("_")[:60]
                (FIGURES / f"{path.stem[:2]}_{slug}{'_' + str(k) if k > 1 else ''}.png").write_bytes(base64.b64decode(png))
                n += 1
    return n


def main():
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    pool = cp.load_pool()   # post-September pool: rolled-forward August tape, or a September tape
    scenario_tables(pool)
    params_table()
    calibration_tables()
    print(f"tables: {len(list(TABLES.glob('*.csv')))} CSVs in {TABLES}")
    print(f"figures: {figures()} PNGs in {FIGURES}")


if __name__ == "__main__":
    main()
