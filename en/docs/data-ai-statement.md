# Data and AI Statement

**Meiyu Prepare / AI for Climate**  
English release prepared 2026-10-24. The source weather snapshot referenced below was captured on 2026-10-19; these are separate dates.

## Purpose and current status

Meiyu Prepare uses public data and local statistical-learning code to study an offline method for rainfall reference events and to explain preparation costs for small shops considering stock relocation. It is a research prototype, not an official warning service, a shop-flood predictor, or a loss-probability product. The project has not yet completed real merchant validation, measured avoided loss, demonstrated revenue impact, or demonstrated carbon reduction. No equipment was purchased, no school or merchant back-office data was connected, and no personal information was collected.

All cost examples are user-entered scenario assumptions in CNY. They are not measured shop costs, loss estimates, or evidence of financial benefit.

## Data sources

| Source | Use in this project | Main limitation |
| --- | --- | --- |
| [NOAA SSODv2](https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly/synoptic-summary-of-the-day) | Archived station-reference information used to explain historical labels and completeness in the English pages | Daily summaries may under-report; a complete measurement code is not a high-precision ground truth. It is not a live station feed in the English pages. |
| [NOAA SSOD format documentation](https://www.ncei.noaa.gov/oa/synoptic-summary-of-the-day/v2/doc/ssodv2_DOCUMENTATION.pdf) and [NOAA ISD format documentation](https://noaaisd.blob.core.windows.net/noaa-isd/pub/data/noaa/isd-format-document.pdf) | Check day boundaries, units, AA1-AA4 fields, and reporting codes; record exclusion reasons | The available file does not provide a conservative, complete 24-hour truth for the excluded cases, so those cases do not build labels. |
| [GHCN-Daily](https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt) | Cross-reference for an urban Hangzhou station | It is a different station and its row-level day boundary was not verified; it is not merged with the airport record. |
| [Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api) | A daily sequence from ECMWF IFS 0.25-degree forecasts at a fixed lead | Daily aggregation can combine valid times from different initializations. We have not established that the full set was publicly available at one decision time. |
| [Open-Meteo Forecast API](https://open-meteo.com/en/docs) | Button-triggered **Forecast** in the original Python/Chinese research workbench (`app.py`) for Hangzhou or Ningbo | It is gridded numerical weather prediction, not an observation or replay of one frozen initialization. This source is not an ensemble source. |
| [Open-Meteo Ensemble API](https://open-meteo.com/en/docs/ensemble-api) | Automatic **Ensemble** in the English main app (`/en/`); button-triggered **Ensemble** in the English static historical demo (`/en/demo.html`) | ECMWF members are uncalibrated numerical forecast samples. Member fractions are internal ensemble frequencies, not shop-flood or loss probabilities. |
| [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) | Archived ERA5 precipitation and temperature context shown for explanation in the English pages | Reanalysis is not a station observation, is not a complete real-time English-page implementation, and is not used to fill SSOD labels or the main experiment. |
| Public Hangzhou and Zhejiang materials | Context for the problem and a preparation checklist | There are no local merchant interviews, intent measurements, or payment validation. Adaptation suggestions are not official merchant instructions. |

The complete source URLs, byte hashes, retrieval times, and returned coordinates are recorded in `data/source_manifest.json`. Local source links and scope notes are in `docs/action_sources.md`.

The additional 2026 same-station check is kept separately in `external/hangzhou_2026` and is not added to the main 636-day sample. Of 273 configured days from January through September 2026, only 85 are complete paired days and there is one reference event. Complete reference coverage reaches only January through March; April through September lack complete references. We therefore do not claim to have validated 2026 plum-rain-season performance. Metrics, monthly coverage, source summaries, and evidence for retaining the original model are in `reports/temporal_validation.json`.

## Historical experiment and model boundary

The historical experiment uses 636 paired days. The configured split is 276 training days, 120 validation days, and 240 test days, with 18 reference events in the test set. The event threshold is 25 mm of nominal UTC-day reference precipitation. This is a research threshold, not an official warning level.

The AI task is to map numerical-weather inputs to the probability that the reference event reaches that threshold, then compare that mapping with simple methods on the same held-out test days. The selected method is a small logistic regression using the precipitation feature (`logistic_rain`), with `C=10` selected only on the validation segment. The test Brier scores are 0.0455 for the selected precipitation-probability model and 0.0697 for the fixed training-period event-rate baseline. A precipitation-plus-temperature/humidity model scored 0.0444 as a complete comparison but was not selected. Lower Brier is better.

The model is a frozen offline research result. It does not retrain in the browser, select a test threshold, or create a prediction without a source. The page's current-weather view is a separate public forecast display. It must not be described as the historical model running online.

The original continuous-rain rule and the selected model have the same ROC-AUC of 0.9712. The model preserves the rainfall ordering while adding a probability expression; it does not establish new weather-ranking ability. The validation set contains only three events and the test set contains 18, so some probability bins under-estimate event frequency. The frozen report also retains the original 25-mm rule's 0/1 squared-error score of 0.0625.

## Online weather, cache, and completeness

Online weather and the frozen experiment are stored separately. The Python online cache under `runtime/weather` keeps the raw response, content hash, retrieval time, and source-specific completeness checks; files are content-addressed and the index is atomically replaced. The HTML application keeps a browser-local cache. Freshness is calculated from retrieval time: a forecast older than three hours, or background/station reference older than 24 hours, is marked stale. Retrieval time is not the weather model initialization time or the provider's publication time.

The three relevant paths have different network behavior:

- The English main app (`/en/`) automatically requests Hangzhou **Ensemble** weather and reuses a valid browser cache when available.
- The English static historical demo (`/en/demo.html`) keeps the historical evidence offline; its **Latest weather & completeness** view requests **Ensemble** only after the user clicks the refresh button.
- The original Python/Chinese research workbench (`app.py`) keeps its **Latest weather** page button-triggered and uses **Forecast**, not Ensemble.

Timeouts, rate limits, wrong units, a wrong station, duplicate timestamps, and malformed responses do not replace a valid cache. A 24-hour window with missing hourly precipitation is not assigned a complete total and is not filled with zeros. Ensemble member fractions describe internal numerical-forecast frequency only. They are uncalibrated, and are not shop-flood or loss probabilities. The Forecast API cannot be presented as an ensemble source.

The delivered weather snapshot is a real retrieval that can be checked against its raw response and is labeled with its own capture time. The snapshot captured on 2026-10-19 must not be presented as freshly updated when a page is opened offline. ERA5 and SSOD shown in the English pages are archived explanatory information, not a claim that those pages implement a complete real-time station-and-forecast service. The English main app's automatic **Ensemble**, the English static demo's button-triggered **Ensemble**, and the original workbench's button-triggered **Forecast** are distinct behaviors.

## AI assistance, software, and human responsibility

Codex assisted with locating public entry points, drafting parsers, writing tests, building the app, and preparing materials. The code uses Python, pandas, NumPy, scikit-learn, Streamlit, and Plotly. This stage does not require an OpenAI API key, and language-model prose is not used as rainfall data, labels, or a weather decision.

The human team must verify team identity, contact details, submission fields, user assumptions, source links, and final claims. Team names, organization, and email are intentionally left for the team to fill in; none are invented here.

The selected promotional video is 73.866666667 seconds long, 1920x1080 at 30 fps, 2,216 frames, and 10 scenes. Frames were generated programmatically and encoded with WebCodecs; screenshots, screen recordings, and external image/video inputs were not used as visual inputs. The video has one AAC audio track and no narration or other voice-over. Music is **Young Visionaries - Eric Matyas**, used under the [Soundimage International Public License](https://soundimage.org/sample-page/), with the attribution `Music by Eric Matyas / www.soundimage.org`. The source page is [soundimage.org/techno](https://soundimage.org/techno/). The source excerpt is 17.313872945628-91.180539612295 seconds, at original speed and pitch, continuously cut with fades at the ends and no loop. Source project files and third-party library notices are provided under `media/latest/source/`.

The separate English cut is `media/en/meiyu-prepare-en.mp4`: 87.066666667 seconds, 1920x1080, 30 fps, 2,612 frames, 10 scenes, and 132 beats, with one AAC track and no voice-over. Its source excerpt is 6.764338247872-93.831004914539 seconds, at original speed and pitch. The current file size and SHA-256 are recorded in `media/en/video-info.json` and `docs/en/video-technical-check.json`. Independent visual and technical checks for the current English cut are recorded there; full team viewing/listening remains pending. See README.en.md for verified publication status; the Chinese and English media are separate assets.

## Use, licensing, and limits

Open-Meteo data is attributed under its [CC BY 4.0 and terms of use](https://open-meteo.com/en/terms); the free endpoint is used for this non-commercial research, and source attribution must be retained. NOAA files retain the agency and upstream information stated by their source; the project does not assume ownership of every upstream record. The project's code license does not cover third-party data, documentation, or libraries. The music remains under the Soundimage International Public License and is not described as Creative Commons or an equivalent license.

Meiyu Prepare is positioned as a climate-adaptation and preparedness prototype. It asks whether people can understand uncertainty and choose suitable stock-relocation preparations. That question requires later pilot validation. The project has not shown reduced real-world damage, increased operating income, avoided loss, or carbon reduction. Outputs are not official weather warnings, emergency instructions, or shop-flood forecasts.

## Reproducibility references

The frozen model version and scores are recorded in `reports/evaluation.json` and `reports/experiment_run.json`; source manifests and public-data snapshots are retained in the repository. The English materials are prepared on 2026-10-24, while historical and capture dates remain as recorded in the source evidence.
