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


## Optional features re-verification (2026-11-11)

Prompt A desktop gate: 17 supplied offline tests, 14 frontend tests, 52 existing backend tests and Vite build passed. The fake-microphone browser check initially failed transiently at a playback assertion; its single repeat passed all eight cases, including hardware-track release, muted persistence, no audio sent while muted, typed text-only responses, echo rejection and 488 ms interruption/fade. Physical Android limits remain explicit.

Camera: live hosted synthetic medicine image HTTP 200 in 12466 ms; Hindi letter explanation HTTP 200 in 8810 ms; Kannada bus-board explanation HTTP 200 in 1797 ms. All used Gemini gemini-3.1-flash-lite. A separate real hosted browser upload verified medicine transcription/caution, actual Timbre playback, cleared file input, no retained preview and the Android UI hiding screen sharing. Native screen-sharing chooser still unverified. Image handling remains memory-only in this application; this does not guarantee third-party provider retention policies.

Web: hosted weather succeeded in 9974 ms (four screenshot frames), using Gemini and a matching quote from wttr.in. The hosted Wikipedia attempt failed after clicking the article link in 25355 ms (14 frames). Added bounded snapshot retry for execution-context changes and clearer fixed error messages; 53 backend tests pass. A real local isolated-browser run with the patched engine then returned the exact Wikipedia article paragraph in 11247 ms (11 frames, three Gemini actions). That run did not exercise the retry, so the first failure's precise cause is not established.

Safety checks re-run: 15-step cap and browser/network cleanup, fresh cookie contexts, no cookie reuse, blocked downloads, STOP in 19 ms with no subsequent screenshots. Default-off UI, No, separate domain/submit approvals, screenshot/source display and STOP button passed using a replay of the newly recorded real weather result. The shortened watchdog test verifies cancellation mechanics, not a physical 90-second test.

Free-model reliability remains variable: all three camera requests succeeded; one of the first two hosted web tasks succeeded. A subsequent local Wikipedia run succeeded. This is a small sample, not a reliability guarantee. Payment/credential blocking is enforced in the backend. No person identification is offered. The isolated browser cannot control the user's phone, apps, personal tabs or profile.

Official references: https://aistudio.google.com/docs/openai ; https://aistudio.google.com/docs/image-understanding ; https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite ; https://console.groq.com/docs/vision
