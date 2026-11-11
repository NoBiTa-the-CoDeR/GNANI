"""LLM provider chain: tries each configured provider in order and falls
back on rate limits, timeouts, auth errors or server errors.
All providers use the OpenAI-compatible /chat/completions API.
Models are NEVER hardcoded: set <NAME>_MODEL in .env."""
import os
import logging
import httpx

log = logging.getLogger("llm")

DEFAULT_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",  # verify in Google docs
    "openrouter": "https://openrouter.ai/api/v1",
}


class LLMError(Exception):
    """kind: rate_limit | auth | timeout | unavailable | no_providers"""
    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind


def load_providers():
    names = os.getenv("LLM_PROVIDERS", "groq,cerebras,gemini,openrouter").split(",")
    out = []
    for name in (n.strip().lower() for n in names if n.strip()):
        up = name.upper()
        key, model = os.getenv(f"{up}_API_KEY"), os.getenv(f"{up}_MODEL")
        if not key or not model:
            continue  # skip providers that are not fully configured
        url = os.getenv(f"{up}_BASE_URL", DEFAULT_URLS.get(name, "")).rstrip("/")
        if url:
            out.append({"name": name, "key": key, "model": model, "url": url})
    return out


async def chat(messages, tools=None, timeout=8.0, client=None):
    """Returns the assistant message dict. Raises LLMError if all providers fail."""
    providers = load_providers()
    if not providers:
        raise LLMError("no_providers", "set <PROVIDER>_API_KEY and <PROVIDER>_MODEL in .env")
    own = client is None
    client = client or httpx.AsyncClient(timeout=timeout)
    errors = []
    try:
        for p in providers:
            r = None
            for use_tools in ([True, False] if tools else [False]):
                body = {"model": p["model"], "messages": messages,
                        "temperature": 0.4, "max_tokens": 350}
                if use_tools:
                    body["tools"] = tools
                try:
                    r = await client.post(f"{p['url']}/chat/completions", json=body,
                                          headers={"Authorization": f"Bearer {p['key']}"},
                                          timeout=timeout)
                except httpx.TimeoutException:
                    errors.append("timeout"); log.warning("%s: timeout", p["name"]); r = None; break
                except httpx.HTTPError as e:
                    errors.append("unavailable"); log.warning("%s: %s", p["name"], type(e).__name__); r = None; break
                if r.status_code == 400 and use_tools:
                    # model may not support tool calling: retry once as plain chat
                    log.warning("%s: HTTP 400 with tools (%s); retrying without tools", p["name"], r.text[:200])
                    continue
                break
            if r is None:
                continue
            if r.status_code == 429:
                errors.append("rate_limit"); log.warning("%s: rate limited", p["name"]); continue
            if r.status_code in (401, 403):
                errors.append("auth"); log.warning("%s: auth failed", p["name"]); continue
            if r.status_code >= 400:
                errors.append("unavailable"); log.warning("%s: HTTP %s %s", p["name"], r.status_code, r.text[:200]); continue
            try:
                msg = r.json()["choices"][0]["message"]
            except (KeyError, IndexError, ValueError):
                errors.append("unavailable"); continue
            log.info("answered by %s", p["name"])
            return msg
    finally:
        if own:
            await client.aclose()
    # report the most useful reason
    for kind in ("rate_limit", "auth", "timeout"):
        if kind in errors:
            raise LLMError(kind)
    raise LLMError("unavailable")
