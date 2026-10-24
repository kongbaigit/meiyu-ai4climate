# Independent Temporal Validation Protocol

**Protocol saved:** 2026-10-13 evening, before downloading and analyzing the 2026 SSOD reference precipitation.  
This is a locally saved internal protocol, not a third-party public preregistration and not a prospective operational pilot.

## Question

Does the Hangzhou rainfall-probability mapping fitted in 2024 and selected in January-April 2025 retain a describable result in a later, not-yet-analyzed period? This check freezes the method. It does not update the model, change the station, or choose months because they look favorable.

## Fixed scope

- **Reference station:** Xiaoshan Airport `CHI0000ZSHC`, same as the main experiment.
- **Period:** 2026-01-01 00:00 UTC through 2026-10-01 00:00 UTC, 273 complete nominal days. Incomplete October is excluded; the subset is not selected for plum-rain conditions.
- **Observation:** NOAA SSODv2, keeping only D/F/G/numeric-24 complete codes. Missing, partial, H/I, and unknown codes are quarantined.
- **Forecast:** Same Open-Meteo Previous Runs `ecmwf_ifs025` `previous_day1` sequence. Sum the 24 hours in `(start,end]`; missing, negative, or non-finite values are not filled with zero.
- **Event:** Reference precipitation reaches 25 mm, retaining the main definition. It is not a flood label or official warning level.

## Frozen model identity

- Dataset version: `meiyu-493c58d793af9bf4`
- Selected method: `logistic_rain`, `C=10`, fitted only on the 2024 training segment
- Model-parameter SHA-256: `297f0d6e4a574b634848fbd92a4354b7b91383439e29b404e2f81e0e5ac60418`
- Main-prediction SHA-256: `65096b2db07625826ad9ea90e2ca9d373fe5f18c088bc50b80a0dc6e349fc961`
- Main-evaluation SHA-256: `f14becfd108b0d4ef0b45a72b726e5d91a4a2c2bc12caf484caf46748f6ecbf2`

The fixed event rate remains 16/276. The raw rule remains forecast-day rain reaching 25 mm. Reuse the selected precipitation model's imputation, standardization, coefficients, and intercept. The temperature/humidity model can be reported as a frozen comparison but must not replace the selected model. Do not call `fit`, select a new `C`, change the recommended method based on 2026, or overwrite the main result.

## Reporting and stopping rules

First report source accessibility, reference-row count, complete candidate days, paired days, missingness, and event count. Every comparison uses the same available days.

If a sample can be formed, report Brier, ROC-AUC, average precision, the fixed 10% threshold confusion matrix, and the five probability bins for all four frozen methods. If enough non-empty calendar weeks exist, use seed `20261013` and 2,000 paired-week-block resamples. If the sample or event count is too small, say so; do not compute AUC/AP for a single class. Keep the six original hypothetical cost ratios, without describing them as measured gain.

If complete reference is unavailable, forecast cannot be obtained, or unit/time fields cannot be checked, stop pairing and the effect claim. Do not solve the data block by replacing the station or relaxing completeness. Whether the result improves, ties, or worsens, preserve source, sample, errors, and all metrics; do not update the main model.

## Remaining limits

Same-station later data is not cross-station validation. SSOD under-reporting, nominal UTC-day boundaries, composite forecasts from different initializations, and unverified public availability time remain limitations. An archived offline check cannot prove user benefit, climate trend, or that a real decision maker had this information at the claimed time.
