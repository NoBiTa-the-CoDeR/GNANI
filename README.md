# gNani AI

A voice companion with in-page journey guidance, recipes and visual help. The latest user-supplied `backend/brain.py` and `backend/test_brain.py` are preserved byte for byte. FastAPI connects Prisma transcripts and one history list per WebSocket session to the supplied brain. Timbre speaks the visible answer; there is no browser speech fallback.

## Run locally

Use Python 3.12+ and Node.js 20.19+ (verified here with Python 3.12 and Node 24). Apple's older system Python/LibreSSL failed the OSRM TLS handshake; the installed Python 3.12/OpenSSL runtime succeeded with certificate verification enabled.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
# Preserve an existing .env. For a new installation only:
test -f .env || cp .env.example .env
test -e backend/.env || ln -s ../.env backend/.env
# Fill credentials privately in .env.
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
npm install
npm run dev
```

Open http://localhost:5173/. The backend `.env` is a symlink to the project `.env`, so the supplied `check_llm.py` and the application read the same settings. `.env`, virtual environments, dependency folders and runtime logs are ignored by Git. Microphone and geolocation on a smartphone require trusted HTTPS. Deploy behind an HTTPS reverse proxy which forwards `/api` and WebSocket upgrades; configure the actual client IP at that trusted proxy for meaningful per-IP limits.

## Services

Gnani Prisma and Timbre and at least one configured LLM provider are required for conversation. `LLM_PROVIDERS` lists the fallback order. The bridge enables Qwen's non-reasoning mode and a larger tool-output budget without changing the supplied LLM or brain files. It retries Groq's HTTP 400 `tool_use_failed` errors and displays sanitized service failures. Spoken overviews are limited to three sentences. The original brain is non-streaming; this integration does not claim token streaming.

`PIXABAY_API_KEY` is optional. The supplied brain searches Pixabay, Pexels if configured, then Wikimedia Commons. Pexels is not configured in this installation. Photos retain source credits and links. Query results are cached in memory for 24 hours, as required by the Pixabay API. Images from approved provider hosts are downloaded once through the backend and cached for 24 hours (64 images, maximum 2 MB each). Only catalogued provider URLs are accepted, all redirects are checked, and HTTP failures respect a retry delay. Cache capacity limits omit new media rather than evicting valid query results early. Caches are per-process and clear on restart; use one backend worker locally. For a production deployment that restarts frequently or uses multiple workers, use shared persistent caches before enabling Pixabay.

`YOUTUBE_API_KEY` is optional. Video search results are cached in memory for 24 hours. The supplied brain also enforces its daily search cap, configured by `YT_DAILY_SEARCH_LIMIT`; this cap is per process and resets on restart. The UI displays at most two thumbnails and loads a `youtube-nocookie.com` player only after a tap. Speaking to the companion, playing an assistant response, or closing the helper removes the player. No key, quota exhaustion, empty results or service failure hides the video section. If the model omits optional media queries for a recipe/how-to, the UI searches from the panel title.

`GOOGLE_MAPS_EMBED_KEY` is optional and is a browser-visible Embed key. Restrict it to the website's HTTP referrer and the Maps Embed API in Google Cloud. The backend config returns only whether it exists; the embed URL is returned only on an explicit transit selection. The URL uses `https://www.google.com/maps/embed/v1/directions` with `mode=transit` and an origin. The iframe uses `strict-origin-when-cross-origin` so referrer restrictions work. With no Embed key there is an explicit Open in Google Maps button. No external map opens automatically. Bus times, numbers, fares and live vehicle data are never invented by the app.

See [Google Embed directions](https://developers.google.com/maps/documentation/embed/embedding-map), [Pixabay caching requirements](https://pixabay.com/api/docs/), and [YouTube player parameters](https://developers.google.com/youtube/player_parameters).

## In-page navigation and helper content

`POST /api/route` accepts `{origin:{lat,lon}|null,dest:{lat,lon}|null,destination:"place name",mode:"walk"|"drive"}`. Missing destination coordinates cause a real geocoder search biased around the origin using a preferred viewbox, with candidates returned for user selection. The app never silently selects from several matches. OSRM walking and car routes use their corresponding profiles. Errors include helpful next steps and safe upstream status information.

`GET /api/images?q=...` accepts 1–80 characters and limits each IP to 12 requests/minute. `GET /api/videos?q=...` accepts 1–100 characters and limits each IP to 8 requests/minute. Image/video queries retain a 24-hour memory cache. Route calculation and media calls have total timeouts. `POST /api/speech` generates cached Timbre guidance without an LLM.

The separate walking engine projects GPS fixes onto the route, tracks remaining distance/time, announces real maneuvers in English/Hindi/Kannada, pre-generates upcoming Timbre speech, prioritizes immediate turns, and queues announcements while the user is speaking. It pauses turns for accuracy worse than 50 m, recalculates after three good fixes more than 40 m off-route, and arrives within 25 m of the destination. Arrival stops the watch and releases wake lock. Safety reminders never assert that a crossing is safe. Auto/Car has route/ETA only. Screen wake lock is best-effort and reacquired when the page becomes visible.

The location controller checks Permissions API state and reuses one high-accuracy watch. It never automatically retries a denial. Recent good fixes survive transient location errors. A denied/unavailable position still allows a destination map and a single spoken request for the origin. Live navigation facts, without GPS coordinates, accompany user questions to `brain.respond(...,nav=...)`.

Helper panels keep ingredients as checklists, numbered steps, tips, photo credits and video titles. Step commands such as “next step”/“अगला कदम” move the current-step index reliably; health panels show the general-information notice. Journey and helper sections can coexist. Close buttons replace/clear their own content only. A floating mic remains available when the main orb scrolls away. Reduced-motion preferences are respected.

## Verification commands

```sh
# Supplied offline tests: run without loading real credentials into that process.
.venv/bin/python backend/test_brain.py
.venv/bin/python -m unittest discover -s backend/tests
node --test frontend/tests/*.test.mjs
npm run build --prefix frontend
# Real provider diagnostic (prints safe status output; do not enable HTTP debug logging):
(cd backend && ../.venv/bin/python check_llm.py)
```

The browser verification harness is in the workspace's `work/browser-tests/verify.mjs`, with screenshots and reports under `outputs/verification`. It uses mocked geolocation and replays real recorded assistant/media results, a real OSRM route fixture and short test audio. Its Electronic City request label is a UI simulation; the 683 m public Bengaluru route fixture is not a verified route to that metro station. Real STT/LLM/Timbre/media calls are tested separately. Consult the current verification report for actual results and limitations; simulation does not establish safe outdoor navigation.

## Mute, typing and voice choices

The fixed bottom Mute button releases every microphone track and disconnects the capture graph. Its state is held in sessionStorage across reloads. Muting cancels active STT/conversation work for an unfinished voice turn, drops subsequent binary audio, and leaves an already-playing reply alone. Stop talking stops output separately. A silent banner appears after ten minutes muted. Keyboard messages work without acquiring the microphone and default to text-only replies; Listen explicitly requests Timbre audio. Replies aloud controls voice-message replies. No browser speech voice is used.

Capture requests echo cancellation, noise suppression and automatic gain control. A residual-echo correlator compares the actual decoded Timbre PCM before voice activity can trigger an upload. Independent speech sustained for about 250 ms triggers a 150 ms playback fade. This was tested with controlled audio signals in Chromium; acoustic echo on an Android handset still requires physical testing.

Open `/voice-test` to compare five fixed sentences in English, Hindi and Kannada. The page lists documented v2.5 and v3 voices, three speeds, and a Hindi native/Latin place-name comparison. Playback checks account access on demand; listing a documented voice does not guarantee the account can use it. Save writes only the selected language's model/voice/speed to backend .env. Default speed is 0.93. Timbre supports speed 0.85–1.15. Pitch and SSML controls are not documented; v3 supports its own audio tags. See [Timbre streaming](https://docs.gnani.ai/api/TTS/tts-sse) and [voice catalogs](https://docs.gnani.ai/api/TTS/available-voices).

`backend/tts_normalize.py` strips formatting, expands numbers/units/currency/time and common abbreviations in the selected language, applies `backend/pronunciation.json`, and splits output into at most twenty words per audio sentence. WebSocket replies and `/api/speech/stream` emit each sentence as soon as ready. Later sentences generate while the first plays, with a 200 ms playback pause. A global lock respects Timbre's one-active-request limit. Timing logs contain stages/durations only; browser end-of-speech-to-playback metrics are sent back as `stage=playback_start elapsed_eos_ms=...` in backend/timing.log. The supplied brain remains non-streaming at the LLM layer.

## Music

Set `JAMENDO_CLIENT_ID` in the backend .env. `GET /api/music?q=&mood=` calls the supplied helper unchanged, validates query lengths, limits requests per IP, and caches search results for one hour. [Jamendo tracks documentation](https://developer.jamendo.com/v3.0/tracks) confirms its endpoint and parameters. Returned streams are relayed from catalogued Jamendo hosts through `/api/music-audio/<opaque id>` so missing CORS headers do not silence Web Audio analysis. Upstream HTTP errors are surfaced; a missing track can be skipped with Next. No file download is offered. Credits link to the track and Creative Commons license.

Music starts on an explicit Play tap. Library audio uses an anonymous-CORS audio element; generated music uses a dynamically loaded Tone.js warm pad and pentatonic melody. Generated lullabies speak the supplied lines with Timbre over the backing and are explicitly labeled as spoken, not real singing. YouTube loads the official IFrame API/player after Play; state events control a simulated wave envelope because its audio cannot be analysed. Jamendo, generated music and Timbre use real analyser data. Waves fade smoothly and become a static gradient for reduced-motion users. Speech ducks music to twenty percent of the selected volume. Stop works from the card or a voice/text request. A new music request replaces the old player. Missing/unplayable library audio offers YouTube or on-device backing.

## My people and phone actions

Opening My people mutes and releases the microphone while contact details are edited; its dialog retains a talk-again button. My people stores names, nicknames and phone numbers in localStorage on that browser only. Contact records are never uploaded. Names a user says and names spoken for clarification pass through the normal speech/assistant services; phone numbers are never included in backend messages. Matching and link construction happen locally. Ambiguous contacts need selection; missing contacts offer a local add form.

Every action requires a tap. Calls open a `tel:` link. WhatsApp opens a prefilled draft, which still needs Send in WhatsApp; SMS is offered as an alternative. Unknown/sensitive action types are rejected. The local What I did today list records handoffs and reminder events, not proof that a call connected or a message was sent.

Reminders/timers are saved locally and fired by the open page, with a gentle chime, in-page alert and Timbre speech. Overdue reminders are checked when returning to the page and marked fired before alerts to avoid repeats on reload. **Keep the app open; sleep/background throttling can delay timers. Closing the app cannot reliably trigger an alarm.** A user can enable Notifications; a small service worker supports notification display/focus, but it does not schedule timers or use remote push. Android background delivery must be tested on an actual device. Desktop headless Chromium here registered the worker but rejected notification display despite its test permission override; in-app reminders continued working.

## Optional camera reading

The `Look at this` button opens a camera/photo picker and mutes the mic. The browser and backend resize in memory; the backend verifies JPEG/PNG/WebP and strips metadata. `POST /api/vision` accepts `{image:"data:image/...;base64,...",lang:"en"|"hi"|"kn"}`. The application writes no uploaded image to a file, cache, conversation history or log. It releases image references after the response; HTTP responses use `Cache-Control: no-store`. This is an application retention statement, not a claim about a third-party provider's retention policy. Verification PNGs under work/vision-fixtures are synthetic test labels, not user uploads.

With a configured Gemini key, the optional features first use `gemini-3.1-flash-lite`, verified against Google's current model list, image-input docs and free-tier pricing. Its documented minimal-thinking mode is used. Groq's documented `qwen/qwen3.8-27b` is the next vision provider, selected through `VISION_MODEL` or the existing `GROQ_MODEL`. OpenRouter is the final fallback using **only `openrouter/free`**, which documents image input and zero-priced routing. Requests are serialized per provider; camera calls have bounded per-provider timeouts and a total deadline. No new key is sent to the browser. Account quota errors remain visible, including safe HTTP status and a retry hint; the app never pretends to read an unavailable image.

Medicine reading transcribes printed text, avoids dosing/diagnosis advice and adds a doctor/pharmacist caution. Explicit person-identification requests are rejected before any provider call. Credential-like and long private numbers are redacted in returned text. OCR can be wrong: unclear photos ask for another picture. Desktop screen reading is optional, one frame and view-only, with tracks stopped immediately; it is hidden on Android/iOS. The native desktop chooser was not physically tested.

References: [Groq image input](https://console.groq.com/docs/vision), [OpenRouter free image-capable router](https://openrouter.ai/openrouter/free/), [Gemini OpenAI-compatible API](https://aistudio.google.com/docs/openai), [Flash-Lite image support](https://aistudio.google.com/docs/models/gemini-3.1-flash-lite), [free-tier pricing](https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite).

## Experimental isolated web helper

The optional settings checkbox is **off for a new browser**. Its plain consent text explains that public page text goes to the configured AI service. It is saved locally after an explicit choice. Normal conversation continues to use the supplied brain; only explicit web requests route to the helper when enabled. A task can also be typed in its own form. Typed tasks finish in text; voice tasks can use Timbre. The backend rejects starts without consent.

Install the tested Python Playwright and its own Chromium browser:

```sh
pip install -r backend/requirements.txt
python -m playwright install chromium
# Linux servers may need: python -m playwright install --with-deps chromium
```

If you install browsers to a custom path, set `PLAYWRIGHT_BROWSERS_PATH` to that same directory for both install and backend execution. The current local setup uses /private/tmp/gnani-playwright-browsers. `WEB_CHROMIUM_EXECUTABLE` can override the test Chromium executable; never point it at a personal profile. Production must set `APP_ORIGINS` to the frontend's exact HTTPS origin and forward WebSocket upgrades for `/api/web/session`.

Every run launches a separate fresh Playwright Chromium and incognito-style context. It does not attach to the user's tabs/profile, load storage state or reuse cookies. Camera/mic permissions, service workers, scripts and web sockets inside that separate browser are disabled. It works best on simple public pages and cannot control the phone screen or other apps. Complex interactive sites may not work.

The backend sends JPEG screenshots about once a second plus action events through its WebSocket. It provides URL/title/rendered main text and numbered controls to the LLM. Only validated click, type, scroll, goto, done and ask_user JSON actions are allowed. Final factual answers require a verbatim page-evidence quote. A first-paragraph request cannot finish on a disambiguation page; English reading uses the verified article paragraph rather than an invented summary. Models try configured Gemini, then Groq, then only free OpenRouter routing; no paid LLM fallback is enabled. Invalid JSON has one bounded retry. Unavailable or rate-limited models stop with the real safe reason, never an invented answer.

Domain and submission approval are server-side decisions with one-use approval IDs; the user must tap Yes/No. Redirects cannot silently open an unapproved site. Login/booking actions require separate approval; passwords, codes, account/card/Aadhaar details, payments and downloads remain blocked even after Yes. The typing/query guard is intentionally conservative about four-or-more-digit strings and may reject innocent numeric searches. The helper does not complete password/OTP logins.

All network traffic goes through an authenticated loopback HTTPS CONNECT proxy. It rejects private/reserved DNS answers and connects to the validated public IP itself, preventing Chromium from performing a second, potentially rebound DNS lookup. Unapproved third-party resources are blocked. Sessions allow at most fifteen model actions or ninety seconds; STOP, disconnect and timeout close the browser and proxy sockets. Capacity is two isolated sessions, with per-IP start limits. No screenshots are persisted by the app. `backend/web-actions.log` contains scrubbed action records and is ignored by Git; page input values, cookies, credentials and raw model responses are not logged.

Verification report for these optional phases: `VERIFICATION.md`. The observed free services were not reliable enough to claim every requested live test passed; see the explicit quota-limited cases there. Android acoustics/background notifications from Prompt A remain unverified as agreed.

## GitHub and production deployment

This repository includes a Dockerfile that builds React and serves it with FastAPI on one HTTPS origin, including WebSockets. `render.yaml` configures a free Render web service and automatic deployment on each commit to the connected branch. See https://render.com/docs/blueprint-spec.

1. Push this source to your GitHub repository.
2. In Render choose New → Blueprint and connect that repository. Review the free plan before creating it.
3. Enter the private runtime variables from your local `.env` in Render's Environment page; never upload `.env`. The blueprint prompts for Gnani and Groq keys; copy other configured speech settings and optional service keys there as needed.
4. Set APP_ORIGINS to the exact HTTPS address Render assigns, then redeploy. This is required for the opt-in experimental web assistant.
5. Open the assigned HTTPS address and check `/api/health`, microphone, Timbre playback and a typed question. A build alone does not verify live API credentials.

Subsequent pushes redeploy automatically; uncommitted local changes are not uploaded automatically. Free instances may sleep and have cold starts. Browser automation can exceed free-instance memory; its live hosted behavior remains unverified. Android acoustics and background notifications require a physical-phone check.

Do not use GitHub Pages for this app: the Python backend and WebSockets require a running server.
