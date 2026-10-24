# Meiyu Prepare: Making Rainfall Probability an Explainable Preparation Reference

**English release prepared 2026-10-24**  
Hangzhou Xiaoshan Airport public reference point | Offline method prototype | AI for Climate

## Problem and intended users

Meiyu Prepare is for small shops in Hangzhou that may need to sort or relocate moisture-sensitive stock before a heavy-rain scenario. Public market monitoring describes effects of prolonged rain on product quality, harvesting, storage, and transport, but there is no evidence yet that a particular shop needs this prototype, would use it, or would pay for it. Those assumptions remain to be tested with merchants.

The climate value is adaptation and preparedness. Two years of one-station data cannot attribute climate change or establish a long-term trend. Airport precipitation is not shop flooding, and the prototype does not issue official warnings.

| Main experiment | Count |
| --- | ---: |
| Paired historical days | 636 |
| Training / validation / test days | 276 / 120 / 240 |
| Test reference events | 18 |

The interactive history view lets a user choose a window, inspect a probability, compare a hypothetical stock-relocation cost in CNY, and then reveal the reference precipitation. It is a runnable research prototype, not evidence of merchant loss avoidance, revenue impact, carbon reduction, or payment.

## Method and result

The AI task is to map public numerical-weather inputs to the probability that nominal UTC-day reference precipitation reaches 25 mm. The threshold is a research definition, not an official warning level. A small logistic regression (`logistic_rain`, `C=10`) was selected only on the validation segment. The language model does not generate observations or labels.

| Method | Test Brier | Role |
| --- | ---: | --- |
| Fixed training-period event rate | 0.0697 | Baseline |
| Selected precipitation-probability model | 0.0455 | Validation-selected |
| Precipitation + temperature/humidity comparison | 0.0444 | Complete comparison, not selected |

Lower Brier is better. On the same 240 test days, the selected model has a fixed 10% scenario-threshold confusion count of 12 hits, 6 misses, 9 false alarms, and 213 correct exclusions. The original 25-mm rule has 7 hits, 11 misses, 4 false alarms, and 218 correct exclusions. Fewer misses come with more false alarms; this is not an equal-false-alarm-rate comparison. The original rainfall rule and selected model have the same ROC-AUC, 0.9712, so the model adds a probability expression rather than new rainfall-ranking ability. The selected probability result should not be described as a calibrated operational forecast.

## Product and data boundary

The English main app (`/en/`) provides the stock-relocation decision and automatically requests the public Hangzhou **Ensemble**. The English static historical demo (`/en/demo.html`) keeps the historical evidence offline and its **Latest weather & completeness** view requests **Ensemble** only after the user clicks. The original Python/Chinese research workbench (`app.py`) remains a separate button-triggered **Forecast** workbench.

The English pages show numerical forecast evidence, archived ERA5 explanatory context, and archived SSOD reference completeness as separate concepts. They do not claim a complete real-time station-and-forecast implementation. Where the English Ensemble view is available, it shows seven complete future UTC-day windows for Hangzhou or Ningbo, with retrieval time, source, and completeness; an incomplete or stale result pauses the current conclusion. These paths and the original workbench must not be conflated.

| Evidence | What it supports | What it does not support |
| --- | --- | --- |
| 2024-2025 main data | 731 configured days, 670 complete references, 636 paired days | Missing days are not no-rain days |
| 2026 Jan-Sep check | 85/273 paired days and one event | April-Sep lack complete reference; no 2026 plum-rain validation claim |
| Ningbo 2025 | 362 precipitation-reference rows are missing | No cross-city transfer result |
| ERA5 background | Source-labeled historical context | Not a station label and cannot fill a missing label |
| Latest numerical forecast | A source- and time-labeled public update | Not the frozen historical probability model and not an observation |

The primary reference is the airport's nominal UTC day, which may under-report and does not prove exact accumulation boundaries. Previous Runs daily aggregation can combine different initializations; public availability at one historical decision time has not been established. We therefore do not claim a 24-hour operational warning lead time. All sources, quality notes, and hashes remain traceable. The data version is `meiyu-493c58d793af9bf4`.

## Decision cost example

Let $p$ be the scenario event estimate, $C$ the stock-relocation cost, and $L_0$ and $L_1$ the conditional average losses without and with relocation. The page compares only the additional scenario cost:

$$
E_{\text{keep}}=pL_0,\qquad E_{\text{relocate}}=C+pL_1.
$$

The expected difference is $p(L_0-L_1)-C$. A positive value favors **Relocate**, a negative value favors **Keep in place**, and zero displays a tie. The comparison uses unrounded values internally and shows two decimals. It is a hypothetical scenario, not realized income or loss.

For the 60% example with relocation cost $C=\mathrm{CNY}\ 80$, conditional losses $L_0=\mathrm{CNY}\ 1000$ and $L_1=\mathrm{CNY}\ 100$, the hypothetical totals are CNY 600 for **Keep in place** and CNY 140 for **Relocate**, a difference of CNY 460. The tie cost is $C=\mathrm{CNY}\ 540$; at $C=\mathrm{CNY}\ 600$, choose **Keep in place**. These figures are illustrative only.

## 90-day validation

The first 90 days focus on understanding, operation, and real forecast availability, not on claiming a new plum-rain-season result:

1. Confirm the user assumptions and recruit 5-8 voluntary participants.
2. Use fixed historical cases to test whether participants can interpret probability, UTC-day boundaries, non-flood meaning, and hypothetical costs.
3. Verify when a single forecast is publicly available before a decision, then run in shadow mode and stop when source or completeness evidence is missing.
4. Review misunderstandings and failures, run a second comprehension round, and decide whether to continue, revise, or narrow the product.

The plan target is at least 80% completing the key operation within three minutes and correctly explaining the core limits. These are pre-specified exploratory targets, not completed user results. The 90-day window does not cover a complete next plum-rain season.

## Team, AI use, and delivery status

Team names, organization, role allocation, and contact email are intentionally blank for the team to complete. Codex assisted with public-source lookup, parsing, tests, app implementation, and material drafting. The core model runs locally. The Chinese release film is retained at 73.866666667 seconds, 1920x1080, 30 fps, 2,216 frames, and 10 scenes, with instrumental music and no voice-over; its music is Young Visionaries by Eric Matyas under the Soundimage International Public License, attributed as `Music by Eric Matyas / www.soundimage.org`. The English native-animation cut is 87.066666667 seconds, 1920x1080, 30 fps, 2,612 frames, 10 scenes, and 132 beats, with the same instrumental track and no voice-over. English entry points are `/en/`, `/en/promo/`, and `/en/materials/`. See README.en.md for verified publication status.

The repository includes source code, public-data snapshots, frozen results, the current media source, and validation materials. It does not include proof of real merchant use, avoided loss, payment, or carbon benefit.

## References

Public data and official-source links are listed in the [Data and AI Statement](data-ai-statement.md), [online-data-completeness](online-data-completeness.md), and [action sources](action-sources.md). Reproducibility and packaging instructions are in [reproduction-and-delivery](reproduction-and-delivery.md).
