# Online Demo Notes

## Delivery entry points

- English app: <https://kongbaigit.github.io/meiyu-ai4climate/en/>
- English promotional page: <https://kongbaigit.github.io/meiyu-ai4climate/en/promo/>
- English materials: <https://kongbaigit.github.io/meiyu-ai4climate/en/materials/>
- Chinese app and promotional page retained separately: <https://kongbaigit.github.io/meiyu-ai4climate/> and <https://kongbaigit.github.io/meiyu-ai4climate/promo/>
- Chinese native preview: `/promo/native.html`

The local evidence and human-review records below describe the delivered files; public HTTP results are maintained separately.

## Current English film

- Delivery page: <https://kongbaigit.github.io/meiyu-ai4climate/en/promo/>
- Materials: <https://kongbaigit.github.io/meiyu-ai4climate/en/materials/>
- File: `media/en/meiyu-prepare-en.mp4`
- Source project: `media/en/source/`
- Duration 87.066666667 seconds; 1920x1080, 30 fps, 2,612 frames, 10 scenes, 132 beats
- H.264/AAC, one audio track, no voice-over
- Young Visionaries - Eric Matyas, Soundimage International Public License
- Attribution: `Music by Eric Matyas / www.soundimage.org`
- Source: <https://soundimage.org/techno/>; license: <https://soundimage.org/sample-page/>
- English music excerpt 6.764338247872-93.831004914539 seconds, original speed/pitch, no loop
- File size 9,853,172 bytes; SHA-256 `0958cc924e5a767dbb94abbb2de0ee17f56a0b855595cebe75f2f9a3208f35ba`

Independent visual checks and full decode passed. Full two-person viewing/listening remains pending.

## Chinese version retained

The Chinese film remains a separate asset at `media/latest/promo-full-young-visionaries.mp4`: 73.866666667 seconds, 1920x1080, 30 fps, 2,216 frames, 10 scenes, H.264/AAC, one audio track, no narration. Its existing Chinese source, licence, SHA-256, and native-preview records remain separate.

## App behavior

`site/index.html` is the current Chinese stock-relocation decision entry; it requests public ensemble weather when opened and checks hourly while open. The English main app at `/en/` has the same automatic **Ensemble** behavior. The English static historical demo at `/en/demo.html` keeps its historical evidence offline and its **Latest weather & completeness** view requests **Ensemble** only after the user clicks. The original Python/Chinese research workbench (`app.py`) remains button-triggered **Forecast**. A forecast older than three hours, missing members, or missing hours stops the relevant stock-relocation conclusion. Costs are computed in the browser and are not uploaded to the weather endpoint; closing a page leaves no background task.

Automatic weather updates and the frozen historical model are separate. English views validate source, schema, freshness, and ensemble-member completeness before using results and block incomplete windows. ERA5 and SSOD in the English pages are archived explanatory information and do not make those pages a complete real-time station-and-forecast implementation. Ensemble fractions are uncalibrated and are not loss probabilities. The model does not retrain online; historical results are offline research evidence and do not replace official warnings. Cost is a user-entered hypothetical scenario, not measured cost or loss.

## Build and check

Run `python tools/build_pages.py` from the repository root. Confirm the local source package, English delivery entries, media file, and relative links. Public-access results are recorded in `english-release-check.json`; this note does not assert HTTP success. Full two-person viewing and listening are still required.

Historical process files and old publication records are not current entry points.
