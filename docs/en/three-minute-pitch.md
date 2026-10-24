# Three-Minute Pitch Script

For team rehearsal with the current approximately 74-second Chinese release film. This is not a completed live rehearsal. Time it once at a natural speaking pace; do not speed up until it becomes hard to hear.

## 0:00-0:25 - Problem

We are building Meiyu Prepare for Hangzhou small shops that may need to sort moisture-sensitive stock. Prolonged rain can affect product quality and storage, yet the link between a weather number and a preparation cost is hard to explain. We want to test whether people can understand uncertainty and how a different hypothetical preparation cost changes a choice. The user need is still an assumption awaiting interviews.

## 0:25-1:00 - Demo

Here we choose the historical window starting 2025-06-01 at 08:00 Beijing time. The model estimates about 67.9% for the nominal UTC-day reference event. The preparation cost is a hypothetical CNY scenario input, not measured CNY evidence. After reveal, the SSOD reference precipitation is 29 mm. The page keeps the time window, source, and limits visible so the same decision can be checked.

## 1:00-1:40 - AI and evidence

AI maps public numerical forecasts to the probability of a reference rainfall event using a small logistic regression. We separate training, validation, and test in time and select the method only on validation. The main experiment has 636 paired days; the test set has 240 days and 18 events. The selected model's test Brier is 0.0455, compared with 0.0697 for the training event-rate baseline. It adds probability language, not new rainfall ranking.

## 1:40-2:15 - Failure and limits

At a fixed 10% scenario threshold, the model has 6 misses and 9 false alarms; the original 25-mm rule has 11 misses and 4 false alarms. Fewer misses come with more false alarms. In another case, 2025-07-18 has an estimated probability of about 2.8% but 101.8 mm of reference rain. Low probability is not safety, and rainfall probability is not shop-flood probability.

## 2:15-2:40 - Data boundary

Latest weather displays numerical forecast, ERA5 background, and station reference separately and keeps an old cache only with its actual timestamp. The 2026 independent check has 85 paired days and one event; complete reference is missing from April through September. Ningbo has no transfer score. ERA5 is not used to fill a station-label gap.

## 2:40-3:00 - Next step

Within 90 days we will test comprehension with 5-8 volunteers, then verify when a real forecast is available and run in shadow mode. There is no measured avoided loss or payment evidence. We deliver a runnable, traceable research prototype and a concrete validation path.

Rehearsal record: speaker ____; date ____; actual duration ____; unclear points ____; changes ____.

Show one hit and one miss only. If the network fails, use the offline app and say so; do not call an offline page a live forecast. Replace the final URL only after publication checks confirm it.
