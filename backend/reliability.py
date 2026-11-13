"""Bounded provider failover with process-wide cooldowns; no prompt/answer cache."""
import os,time
import httpx
from backend import trace

def install(module):
 cooldown={}
 async def chat(messages,tools=None,timeout=8.0,client=None):
  providers={p['name']:p for p in module.load_providers()}
  # Gemini was explicitly approved for a billing-disabled Free-tier project.
  if os.getenv('GEMINI_SPEECH_FREE_TIER')=='1' and os.getenv('GEMINI_API_KEY') and os.getenv('GEMINI_MODEL'):
   providers['gemini']={'name':'gemini','key':os.environ['GEMINI_API_KEY'],'model':os.environ['GEMINI_MODEL'],'url':module.DEFAULT_URLS['gemini']}
  order=[n for n in ('groq','gemini','cerebras','openrouter') if n in providers]
  if not order:raise module.LLMError('no_providers')
  own=client is None;client=client or httpx.AsyncClient(timeout=timeout);errors=[]
  try:
   for name in order:
    p=providers[name];identity=(name,p['model'])
    if cooldown.get(identity,0)>time.monotonic():trace.event('llm_'+name,'skipped','cooldown');continue
    body={'model':p['model'],'messages':messages,'temperature':.4,'max_tokens':int(os.getenv('LLM_MAX_TOKENS','900'))}
    if tools:body['tools']=tools
    try:
     r=await client.post(p['url']+'/chat/completions',headers={'Authorization':'Bearer '+p['key']},json=body,timeout=min(timeout,8))
     if r.status_code==400 and tools:
      plain={k:v for k,v in body.items() if k!='tools'}
      r=await client.post(p['url']+'/chat/completions',headers={'Authorization':'Bearer '+p['key']},json=plain,timeout=min(timeout,8))
     if r.status_code>=400:
      kind='rate_limit' if r.status_code==429 else 'auth' if r.status_code in (401,403) else 'unavailable'
      delay=60 if kind=='rate_limit' else 300 if kind=='auth' else 15
      try:delay=max(delay,min(3600,float(r.headers.get('retry-after','0'))))
      except ValueError:pass
      cooldown[identity]=time.monotonic()+delay;errors.append(kind);trace.event('llm_'+name,'error','http_'+str(r.status_code));continue
     value=r.json()['choices'][0]['message']
     if not isinstance(value,dict) or not (value.get('tool_calls') or isinstance(value.get('content'),str) and value['content'].strip()):raise ValueError()
     cooldown.pop(identity,None);trace.event('llm_'+name,'answered','http_200');return value
    except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError) as exc:
     kind='timeout' if isinstance(exc,httpx.TimeoutException) else 'unavailable';errors.append(kind);cooldown[identity]=time.monotonic()+10;trace.event('llm_'+name,'error',kind)
  finally:
   if own:await client.aclose()
  raise module.LLMError(next((k for k in ('rate_limit','auth','timeout') if k in errors),'unavailable'))
 module.chat=chat
