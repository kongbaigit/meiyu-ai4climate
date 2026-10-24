# Build the English pitch deck

The source creates ten slides with editable text, one native table and two native charts. Chart workbooks contain the complete literal data shown on the slides. Their labels are in English. The Chinese source presentation remains a separate archive in `presentations/zh-CN/`.

The builder uses the Codex bundled `@oai/artifact-tool` library and presentation finalizer. It does not use a PowerPoint generation substitute.

Set these paths before running `build_deck.mjs` with the bundled Node.js executable:

- `RUNTIME_NODE_MODULES`: bundled Node.js package directory
- `PRESENTATIONS_SKILL_DIR`: installed Presentations skill directory
- `RUNTIME_PYTHON`: bundled Python executable
- `DECK_WORK_DIR`: private build and validation directory outside the repository
- `DECK_FINAL_PPTX`: new output filename inside `DECK_WORK_DIR`
- `DECK_REVISION`: optional revision name, default `v1`

Before the first authoring run for a task, run the skill's `container_tools/mark_artifact_operation_started.mjs` once with `--operation-kind create --expected-output-count 1 --output-format pptx`. The finalizer refuses to overwrite a final output. Use a new output filename for each revision.

The builder writes the final PPTX, `speaker-notes.md`, a private draft, layout records and validation receipts. Copy a validated final file into the English presentation directory without changing it.

Use `render_powerpoint.ps1` to render the deck in Microsoft PowerPoint and test native editability in a separate copy. It creates an HTML proof before PDF export. Review every slide and the example formulas in that proof before using its `ExportPdf` mode. PDF export prints the inspected rendered pages through a hidden Edge session. Run `finish_pdf.py <pdf path>` with the bundled Python executable to add the three closing-slide links and verify the page count. The PPTX retains editable text and data. The companion PDF preserves the checked appearance as raster pages.

The online weather example is a fixed snapshot captured on 19 October 2026 at 19:22 UTC+08. It must not be relabelled as current weather. Scenario results are hypothetical. Merchant loss reduction and carbon benefits remain unverified.
