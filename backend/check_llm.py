"""Run: python check_llm.py   (from the backend folder, after loading .env)
Prints OK/FAIL per provider with the real HTTP status. Never prints keys."""
import asyncio, httpx
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import llm

async def main():
    providers = llm.load_providers()
    if not providers:
        print("No provider configured: each needs <NAME>_API_KEY and <NAME>_MODEL in .env"); return
    async with httpx.AsyncClient(timeout=15) as c:
        for p in providers:
            try:
                r = await c.post(f"{p['url']}/chat/completions", headers={"Authorization": f"Bearer {p['key']}"},
                                 json={"model": p["model"], "messages": [{"role": "user", "content": "Say hi in one word."}], "max_tokens": 10})
                ok = r.status_code == 200
                print(f"{p['name']}: {'OK' if ok else 'FAIL'} | HTTP {r.status_code} | model={p['model']}" + ("" if ok else f" | {r.text[:200]}"))
            except httpx.HTTPError as e:
                print(f"{p['name']}: FAIL | {type(e).__name__}")

asyncio.run(main())
