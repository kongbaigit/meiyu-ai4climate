# Online Data and Completeness

This release adds online weather and completeness views while preserving the main 636-day table, 2,544 forecast rows, model parameters, and independent temporal-check results. Latest weather does not refit the model or choose a test threshold.

## What the online view does

The English main app automatically requests the public Ensemble for Hangzhou or Ningbo. The English static historical demo requests its Ensemble view only after the user clicks **Fetch latest data**. The original Python/Chinese research workbench refreshes its button-triggered Forecast view separately. The English pages keep archived ERA5 and SSOD information as explanatory context; they do not claim a complete real-time station-and-forecast implementation. Where a live Ensemble request is made, the page shows retrieval time, cache age, covered days, valid dates, returned location, request URL, and response digest. A failed request is reported separately; successful cached evidence remains available.

| Source | Output | Scope |
| --- | --- | --- |
| Open-Meteo Ensemble, fixed ECMWF IFS 0.25-degree | English main app automatic view; English static demo button-triggered view; seven complete UTC-day windows with ensemble members | Uncalibrated ensemble member fraction; not a validated online probability, shop-flood probability, or loss probability |
| Open-Meteo Forecast, fixed ECMWF IFS 0.25-degree | Button-triggered Latest weather view in the original Python/Chinese research workbench | Gridded numerical forecast; not the English pages' Ensemble path and not a validated online probability |
| Open-Meteo Archive, fixed ERA5 | Archived current-year precipitation and temperature explanation retained in the English pages | Gridded reanalysis; not a station label or a complete real-time implementation |
| NOAA SSODv2, fixed same-station annual file | Archived station-reference completeness explanation retained in the English pages | Not a live station feed; counts only valid daily amount and complete measurement code |

Forecast precipitation represents the preceding hour. A 24-hour window uses 24 full-point timestamps under `(start,end]`; UTC 00:00-24:00 corresponds to Beijing 08:00 to the following day 08:00. Missing any required precipitation hour leaves the window incomplete and no pseudo-total is computed. Temperature and humidity missingness is kept separately.

## Completeness findings

The frozen main calendar has 731 configured days, 670 complete references, and 636 paired days. Sixty-one days lack a complete reference: 58 have incomplete reports and three have no reference report. Another 34 complete reference days lack a pairable forecast. The denominator is the configured calendar; do not inspect only the already filtered 636 rows.

The independent 2026 January-September check has 85 paired days out of 273 and one reference event. On the real network check captured 2026-10-14, the last SSOD report reached October 11, while complete reference coverage still ended at 85 days and the last valid paired day remained March 26. ERA5 was available through October 7 for 280 days, but better background coverage does not repair the station-label gap.

## Cache and reproducibility

The Python cache under `runtime/weather/{location}/{source}` keeps raw responses, snapshots, and an index. Responses and snapshots are SHA-named and never overwritten; the index is atomically replaced. If an index write is interrupted, an older valid cache can still be read. Cache reads re-parse the source and check location, date, unit, model, file boundary, and content digest.

The English main app and static demo request only the allowed Ensemble domain for their live weather path and keep the response in the current browser. The delivered snapshot includes the raw response and is rechecked when loaded offline. It uses its capture time and is not labeled as newly updated. Forecast data older than three hours, or archived background/station reference older than 24 hours when displayed, is stale.

Timeouts, HTTP 429, network failure, wrong station, changed units, duplicate or non-hour timestamps, invalid values, corruption, and future-dated caches have explicit handling. If an Open-Meteo response has no valid precipitation coverage, it does not replace the existing cache. A fully missing SSOD file may still be saved as a coverage-monitoring result. Missingness is never filled as no rain and no observation label is invented.

Sources: [Forecast API](https://open-meteo.com/en/docs), [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), [Open-Meteo terms](https://open-meteo.com/en/terms), and [NOAA SSOD](https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly/synoptic-summary-of-the-day). Open-Meteo is used for non-commercial research with CC BY 4.0 attribution; NOAA source and upstream notices are retained. Browser, rate-limit, and network state can affect refresh, so the page reports actual results.
