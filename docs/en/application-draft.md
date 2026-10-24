# Application Draft

**Status:** prepared from existing materials; not submitted. This is paste-ready prose, not a statement about the logged-in form. Actual word limits, attachment types, and file sizes must be checked on the application platform. Team identity and email remain blank.

## Project name

Meiyu Prepare: Making Rainfall Probability an Explainable Preparation Reference

## Short description

Meiyu Prepare helps Hangzhou small shops reason about moisture-sensitive stock relocation using public weather data, a logistic-regression probability mapping, and explicit hypothetical CNY preparation costs. The prototype provides history, method comparison, latest public weather, and data-completeness views. The main experiment has 636 paired days, with 240 held-out test days and 18 test events. It is a runnable research prototype; no merchant avoided-loss, payment, or complete new-season validation evidence exists yet.

## Problem, user, and approach

Public market monitoring describes how prolonged rain can affect product quality and storage/transport. The initial user hypothesis is a Hangzhou small shop handling moisture-sensitive stock; interviews and willingness-to-pay evidence are still missing. The prototype lets a user inspect the probability of a reference rainfall event in a fixed historical window, compare hypothetical stock-relocation costs, reveal the reference precipitation, and see forecast, ERA5, and station-reference coverage separately.

## AI task

The logistic model maps numerical-weather inputs to the probability that nominal UTC-day reference precipitation reaches 25 mm. Training, validation, and test are time-separated. The selected `logistic_rain` model has test Brier 0.0455 against the 0.0697 event-rate baseline. The model expresses a probability but adds no rainfall-ranking ability. Twenty-five millimeters is a research threshold, not an official warning or shop-flood probability.

## Evidence and limitations

On 240 test days with 18 events, the selected model has 12 hits, 6 misses, 9 false alarms, and 213 correct exclusions at a fixed 10% scenario threshold. The cost model and complete avoidance of loss are hypothetical; no CNY gain is measured. The 2026 January-September check has 85/273 paired days and one event; April-September lack complete reference. Ningbo has no transfer result. ERA5 cannot fill station labels. Ensemble member fractions are uncalibrated and are not shop-flood or loss probabilities.

## 90-day plan

Confirm the user hypothesis and recruit 5-8 volunteers; test comprehension on fixed historical cases; verify when a forecast is publicly available and run in shadow mode; then review misunderstandings and decide whether to continue, change, or narrow. The plan target is at least 80% independent completion within three minutes and correct explanation of core limits. It is a plan, not an existing user result. The 90-day period does not cover a complete next plum-rain season.

## Team fields to complete

| Field | Entry |
| --- | --- |
| Team names and organization | To be supplied by the team |
| Roles and lead | To be supplied by the team |
| Contact email | To be supplied by the team |
| Existing registration/application ID | To be confirmed; avoid duplicate applications |
| Final public demo and materials URL | Fill after publication and no-login checks |
| Film final acceptance | Awaiting two-person full viewing and listening |

Before submitting, check the platform fields, five required materials, and team confirmation. Save the actual submission time, ID, or confirmation email. A prepared draft is not a submission receipt.
