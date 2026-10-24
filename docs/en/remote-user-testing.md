# Remote User Comprehension Test: Executable Plan and Blank Record

**Status:** not conducted. This corresponds to the first planned round. Complete the application and public-access check before inviting volunteers. Team trials must not be called external-user research.

The complete local execution package is `docs/en/user-testing-kit/`, version `UT-20261016-v1`. It includes recruitment text, a host script, participant tasks, scoring rules, an individual record, and an aggregation template. Use that package for the fixed task, 180-second timer, first answers, and denominator rules. No real test has been run.

## Opening statement for participants

This is an approximately 10-minute prototype comprehension test. You will see historical rainfall and hypothetical costs; you do not need to act on real weather. Participation is voluntary and you may stop at any time. By default we record only an anonymous code, operation time, and comprehension result. We do not collect shop address, contact details, turnover, or inventory value. We do not record audio or video. If a quote or recording is needed, ask for separate consent.

## Host procedure

1. Give the accessible demo link and assign an anonymous ID such as P01; never write a real name in the record.
2. Ask whether the person volunteers. Do not continue after a refusal.
3. Do not explain the answer. Ask the participant to choose a historical window, find the probability, inspect the hypothetical cost, reveal the reference precipitation, and find the source within three minutes. Record help and time.
4. Ask: “What does the probability refer to?”, “Does low probability mean safe?”, “Is the hypothetical CNY 10 amount an actual loss?”, “Can ERA5 be used as this station observation?”, and “Where can you tell whether the data is stale?”
5. Show one miss case and ask whether it changes understanding. Ask what is useful, what is unclear, and whether they would use it again. Do not lead toward a positive answer.
6. After the first answers, explain the fixed wording: the research event is reference-day rainfall reaching 25 mm; it is not shop flooding; low probability is not safety; cost is hypothetical; ERA5 is background; and forecast cache status requires the actual retrieval time.

## Anonymous record

| Field | Entry |
| --- | --- |
| Anonymous ID / date / prototype version | |
| Voluntary consent | |
| Device type | |
| Key operation time (seconds) | |
| Independent completion / number of help prompts | |
| Can distinguish rainfall probability from flood probability | |
| Can state low probability is not safety | |
| Can identify hypothetical cost | |
| Can distinguish ERA5 background from station reference | |
| Can find source and stale notice | |
| Misunderstanding or stuck point, without identity | |
| Willingness to continue and reason | |
| Permission to quote anonymously | |
| Host's suggested change | |

Planned sample: 5-8 people. Planned targets: at least 80% complete the key operation within three minutes and correctly explain the core limits. Report numerator and denominator, for example 4/5; do not report a percentage alone. A small, failed, or unfavorable recruitment round remains evidence about usability only, not population adoption or commercial demand.

## Completion-only summary

Actual invited ____; consented ____; started ____; retained $N$ ____; independent completion ____/$N$; first-attempt core comprehension ____/$N$; common misunderstanding ____; changes required ____; second round? ____.
