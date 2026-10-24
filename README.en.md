# Meiyu Prepare

An explainable rainfall-preparation reference for Hangzhou small shops | AI for Climate

**English materials prepared 2026-10-24.** The repository's historical and capture dates remain the dates in their evidence. English delivery entries are listed below; public-access results are maintained separately.

## What the prototype does

Meiyu Prepare helps a small shop explore a rainfall reference event, compare a hypothetical stock-relocation cost, and inspect the source and completeness behind the result. It is an offline research method plus a separately updated public-weather display. It is not an official warning, shop-flood predictor, or loss-probability product.

The main experiment has 636 paired historical days: 276 training, 120 validation, and 240 test days with 18 test events. The selected precipitation-probability model has test Brier 0.0455 versus 0.0697 for the fixed training event-rate baseline. The event threshold is 25 mm of nominal UTC-day reference precipitation, not an official warning level. No real merchant validation, avoided-loss, payment, or carbon-reduction evidence is claimed.

## Current entry points

- English public app: <https://kongbaigit.github.io/meiyu-ai4climate/en/>
- English promotional page: <https://kongbaigit.github.io/meiyu-ai4climate/en/promo/>
- English materials: <https://kongbaigit.github.io/meiyu-ai4climate/en/materials/>
- Chinese public app retained separately: <https://kongbaigit.github.io/meiyu-ai4climate/>
- Chinese promotional page retained separately: <https://kongbaigit.github.io/meiyu-ai4climate/promo/>
- App source: `index.html`; full workbench: `app.py`

The English main app at `/en/` automatically requests public **Ensemble** weather while the page remains open. The English static historical demo at `/en/demo.html` keeps history offline and requests its **Ensemble** view only after the user clicks. The original Python/Chinese research workbench (`app.py`) has a separate button-triggered **Forecast** page. A forecast older than three hours, a missing member, or a missing hour stops the relevant stock-relocation conclusion. ERA5 and SSOD shown in English pages are archived explanatory information, not proof of a complete real-time station-and-forecast implementation. Costs are computed in the browser and are not uploaded. The historical model does not retrain online. These behaviors are separate.

## English material map

### Core documents

- [Project description](docs/en/project-description.md) - problem, method, evidence, limits, and 90-day path
- [Data and AI statement](docs/en/data-ai-statement.md) - sources, AI assistance, cache, licensing, and boundaries
- [90-day validation plan](docs/en/90-day-validation-plan.md) - pre-specified exploratory validation
- [Decision guide](docs/en/decision-guide.md) - Keep in place / Relocate logic and cost examples
- [Online data completeness](docs/en/online-data-completeness.md) - freshness, missingness, and cache behavior
- [Data dictionary](docs/en/data-dictionary.md) - unified sample fields and coverage denominators
- [Model result contract](docs/en/model-result-contract.md) - prediction-upload schema and research boundary
- [Reproduction and delivery](docs/en/reproduction-and-delivery.md) - source, build, package, and review workflow

### Submission and rehearsal

- [Submission checklist](docs/en/submission-checklist.md)
- [Application draft](docs/en/application-draft.md)
- [Three-minute pitch](docs/en/three-minute-pitch.md)
- [Q&A rehearsal](docs/en/qa-rehearsal.md)
- [Demo fact sheet](docs/en/demo-fact-sheet.md)
- [Online demo notes](docs/en/online-demo.md)
- [Promotional film release note](docs/en/promo-full-release.md)
- [Human video acceptance](docs/en/video-human-acceptance.md)
- [Official requirements record as of 2026-10-18](docs/en/competition-requirements-20261018.md)

### Validation and user testing

- [Temporal validation protocol](docs/en/temporal-validation-protocol.md)
- [Temporal validation results](docs/en/temporal-validation-results.md)
- [Remote user testing](docs/en/remote-user-testing.md)
- [User-testing kit](docs/en/user-testing-kit/00-start-here.md)

### Sources

- [Official Hangzhou/Zhejiang sources](docs/en/action-sources.md)
- [Media notes](media/README.en.md)

## Data sources and limitations

Historical reference precipitation comes from archived NOAA SSODv2 evidence for Xiaoshan Airport. Public numerical forecasts use Open-Meteo ECMWF IFS 0.25-degree **Ensemble** in the English app and static demo, while the original Python/Chinese workbench uses **Forecast**. ERA5 and SSOD in the English pages are archived explanatory information, not live station feeds or proof of a complete real-time implementation. The source manifest records URLs, retrieval time, coordinates, and hashes. SSOD can under-report, nominal UTC-day boundaries are not exact measured accumulation boundaries, and Previous Runs does not establish one historical public-availability time. Missing reference is not no rain.

The independent 2026 check has 85 paired days out of 273 and one event; complete reference is missing from April through September. Ningbo has no transfer score. Ensemble member fractions are uncalibrated internal frequencies, not shop-flood or loss probabilities. Costs are scenario assumptions in CNY; the 60% example with relocation cost $C=\mathrm{CNY}\ 80$, conditional losses $L_0=\mathrm{CNY}\ 1000$, $L_1=\mathrm{CNY}\ 100$ gives hypothetical totals CNY 600 for **Keep in place** and CNY 140 for **Relocate**, difference CNY 460, tie $C=\mathrm{CNY}\ 540$, and **Keep in place** at $C=\mathrm{CNY}\ 600$.

## Run and reproduce

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

For the local stock-relocation decision page, run `start.cmd` and open the printed local address, normally `http://127.0.0.1:8532/`. The page listens only on the local machine. For source checks, preserve data/model/report hashes, use `requirements.txt`, and read the English data dictionary and model contract before changing a run. Run tests with `python -m pytest` and the cost check with `node tests/decision_cost_js.cjs`.

Build public pages with `python tools/build_pages.py`. Do not treat a successful local build as proof of an online URL. Do not overwrite `artifacts/predictions.csv`; new predictions need a separate versioned directory and manifest.

## Video and music

The current Chinese film is `media/latest/promo-full-young-visionaries.mp4`: 73.866666667 seconds, 1920x1080, 30 fps, 2,216 frames, 10 scenes, H.264/AAC, one audio track, no narration. SHA-256: `2b52e74cf2302196d46e128802613a280aa584a914dc416fdc727dd3b91d2d86`.

Music is **Young Visionaries - Eric Matyas**, used under the **Soundimage International Public License**. Attribution: `Music by Eric Matyas / www.soundimage.org`. Source page: <https://soundimage.org/techno/>. License page: <https://soundimage.org/sample-page/>. The Chinese source excerpt is 17.313872945628-91.180539612295 seconds, original speed and pitch, continuous cut, end fades, no loop.

The English cut is `media/en/meiyu-prepare-en.mp4`: 87.066666667 seconds, 1920x1080, 30 fps, 2,612 frames, 10 scenes, and 132 beats, with no voice-over. Its English source excerpt is 6.764338247872-93.831004914539 seconds at original speed and pitch. File size is 9,853,172 bytes; SHA-256 is `0958cc924e5a767dbb94abbb2de0ee17f56a0b855595cebe75f2f9a3208f35ba`. Independent visual checks and full decode passed. Full two-person viewing/listening remains pending.

## Licenses and copyright

New project code is under the MIT License in [LICENSE](LICENSE). Third-party data, documents, libraries, and music remain under their own source terms. Soundimage music is not Creative Commons or an equivalent license. The original Chinese copyright limitation in `LICENSE` remains authoritative and is retained here verbatim:

> 本许可仅适用于团队新增代码。第三方数据、格式文档和软件依各自来源许可使用。

English meaning: this license applies only to code added by the team; third-party data, format documentation, and software are used under their respective source licenses.
