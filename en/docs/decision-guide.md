# Stock-Relocation Decision Guide and Auto-Refresh Behavior

## Start the app

Double-click `start.cmd` at the repository root. The first run creates `.venv-decision` and installs `requests` and `tzdata`. Open the local address printed by the terminal, normally `http://127.0.0.1:8532/`. The service listens only on the local machine. Keep the terminal open; press Ctrl+C to stop it.

Opening `index.html` directly requests the Chinese decision page's public Ensemble while the page is open. The English main app at `/en/` uses the same automatic Ensemble pattern; the English static historical demo at `/en/demo.html` requests Ensemble only after the user clicks in its Latest weather view. The original Python/Chinese research workbench is started by `start.ps1`, uses `requirements.txt`, and keeps its **Latest weather** page button-triggered Forecast. These are separate paths.

## What to enter

**Relocation cost** includes labor, supplies, and operating impact. **Conditional loss** when choosing **Keep in place** and residual conditional loss after **Relocate** are both conditional average losses **given that the selected rainfall scenario occurs**. Do not enter the full inventory value as the loss from every rain event. Residual loss is not assumed to be zero; the initial CNY 100 is a demo value. The three CNY values must be confirmed before a scenario recommendation is shown. The 60% example is separate from current weather and is not a live observation.

Let $p$ be the scenario event estimate, $C$ the relocation cost, and $L_0$ and $L_1$ the conditional average losses without and with relocation:

$$
E_{\text{keep}}=pL_0,\qquad E_{\text{relocate}}=C+pL_1.
$$

The expected difference is $p(L_0-L_1)-C$. A positive value favors **Relocate**, a negative value favors **Keep in place**, and equality displays a tie. The browser compares unrounded CNY values and displays two decimals. This is a hypothetical scenario and excludes other risks; it is not realized revenue or avoided loss.

For the fixed 60% hypothetical example with relocation cost $C=\mathrm{CNY}\ 80$, conditional losses $L_0=\mathrm{CNY}\ 1000$ and $L_1=\mathrm{CNY}\ 100$, the expected totals are CNY 600 for **Keep in place** and CNY 140 for **Relocate**, a difference of CNY 460. The tie is $C=\mathrm{CNY}\ 540$; at $C=\mathrm{CNY}\ 600$, choose **Keep in place**. These figures are hypothetical only, not merchant measurements.

## How weather is obtained

The English main app's automatic home page uses the Open-Meteo Ensemble API with ECMWF IFS 0.25-degree members. The English static historical demo uses the same Ensemble API only after a button click; the original Python/Chinese workbench uses the separate Forecast API. Hangzhou and Ningbo use fixed reference locations and nearest grids; returned member identity and expected member count are stored in code and source records. Each Ensemble member sums the preceding-hour precipitation from Beijing 08:00 to the next day 08:00, so hour labels use $(start,end]$.

The first window is Beijing tomorrow 08:00 to the following day 08:00, with seven windows in total. A member counts as reaching the 25-mm research threshold only when all 24 hours are present and its total is at least 25 mm. The member fraction is shown only when every expected member and required hour is complete. Missing values are not filled with zero. The fraction is uncalibrated, is not a shop-flood or loss probability, and must not be replaced with the historical model's 67.9% example.

The English main app checks Ensemble forecasts while open; the static demo checks Ensemble only after the user requests it. ERA5 and SSOD shown in the English pages are archived explanatory information, not a claim of complete real-time station coverage. Each live response keeps retrieval time, raw response, and a digest. A source older than three hours, an incomplete window, or a window outside the current seven-day horizon pauses the current stock-relocation conclusion. A failed request keeps a valid old cache, but an expired cache cannot continue a recommendation.

Retrieval time is when this app received the response, not model initialization or provider publication. Daily reference and background updates do not rebuild the main experiment or convert a missing value into no rain. The frozen 636-day experiment, 85-day independent check, and their metrics remain unchanged.

Sources: [Open-Meteo Ensemble API](https://open-meteo.com/en/docs/ensemble-api), [Open-Meteo terms](https://open-meteo.com/en/terms), and [NOAA SSODv2](https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly/synoptic-summary-of-the-day). Open-Meteo is attributed under CC BY 4.0 and used here through a free endpoint for non-commercial research.

## Save and rebuild

Costs and checkboxes are calculated in the current browser only. A downloadable statement records the mode, CNY assumptions, window, source retrieval times, and result; merchant amounts are not uploaded to a weather service.

Runtime weather cache is under `runtime`; it is not the frozen historical experiment. `index.html` includes a generated snapshot and checks for updates when opened. The snapshot is labeled with its own time and must not be presented as a new retrieval.

After editing `templates/decision.html`, `decision.css`, or `decision_client.js`, rebuild the home page with `python -m src.decision_build`. Cost logic lives in `src/decision_cost.py` and `templates/decision_cost.js` and uses the same fields and formula. Run Python tests with `python -m pytest`; run the Node cost test with `node tests/decision_cost_js.cjs`. Browser checks use Playwright and Edge. The launch workaround merges `AutofillAiWalletPrivatePasses`; its effectiveness is not yet verified.
