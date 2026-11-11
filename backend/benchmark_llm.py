"""Measure five fixed, non-personal prompts. Run: python -m backend.benchmark_llm."""
import asyncio, os, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent/'.env')
from backend.llm_providers import configured_providers,call_stream
from backend import timing

PROMPTS=['Majestic kaise jaana hai?','नमस्ते, आप कैसे हैं?','ನಮಸ್ಕಾರ, ಮಳೆ ಏಕೆ ಬರುತ್ತದೆ?','What is a rainbow?','मुझे चाय कैसे बनानी है?']
SYSTEM="You are gNani, a kind AI companion. Reply in the user's language in 1–3 short spoken sentences. Return JSON with intent first: intent (chat, search), destination, reply, language. Never invent navigation."

async def main():
    all_providers=configured_providers(); providers={p.name:p for p in all_providers}
    secrets=[p.key for p in all_providers if p.key]
    def redact(value):
        text=str(value)
        for secret in secrets: text=text.replace(secret,'[REDACTED]')
        return text
    print('provider | prompt | first-token ms | result')
    for name in ('groq','cerebras','gemini','openrouter'):
        provider=providers.get(name)
        if not provider:
            for i in range(1,6): print(f'{name} | {i} | - | missing key')
            continue
        for i,prompt in enumerate(PROMPTS,1):
            clock=timing.Timing();timing.current.set(clock)
            try:
                result=await call_stream(provider,[{'role':'system','content':SYSTEM},{'role':'user','content':prompt}])
                print(f"{name} | {i} | {clock.events.get('llm_first_token','-')} | OK")
                if i in (2,3): print('  sample: '+redact(result.get('reply',''))[:400])
            except Exception as exc:
                status='HTTP '+str(exc.response.status_code) if hasattr(exc,'response') and getattr(exc,'response',None) is not None else type(exc).__name__
                print(f"{name} | {i} | {clock.events.get('llm_first_token','-')} | {status}")
if __name__=='__main__': asyncio.run(main())
