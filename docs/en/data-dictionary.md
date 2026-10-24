# Unified Sample Data Dictionary

One row represents one Xiaoshan Airport nominal UTC-day reference precipitation window paired with the specified fixed-lead ECMWF hourly sequence. The SSOD day is UTC 00:00 to the next 00:00, or Beijing 08:00 to the next day 08:00. `passed` means that the project filtering and pairing rules passed; it does not mean that the daily rainfall was independently confirmed.

| Field | Meaning, unit, and limitation |
| --- | --- |
| `sample_id` | Unique ID determined by the observation window and forecast source definition |
| `observation_window_id` | Reference observation-window ID; forecast versions cannot be counted as independent weather events |
| `forecast_spec_id` | Forecast-request definition ID, traceable in `source_manifest.json` |
| `station_id` | SSOD station `CHI0000ZSHC`; processed separately from the GHCN urban station |
| `station_name` | Provider station name `XIAOSHAN` |
| `station_lat`, `station_lon` | Reference station coordinates in decimal degrees, not a shop location |
| `window_start_utc`, `window_end_utc` | UTC timestamps with `Z`; 24-hour window |
| `observed_rain_mm` | SSOD reference-day precipitation in millimeters; may under-report and is not flood depth |
| `observation_measurement_code` | `D` four 6-hour reports, `F` two 12-hour reports, `G` one 24-hour report, `24` 24 hourly reports; current sample is all `G` |
| `reference_kind` | `ssod_derived_station`, preserving derived daily-summary identity |
| `window_basis` | `nominal_utc_synoptic_day`, preserving nominal day-boundary identity |
| `forecast_model` | `ecmwf_ifs025`, fixed model; not variable Best Match |
| `forecast_kind` | `fixed_lead_composite`, a fixed-lead hourly composite |
| `run_init_utc` | Empty because there is no unique initialization; do not invent one |
| `available_at_utc` | Empty because actual public-availability time was not verified |
| `availability_evidence` | Empty; a real decision replay requires separate publication-time evidence |
| `decision_time_utc` | Empty; no historical operational decision time is defined |
| `forecast_rain_mm` | Accumulated precipitation from 24 complete hourly forecasts in millimeters |
| `forecast_temperature_mean_c` | Mean temperature for the 24 valid forecast times in degrees Celsius; empty when missing |
| `forecast_relative_humidity_mean_pct` | Mean relative humidity for the valid times in percent; empty when missing |
| `experiment_kind` | `offline_fixed_lead`; must not be rewritten as an operational forecast score |
| `quality_status` | `passed`, meaning only project rules passed |
| `audit_version` | Parser and filtering-rule version |
| `obs_record_id` | Reference-record ID in `observations.csv` |
| `forecast_record_id` | Forecast-source ID plus paired window start and end |
| `source_manifest_id` | Matching `manifest_id` in `source_manifest.json` |
| `split` | Main table is `unassigned`; frozen split is in `artifacts/sample_splits.csv` |

Open-Meteo precipitation timestamps represent the preceding hour. Therefore the 24 timestamps use $(t_0,t_1]$ and cover the hourly intervals $[t_0,t_1)$. Any missing hour, non-finite value, or negative precipitation excludes the pair; nothing is filled with zero. See the [Open-Meteo field documentation](https://open-meteo.com/en/docs).

The forecast request is 30.2283 N, 120.4317 E; the returned grid is approximately 30.25 N, 120.5 E. Grid-station differences do not support a shop-level or campus-level flood conclusion. Exact returned coordinates and elevation are in the source manifest.

## Supporting tables

`observations.csv` preserves complete SSOD reference totals and GHCN urban-station records. GHCN uses `window_basis=nominal_date_only` and `boundary_status=unverified`; its UTC date is a retrieval placeholder, not a proven accumulation interval. It is not in the main table.

`quarantined_records.csv` preserves excluded ISD, SSOD, and forecast-pair windows. `reason` can contain multiple semicolon-separated reasons. A record is not an independent weather event, and its 4,681 rows must not be called missing days.

`source_manifest.json` stores request URL, source ID, download time, raw-byte SHA-256, license notes, and local snapshot path. `data_quality.json` stores hashes for the sample CSV and source manifest; the app rejects inconsistent packages.

## Coverage denominators

The configured calendar is two complete UTC years, 2024 and 2025, totaling 731 days. Complete SSOD candidates are 670 days; 61 lack a complete reference total. Of the candidates, 636 pair with a complete forecast window, while 34 lack a complete forecast. Candidate retention is $636/670$ and calendar coverage is $636/731$; do not mix them. Filtering May-July identifies months only and does not claim official yearly plum-rain start or end dates.
