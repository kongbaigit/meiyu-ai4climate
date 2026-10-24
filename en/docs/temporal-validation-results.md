# 2026 Independent Temporal Check Results

**Conclusion:** coverage is insufficient to validate 2026 plum-rain performance. The January-September plan covers 273 configured days but yields only 85 complete paired days and one reference event, or 31.1% calendar coverage. Complete reference reaches only January-March; missing April-September does not mean no rain.

| Month | Configured days | Paired days | Reference events |
| --- | ---: | ---: | ---: |
| 2026-01 | 31 | 31 | 0 |
| 2026-02 | 28 | 28 | 1 |
| 2026-03 | 31 | 26 | 0 |
| 2026-04 | 30 | 0 | Not defined |
| 2026-05 | 31 | 0 | Not defined |
| 2026-06 | 30 | 0 | Not defined |
| 2026-07 | 31 | 0 | Not defined |
| 2026-08 | 31 | 0 | Not defined |
| 2026-09 | 30 | 0 | Not defined |

The model read the original parameters directly; it did not fit or select a new method. These Brier scores describe only the small available sample and cannot be subtracted from the main test score as evidence of improvement. The additional sample is stored as `meiyu-temporal-35047953133d42d2`; it is not merged into the main 636 days or the 2025 240-day test.

| Frozen method | Additional-sample Brier | Role |
| --- | ---: | --- |
| `training_climatology` | 0.013761 | Comparison; not reselected |
| `raw_nwp_rule` | 0.011765 | Comparison; not reselected |
| `logistic_rain` | 0.010539 | Validation-selected original method |
| `logistic_weather` | 0.010136 | Comparison; not reselected |

Complete AUC/AP, confusion matrix, five probability bins, weekly block resampling, and six hypothetical CNY cost points are in [`reports/temporal_validation.json`](https://github.com/kongbaigit/meiyu-ai4climate/blob/main/reports/temporal_validation.json). With one event, ranking and frequency numbers are unstable; the paired-Brier interval versus the raw rule crosses zero. This check is not a stable gain claim.

The internal protocol was saved at `2026-10-13T15:10:43.5946991+00:00`, before the source download. Protocol SHA-256 is `5a31d8c9960d409791fc93549ce393702a611303b21b1a5261f54de117e1f4bc`. This is not a public preregistration or prospective operational pilot. The NOAA raw file has 284 rows; October records did not enter the formal sample. Main model, main data, and main-prediction hashes remain unchanged.

The main experiment remains limited by SSOD under-reporting, nominal UTC-day boundaries, and composite fixed-lead forecasts. The next step is to obtain complete independent-season reference and verified public-availability timing before discussing broader use.
