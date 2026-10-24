# Reproduction and Delivery

Run commands from the repository root. Current media, public-page, and material status are defined by the root README, `docs/en/online-demo.md`, and `docs/en/promo-full-release.md`. Historical process notes are not current delivery entry points.

## Build the materials

Source HTML and Markdown should be reviewed before any PDF export. For the English release, the source files are under `docs/en/`. PDF export uses the bundled Playwright runtime; keep the resulting HTML and PDF beside the named document. Render every PDF page to PNG with Poppler and inspect text, tables, formulas, footers, and whitespace. Do not mechanically force the English document to the Chinese page count.

The three formal English PDFs are:

- `docs/en/project-description.pdf`
- `docs/en/data-ai-statement.pdf`
- `docs/en/90-day-validation-plan.pdf`

The corresponding `.md` and `.html` files are the editable and reviewable sources. The application should embed the Markdown AI statement for the app download; publication routes `/en/`, `/en/promo/`, and `/en/materials/` remain pending until publication checks are complete.

## Research reproduction

Keep the data, model, and report hashes before running a new experiment. Reproduce the frozen files with the existing Python modules and `requirements.txt`; use the data dictionary, model contract, and source manifest to confirm schema, day boundary, units, station, model ID, and completeness. Do not call `fit`, select `C`, or overwrite frozen predictions when checking the 2026 temporal file.

The main experiment contains 636 paired days (276 train, 120 validation, 240 test) and 18 test events. Its selected test Brier is 0.0455 against the 0.0697 training event-rate baseline. These numbers are not recomputed by the online weather page.

## Engineering package

The source package includes code, templates, public-data snapshots, frozen results, current English and Chinese materials, and needed reports. Do not include build output, distribution ZIPs, or runtime cache. After packaging, check ZIP CRCs, per-file hashes, and that packaged bytes match the source checkout.

The package is a reproducible candidate, not proof of a published URL or a submitted entry. Team identity, contact email, public links, human video acceptance, and actual application receipt must be completed from real evidence.

## Media and copyright

The current Chinese promotional film is 73.866666667 seconds, 1920x1080, 30 fps, 2,216 frames, 10 scenes, H.264/AAC, one audio track, and no narration. SHA-256 is `2b52e74cf2302196d46e128802613a280aa584a914dc416fdc727dd3b91d2d86`. Music is Young Visionaries by Eric Matyas under the Soundimage International Public License, credited as `Music by Eric Matyas / www.soundimage.org`; source and license pages remain linked in `docs/en/data-ai-statement.md`. Do not relabel this license as Creative Commons.

The separate English cut is `media/en/meiyu-prepare-en.mp4`: 87.066666667 seconds, 1920x1080, 30 fps, 2,612 frames, 10 scenes, 132 beats, one AAC track, and no voice-over. The current file size and SHA-256 are recorded in `media/en/video-info.json` and `docs/en/video-technical-check.json`. Independent visual and technical checks for v2 are recorded there; full team viewing/listening and publication remain pending.
