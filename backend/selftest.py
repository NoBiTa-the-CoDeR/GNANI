"""On-demand checks. Return fixed errors/statuses, never provider bodies or credentials."""
import os,time,json,asyncio
import httpx
from fastapi import Request,HTTPException
from backend.api import Limits
from backend.diagnostics import check_tts,check_stt

def install(app,brain):
 limits=Limits()
 @app.post('/api/selftest')
 async def run(request:Request):
  limits.check(request,'selftest',1)
  from backend.main import ConversationClient
  rows=[];audio=None
  def row(name,ok,detail,status=None,ms=None):rows.append(dict(name=name,pass_=ok,detail=detail,status=status,ms=ms))
  for k in ('GNANI_API_KEY','GROQ_API_KEY','LOCATIONIQ_API_KEY','PIXABAY_API_KEY','YOUTUBE_API_KEY','JAMENDO_CLIENT_ID'):
   row(k,bool(os.getenv(k)),'present' if os.getenv(k) else 'missing')
  async def check(name,fn,valid):
   t=time.monotonic()
   try:
    v=await asyncio.wait_for(fn(),45);row(name,bool(valid(v)),'OK' if valid(v) else 'Empty or unexpected service response',200,round((time.monotonic()-t)*1000));return v
   except httpx.HTTPStatusError as e:row(name,False,'HTTP '+str(e.response.status_code),e.response.status_code)
   except asyncio.TimeoutError:row(name,False,'Request timed out')
   except Exception as e:row(name,False,type(e).__name__)
  async def media(path):
   async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://selftest') as internal:
    response=await internal.get(path);response.raise_for_status();return response.json()
  async with httpx.AsyncClient(timeout=20) as c:
   result,audio=await check_tts(c);row('Gnani TTS',result[0]=='OK',result[2],result[1])
   result=await check_stt(c,audio);row('Gnani STT',result[0]=='OK',result[2],result[1])
   import sys
   for p in sys.modules['llm'].load_providers():
    async def probe(p=p):
     payload={'model':p['model'],'messages':[{'role':'user','content':'Call diagnostic now.'}],'max_tokens':80,'tools':[{'type':'function','function':{'name':'diagnostic','parameters':{'type':'object','properties':{}}}}],'tool_choice':{'type':'function','function':{'name':'diagnostic'}}}
     if p['name']=='groq' and p['model'].startswith('qwen/'):payload['reasoning_effort']='none'
     r=await c.post(p['url']+'/chat/completions',headers={'Authorization':'Bearer '+p['key']},json=payload);r.raise_for_status();return r.json()
    await check('LLM/tool support: '+p['name'],probe,lambda v:bool(v['choices'][0]['message'].get('tool_calls')))
   await check('Jamendo',lambda:media('/api/music?q=calm&mood=calm'),lambda v:bool(v.get('tracks')))
   await check('YouTube',lambda:media('/api/videos?q=dosa%20recipe'),lambda v:bool(v.get('videos')))
   await check('Images',lambda:media('/api/images?q=masala%20dosa'),lambda v:bool(v if isinstance(v,list) else v.get('photos')))
   places=await check('Geocoder',lambda:brain.search_place('Electronic City Bengaluru',c,None),lambda v:bool(v))
   # Fixed test points, never treated as the user's GPS.
   await check('Walking route (test coordinates)',lambda:brain.full_route({'lat':12.9765,'lon':77.5724},{'lat':12.975,'lon':77.573},'walk',c),lambda v:bool(v.get('coords')))
  return {'rows':rows,'audio':__import__('base64').b64encode(audio).decode() if audio else None,'songs_enabled':False}
