"""Offline tests using fake HTTP responses. Run: python test_brain.py"""
import asyncio, json, os
import httpx
import brain, llm

os.environ.update({"LLM_PROVIDERS": "groq,cerebras", "GROQ_API_KEY": "x", "GROQ_MODEL": "m1",
                   "CEREBRAS_API_KEY": "y", "CEREBRAS_MODEL": "m2"})
brain._last_nom = float('-inf')  # makes the 1s Nominatim delay compute to 0 in tests


def reply(content=None, tool_calls=None):
    return {"choices": [{"message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}]}


def make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def t_language():
    assert brain.detect_language("Hello") == "en"
    assert brain.detect_language("आप कैसे हैं?") == "hi"
    assert brain.detect_language("ನೀವು ಹೇಗಿದ್ದೀರಿ") == "kn"


async def t_fallback_to_second_provider():
    def h(req):
        if "groq" in str(req.url): return httpx.Response(429)
        return httpx.Response(200, json=reply("Mix dosa batter and rest it overnight."))
    out = await brain.respond([], "How do I make dosa?", client=make_client(h))
    assert out["error"] is None and "dosa" in out["text"], out


async def t_all_rate_limited_gives_honest_message_in_user_language():
    h = lambda req: httpx.Response(429)
    out = await brain.respond([], "आप कैसे हैं?", client=make_client(h))
    assert out["error"] == "rate_limit" and out["lang"] == "hi", out
    out = await brain.respond([], "Hello", client=make_client(h))
    assert out["lang"] == "en" and "busy" not in out["text"].lower()


async def t_navigation_uses_only_tool_data():
    calls = []
    osrm = {"code": "Ok", "routes": [{"distance": 5230.4, "duration": 3900, "legs": [{"steps": [
        {"distance": 150, "name": "MG Road", "maneuver": {"type": "depart"}},
        {"distance": 80, "name": "Brigade Road", "maneuver": {"type": "turn", "modifier": "left"}},
        {"distance": 0, "name": "", "maneuver": {"type": "arrive"}}]}]}]}
    def h(req):
        u = str(req.url)
        if "chat/completions" in u:
            n = len(json.loads(req.content)["messages"])
            if n == 2:  # system + user -> ask to search
                return httpx.Response(200, json=reply(tool_calls=[{"id": "1", "type": "function",
                    "function": {"name": "search_place", "arguments": json.dumps({"query": "Electronic City Bengaluru"})}}]))
            if n == 4:
                return httpx.Response(200, json=reply(tool_calls=[{"id": "2", "type": "function",
                    "function": {"name": "get_route", "arguments": json.dumps({"dest_lat": 12.84, "dest_lon": 77.67, "mode": "walk"})}}]))
            tool_msgs = [m for m in json.loads(req.content)["messages"] if m["role"] == "tool"]
            calls.append(tool_msgs[-1]["content"])
            return httpx.Response(200, json=reply("It is about 5 kilometres, around 65 minutes on foot."))
        if "nominatim" in u:
            return httpx.Response(200, json=[{"display_name": "Electronic City, Bengaluru", "lat": "12.84", "lon": "77.67"}])
        return httpx.Response(200, json=osrm)
    hist = []
    out = await brain.respond(hist, "I want to go to Electronic City", {"lat": 12.97, "lon": 77.59}, make_client(h))
    assert out["error"] is None and "5 kilometres" in out["text"], out
    facts = json.loads(calls[0])
    assert facts["distance_m"] == 5230 and facts["duration_min"] == 65
    assert facts["first_steps"][1] == {"action": "turn", "turn": "left", "road": "Brigade Road", "meters": 80}
    assert len(hist) == 2


async def t_model_without_tool_support_still_chats():
    def h(req):
        if "tools" in json.loads(req.content): return httpx.Response(400, text="tools not supported")
        return httpx.Response(200, json=reply("Mix the batter and let it rest."))
    out = await brain.respond([], "How do I make dosa?", client=make_client(h))
    assert out["error"] is None and "batter" in out["text"], out


async def t_geocoder_fallback_uses_keyed_service():
    os.environ["GEOAPIFY_API_KEY"] = "g"
    def h(req):
        u = str(req.url)
        if "geoapify" in u:
            return httpx.Response(200, json={"features": [{"properties": {"formatted": "Majestic, Bengaluru", "lat": 12.977, "lon": 77.572}}]})
        return httpx.Response(500)
    r = await brain.search_place("Majestic Bengaluru", make_client(h), {"lat": 12.9, "lon": 77.6})
    assert r["source"] == "geoapify" and r["results"][0]["lat"] == 12.977, r
    def h2(req):
        if "geoapify" in str(req.url): return httpx.Response(500)
        return httpx.Response(200, json=[{"display_name": "Majestic", "lat": "12.97", "lon": "77.57"}])
    r = await brain.search_place("Majestic", make_client(h2))
    assert r["source"] == "nominatim", r
    os.environ.pop("GEOAPIFY_API_KEY")
    r = await brain.search_place("zzz", make_client(lambda q: httpx.Response(200, json=[])))
    assert r["results"] == [] and "note" in r, r


async def t_map_card_for_destination():
    def h(req):
        msgs = json.loads(req.content)["messages"]
        if len(msgs) == 2:
            return httpx.Response(200, json=reply(tool_calls=[{"id": "1", "type": "function", "function": {
                "name": "show_map", "arguments": json.dumps({"destination": "Electronic City Metro Station, Bengaluru"})}}]))
        return httpx.Response(200, json=reply("I have opened the map. Tap the Bus or Metro button."))
    out = await brain.respond([], "Take me to Electronic City metro", {"lat": 12.9, "lon": 77.6}, make_client(h))
    m = out["map"]
    assert out["error"] is None and m["destination"].startswith("Electronic City"), out
    assert "travelmode=transit" in m["links"]["transit"] and "destination=Electronic%20City%20Metro" in m["links"]["transit"]
    assert "origin=12.9,77.6" in m["links"]["walk"], m["links"]
    out = await brain.respond([], "Hello", None, make_client(lambda r: httpx.Response(200, json=reply("Hello!"))))
    assert out["map"] is None


async def t_panel_and_context_note():
    def h(req):
        if len(json.loads(req.content)["messages"]) == 2:
            return httpx.Response(200, json=reply(tool_calls=[{"id": "1", "type": "function", "function": {
                "name": "show_panel", "arguments": json.dumps({"kind": "recipe", "title": "Dosa",
                    "image_queries": ["masala dosa", "dosa batter"], "ingredients": ["rice", "urad dal"],
                    "steps": ["Soak rice and dal.", "Grind and ferment overnight."], "tips": ["Use a hot pan."]})}}]))
        return httpx.Response(200, json=reply("Dosa is easy. The details are below. Shall I go step by step? [on screen: x]"))
    hist = []
    out = await brain.respond(hist, "How do I make dosa?", None, make_client(h))
    p = out["panel"]
    assert p["title"] == "Dosa" and p["steps"][1].startswith("Grind") and len(p["image_queries"]) == 2, out
    assert "[on screen" not in out["text"], out["text"]
    assert "[on screen: Dosa" in hist[1]["content"] and "2) Grind" in hist[1]["content"], hist


async def t_live_nav_state_reaches_model():
    seen = []
    def h(req):
        seen.append(json.loads(req.content)["messages"])
        return httpx.Response(200, json=reply("About 400 metres left."))
    await brain.respond([], "Kitna door hai?", None, make_client(h), nav={"remaining_m": 400, "next": "left"})
    assert any(m["role"] == "system" and "LIVE NAVIGATION STATE" in m["content"] and "400" in m["content"]
               for m in seen[0]), seen[0]


async def t_full_route_shape():
    osrm = {"code": "Ok", "routes": [{"distance": 300.2, "duration": 240, "geometry": {"coordinates": [[77.5, 12.9], [77.51, 12.91]]},
            "legs": [{"steps": [{"distance": 200, "name": "A Rd", "maneuver": {"type": "depart", "location": [77.5, 12.9]}},
                                {"distance": 0, "name": "", "maneuver": {"type": "arrive", "location": [77.51, 12.91]}}]}]}]}
    r = await brain.full_route({"lat": 12.9, "lon": 77.5}, {"lat": 12.91, "lon": 77.51}, "walk",
                               make_client(lambda q: httpx.Response(200, json=osrm)))
    assert r["coords"][0] == [12.9, 77.5] and r["steps"][0]["lat"] == 12.9 and r["steps"][1]["action"] == "arrive", r
    r = await brain.full_route({"lat": 1, "lon": 1}, {"lat": 2, "lon": 2}, "walk",
                               make_client(lambda q: httpx.Response(200, json={"code": "NoRoute"})))
    assert r == {"error": "no_route_found"}


async def t_image_search_sources():
    commons = {"query": {"pages": {"1": {"index": 1, "imageinfo": [{"mime": "image/jpeg", "thumburl": "https://x/a.jpg",
               "descriptionurl": "https://c/a", "extmetadata": {"Artist": {"value": "<a>Ravi</a>"}, "LicenseShortName": {"value": "CC BY-SA 4.0"}}}]},
               "2": {"index": 2, "imageinfo": [{"mime": "image/svg+xml", "url": "https://x/b.svg"}]}}}}
    r = await brain.image_search("dosa", make_client(lambda q: httpx.Response(200, json=commons)))
    assert len(r) == 1 and r[0]["credit"] == "Ravi" and r[0]["license"].startswith("CC"), r
    os.environ["PEXELS_API_KEY"] = "p"
    pex = {"photos": [{"src": {"medium": "https://p/1.jpg"}, "alt": "dosa", "photographer": "Asha", "url": "https://p/1"}]}
    r = await brain.image_search("dosa", make_client(lambda q: httpx.Response(200, json=pex)))
    assert r[0]["source"] == "Pexels"
    r = await brain.image_search("dosa", make_client(lambda q: httpx.Response(500)))
    assert r == []
    os.environ.pop("PEXELS_API_KEY")
    os.environ["PIXABAY_API_KEY"] = "q"
    pix = {"hits": [{"webformatURL": "https://cdn.pixabay.com/a.jpg", "tags": "dosa, food", "user": "Meera", "pageURL": "https://pixabay.com/x"}]}
    def hp(req):
        assert "safesearch=true" in str(req.url)
        return httpx.Response(200, json=pix)
    r = await brain.image_search("dosa", make_client(hp))
    assert r[0]["source"] == "Pixabay" and r[0]["credit"] == "Meera", r
    r = await brain.image_search("dosa", make_client(lambda q: httpx.Response(200, json=commons) if "wikimedia" in str(q.url) else httpx.Response(429)))
    assert r[0]["source"] == "Wikimedia Commons", r
    os.environ.pop("PIXABAY_API_KEY")


async def t_video_search_and_cap():
    assert (await brain.video_search("dosa", make_client(lambda q: httpx.Response(200))))["reason"] == "no_key"
    os.environ["YOUTUBE_API_KEY"] = "k"; os.environ["YT_DAILY_SEARCH_LIMIT"] = "2"
    yt = {"items": [{"id": {"videoId": "abc123"}, "snippet": {"title": "Perfect Dosa", "channelTitle": "Chef A",
          "thumbnails": {"medium": {"url": "https://i.ytimg.com/vi/abc123/mqdefault.jpg"}}}},
          {"id": {"kind": "youtube#channel"}, "snippet": {}}]}
    def h(req):
        u = str(req.url)
        assert "videoEmbeddable=true" in u and "safeSearch=strict" in u
        return httpx.Response(200, json=yt)
    brain._yt_usage.update(day="", n=0)
    r = await brain.video_search("dosa recipe", make_client(h))
    assert r["videos"][0]["id"] == "abc123" and len(r["videos"]) == 1, r
    await brain.video_search("dosa recipe", make_client(h))
    assert (await brain.video_search("dosa recipe", make_client(h)))["reason"] == "daily_limit"
    brain._yt_usage.update(day="", n=0)
    assert (await brain.video_search("x", make_client(lambda q: httpx.Response(403))))["reason"] == "quota_or_key"
    for k in ("YOUTUBE_API_KEY", "YT_DAILY_SEARCH_LIMIT"): os.environ.pop(k)


async def t_panel_keeps_video_query():
    def h(req):
        if len(json.loads(req.content)["messages"]) == 2:
            return httpx.Response(200, json=reply(tool_calls=[{"id": "1", "type": "function", "function": {
                "name": "show_panel", "arguments": json.dumps({"kind": "recipe", "title": "Dosa",
                    "video_query": "dosa recipe in Hindi", "steps": ["Soak."]})}}]))
        return httpx.Response(200, json=reply("Details are below."))
    out = await brain.respond([], "dosa kaise banate hain", None, make_client(h))
    assert out["panel"]["video_query"] == "dosa recipe in Hindi", out


async def t_music_and_actions_tools():
    def h(req):
        msgs = json.loads(req.content)["messages"]
        if len(msgs) == 2:
            return httpx.Response(200, json=reply(tool_calls=[
                {"id": "1", "type": "function", "function": {"name": "play_music", "arguments": json.dumps(
                    {"source": "generated", "mood": "sleepy", "sing_text": "Chanda mama door ke*\nline two"})}},
                {"id": "2", "type": "function", "function": {"name": "propose_action", "arguments": json.dumps(
                    {"kind": "reminder", "text": "Take medicine", "minutes": 99999})}},
                {"id": "3", "type": "function", "function": {"name": "propose_action", "arguments": json.dumps(
                    {"kind": "transfer_money", "text": "pay"})}}]))
        return httpx.Response(200, json=reply("Okay, tap the button to confirm."))
    out = await brain.respond([], "play something calm and remind me about medicine", None, make_client(h))
    assert out["music"]["source"] == "generated" and "*" not in out["music"]["sing_text"], out["music"]
    assert len(out["actions"]) == 1 and out["actions"][0]["minutes"] == 1440 and out["actions"][0]["kind"] == "reminder", out["actions"]
    plain = await brain.respond([], "Hello", None, make_client(lambda r: httpx.Response(200, json=reply("Hi!"))))
    assert plain["music"] is None and plain["actions"] == []


async def t_music_search_jamendo():
    assert (await brain.music_search("calm", make_client(lambda q: httpx.Response(200))))["reason"] == "no_key"
    os.environ["JAMENDO_CLIENT_ID"] = "c"
    data = {"results": [{"name": "Morning Raga", "artist_name": "Arun", "audio": "https://mp3/1.mp3", "image": "i",
                         "license_ccurl": "https://cc", "shareurl": "https://j/1"}, {"name": "no audio"}]}
    def h(req):
        assert "client_id=c" in str(req.url)
        return httpx.Response(200, json=data)
    r = await brain.music_search("raga", make_client(h))
    assert len(r["tracks"]) == 1 and r["tracks"][0]["url"].endswith(".mp3"), r
    r = await brain.music_search("raga", make_client(lambda q: httpx.Response(500)))
    assert r["tracks"] == [] and r["reason"] == "none_found"
    os.environ.pop("JAMENDO_CLIENT_ID")


async def t_voices_theme_and_song_rules():
    assert brain.split_voices("Hello [[M]]Come here[[/M]] she said") == [
        {"voice": "f", "text": "Hello"}, {"voice": "m", "text": "Come here"}, {"voice": "f", "text": "she said"}]
    assert brain.strip_voice_tags("A [[M]]b[[/M]] c") == "A b c"
    os.environ["GEMINI_API_KEY"] = "g"; os.environ["SONGS_ENABLED"] = "1"
    def h(req):
        msgs = json.loads(req.content)["messages"]
        if len(msgs) == 2:
            return httpx.Response(200, json=reply(tool_calls=[
                {"id": "1", "type": "function", "function": {"name": "compose_song", "arguments": json.dumps(
                    {"title": "Hi", "style": "pop ballad in the voice of a famous singer", "vocal": "male",
                     "lyrics": "[Verse]\nline one"})}}]))
        if len(msgs) == 4:  # model retries with a generic style after the refusal
            assert "no_artist_imitation" in msgs[-1]["content"]
            return httpx.Response(200, json=reply(tool_calls=[
                {"id": "2", "type": "function", "function": {"name": "compose_song", "arguments": json.dumps(
                    {"title": "Hi", "style": "warm acoustic pop ballad, slow tempo", "vocal": "male", "length_sec": 9999,
                     "lyrics": "[Verse]\nline one\nline two"})}}]))
        return httpx.Response(200, json=reply("Your song is being made. [[M]]Listen soon[[/M]]."))
    out = await brain.respond([], "sing me a song", None, make_client(h))
    sg = out["song"]
    assert sg["vocal"] == "male" and sg["length_sec"] == 180 and sg["lyrics"][1] == "line one", sg
    assert out["theme"] == "music" and [x["voice"] for x in out["segments"]] == ["f", "m", "f"], out
    assert "[[" not in out["text"]
    # a Gemini key alone (for chat) must NOT switch songs on; SONGS_ENABLED=1 is required
    os.environ.pop("SONGS_ENABLED")
    r = await brain.run_tool("compose_song", {"title": "x", "style": "pop", "vocal": "male", "lyrics": "a"}, None, None, {})
    assert r == {"error": "song_service_not_configured"}, r
    os.environ.pop("GEMINI_API_KEY")
    r = await brain.run_tool("compose_song", {"title": "x", "style": "pop", "vocal": "male", "lyrics": "a"}, None, None, {})
    assert r == {"error": "song_service_not_configured"}
    # theme: explicit tool wins, else inferred from the panel kind
    def h2(req):
        if len(json.loads(req.content)["messages"]) == 2:
            return httpx.Response(200, json=reply(tool_calls=[{"id": "1", "type": "function", "function": {
                "name": "show_panel", "arguments": json.dumps({"kind": "recipe", "title": "Dosa"})}}]))
        return httpx.Response(200, json=reply("Details below."))
    out = await brain.respond([], "dosa", None, make_client(h2))
    assert out["theme"] == "cooking", out


async def t_quick_intents():
    q = brain.quick_intents
    assert q("play some calm music")["music"] == {"source": "library", "query": "calm", "mood": "calm"}
    m = q("Play Sapphire by Ed Sheeran")["music"]
    assert m["source"] == "youtube" and "sapphire by ed sheeran" in m["query"], m
    m = q("I want to listen to Arijit Singh songs")["music"]
    assert m["source"] == "youtube" and "arijit singh" in m["query"], m
    assert q("gaana bajao")["music"]["source"] == "library"
    assert q("stop the music")["music"]["source"] == "stop"
    assert q("sing me a song")["music"]["source"] == "generated"
    assert q("गाना बजाओ")["music"]["source"] == "library"
    assert "music" not in q("what is the best song for a lullaby?")
    assert q("Take me to Electronic City metro station")["map"] == "Electronic City metro station"
    assert q("Take me to Electronic City metro station")["map_strong"] is True
    assert q("Mujhe Majestic jaana hai")["map"] == "Majestic"
    assert q("मुझे मजेस्टिक जाना है")["map"] == "मजेस्टिक"
    w = q("how do I get to sleep")
    assert w.get("map_strong") is False
    assert q("How do I make dosa?") == {} and q("Hello") == {}
    assert brain.reply_lang("gaana bajao") == "hl" and brain.reply_lang("hello") == "en" and brain.reply_lang("गाना") == "hi"


async def t_music_and_map_survive_llm_failure():
    down = lambda req: httpx.Response(429)
    out = await brain.respond([], "play some calm music", None, make_client(down))
    assert out["error"] is None and out["music"]["source"] == "library" and out["theme"] == "music", out
    assert "music" in out["text"].lower()
    out = await brain.respond([], "गाना बजाओ", None, make_client(down))
    assert out["error"] is None and out["lang"] == "hi", out
    out = await brain.respond([], "Take me to Majestic", {"lat": 1, "lon": 2}, make_client(down))
    assert out["error"] is None and out["map"]["destination"] == "Majestic" and out["theme"] == "travel", out
    assert "origin=1,2" in out["map"]["links"]["walk"]
    out = await brain.respond([], "Hello", None, make_client(down))
    assert out["error"] == "rate_limit"


async def t_model_ignores_tools_music_still_plays():
    h = lambda req: httpx.Response(200, json=reply("Sorry, I can't play music."))
    out = await brain.respond([], "Play Sapphire by Ed Sheeran", None, make_client(h))
    assert out["music"]["source"] == "youtube" and "can't" not in out["text"], out
    out = await brain.respond([], "stop the music", None, make_client(h))
    assert out["music"]["source"] == "stop"


async def t_no_location_is_reported():
    r = await brain.get_route({"dest_lat": 1, "dest_lon": 2}, None, None)
    assert r == {"error": "location_unavailable"}


async def t_unconfigured_providers():
    for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY"): os.environ.pop(k)
    out = await brain.respond([], "Hello", client=make_client(lambda r: httpx.Response(200)))
    assert out["error"] == "no_providers"


async def main():
    for t in (t_language, t_fallback_to_second_provider, t_all_rate_limited_gives_honest_message_in_user_language,
              t_navigation_uses_only_tool_data, t_model_without_tool_support_still_chats, t_geocoder_fallback_uses_keyed_service, t_map_card_for_destination, t_panel_and_context_note, t_live_nav_state_reaches_model, t_full_route_shape, t_image_search_sources, t_video_search_and_cap, t_panel_keeps_video_query, t_music_and_actions_tools, t_music_search_jamendo, t_voices_theme_and_song_rules, t_quick_intents, t_music_and_map_survive_llm_failure, t_model_ignores_tools_music_still_plays, t_no_location_is_reported, t_unconfigured_providers):
        await t(); print("PASS", t.__name__)

asyncio.run(main())
