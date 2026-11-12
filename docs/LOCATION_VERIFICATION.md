# Location and key-exposure verification

12 November 2026. No key values printed, logged or committed.

Root causes fixed:
- A null location frame set the backend first-fix event prematurely.
- Typed messages and WebSocket reconnects omitted the latest GPS.
- An existing watch did not replay its fix when a new backend session asked.
- Previously denied controllers could not recover after permission was enabled.
- Ended journeys and stale fixes could leave old positions usable as current GPS.
- Geoapify could substitute a broad city result for a specific station search.
- Leaflet destination tooltip strings could interpret HTML; labels now use text nodes.

Verification:
- 13 targeted backend tests PASS: GPS wait/handoff, denial, freshness, geocoder quality/cache, plus speech, YouTube and shared hearts regressions.
- 17 frontend unit tests PASS, including GPS controller, simulated real OSRM walking, weak accuracy, off-route and arrival.
- Production build PASS (existing bundle-size warning remains).
- Chromium 390×844 mocked GPS: granted permission sends coordinates plus accuracy and shows in-page map/route. Denied permission shows the destination and accepts a manually selected start; route appears and live walking is disabled. Conversation/routing responses mocked in browser interaction test.
- Actual Geoapify: Majestic Bus Station (2 candidates, 4.06 s), Lalbagh Botanical Garden (3 candidates, 2.07 s), Electronic City area (5 candidates, 0.99 s).
- Exact Electronic City metro station search: no verified matches after rejecting the false broad-city result and trying LocationIQ/Nominatim (4.00 s). No exact-station route claimed.
- Actual OSRM route between explicitly selected public test landmarks, Majestic Bus Station and Lalbagh: walking 4,928 m / 66 min (0.59 s); driving 5,746 m / 9 min (0.59 s). Test points are not the user's GPS.
- No current configured key values found in frontend source/dist/public, full Git patch history, backend logs or eight public responses. No Groq/OpenRouter/Google key patterns found in Git history. No private .env tracked.
- Dot-file paths blocked. Public /api/config returns only a boolean feature flag, not keys.

New Geoapify key is used backend-only. Google Geolocation and OpenWeather keys are privately stored but inactive for GPS; no paid API requests were made.

Not verified: physical Android GPS/acoustics, the user's OS/browser location settings, every provider-account key restriction, every possible vulnerability. Passing these checks is not a claim of a completely bug-free or leak-proof system. Geocoders may lack specific recently opened station/entrance data; the app asks for a landmark instead of inventing a match.
