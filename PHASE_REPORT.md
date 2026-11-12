# gNani audit and verification — 12 November 2026

The four supplied files are installed byte-for-byte: brain (8).py, llm (3).py, check_llm (1).py, test_brain (8).py. Their logic was not edited. All adaptations are in the existing bridge or separate modules. Songs are forcibly disabled in the application process. Optional paid mapping is disabled; transit uses a user-tapped Google Maps link. No paid song generation was called. No credentials are included in this report or the repository.

## Phase results

| Phase | What was implemented or reused and actually checked |
|---|---|
| 0 | Audited existing voice, maps, panels, music, actions and caches before adding anything. Supplied tests: 21 passed. check_llm: Groq Qwen and OpenRouter free router HTTP 200. Forced Groq tool call HTTP 200; both provider tool checks subsequently passed in /selftest. The documented llama-3.1-8b-instant candidate returned HTTP 404 for this account, so Qwen is retained with reasoning disabled in the adapter. All six required keys/IDs: present. |
| 0 diagnostics | Root cause of the misleading hearing notice: an unconditional backend message on an empty STT response, without checking microphone level or elapsed silence. Empty STT is now reported as recognition failure. The low-mic warning requires eight seconds of low RMS and no transcript, clears on transcript, and does not run while awaiting or speaking. Fake-mic browser checks verified no warning at 6.5 seconds, warning after eight, and clearing on transcript. Triple-tap the existing gNani brand for level/VAD/timers/WebSocket/AudioContext diagnostics. |
| 0 selftest | /selftest Run all made real calls: Gnani STT/TTS, Groq/OpenRouter tool support, Jamendo, YouTube, Pixabay images, LocationIQ/geocoder and a real OSRM test route. All rows passed. Theme change and actual browser audio-playing event passed. The route test uses explicitly labelled test coordinates, never the user's GPS. Media checks reuse production caches. |
| 1 | Existing microphone/typing controls reused. Eight fake-mic Chromium checks passed, including track release, zero muted audio uploads, reload persistence, typed text-only reply, Listen/Stop, preserved playback while muted, echo rejection, fresh acquisition and the ten-minute silent banner. Final detection plus fade: 494 ms. |
| 2 | Removed the three-sentence bridge cutoff, added f/m segment handling and next-sentence prefetch. Normalized speech and voice-test page retained. Real male selections Pranav (English), Deepak (Hindi), Kavin (Kannada) all returned Timbre HTTP 200 audio. Controlled bridge test passed a 24-sentence two-voice story. A real 43-sentence synthesis exposed a separate model-token cutoff; the adapter now continues responses ending with finish_reason=length, with a tested bounded continuation path and 900 tokens per call. The final complete real model response took 3417 ms. Its recorded response was replayed through the browser with real Timbre: all 44 audio sentences played and ended, across eleven female/male segment streams, including the actual final sentence. No browser voice or pitch shifting is used. |
| 3 | Actual calm-music browser playback succeeded from Jamendo, stop removed its card, and Sapphire by Ed Sheeran played in the visible official YouTube player. The first tested library stream failed but the next returned HTTP 200. Automatic track/provider fallback, non-CORS retry and explicit tap-to-play state were added. Generated music uses chords, bass, light percussion and reverb; generated spoken-line pause/resume/stop and YouTube state controls passed. Generated lines remain labelled spoken rather than real singing. |
| 4 | All eight warm themes rendered in Chromium. CSS/Canvas foundations retained; React Bits backgrounds are deferred. Wave bands read music and Timbre analysers, with simulated YouTube movement, 30 fps maximum and reduced-motion/Calm mode static rendering. |
| 5 | Destination card and spoken origin question work without GPS. The real no-GPS Electronic City request completed without an error after the empty-map-text adapter fix. No route distance is invented without origin. A recorded real 683 m OSRM route and mocked GPS verified the in-page line, dot and walking banner. Unit simulation covers progress, early/now announcements, wrong turns, weak GPS, arrival and safety reminders. No physical user journey was tested; GPS work remains parked. |
| 6 | Reused cached photo/video endpoints and helper panel. Browser verified real photo/video responses, no video iframe before tapping, tap-created timers, next-step highlighting and scrolling. Timer parser tested English, Devanagari and Kannada digits, minutes, hours and seconds. |
| 7 | Actual browser contact confirmation passed; dial link was intercepted so no real call was placed. The one-minute reminder fired after 60623 ms, spoke, produced desktop service-worker notifications and did not repeat on reload. Phone number was not uploaded. |
| 8 | Final suites: 21 supplied offline tests, 55 backend tests, 15 frontend tests, production build passed. English, Hindi and Kannada live text requests matched their languages; Hindi dosa request selected cooking and a helper panel. Failed/ignored-LLM map/music backups passed supplied tests; browser checks also replayed actual backend failed-LLM fallback events. See limitations below. |
| 9 | All ten requested JS+CSS components were installed using the documented CLIs: shadcn requested initialization, then jsrepo installed them. Installed component props were read before wiring. Vendor CSS files were moved adjacent to their installed JSX imports; component source was not pasted/retyped. Strands replaces the orb on capable devices. VoicePill is a decorative/control composition using the existing mic's RMS, with its own mic capture disabled; it never acquires a second stream. SpringCheck, Stepper and StatusMark are integrated. Backgrounds are lazy, one at a time; warm light-mode props, DPR 1.5 cap and 800 ms theme transition. Every theme, Calm mode, lite=1, WebGL-disabled fallback, weak-device fallback and hidden-page WebGL cleanup were tested. |

## Bundle sizes

Before visual upgrade: main JavaScript 148.19 KB gzip (original baseline 146.13 KB). Final main bundle is approximately 150.5 KB gzip. Backgrounds, Strands, VoicePill, motion widgets and Tone.js remain separate lazy chunks; the largest background is Topography at 12.90 KB gzip, and the shared motion chunk is 21.67 KB gzip. Growth is well below 250 KB gzip.

## Evidence and limits

- Screenshots below include controlled theme events, not a claim that every topic was requested from the live LLM. Recipe/walking UI checks use replayed real panel data and explicitly controlled test steps/GPS/OSRM fixtures. The full-story browser test replays the verified complete real model response while using real Timbre synthesis and playback.
- Initial development-server tests were interrupted by dependency hot reloads. Final microphone/panel/theme checks were rerun against the compiled production app.
- Real provider rate limits were observed, including Groq HTTP 429; a later check succeeded. Free services are not consistently available.
- The 43-sentence initial story was not a complete model ending; this was caught, reported and corrected. A forced truncation/continuation regression test passed, and a subsequent real response plus full browser playback reached a complete ending.
- Physical Android acoustics, Android background alerts after closing the app, on-road safety/real GPS travel, and subjective voice naturalness remain unverified. Notifications are promised only while the app remains open. A separate v2.5 Hinglish male voice is not documented; that locale falls back to its normal voice.
- Playback events verify browser playback, not a person physically hearing it. No microphone end-of-speech latency average on a physical phone was measured. The old long-story test had 17.27 seconds to first synthesized audio; its model wait was 14.78 seconds, so this is not a measurement of ordinary conversation latency.

## Screenshots

[Self-test table](docs/verification-2026-11-12/selftest.png) · [Calm mode](docs/verification-2026-11-12/calm-mode.png) · [WebGL disabled](docs/verification-2026-11-12/webgl-disabled.png) · [Complete story playback](docs/verification-2026-11-12/story-finished.png)

[Default theme](docs/verification-2026-11-12/bits-default.png)

[Cooking theme](docs/verification-2026-11-12/bits-cooking.png)

[Music theme](docs/verification-2026-11-12/bits-music.png)

[Travel theme](docs/verification-2026-11-12/bits-travel.png)

[Health theme](docs/verification-2026-11-12/bits-health.png)

[Devotional theme](docs/verification-2026-11-12/bits-devotional.png)

[Story theme](docs/verification-2026-11-12/bits-story.png)

[Learning theme](docs/verification-2026-11-12/bits-learning.png)

Official references: [Groq models](https://console.groq.com/docs/models), [Groq tools](https://console.groq.com/docs/tool-use/overview), [Timbre voices](https://docs.gnani.ai/api/TTS/available-voices), [React Bits installation](https://reactbits.dev/get-started/installation).
