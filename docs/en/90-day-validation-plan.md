# 90-Day Validation Plan

**Status:** planned work, not completed research or a merchant pilot.  
**English release prepared:** 2026-10-24.  
**Intended users:** Hangzhou small shops that may need moisture and rain preparation. Recruiters, shop types, dates, and team contacts are not yet confirmed.

## Scope and timing

Day 1 is the date the team actually confirms the start. If work begins in late October 2026, the 90-day window ends around late January 2027. It does not include a complete next plum-rain season. New-season forecast performance requires a separate independent seasonal evaluation; a historical demo is not a substitute.

| Period | Planned work | Decision evidence |
| --- | --- | --- |
| Weeks 1-2 | Confirm the user hypothesis; plan to recruit 5-8 volunteers; write purpose, withdrawal, and non-collection statements | Whether the preparation explanation is actually needed; if recruitment fails, report a desk evaluation only |
| Weeks 3-4 | Run comprehension tests on fixed historical cases without asking participants to take real-weather action | Whether probability, UTC-day boundary, non-flood meaning, and hypothetical CNY cost are understood |
| Weeks 5-8 | Verify initialization and public-availability timing for one forecast; record retrieval failures and run in shadow mode | Whether each result was available before the decision; stop when source or complete-hour evidence is missing |
| Weeks 9-12 | Review failures and operation logs; run a second comprehension round; decide whether to continue, modify, or stop | Whether misunderstanding falls and users would continue; do not promise plum-rain performance from winter data |

## Pre-specified exploratory targets

These numbers are plan thresholds, not existing results and not statistical guarantees.

- **Operation:** at least 80% of participants complete window selection, probability interpretation, source lookup, and reference reveal independently within 180 seconds.
- **Understanding:** at least 80% correctly explain that low probability is not safety, rainfall is not flooding, and cost is a hypothetical scenario.
- **Technology:** record source, retrieval time, publication/availability evidence, parsing, and missingness. A forecast without verified availability timing is not counted as a real decision replay.
- **Model:** keep the event rule and scoring rule fixed in new independent data and compare with an equivalent baseline. If sample or event counts are too small, report insufficiency rather than stable gain.
- **Cost:** record team-observed run time and API calls separately. Merchant preparation cost and loss-avoidance ability require separate evidence.

## Stop and narrow conditions

Stop the corresponding effect claim if same-station, same-window, interpretable-quality data cannot be obtained. If real forecast availability cannot be established, retain the offline demo only. If participants repeatedly treat the probability as an official warning or flood result, stop outward action guidance and revise the wording first. If the method does not beat an interpretable baseline, retain the baseline and narrow the claim that AI is necessary.

## Participation and privacy

No back-office connection or on-site device is required. The team will recruit volunteers, explain the purpose and withdrawal process, and record only completion and necessary feedback. Store address, turnover, inventory value, and personal contact details are not default fields. The public prototype shows no private merchant information.

The prepared execution package is `UT-20261016-v1` and contains recruitment text, a host script, fixed participant tasks, scoring rules, blank individual records, and an aggregation template. No real-user test has been conducted. A person who consents, starts the task, and allows retention of the record enters the denominator. A full withdrawal is deleted and excluded. A technical interruption that was not withdrawn remains in the denominator and is reported separately. Independent task success and first-attempt comprehension are reported as separate numerators and denominators. Help, retries, and post-explanation answers do not count as first-attempt success.

## Reporting template

When a round has been completed, report the version, dates, invitation and consent counts, retained denominator $N$, withdrawals, technical interruptions, completion count, first-attempt comprehension count, time range and median for independent successes, common misunderstandings, changes made, and next decision. If $N=0$, write **not conducted / no records to aggregate**, not 0% or 100%. A small sample cannot support population adoption, payment, avoided-loss, or weather-effect claims.
