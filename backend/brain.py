"""Conversation brain: general assistant by default; navigation via real
OSM data (Nominatim + OSRM) only when the user asks for directions."""
import asyncio
import json
import os
import re
import time
import httpx
import llm

SYSTEM = """You are gNani, a warm, patient voice companion for elderly people in India.
You are a general personal assistant: answer ANY question (recipes, health basics,
general knowledge, writing messages, advice) directly and helpfully.

LANGUAGE: Reply in the SAME language and script as the user's latest message.
English in -> English out. Hindi (Devanagari) -> Hindi. Kannada -> Kannada.
Romanized Hindi/Hinglish -> reply in simple Romanized Hindi. If the user switches, switch.

STYLE: You are spoken aloud. By default use 1-3 short, warm sentences. BUT when she asks for something long (a story, a poem, reading something out, a detailed explanation, a recipe told step by step) speak for as long as it needs, in natural paragraphs of short sentences, with no length cap. No lists, markdown,
emojis or symbols. Sound like a kind family member. Offer more only if useful.

DIRECTIONS: Only when the user wants to go somewhere, use the tools. ALWAYS call show_map
with the destination so a map with walk, drive and bus/metro buttons appears, and tell her
she can tap the big Bus/Metro button for buses and metro from Google Maps. Bus and metro
details come from Google Maps, not from you, so never state bus numbers or times yourself.
1) search_place for the destination. If several results differ, ask which one.
2) get_route with the destination. If it says location_unavailable, ask once
   "Where are you right now?", search_place for that, and call get_route with origin.
3) Tell the real distance and time and the first one or two steps in plain words.
   Use ONLY numbers, turns and road names the tools returned. Never invent routes,
   distances, bus numbers, fares or live times. For buses say honestly that live
   times and fares cannot be checked, suggest the nearest bus stop or asking the
   conductor, and still give the walking/driving route. Never end with a dead end.
VISUAL HELP: When the user asks how to make or do something (a recipe, a repair, a form,
a health routine) or about a topic where pictures help, ALSO call show_panel with a short
title, a few photo search phrases (English), and short steps/ingredients/tips written in the
user's language. Speak only a short overview (1-3 sentences), say the details are on screen
below, and offer to go step by step. Never read the whole list aloud. Text inside
[on screen: ...] in earlier turns is context for you only; never say or repeat it.
When the user asks "next step" or "repeat step 2", use that context.
LIVE GUIDANCE: While the user is walking, the app speaks the turn instructions itself.
You only answer questions, using ONLY the numbers in the LIVE NAVIGATION STATE message. If
no such message exists, say you cannot see where they are right now.
HUMAN VOICE: Talk like a warm real person, not a chatbot. Use everyday spoken words, contractions,
and natural little reactions ("achha", "oh, I see") but vary them and do not start every reply the
same way. Match her mood: gentle if she sounds worried, cheerful if she is happy. Ask at most one
question at a time. Never mention being an AI unless sincerely asked.
VOICES: Your own voice is female. When telling a story or quoting a man or boy, put those words between
[[M]] and [[/M]] so a male voice is used, and between [[F]] and [[/F]] for a woman or girl. Use the tags
only for such quoted speech, never for normal talking.
THEMES: At the start of every new topic call set_theme so the screen matches (cooking, music, travel,
health, devotional, story, learning). Return to default for ordinary chat.
SINGING: When she asks you to sing, call compose_song with ORIGINAL lyrics you write, a clear style
(genre, mood, tempo, instruments) and the vocal she wants (male or female). Never name real artists in
the style. If she asks for a specific song by a real artist, or for a real singer's voice, kindly say you
cannot copy another singer's song or voice, then offer (a) to play the real song with play_music source
'youtube', or (b) to compose a new original song in a similar mood. Never write out lyrics of existing songs.
If compose_song reports it is not configured, fall back to play_music with source 'generated'.
MUSIC: When she wants music or a song, call play_music (source 'stop' to stop it). Use 'youtube' when she names a particular
song or singer, 'library' for calm or background music, 'generated' for soft instrumental or when
you offer to sing a traditional lullaby or folk song. NEVER write out lyrics of copyrighted songs;
offer to play the real song instead. Say honestly that you are speaking the song with music, not
singing like a real singer, if she asks.
PHONE ACTIONS: For "call Ramesh", "message my son", "remind me to take medicine in 30 minutes" or
"set a 10 minute timer", call propose_action. You cannot do it yourself: say that a button is on
screen and she should tap it to confirm. Never handle money, passwords, OTPs or bank apps.
SAFETY: Never tell someone to cross a road based on the route alone; say to cross only
at a safe place and not to look at the phone while crossing. Never ask for OTPs,
bank details or Aadhaar numbers; warn about scams. For serious health or money
matters, give simple careful info and suggest a doctor or family member.
If sincerely asked, say you are an AI companion."""

TOOLS = [
    {"type": "function", "function": {
        "name": "set_theme",
        "description": "Change the look of the whole screen to match the topic. Call this at the START of "
                       "any new topic: cooking/recipes -> cooking, songs/music -> music, directions -> travel, "
                       "health -> health, bhajans/prayer -> devotional, stories/kids -> story, learning -> learning, "
                       "otherwise default.",
        "parameters": {"type": "object", "properties": {"theme": {"type": "string", "enum": [
            "default", "cooking", "music", "travel", "health", "devotional", "story", "learning"]}},
            "required": ["theme"]}}},
    {"type": "function", "function": {
        "name": "compose_song",
        "description": "Compose a complete ORIGINAL song with real AI vocals when she asks you to sing. You write "
                       "original lyrics. Describe style by genre, mood, tempo and instruments only. NEVER name real "
                       "artists, never imitate a real singer's voice, never use lyrics from existing songs.",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"},
            "style": {"type": "string", "description": "e.g. 'warm acoustic pop ballad, gentle guitar, slow tempo'"},
            "vocal": {"type": "string", "enum": ["male", "female"]},
            "language": {"type": "string", "description": "language of the lyrics"},
            "mood": {"type": "string"},
            "lyrics": {"type": "string", "description": "original lyrics, one line per row, up to 30 lines, "
                       "with [Verse]/[Chorus] markers"},
            "length_sec": {"type": "integer", "description": "30-180"}},
            "required": ["title", "style", "vocal", "lyrics"]}}},
    {"type": "function", "function": {
        "name": "play_music",
        "description": "Play music or a song for the user, or sing a short traditional song. source: "
                       "'library' = free royalty-free music (calm, instrumental, devotional-style); "
                       "'youtube' = a specific popular song or film song the user names (plays the official "
                       "video); 'generated' = soft instrumental made on the device, optionally with a short "
                       "traditional/public-domain lullaby or folk song spoken rhythmically.",
        "parameters": {"type": "object", "properties": {
            "source": {"type": "string", "enum": ["library", "youtube", "generated", "stop"]},
            "query": {"type": "string", "description": "search phrase, e.g. 'Kishore Kumar songs' or 'calm flute'"},
            "mood": {"type": "string", "description": "e.g. calm, happy, devotional, sleepy"},
            "sing_text": {"type": "string", "description": "ONLY for source=generated: up to 8 lines of a "
                          "traditional or public-domain song, or an original rhyme. NEVER copyrighted lyrics."}},
            "required": ["source"]}}},
    {"type": "function", "function": {
        "name": "propose_action",
        "description": "Prepare a simple phone action for the user to confirm with one tap. Never executes by "
                       "itself. kinds: call, message, reminder, timer.",
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["call", "message", "reminder", "timer"]},
            "contact": {"type": "string", "description": "who, as the user said it (call/message)"},
            "text": {"type": "string", "description": "message text or reminder text, user's language"},
            "minutes": {"type": "integer", "description": "reminder/timer in how many minutes (1-1440)"}},
            "required": ["kind"]}}},
    {"type": "function", "function": {
        "name": "show_panel",
        "description": "Show a visual helper panel below the conversation (photos, ingredients, steps, "
                       "tips). Use when the user asks how to make or do something, or about a topic where "
                       "pictures or a checklist help. Not for chit-chat or directions.",
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["recipe", "howto", "info", "health"]},
            "title": {"type": "string", "description": "in the user's language"},
            "summary": {"type": "string", "description": "one short sentence, user's language"},
            "image_queries": {"type": "array", "items": {"type": "string"},
                              "description": "1-3 short ENGLISH photo search phrases"},
            "video_query": {"type": "string", "description": "one YouTube search phrase for a good how-to "
                            "video, in the user's language, e.g. 'dosa recipe in Hindi'. Omit if no video helps."},
            "ingredients": {"type": "array", "items": {"type": "string"}},
            "steps": {"type": "array", "items": {"type": "string"}, "description": "one short sentence each"},
            "tips": {"type": "array", "items": {"type": "string"}}},
            "required": ["kind", "title"]}}},
    {"type": "function", "function": {
        "name": "show_map",
        "description": "Show a map card on screen with walking, driving and bus/metro options "
                       "to a destination. Call this whenever the user wants to go somewhere.",
        "parameters": {"type": "object", "properties": {
            "destination": {"type": "string", "description": "place name as the user said it, add city if known"},
            "dest_lat": {"type": "number"}, "dest_lon": {"type": "number"}},
            "required": ["destination"]}}},
    {"type": "function", "function": {
        "name": "search_place",
        "description": "Find a place by name. Returns up to 3 matches with coordinates.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "place name, add city if known"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_route",
        "description": "Real route to a destination. Origin defaults to the user's GPS.",
        "parameters": {"type": "object", "properties": {
            "dest_lat": {"type": "number"}, "dest_lon": {"type": "number"},
            "origin_lat": {"type": "number"}, "origin_lon": {"type": "number"},
            "mode": {"type": "string", "enum": ["walk", "drive"]}},
            "required": ["dest_lat", "dest_lon"]}}},
]

NOMINATIM = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
OSRM = {"walk": ("foot", os.getenv("OSRM_FOOT_URL", "https://routing.openstreetmap.de/routed-foot")),
        "drive": ("driving", os.getenv("OSRM_CAR_URL", "https://routing.openstreetmap.de/routed-car"))}
UA = os.getenv("NOMINATIM_USER_AGENT", "gNani-voice-assistant/0.1 (contact: set-your-email)")
_nom_lock, _last_nom = asyncio.Lock(), 0.0


IMITATION = re.compile(r"\b(in the (voice|style) of|sounds? like|sing like|mimic\w*|impersonat\w*|"
                       r"cover of|clone\w*|voice of)\b", re.I)
VOICE_TAG = re.compile(r"(\[\[/?[MF]\]\])")
THEMES = ("default", "cooking", "music", "travel", "health", "devotional", "story", "learning")


def split_voices(text):
    """'Hello [[M]]Come here[[/M]] she said' -> [('f','Hello'),('m','Come here'),('f','she said')]"""
    out, voice = [], "f"
    for part in VOICE_TAG.split(text or ""):
        tag = part.upper()
        if tag in ("[[M]]", "[[F]]"):
            voice = tag[2].lower()
        elif tag in ("[[/M]]", "[[/F]]"):
            voice = "f"
        elif part.strip():
            if out and out[-1]["voice"] == voice:
                out[-1]["text"] += " " + part.strip()
            else:
                out.append({"voice": voice, "text": part.strip()})
    return out


def strip_voice_tags(text):
    return re.sub(r"\s+", " ", VOICE_TAG.sub(" ", text or "")).strip()


def detect_language(text):
    """Script-based hint used to pick the TTS voice. en for Latin script."""
    if re.search(r"[\u0C80-\u0CFF]", text or ""): return "kn"
    if re.search(r"[\u0900-\u097F]", text or ""): return "hi"
    return "en"


async def _nominatim(query, client, location):
    global _last_nom
    async with _nom_lock:  # respect Nominatim policy: max 1 request/second
        await asyncio.sleep(max(0, 1.05 - (time.monotonic() - _last_nom)))
        r = await client.get(f"{NOMINATIM}/search", headers={"User-Agent": UA},
                             params={"q": query, "format": "jsonv2", "limit": 3, "countrycodes": "in"})
        _last_nom = time.monotonic()
    r.raise_for_status()
    return [{"name": x["display_name"], "lat": float(x["lat"]), "lon": float(x["lon"])} for x in r.json()]


async def _locationiq(query, client, location):
    key = os.getenv("LOCATIONIQ_API_KEY")
    if not key: return []
    base = os.getenv("LOCATIONIQ_BASE_URL", "https://us1.locationiq.com/v1")
    r = await client.get(f"{base}/search", params={"key": key, "q": query, "format": "json",
                                                   "countrycodes": "in", "limit": 3})
    if r.status_code == 404: return []  # LocationIQ returns 404 when nothing is found
    r.raise_for_status()
    return [{"name": x["display_name"], "lat": float(x["lat"]), "lon": float(x["lon"])} for x in r.json()]


async def _geoapify(query, client, location):
    key = os.getenv("GEOAPIFY_API_KEY")
    if not key: return []
    params = {"text": query, "limit": 3, "filter": "countrycode:in", "apiKey": key}
    if location: params["bias"] = f"proximity:{location['lon']},{location['lat']}"
    r = await client.get("https://api.geoapify.com/v1/geocode/search", params=params)
    r.raise_for_status()
    return [{"name": f["properties"].get("formatted", query), "lat": float(f["properties"]["lat"]),
             "lon": float(f["properties"]["lon"])} for f in r.json().get("features", [])]


GEOCODERS = {"locationiq": _locationiq, "geoapify": _geoapify, "nominatim": _nominatim}


async def search_place(query, client, location=None):
    """Tries each geocoder in GEOCODERS_ORDER; first one with results wins."""
    order = os.getenv("GEOCODERS", "geoapify,locationiq,nominatim").split(",")
    failed = 0
    for name in (n.strip() for n in order):
        fn = GEOCODERS.get(name)
        if not fn: continue
        try:
            results = await fn(query, client, location)
        except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
            failed += 1
            continue
        if results:
            return {"results": results, "source": name}
    if failed:
        return {"error": "service_unavailable"}
    return {"results": [], "note": "no match; ask the user for a nearby landmark or the area name"}


def summarize_route(data, max_steps=6):
    """Reduce an OSRM response to verified facts only."""
    route = data["routes"][0]
    steps = []
    for s in route["legs"][0]["steps"]:
        m = s.get("maneuver", {})
        if m.get("type") == "arrive":
            steps.append({"action": "arrive", "road": s.get("name", ""), "meters": 0})
        else:
            steps.append({"action": m.get("type", "continue"), "turn": m.get("modifier", ""),
                          "road": s.get("name", ""), "meters": round(s["distance"])})
    return {"distance_m": round(route["distance"]), "duration_min": max(1, round(route["duration"] / 60)),
            "first_steps": steps[:max_steps], "total_steps": len(steps)}


async def get_route(args, location, client):
    olat, olon = args.get("origin_lat"), args.get("origin_lon")
    if olat is None and location:
        olat, olon = location["lat"], location["lon"]
    if olat is None:
        return {"error": "location_unavailable"}
    prof, base = OSRM[args.get("mode", "walk")]
    url = f"{base}/route/v1/{prof}/{olon},{olat};{args['dest_lon']},{args['dest_lat']}"
    r = await client.get(url, params={"overview": "false", "steps": "true"})
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        return {"error": "no_route_found"}
    return summarize_route(data)


def google_links(dest_text, dest=None, origin=None):
    """Deep links that open Google Maps with the route ready. Without an origin,
    Google Maps starts from the phone's current location."""
    from urllib.parse import quote
    q = quote(dest_text) if dest_text else (f"{dest['lat']},{dest['lon']}" if dest else "")
    base = f"https://www.google.com/maps/dir/?api=1&destination={q}"
    if origin:
        base += f"&origin={origin['lat']},{origin['lon']}"
    return {"walk": base + "&travelmode=walking", "drive": base + "&travelmode=driving",
            "transit": base + "&travelmode=transit"}


async def run_tool(name, args, location, client, sink=None):
    sink = sink if sink is not None else {}
    try:
        if name == "show_panel":
            def lst(key, n):
                v = args.get(key) or []
                return [clean(str(x))[:200] for x in v if clean(str(x))][:n] if isinstance(v, list) else []
            sink["panel"] = {"kind": args.get("kind", "info"), "title": clean(args.get("title", ""))[:120],
                             "summary": clean(args.get("summary", ""))[:240],
                             "image_queries": lst("image_queries", 3), "video_query": clean(str(args.get("video_query") or ""))[:100],
                             "ingredients": lst("ingredients", 20),
                             "steps": lst("steps", 12), "tips": lst("tips", 5)}
            return {"shown": True}
        if name == "set_theme":
            theme = args.get("theme") if args.get("theme") in THEMES else "default"
            sink["theme"] = theme
            return {"theme": theme}
        if name == "compose_song":
            if os.getenv("SONGS_ENABLED") != "1" or not (os.getenv("GEMINI_API_KEY") or os.getenv("ELEVENLABS_API_KEY")):
                return {"error": "song_service_not_configured"}
            style, title = clean(str(args.get("style") or ""))[:200], clean(str(args.get("title") or ""))[:80]
            if IMITATION.search(style) or IMITATION.search(title):
                return {"error": "no_artist_imitation",
                        "hint": "describe genre, mood, tempo and instruments instead of any real singer"}
            lines = [clean(x)[:200] for x in str(args.get("lyrics") or "").splitlines() if clean(x)][:30]
            if not lines:
                return {"error": "lyrics_required"}
            try:
                length = min(180, max(30, int(args.get("length_sec") or 120)))
            except (TypeError, ValueError):
                length = 120
            sink["song"] = {"title": title, "style": style,
                            "vocal": "male" if args.get("vocal") == "male" else "female",
                            "language": clean(str(args.get("language") or ""))[:30],
                            "mood": clean(str(args.get("mood") or ""))[:40], "lyrics": lines, "length_sec": length}
            return {"started": True, "note": "composing takes about a minute; tell her it is being made"}
        if name == "play_music":
            src = args.get("source") if args.get("source") in ("library", "youtube", "generated", "stop") else "library"
            music = {"source": src, "query": clean(str(args.get("query") or ""))[:100],
                     "mood": clean(str(args.get("mood") or ""))[:40]}
            if src == "generated" and args.get("sing_text"):
                music["sing_text"] = clean(str(args["sing_text"]))[:600]
            sink["music"] = music
            return {"started": True}
        if name == "propose_action":
            kind = args.get("kind")
            if kind not in ("call", "message", "reminder", "timer"):
                return {"error": "unsupported_action"}
            try:
                minutes = min(1440, max(1, int(args.get("minutes") or 0))) if args.get("minutes") else None
            except (TypeError, ValueError):
                minutes = None
            act = {"kind": kind, "contact": clean(str(args.get("contact") or ""))[:60],
                   "text": clean(str(args.get("text") or ""))[:300], "minutes": minutes}
            sink.setdefault("actions", [])
            if len(sink["actions"]) < 3:
                sink["actions"].append(act)
            return {"prepared": True, "needs_user_tap": True}
        if name == "show_map":
            dest = None
            if args.get("dest_lat") is not None and args.get("dest_lon") is not None:
                dest = {"lat": float(args["dest_lat"]), "lon": float(args["dest_lon"])}
            sink["map"] = {"destination": args["destination"], "dest": dest, "origin": location,
                           "links": google_links(args["destination"], dest, location)}
            return {"shown": True}
        if name == "search_place": return await search_place(args["query"], client, location)
        if name == "get_route": return await get_route(args, location, client)
        return {"error": "unknown_tool"}
    except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
        return {"error": "service_unavailable"}


async def full_route(origin, dest, mode, client):
    """Complete route for live guidance: line coordinates [[lat,lon],...] and steps. Each step's
    lat/lon is where its maneuver happens; 'meters' is the distance from that point to the next."""
    prof, base = OSRM[mode]
    url = f"{base}/route/v1/{prof}/{origin['lon']},{origin['lat']};{dest['lon']},{dest['lat']}"
    r = await client.get(url, params={"overview": "full", "geometries": "geojson", "steps": "true"})
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        return {"error": "no_route_found"}
    route, steps = data["routes"][0], []
    for s in route["legs"][0]["steps"]:
        m = s.get("maneuver", {})
        lon, lat = m["location"]
        steps.append({"action": m.get("type", "continue"), "turn": m.get("modifier", ""),
                      "road": s.get("name", ""), "meters": round(s["distance"]), "lat": lat, "lon": lon})
    return {"mode": mode, "distance_m": round(route["distance"]),
            "duration_min": max(1, round(route["duration"] / 60)),
            "coords": [[c[1], c[0]] for c in route["geometry"]["coordinates"]], "steps": steps}


async def image_search(query, client, limit=4):
    """Photos for the helper panel. Order: Pixabay, Pexels (if keys set), then Wikimedia Commons (no key)."""
    out = []
    pkey = os.getenv("PIXABAY_API_KEY")
    if pkey:
        try:
            r = await client.get("https://pixabay.com/api/", params={
                "key": pkey, "q": query, "image_type": "photo", "safesearch": "true", "per_page": max(3, limit)})
            r.raise_for_status()
            out = [{"url": h["webformatURL"], "alt": h.get("tags") or query, "credit": h.get("user", ""),
                    "page": h.get("pageURL", ""), "source": "Pixabay"} for h in r.json().get("hits", [])]
        except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
            out = []
        if out:
            return out[:limit]
    key = os.getenv("PEXELS_API_KEY")
    if key:
        try:
            r = await client.get("https://api.pexels.com/v1/search", params={"query": query, "per_page": limit},
                                 headers={"Authorization": key})
            r.raise_for_status()
            out = [{"url": p["src"]["medium"], "alt": p.get("alt") or query, "credit": p.get("photographer", ""),
                    "page": p.get("url", ""), "source": "Pexels"} for p in r.json().get("photos", [])]
        except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
            out = []
    if out:
        return out[:limit]
    try:
        r = await client.get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": UA}, params={
            "action": "query", "generator": "search", "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": limit * 3,
            "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": 640, "format": "json"})
        r.raise_for_status()
        pages = sorted((r.json().get("query") or {}).get("pages", {}).values(), key=lambda x: x.get("index", 0))
        for p in pages:
            ii = (p.get("imageinfo") or [{}])[0]
            if ii.get("mime") not in ("image/jpeg", "image/png"):
                continue
            meta = ii.get("extmetadata", {})
            out.append({"url": ii.get("thumburl") or ii.get("url"), "alt": query,
                        "credit": re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", ""))[:80],
                        "license": meta.get("LicenseShortName", {}).get("value", ""),
                        "page": ii.get("descriptionurl", ""), "source": "Wikimedia Commons"})
    except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
        return []
    return out[:limit]


_yt_usage = {"day": "", "n": 0}


async def video_search(query, client, limit=3):
    """YouTube how-to videos (embeddable only, strict safe search). Each search costs 100 quota units
    of the free 10,000/day, so there is a hard daily cap (YT_DAILY_SEARCH_LIMIT, default 90)."""
    key = os.getenv("YOUTUBE_API_KEY")
    if not key or not query:
        return {"videos": [], "reason": "no_key" if not key else "empty_query"}
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if _yt_usage["day"] != today:
        _yt_usage.update(day=today, n=0)
    if _yt_usage["n"] >= int(os.getenv("YT_DAILY_SEARCH_LIMIT", "90")):
        return {"videos": [], "reason": "daily_limit"}
    _yt_usage["n"] += 1
    try:
        r = await client.get("https://www.googleapis.com/youtube/v3/search", params={
            "part": "snippet", "type": "video", "q": query, "maxResults": limit, "videoEmbeddable": "true",
            "safeSearch": "strict", "regionCode": "IN", "key": key})
        if r.status_code == 403:
            return {"videos": [], "reason": "quota_or_key"}
        r.raise_for_status()
        vids = [{"id": i["id"]["videoId"], "title": i["snippet"]["title"], "channel": i["snippet"]["channelTitle"],
                 "thumb": (i["snippet"]["thumbnails"].get("medium") or i["snippet"]["thumbnails"]["default"])["url"]}
                for i in r.json().get("items", []) if i.get("id", {}).get("videoId")]
        return {"videos": vids}
    except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
        return {"videos": [], "reason": "unavailable"}


async def music_search(query, client, mood=None, limit=5):
    """Creative Commons tracks from Jamendo (free client id, non-commercial use). Needs JAMENDO_CLIENT_ID."""
    cid = os.getenv("JAMENDO_CLIENT_ID")
    if not cid:
        return {"tracks": [], "reason": "no_key"}
    base = os.getenv("JAMENDO_BASE_URL", "https://api.jamendo.com/v3.0")
    out = []
    for params in ({"search": query} if query else {}, {"fuzzytags": mood} if mood else {}):
        if not params:
            continue
        try:
            r = await client.get(f"{base}/tracks/", params={"client_id": cid, "format": "json", "limit": limit,
                                 "audioformat": "mp32", "order": "popularity_week", **params})
            r.raise_for_status()
            out = [{"title": t["name"], "artist": t.get("artist_name", ""), "url": t["audio"],
                    "image": t.get("image", ""), "license": t.get("license_ccurl", ""), "page": t.get("shareurl", "")}
                   for t in r.json().get("results", []) if t.get("audio")]
        except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
            out = []
        if out:
            break
    return {"tracks": out[:limit]} if out else {"tracks": [], "reason": "none_found"}


FALLBACK = {
    "rate_limit": {"en": "Too many people are talking to me right now. Please ask again in a minute.",
                   "hi": "अभी बहुत लोग मुझसे बात कर रहे हैं। एक मिनट बाद फिर से कहिए।",
                   "kn": "ಈಗ ಸ್ವಲ್ಪ ಜನದಟ್ಟಣೆ ಇದೆ. ಒಂದು ನಿಮಿಷ ಬಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ."},
    "auth": {"en": "My connection has a problem. Please tell the person who set me up.",
             "hi": "मेरे कनेक्शन में कुछ गड़बड़ है। जिसने मुझे बनाया है, उन्हें बता दीजिए।",
             "kn": "ನನ್ನ ಸಂಪರ್ಕದಲ್ಲಿ ಸಮಸ್ಯೆ ಇದೆ. ನನ್ನನ್ನು ಸಿದ್ಧಪಡಿಸಿದವರಿಗೆ ತಿಳಿಸಿ."},
    "unavailable": {"en": "I can't answer right now. Please try again in a little while.",
                    "hi": "अभी मैं जवाब नहीं दे पा रही हूँ। थोड़ी देर बाद फिर कोशिश कीजिए।",
                    "kn": "ನನಗೆ ಈಗ ಉತ್ತರಿಸಲು ಆಗುತ್ತಿಲ್ಲ. ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."},
}
FALLBACK["timeout"] = FALLBACK["unavailable"]
FALLBACK["no_providers"] = FALLBACK["auth"]


def clean(text):
    text = re.sub(r"\[on screen:.*?\]", "", text or "", flags=re.S)
    text = re.sub(r"[*_#`>]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------- rule-based backup so key features still work if the LLM fails or ignores its tools ----------
MUSIC_WORDS = re.compile(r"\b(songs?|music|gaan[ae]|gana|bhajans?|lullab(?:y|ies)|tracks?|playlist|sangeet)\b|"
                         r"गाना|गाने|गीत|संगीत|म्यूज़िक|म्यूजिक|भजन|लोरी|ಹಾಡು|ಹಾಡನ್ನು|ಸಂಗೀತ|ಭಜನೆ", re.I)
ACTION_CUE = re.compile(r"\b(play|put on|start|listen|hear|want|wanna|need|give me|bajao|bajaao|baja|laga|lagao|"
                        r"chalao|chala|sunao|suna|sunna|chahiye|dalo)\b|सुन|बजा|चला|लगा|चाहिए|ಹಾಕಿ|ಕೇಳ|ಬೇಕು", re.I)
STOP_WORD = re.compile(r"\b(stop|pause|turn off|band karo|band kar do|bandh karo)\b|बंद|रोक|ನಿಲ್ಲಿಸಿ|ನಿಲ್ಲಿಸು", re.I)
SING_WORD = re.compile(r"\b(sing|gaao|gao|gaa do)\b|गाओ|गा दो|ಹಾಡಿ", re.I)
_FILLER = re.compile(r"\b(please|can you|could you|will you|for me|me|i want to|i wanna|i would like to|want to|"
                     r"listen to|hear|play|put on|start|some|a|an|the|my|songs?|music|tracks?|playlist|gaan[ae]|gana|"
                     r"bajao|bajaao|baja do|laga do|lagao|chalao|chala do|sunao|suna do|mujhe|kuch|koi|ek|ka|ki|ke|ko|"
                     r"do|de|karo|zara|plz|pls)\b|गाना|गाने|संगीत|सुनाओ|बजाओ|लगाओ|चलाओ|मुझे|कुछ|कोई|एक|के|का|की|को|दो|करो", re.I)
_GENERIC = {"calm", "relaxing", "relax", "soothing", "soft", "gentle", "happy", "sleepy", "sleep", "devotional",
            "bhajan", "bhajans", "lullaby", "good", "nice", "new", "old", "any", "something", "instrumental",
            "background", "peaceful", "morning", "evening", "night", "party", "dance", "prayer", "and", "to", "of", "on"}
_MOODS = (("sleepy", ("lullaby", "lori", "sleep", "sleepy", "लोरी")), ("devotional", ("bhajan", "devotional", "prayer", "भजन")),
          ("happy", ("happy", "party", "dance", "cheerful")), ("calm", ("calm", "relax", "relaxing", "soothing", "peaceful", "soft", "gentle")))
MAP_STRONG = [
    re.compile(r"\b(?:take me to|navigate to|directions? to|route to|i (?:want|need) to (?:go|get) to|i(?:'m| am) going to)\s+(?P<d>.+)", re.I),
    re.compile(r"\b(?:mujhe|muje)\s+(?P<d>.+?)\s+(?:jaana|jana|pahunchna|pahuchna)\s+(?:hai|h)\b", re.I),
    re.compile(r"(?:मुझे\s+)?(?P<d>.+?)\s+(?:जाना|पहुंचना|पहुँचना)\s+है"),
]
MAP_WEAK = [
    re.compile(r"\b(?:how (?:do|can) i (?:get|go|reach)(?: to)?|how to (?:get|go|reach)(?: to)?|way to)\s+(?P<d>.+)", re.I),
    re.compile(r"(?P<d>.+?)\s+(?:kaise|kese)\s+(?:jaun|jaoon|jayen|jaye|pahunchu|pahunchun|jaana|jana)\b", re.I),
    re.compile(r"(?P<d>.+?)\s+कैसे\s+(?:जाऊं|जाऊँ|जाएं|जाएँ|पहुंचूं|पहुँचूँ|जाना)"),
]
_DEST_TAIL = re.compile(r"\s*\b(please|from here|now|today|right now|kaise|na|plz|pls)\b.*$|[?!.,।]+$", re.I)
_ROMAN_HINDI = re.compile(r"\b(mujhe|muje|kaise|kahan|jaana|jana|bajao|sunao|gaana|laga|chahiye|karo|kya|nahi|accha|achha)\b", re.I)


def _destination(text, patterns):
    for p in patterns:
        m = p.search(text)
        if m:
            d = _DEST_TAIL.sub("", m.group("d")).strip(" '\"")
            d = re.sub(r"^(the|a)\s+", "", d, flags=re.I)
            if d and len(d.split()) <= 6 and not MUSIC_WORDS.search(d):
                return d
    return None


def _music_intent(text):
    t = text or ""
    low = t.lower()
    if STOP_WORD.search(t) and (MUSIC_WORDS.search(t) or SING_WORD.search(t)):
        return {"source": "stop", "query": "", "mood": ""}
    if SING_WORD.search(t):
        return {"source": "generated", "query": "", "mood": "calm"}
    by_song = ACTION_CUE.search(t) and re.search(r"\bplay\b.+\bby\b", low)
    if not ((MUSIC_WORDS.search(t) and ACTION_CUE.search(t)) or by_song):
        return None
    q = re.sub(r"[?!.,।]", " ", low)
    q = re.sub(r"\s+", " ", _FILLER.sub(" ", q)).strip()
    mood = next((m for m, words in _MOODS if any(w in low for w in words)), "")
    named = [w for w in q.split() if w not in _GENERIC]
    if not named:
        return {"source": "library", "query": mood or "calm", "mood": mood or "calm"}
    if " by " not in f" {q} " and "songs" not in q:
        q += " songs"
    return {"source": "youtube", "query": q, "mood": mood}


def quick_intents(text):
    """Cheap, deterministic detection used when the LLM fails or ignores its tools."""
    out = {}
    music = _music_intent(text)
    if music:
        out["music"] = music
    strong = _destination(text, MAP_STRONG)
    weak = None if strong else _destination(text, MAP_WEAK)
    if strong or weak:
        out["map"], out["map_strong"] = strong or weak, bool(strong)
    return out


def reply_lang(text):
    lang = detect_language(text)
    return lang if lang != "en" else ("hl" if _ROMAN_HINDI.search(text or "") else "en")


TEMPLATES = {
    "music": {"en": "Sure! I've put some music on the screen. Tap play if it does not start by itself.",
              "hi": "ज़रूर! मैंने संगीत लगा दिया है। अगर अपने आप न बजे तो प्ले बटन दबाइए।",
              "hl": "Zaroor! Maine gaana laga diya hai. Agar apne aap na baje to play button dabaiye.",
              "kn": "ಖಂಡಿತ! ನಾನು ಸಂಗೀತವನ್ನು ಹಾಕಿದ್ದೇನೆ. ತಾನಾಗಿ ಪ್ರಾರಂಭವಾಗದಿದ್ದರೆ ಪ್ಲೇ ಬಟನ್ ಒತ್ತಿ."},
    "stop": {"en": "Okay, I've stopped the music.", "hi": "ठीक है, मैंने संगीत बंद कर दिया।",
             "hl": "Theek hai, maine gaana band kar diya.", "kn": "ಸರಿ, ಸಂಗೀತ ನಿಲ್ಲಿಸಿದ್ದೇನೆ."},
    "sing": {"en": "I can't sing like a real singer, but I've put on some soft music for you.",
             "hi": "मैं किसी असली गायक की तरह नहीं गा सकती, लेकिन आपके लिए हल्का संगीत लगा दिया है।",
             "hl": "Main asli gayak ki tarah nahi gaa sakti, lekin aapke liye halka sangeet laga diya hai.",
             "kn": "ನಾನು ನಿಜವಾದ ಗಾಯಕರಂತೆ ಹಾಡಲು ಸಾಧ್ಯವಿಲ್ಲ, ಆದರೆ ನಿಮಗಾಗಿ ಮೃದು ಸಂಗೀತ ಹಾಕಿದ್ದೇನೆ."},
    "map": {"en": "Here is the way to {d}. Please look below, and tap Bus or Metro for buses.",
            "hi": "{d} जाने का रास्ता नीचे दिखाया है। बस या मेट्रो के लिए नीचे बटन दबाइए।",
            "hl": "{d} jaane ka raasta neeche dikhaya hai. Bus ya metro ke liye neeche button dabaiye.",
            "kn": "{d} ಗೆ ಹೋಗುವ ದಾರಿಯನ್ನು ಕೆಳಗೆ ತೋರಿಸಿದ್ದೇನೆ. ಬಸ್ ಅಥವಾ ಮೆಟ್ರೋಗಾಗಿ ಕೆಳಗಿನ ಬಟನ್ ಒತ್ತಿ."},
}


async def respond(history, user_text, location=None, client=None, nav=None):
    """history: list of {"role","content"} plain turns (mutated).
    location: {"lat":..,"lon":..} or None. Returns {"text","lang","error"}."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=10)
    user_lang, error, text, sink = detect_language(user_text), None, "", {}
    intent, used, llm_failed = quick_intents(user_text), set(), False
    msgs = [{"role": "system", "content": SYSTEM}] + history[-12:] + [{"role": "user", "content": user_text}]
    if nav:
        msgs.insert(1, {"role": "system", "content": "LIVE NAVIGATION STATE (verified from GPS; use only "
                        "these numbers): " + json.dumps(nav)})
    try:
        for _ in range(4):  # allow a few tool rounds
            msg = await llm.chat(msgs, TOOLS, client=client)
            calls = msg.get("tool_calls")
            if not calls:
                text = clean(msg.get("content"))
                break
            msgs.append(msg)
            for c in calls:
                try: args = json.loads(c["function"]["arguments"] or "{}")
                except ValueError: args = {}
                used.add(c["function"]["name"])
                result = await run_tool(c["function"]["name"], args, location, client, sink)
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result)})
        if not text and not intent:
            error, text = "unavailable", FALLBACK["unavailable"][user_lang]
    except llm.LLMError as e:
        llm_failed = True
        if not intent:
            error, text = e.kind, FALLBACK[e.kind][user_lang]
    finally:
        if own: await client.aclose()
    rl = reply_lang(user_text)
    music = intent.get("music")
    if music and not (sink.get("music") or sink.get("song")):
        sink["music"] = music
        kind = "stop" if music["source"] == "stop" else "sing" if music["source"] == "generated" else "music"
        text = TEMPLATES[kind][rl]
    dest = intent.get("map")
    if dest and not sink.get("map") and (intent["map_strong"] or llm_failed) and not music:
        await run_tool("show_map", {"destination": dest}, location, None, sink)
        if not text or not (used & {"search_place", "get_route"}):
            text = TEMPLATES["map"][rl].format(d=dest)
    panel = sink.get("panel")
    segments = split_voices(text)
    text = strip_voice_tags(text)
    theme = sink.get("theme")
    if not theme:
        if panel and panel["kind"] == "recipe": theme = "cooking"
        elif panel and panel["kind"] == "health": theme = "health"
        elif sink.get("music") or sink.get("song"): theme = "music"
        elif sink.get("map"): theme = "travel"
    if not error:
        note = ""
        if panel:
            note = f" [on screen: {panel['title']}; ingredients: {', '.join(panel['ingredients'])}; steps: " + \
                   " | ".join(f"{i + 1}) {x}" for i, x in enumerate(panel["steps"])) + "]"
        history += [{"role": "user", "content": user_text}, {"role": "assistant", "content": text + note}]
    return {"text": text, "lang": detect_language(text), "error": error, "map": sink.get("map"), "panel": panel,
            "music": sink.get("music"), "actions": sink.get("actions", []),
            "theme": theme, "song": sink.get("song"), "segments": segments}
