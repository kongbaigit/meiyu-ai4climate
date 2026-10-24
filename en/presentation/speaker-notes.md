# Meiyu Prepare: three-minute speaker notes

Suggested delivery: 180 seconds across 10 slides. Speech length: 429 words.

The spoken script appears first for each slide. Source and definition notes are for reference.

## 01. Meiyu Prepare (15 seconds)

We are two students building Meiyu Prepare. Our prototype helps small shops in Hangzhou compare the expected cost of relocating stock before rain with the expected cost of keeping it in place. Merchant validation is still pending.

Sources:

- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/README.md
- https://github.com/kongbaigit/meiyu-ai4climate

Definitions and limits:

- Target users and their needs remain hypotheses. The project has no completed merchant interviews.

## 02. The small shop dilemma (17 seconds)

Relocation takes labour and materials. Keeping stock in place avoids that immediate expense but leaves exposure. We focus on this specific choice. The need is a hypothesis, so the prototype first makes its inputs and assumptions visible.

Sources:

- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/docs/decision-guide.md
- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/docs/90%E5%A4%A9%E9%AA%8C%E8%AF%81%E8%AE%A1%E5%88%92.md

Definitions and limits:

- No completed merchant recruitment or needs validation supports the target-user statement.

## 03. A single 24-hour decision (17 seconds)

Users choose a location and a 24-hour window, then enter relocation cost and conditional losses for both options. The page compares expected total costs and retains the sources. Missing members, missing hours or stale weather data stop the weather calculation.

Sources:

- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/README.md
- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/docs/decision-guide.md

Definitions and limits:

- The workflow describes implemented prototype behaviour, not observed merchant usage.

## 04. Paired historical data (20 seconds)

Each row pairs a forecast and reference rainfall over the same 24 hours. The configured calendar has 731 days across 2024 and 2025. There are 670 complete reference days and 636 complete pairs. We exclude incomplete windows rather than treating missing observations as zero rain.

Sources:

- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/data/samples.csv
- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/docs/data_dictionary.md
- https://open-meteo.com/en/docs
- https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly/synoptic-summary-of-the-day

Definitions and limits:

- 08:00 to the next 08:00 in UTC+08 corresponds to a nominal UTC day.
- The quality flag passed means the row passed project rules. It does not imply independent validation of the rainfall value.
- The English deck retains the fixed example from the Chinese source deck dated 19 October 2026.

## 05. Historical model and online ensemble (24 seconds)

The historical model and online ensemble have different meanings. The offline example converts 52.5 millimetres into a 67.9 percent probability of the reference rainfall event. The archived online snapshot counts zero of 51 members reaching 25 millimetres. That member fraction lacks local calibration. Neither output is a shop flood or stock loss probability.

Sources:

- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/artifacts/model_parameters.json
- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/artifacts/predictions.csv
- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/reports/evaluation.json
- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/src/decision_weather.py

Definitions and limits:

- Historical model: logistic_rain, trained on 276 days, selected on 120 validation days and evaluated on 240 test days with 18 events.
- The example uses forecast rainfall as its input. Reference rainfall is a later evaluation label.
- Fixed snapshot captured 2026-10-19 19:22 UTC+08 for 2026-10-20 08:00 through 2026-10-21 08:00 UTC+08. It is not current weather.
- Online source: Open-Meteo ECMWF IFS 0.25 degree ensemble, 51 members and 24 required hourly values per member.
- Source snapshot SHA-256: 2c91ea4481afc3ee2d53bbbe863ec4ed8723a693219ca12b8b1bb319090d1a6c

## 06. Expected cost example (21 seconds)

Now consider a hypothetical decision, separate from weather forecasts. Assume a 60 percent event probability, a 1,000-yuan loss if stock stays, a 100-yuan residual loss after relocation, and an 80-yuan relocation cost. Expected costs are 600 and 140 yuan. The 460-yuan difference is a calculation, with no verified merchant savings.

Sources:

- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/docs/decision-guide.md

Definitions and limits:

- Hypothetical inputs: p=0.6, C=80, L0=1000, L1=100, all money in CNY.
- Keep expected cost = pL0. Relocate expected cost = C+pL1. This example assumes no stock loss when the event does not occur.
- C=60 labour + 20 materials is an illustrative decomposition.
- The 60% scenario input does not come from the online ensemble or the historical model.

## 07. Relocation cost sensitivity (17 seconds)

Changing relocation cost changes the choice. At 80 yuan, relocation has the lower expected cost. At 540 yuan, the options tie. At 600 yuan, relocation costs 660 yuan in expectation, so keeping stock has the lower expected cost.

Sources:

- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/docs/decision-guide.md

Definitions and limits:

- The native scatter chart retains the actual numeric distance between costs.
- Keep total cost remains 600. Relocate total cost equals C+60. Break-even cost = p(L0-L1) = 0.6(1000-100) = 540.
- These are hypothetical scenario calculations, not observed merchant outcomes.

## 08. Evidence and limits (20 seconds)

On the held-out test set, logistic rain scores 0.0455 on Brier, compared with 0.0697 for climatology. Lower is better. Yet there are only 18 test events. At a fixed 10 percent scenario threshold, the model misses six events and raises nine false alarms. Merchant and carbon benefits remain unverified.

Sources:

- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/reports/evaluation.json
- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/artifacts/sample_splits.csv
- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/artifacts/predictions.csv

Definitions and limits:

- Both Brier scores refer to the same test split. Climatology is the constant event rate estimated on training data.
- Model selection used validation data. The test period remained separate.
- The 6 missed events and 9 false alarms use a fixed 10% scenario threshold. This is not an equal-false-alarm comparison.
- The project has no verified merchant loss reduction, deployment outcomes or carbon benefit measurements.

## 09. The 90-day plan (19 seconds)

Our pending 90-day plan starts with five to eight willing participants. Fixed historical cases will test understanding, followed by shadow operation and failure logging. We will assess task completion and understanding separately. This is a small usability study. A fresh full Meiyu season is still needed for independent predictive evidence.

Sources:

- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/docs/90%E5%A4%A9%E9%AA%8C%E8%AF%81%E8%AE%A1%E5%88%92.md
- https://github.com/kongbaigit/meiyu-ai4climate/blob/main/docs/%E7%94%A8%E6%88%B7%E6%B5%8B%E8%AF%95%E6%89%A7%E8%A1%8C%E5%8C%85/

Definitions and limits:

- The plan has not been executed and participants have not been recruited.
- Day 1 begins when the team confirms the start date. Weeks describe phases within the 90-day period.
- The 80% target is preregistered for a future study, not an observed result. Independent completion and core understanding are scored separately.
- The planned 90 days do not include the next complete Meiyu rainfall season.

## 10. English demo and source (10 seconds)

The English demo, video and source links are here. Please inspect the calculation and its limits. Our next priority is real user understanding. Thank you.

Sources:

- https://kongbaigit.github.io/meiyu-ai4climate/en/
- https://kongbaigit.github.io/meiyu-ai4climate/en/promo/
- https://github.com/kongbaigit/meiyu-ai4climate

Definitions and limits:

- The links identify the English release destinations. The deck makes no claim that the merchant study has begun.

## Formula reference

All example amounts use CNY. The example assumes no stock loss when the event does not occur.

$$E_{\mathrm{keep}}=pL_0=0.6\times1000=600$$

$$E_{\mathrm{relocate}}=C+pL_1=80+0.6\times100=140$$

$$E_{\mathrm{keep}}-E_{\mathrm{relocate}}=460$$

$$C^*=p(L_0-L_1)=0.6(1000-100)=540$$
