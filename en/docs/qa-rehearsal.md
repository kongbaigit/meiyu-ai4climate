# Ten-Minute Q&A Rehearsal

**Record date:** 2026-10-18. These prompts and answer points are not a record of an actual judging session. The team should fill the rehearsal result after practicing.

| Time | Main question | Answer points |
| --- | --- | --- |
| 0:00-2:00 | Why not use a weather app? Is AI necessary? | The focus is explaining probability and cost, not replacing official weather. Logistic regression maps forecast input to a reference-event probability. Evidence is limited to a finite test; it does not prove superiority to every calibration method or improve rainfall ranking. Keep a simple baseline if it is better. |
| 2:00-4:00 | How did you avoid test-set selection? Why not choose 0.0444? | Train 276, validate 120, test 240. Validation selected `logistic_rain`, `C=10`. The 0.0444 temperature/humidity comparison is disclosed but not used to change the preselected method. Frozen parameters, configuration, and predictions are delivered. |
| 4:00-6:00 | What is the cost of fewer misses? Can low probability mislead? | The model has 6 misses and 9 false alarms at 10%; the original rule has 11 misses and 4 false alarms. This is not an equal-false-alarm comparison. A 2.8% case reached 101.8 mm. Low probability is not safety; costs and full loss avoidance are hypothetical. |
| 6:00-8:00 | What about 2026 and Ningbo? Can this be real-time? | 2026 has 85/273 paired days and one event, with no complete reference April-September. Ningbo's precipitation reference is missing, so there is no transfer score. Previous Runs has no verified single initialization or historical availability time. Online forecasts are displayed separately and do not run the frozen probability model. ERA5 cannot replace a station label. |
| 8:00-10:00 | Who uses or pays? What will 90 days validate? | The user hypothesis is small shops with stock and moisture-preparation needs; interviews, payment, and revenue evidence are missing. First recruit 5-8 volunteers for comprehension, then verify one-forecast availability timing and shadow run. Measure operating cost rather than invent a price. |

## When evidence is insufficient

Say: “We do not have enough evidence for that yet. The evidence we do have is ____. We will verify it with ____. We cannot write it as an effect claim today.”

For real savings: no measured avoided loss; only a relative CNY scenario. For climate trend: two years at one station cannot support attribution. For adoption: the execution package exists but no real participant result exists.

## Self-check

- Match every number to the frozen report.
- Answer the question first, then add the limit; keep each primary answer to 30-45 seconds.
- Separate completed work, planned work, and unproven claims.
- If the demo fails, describe the actual failure and use the offline backup.
- Do not turn one case, a small-sample comprehension rate, or a synthetic film into merchant impact.

Blank record: date ____; asker ____; answerer ____; actual time ____; hard questions ____; number errors ____; added material ____; result: continue practice / ready for formal Q&A.
