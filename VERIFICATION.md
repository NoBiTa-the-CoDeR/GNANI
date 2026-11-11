# Verification status

## Latest deployment preparation

- 52 backend unit tests passed.
- 17 supplied brain tests passed (offline/mocked provider checks).
- 14 frontend unit tests passed, including simulated walking, permission denial, actions and privacy guards.
- Vite production build passed.
- Production same-origin serving checked using FastAPI TestClient: home, voice-test SPA route, health, unknown API 404, and .env request returning the SPA rather than the private file.
- Source scanned against configured credential values before staging. No configured credentials included.
- Supplied brain.py, llm.py and test_brain.py logic preserved.
- Docker is unavailable locally: container build and hosted end-to-end behavior have not been verified.
- GitHub Actions is configured; a local pass does not establish that the hosted workflow passed.

## Previous optional-feature checks

- Camera: real browser upload of a synthetic medicine label returned printed text and the medical caution; actual Timbre playback checked; file input cleared. Hindi and Kannada live image responses were obtained, with intermittent provider errors.
- Experimental isolated browser: one live weather request completed; STOP, fresh browser isolation, domain approvals and action limits checked. Reliability varied due to free-provider limits/timeouts.
- Wikipedia first-paragraph task did not complete reliably. Paragraph extraction was corrected for section-wrapped paragraphs; the complete live task still needs another run.
- UI replays and controlled tests are not live-provider verification.
- Physical Android microphone acoustics, native screen-sharing chooser and Android background notifications remain unverified.

## Hosted verification (2026-11-11)

Public address: https://gnani-ai-02v0.onrender.com

- Container built and started after adding libatomic1 for the Playwright driver.
- HTTPS frontend loaded in the browser.
- GET /api/health: HTTP 200, 215 ms, Gnani and conversation provider configured.
- Real hosted WebSocket request "Hello, how are you?": English reply at 1282 ms, first Timbre sentence at 2329 ms, second at 2909 ms.
- Separate browser "Hello" request: providers rate-limited; visible OpenRouter HTTP 429. Free-provider availability is intermittent.
- Physical microphone recording/playback on a smartphone has not been tested on this hosted deployment.
- Automatic deployment configured after CI checks; update propagation is being checked.

