# Multilingual speech and YouTube verification

Run on 12 November 2026. No secrets printed. Original brain.py and llm.py logic unchanged.

- Production build: PASS (existing main-chunk size warning remains).
- Existing test_brain.py: all 21 offline tests PASS.
- New multilingual tests: six PASS (38 catalog entries, routing, eight detection examples, normalization preservation, secondary-provider payload/audio, free-tier opt-in and quota error, recognition).
- YouTube filter/cache/validation test: PASS, mocked official API verifies videoDuration, eventType, playlist parameters and cache reuse.
- Chromium mobile 390×844: PASS for 38 choices plus Auto, preference persistence, four filters, playlist embed URL, video/playlist favourites saved across reload, replay, no runtime errors. YouTube search/player mocked for browser interaction checks.
- Real French Gemini speech: valid WAV, 3.34 s.
- Real Spanish Gemini speech: valid WAV, 2.97 s; Groq transcription round-trip correctly identified Spanish, 0.55 s.
- Real Japanese Gemini speech: valid WAV, 3.00 s.
- Real WebSocket conversation -> reply -> first audio: French 3.17 s, Spanish 5.09 s, Tamil 2.79 s. Same-language reply locale and valid audio verified. Typed test input with aloud=true; not an acoustic microphone test.
- Real YouTube searches HTTP 200: Videos 12 (0.41 s), short videos 12 (0.36 s), live Bengaluru news 0 (0.28 s), playlists 12 (0.45 s).

Limits: all 38 payload paths covered offline, not 38 live acoustic/fluency tests. Browser decoding and returned WAV format are checked; human judgments of accent/naturalness and physical Android microphone acoustics are not verified. Official YouTube media playback availability varies by owner/device; browser controls/embed behavior used a mocked player. Favourites are device-local, not shared or synced. Shorts is the API's short-duration approximation. Interface labels and walking templates are not localized into all 38 languages. Free-tier status is user-confirmed and guarded by configuration, not discoverable/enforceable from a Gemini API key.
