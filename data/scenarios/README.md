# Scenario paths (Coco)

Drop `scenarios.csv` here. When it exists, `collateral_projection.get_scenarios()` (and
notebook 03) use it instead of the interim placeholder paths.

Format: one row per scenario per month, months 0 to 53 (today to the Feb 2031 call).

| column | meaning |
|---|---|
| `scenario` | name, e.g. `good`, `base`, `moderate`, `severe` |
| `month` | 0, 1, ..., 53 (month 0 = today) |
| `mortgage_rate` | 30-year market mortgage rate in % (Freddie PMMS-type), not SOFR or Treasuries |
| `hpi_index` | national house-price index level, any base (rescaled so month 0 = 1.0) |

Optional extra columns (e.g. `date`, `sofr`) are ignored by the collateral model.

```
scenario,month,mortgage_rate,hpi_index
base,0,7.28,100.0
base,1,7.27,100.25
...
```
