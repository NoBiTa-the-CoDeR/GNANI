"""WebSocket voice bridge to the supplied conversation brain."""
import asyncio
import base64
import contextvars
import importlib
import json
import logging
import math
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / '.env')
# The supplied brain uses `import llm`; register the unchanged backend module.
sys.modules['llm'] = importlib.import_module('backend.llm')
brain = importlib.import_module('backend.brain')

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.diagnostics import sse_audio
from backend import timing, trace, language, voices
from backend.tts_normalize import normalize, sentences
from backend.api import install as install_api, error_info

# The supplied LLM module may log raw provider error bodies. Keep its output
# private and log only provider, HTTP status and safe failure classes here.
logging.getLogger('llm').disabled = True
provider_failure = contextvars.ContextVar('provider_failure', default=None)
class ConversationClient(httpx.AsyncClient):
    async def post(self, url, **kwargs):
        body=kwargs.get('json')
        groq_base=os.getenv('GROQ_BASE_URL','https://api.groq.com/openai/v1').rstrip('/')
        provider='groq' if str(url)==groq_base+'/chat/completions' else 'openrouter'
        if isinstance(body,dict) and body.get('tools'):
            kwargs['json']={**body,'max_tokens':1400}
            messages=body.get('messages',[])
            last_user=next((i for i in range(len(messages)-1,-1,-1) if messages[i].get('role')=='user'),None)
            if last_user is not None and not any(m.get('role')=='tool' for m in messages[last_user+1:]):
                utterance=str(messages[last_user].get('content',''))
                if re.search(r'(?i)^(?:please\s+)?(?:call\s+|message\s+|remind me\b|set\s+(?:a |an |the )?\d+.*timer|start\s+(?:a |an |the )?\d+.*timer)|याद दिला|फ़ोन करो|कॉल करो|ಸ್ಮರಿಸು|ನೆನಪಿಸು|ಕರೆ ಮಾಡು',utterance):
                    kwargs['json']['tool_choice']={'type':'function','function':{'name':'propose_action'}}

        if provider=='groq' and isinstance(body,dict) and body.get('model')=='qwen/qwen3.8-27b':
            kwargs['json']={**kwargs.get('json',body),'reasoning_effort':'none'}
        try:
            response=await super().post(url,**kwargs)
            # Groq occasionally generates a malformed tool name. Retry the
            # tool-enabled request instead of silently dropping all tools.
            if provider=='groq' and isinstance(body,dict) and body.get('tools'):
                for _ in range(2):
                    if response.status_code!=400: break
                    try: code=response.json().get('error',{}).get('code')
                    except (ValueError,AttributeError): break
                    if code!='tool_use_failed': break
                    trace.event('groq','error','http_400_tool_use_failed_retry')
                    response=await super().post(url,**kwargs)
                if response.status_code==400:
                    try: code=response.json().get('error',{}).get('code')
                    except (ValueError,AttributeError): code=None
                    if code=='tool_use_failed':
                        trace.event('groq','error','http_400_tool_use_failed')
                        raise httpx.RequestError('Groq HTTP 400 tool_use_failed')
        except httpx.HTTPError as exc:
            trace.failure(provider,exc)
            provider_failure.set('groq: HTTP 400 tool_use_failed' if str(exc)=='Groq HTTP 400 tool_use_failed' else f'{provider}: {type(exc).__name__}')
            raise
        trace.event(provider,'ok' if response.status_code<400 else 'error',f'http_{response.status_code}')
        if response.status_code>=400:
            provider_failure.set(f'{provider}: HTTP {response.status_code} {response.reason_phrase}')
        return response

# Observe failures without logging provider URLs, request parameters or credentials.
last_tool_failure = contextvars.ContextVar('last_tool_failure', default=None)
tool_error_for_turn = contextvars.ContextVar('tool_error_for_turn', default=None)
verified_places = contextvars.ContextVar('verified_places', default=())
def traced_call(name, fn):
    async def call(*args, **kwargs):
        trace.event(name, 'start')
        try:
            value = await fn(*args, **kwargs)
            trace.event(name, 'ok' if value else 'empty')
            return value
        except Exception as exc:
            trace.failure(name, exc)
            if isinstance(exc, httpx.HTTPStatusError):
                detail=f'HTTP {exc.response.status_code}'
            elif isinstance(exc, httpx.TimeoutException): detail='request timed out'
            elif 'handshake failure' in str(exc).lower(): detail='TLS handshake failure'
            elif 'certificate verify failed' in str(exc).lower(): detail='TLS certificate verification failed'
            elif isinstance(exc, httpx.RequestError): detail='network connection failed'
            else: detail=type(exc).__name__
            last_tool_failure.set(f'{name}: {detail}')
            raise
    return call

for _name, _fn in list(brain.GEOCODERS.items()):
    brain.GEOCODERS[_name] = traced_call(_name, _fn)
brain.get_route = traced_call('route', brain.get_route)
_run_tool = brain.run_tool
async def traced_tool(*args, **kwargs):
    last_tool_failure.set(None)
    if len(args)>=2 and args[0]=='show_map':
        # Only display a destination pin if a geocoder returned those coordinates.
        call_args=list(args); params=dict(call_args[1])
        try:
            lat,lon=float(params['dest_lat']),float(params['dest_lon'])
            places=verified_places.get()
            verified=len(places)==1 and abs(lat-places[0]['lat'])<0.00001 and abs(lon-places[0]['lon'])<0.00001
        except (KeyError,TypeError,ValueError): verified=False
        if not verified:
            params.pop('dest_lat',None);params.pop('dest_lon',None)
        call_args[1]=params; args=tuple(call_args)
    result = await _run_tool(*args, **kwargs)
    if len(args)>=1 and args[0]=='search_place' and isinstance(result,dict):
        verified_places.set(tuple(x for x in result.get('results',[]) if isinstance(x,dict) and isinstance(x.get('lat'),(int,float)) and isinstance(x.get('lon'),(int,float))))
    if isinstance(result, dict) and result.get('error') == 'service_unavailable':
        detail=last_tool_failure.get() or 'Navigation service unavailable'
        result['detail']=detail
        tool_error_for_turn.set(detail)
    return result
brain.run_tool = traced_tool

app=FastAPI()
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['*'],allow_headers=['*'])
GNANI=os.getenv('GNANI_API_BASE_URL','https://api.vachana.ai').rstrip('/')
KEY=os.getenv('GNANI_API_KEY','')

@app.get('/api/health')
async def health():
    return {'ok':True,'gnani_configured':bool(KEY),'brain_configured':bool(sys.modules['llm'].load_providers())}

async def transcribe(audio):
    if not KEY: raise RuntimeError('speech_not_configured')
    timing.mark('stt_start')
    async with httpx.AsyncClient(timeout=45) as c:
        r=await c.post(GNANI+'/stt/v3',headers={'X-API-Key-ID':KEY},files={'audio_file':('speech.wav',audio,'audio/wav')},data={'model':os.getenv('GNANI_STT_MODEL','prisma-v3.0'),'language_code':'indic-auto','format':'codemix'})
        r.raise_for_status();d=r.json();timing.mark('stt_complete')
        return d.get('transcript',''),d.get('detected_language_code')

def voice_for(lang):
    model=os.getenv('GNANI_TTS_MODEL','timbre-v2.5')
    if model=='timbre-v3.0': return os.getenv('GNANI_TTS_VOICE_V3','Shivani')
    defaults={'en-IN':('GNANI_TTS_VOICE_EN','Kaveri'),'hi-IN':('GNANI_TTS_VOICE_HI',os.getenv('GNANI_TTS_VOICE','Nalini')),'kn-IN':('GNANI_TTS_VOICE_KN','Saanvi'),'hi-en':('GNANI_TTS_VOICE_MIXED','Poorvi')}
    name,default=defaults.get(lang,defaults['en-IN'])
    return os.getenv(name,default) or default

tts_lock=asyncio.Lock()
async def synthesize(text,lang,voice=None,speed=None,model=None,script='native'):
    if not KEY: raise RuntimeError('speech_not_configured')
    locale=lang if lang in ('hi-IN','kn-IN','en-IN','hi-en') else 'en-IN'
    model,voice,speed=voices.settings(locale,voice,speed,model)
    text=normalize(text,locale,script)
    if not text:raise ValueError('empty_speech_text')
    payload={'text':text,'model':model,'voice':voice,'language':locale,'speed':speed,'audio_config':{'encoding':'linear_pcm','container':'wav','num_channels':1,'sample_rate':48000,'sample_width':2}}
    trace.event('tts','start',{'en-IN':'locale_en','hi-IN':'locale_hi','kn-IN':'locale_kn','hi-en':'locale_mixed'}[locale]);timing.mark('tts_start')
    lines=[]
    # The account permits one active request. Prefetch while audio plays,
    # without overlapping requests to Timbre.
    async with tts_lock:
      async with httpx.AsyncClient(timeout=45) as c:
        async with c.stream('POST',GNANI+'/api/v1/tts/sse',headers={'X-API-Key-ID':KEY},json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                lines.append(line)
                if line.startswith('data:'):
                    try:
                        part=json.loads(line[5:].strip())
                        if part.get('audio'):timing.mark('tts_first_audio')
                        if part.get('error') or part.get('type')=='error':raise RuntimeError('timbre_stream_error')
                    except (ValueError,AttributeError):pass
    audio=sse_audio('\n'.join(lines));timing.mark('tts_complete')
    return [base64.b64encode(audio).decode('ascii')]

install_api(app,brain,synthesize)
from backend.vision import install as install_vision
install_vision(app)
from backend.web_assistant import install as install_web
install_web(app)

def needs_location(text):
    return bool(re.search(r'(?i)\b(?:directions?|navigate|route|take me to|want to go|how (?:do|can) i (?:get|go|reach)|kaise\s+(?:jaana|jana))\b|जाना|रास्ता|ಹೋಗ|ದಾರಿ',text))

def gps_from(data):
    try:
        p=data['location'];lat=float(p['lat']);lon=float(p['lon'])
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:return None
        return {'lat':lat,'lon':lon}
    except (KeyError,TypeError,ValueError):return None

def gps_accuracy(data):
    try:
        accuracy=float(data['location']['accuracy'])
        return accuracy if math.isfinite(accuracy) and accuracy >= 0 else None
    except (KeyError,TypeError,ValueError):return None

def mentioned_step(text):
    match=re.search(r'(?i)(?:step|कदम|ಹಂತ)\s*(\d+)',text or '')
    if match:return int(match[1])-1
    names={'first':0,'second':1,'third':2,'fourth':3,'fifth':4,'sixth':5,'seventh':6,'eighth':7,'ninth':8,'tenth':9,'पहला':0,'दूसरा':1,'तीसरा':2,'ಮೊದಲ':0,'ಎರಡನೇ':1,'ಮೂರನೇ':2}
    for word,index in names.items():
        if re.search(r'(?i)'+word+r'\s+(?:step|कदम|ಹಂತ)',text or ''):return index
    return None

@app.websocket('/api/session')
async def session(ws:WebSocket):
    await ws.accept()
    history=[]
    location=None
    accuracy=None
    location_asked=False
    nav=None
    panel=None
    panel_step=0
    panel_lang='en'
    origin_asked=False
    mic_enabled=False
    web_enabled=False
    web_asking=False
    worker=None
    worker_id=None
    worker_voice=False
    stage=None
    audio_id=None
    audio_aloud=True
    send_lock=asyncio.Lock()
    location_event=asyncio.Event()
    request_id=contextvars.ContextVar('request_id',default=None)

    async def emit(message):
        identity=request_id.get()
        if identity is not None:message={**message,'request_id':identity}
        async with send_lock:await ws.send_json(message)

    async def get_first_location():
        nonlocal location_asked
        location_asked=True
        await emit({'type':'location_needed'})
        try:await asyncio.wait_for(location_event.wait(),22)
        except asyncio.TimeoutError:trace.event('location','error','timeout')

    async def respond_and_speak(transcript,reply_aloud=True):
        nonlocal location,accuracy,panel,panel_step,panel_lang,origin_asked,stage
        if web_enabled and (web_asking or re.search(r'(?i)^(?:please\s+)?(?:search\b|look up\b|browse\b)|find.*(?:weather|today|website|wikipedia)|विकिपीडिया|वेब पर|ಅಂತರ್ಜಾಲ|ವಿಕಿಪೀಡಿಯ',transcript)):
            await emit({'type':'web_task','text':transcript,'language':language.detect(transcript,None),'aloud':reply_aloud})
            await emit({'type':'response_end'});return
        if needs_location(transcript) and location is None and not location_asked:
            await get_first_location()
        trace.event('gps','present' if location else 'none', 'accuracy_m_'+str(round(accuracy)) if accuracy is not None else 'accuracy_unknown')
        tool_error_for_turn.set(None)
        provider_failure.set(None)
        verified_places.set(())
        stage='llm';trace.event('brain','start');timing.mark('llm_start')
        # The supplied brain passes GPS to get_route but its prompt does not tell
        # the model whether GPS exists. Add a temporary availability hint only.
        hint=None
        if location is not None and needs_location(transcript):
            hint={'role':'system','content':'The current GPS location is available to the route tool. Search for the destination and use the route tool without asking the user for their starting location.'}
            history.append(hint)
        elif panel and panel_lang!=brain.detect_language(transcript) and re.search(r'(?i)how|kaise|कैसे|ಹೇಗೆ',transcript):
            hint={'role':'system','content':'The user has changed language. If answering about the visible helper topic, call show_panel again with all content translated into the latest user language. Include photo queries and a video query in that language.'}
            history.append(hint)
        user_locale=language.detect(transcript,None)
        language_hint={'role':'system','content':'Latest user language: '+{'en-IN':'English. Answer in English only.','hi-IN':'Hindi. Use Devanagari script.','hi-en':'Hindi mixed with English. Use Devanagari for Hindi words.','kn-IN':'Kannada. Use Kannada script.'}[user_locale]+' Music starts only after the user taps Play. For generated songs, use words in this same language and say they are spoken with music, not sung.'}
        history.append(language_hint)
        try:
            step_command=bool(panel and panel.get('steps') and re.search(r'(?i)next step|step by step|repeat step|अगला|अगले|अगली|एक एक|ಮುಂದಿನ|ಹಂತ|agla|agle',transcript))
            if re.search(r'(?i)\b(?:stop|turn off|band karo|band kar do)\s+(?:the\s+)?(?:music|song|gaana)\b|\b(?:music|song|gaana)\s+(?:ko\s+)?band\s+(?:karo|kar do)\b|(?:संगीत|गाना|म्यूजिक).*बंद|(?:ಹಾಡು|ಸಂಗೀತ).*ನಿಲ್ಲಿಸು',transcript):
                lang=brain.detect_language(transcript);result={'text':{'en':'The music is stopped.','hi':'संगीत बंद कर दिया है।','kn':'ಸಂಗೀತ ನಿಲ್ಲಿಸಲಾಗಿದೆ.'}.get(lang,'The music is stopped.'),'lang':lang,'error':None}
                history.extend([{'role':'user','content':transcript},{'role':'assistant','content':result['text']}]);await emit({'type':'music_stop'})
            elif step_command:
                number=re.search(r'(?i)(?:step|कदम|हಂತ|ಹಂತ)\s*(\d+)',transcript)
                if number: panel_step=max(0,min(len(panel['steps'])-1,int(number[1])-1))
                elif re.search(r'(?i)step by step|एक एक',transcript):panel_step=0
                else:panel_step=min(len(panel['steps'])-1,panel_step+1)
                result={'text':panel['steps'][panel_step],'lang':panel_lang,'error':None}
                await emit({'type':'step','index':panel_step})
            else:
                async with ConversationClient(timeout=10) as client:
                    result=await brain.respond(history,transcript,location,client=client,nav=nav)
        finally:
            if hint is not None:
                history.remove(hint)
            history.remove(language_hint)
        timing.mark('llm_complete')
        err=result.get('error')
        # Preserve a completed visual tool result when a free provider fails
        # during its closing sentence. The exact service error stays visible.
        if err and (result.get('map') or result.get('panel')):
            lang=result.get('lang','en')
            overviews={'en':'The details are on the screen below. I can help you go through them step by step.','hi':'जानकारी नीचे स्क्रीन पर है। मैं आपको एक-एक कदम समझा सकती हूँ।','kn':'ವಿವರಗಳು ಕೆಳಗೆ ಪರದೆಯ ಮೇಲೆ ಇವೆ. ಒಂದೊಂದೇ ಹಂತದಲ್ಲಿ ಸಹಾಯ ಮಾಡಬಹುದು.'}
            result['text']=overviews.get(lang,overviews['en'])
        if err and provider_failure.get():
            await emit({'type':'tool_error','text':provider_failure.get()})
        if result.get('map'):
            await emit({'type':'map','map':result['map'],'language':result.get('lang','en')})
        if result.get('panel'):
            panel=result['panel'];panel_step=0;panel_lang=result.get('lang','en')
            await emit({'type':'panel','panel':panel,'language':panel_lang})
        if result.get('music'):
            await emit({'type':'music','music':result['music'],'language':result.get('lang','en')})
        if result.get('actions'):
            await emit({'type':'actions','actions':result['actions'],'aloud':reply_aloud,'language':result.get('lang','en')})
        if tool_error_for_turn.get():
            await emit({'type':'tool_error','text':tool_error_for_turn.get()})
        trace.event('brain','error' if err else 'ok',err if err in ('rate_limit','auth','timeout','no_providers','unavailable') else '')
        text=result['text']
        if isinstance(text,str):
            text=' '.join(re.split(r'(?<=[.!?।])\s+',text.strip())[:3])
            result['text']=text
        index=mentioned_step(text)
        if panel and index is not None and 0<=index<len(panel.get('steps',[])):
            panel_step=index;await emit({'type':'step','index':index})
        if not isinstance(text,str) or not text:
            trace.event('tts','skipped','empty_brain_text')
            await emit({'type':'error','text':'The assistant returned an empty response. Please try again.'})
            await emit({'type':'response_end'});return
        locale={'en':'en-IN','hi':'hi-IN','kn':'kn-IN'}.get(result.get('lang'))
        if locale=='en-IN' and language.detect(transcript,None)=='hi-en':locale='hi-en'
        if not locale:
            trace.event('tts','skipped','unsupported_brain_language')
            await emit({'type':'text_only','text':text})
            await emit({'type':'audio_unavailable'});await emit({'type':'response_end'});return
        await emit({'type':'reply','text':text,'language':locale,'aloud':reply_aloud})
        if not reply_aloud:
            await emit({'type':'text_only','text':text,'language':locale})
            await emit({'type':'response_end'});return
        stage='tts'
        try:
            for index,sentence in enumerate(sentences(text,locale)):
                audio=await synthesize(sentence,locale)
                if index==0:timing.mark('first_sentence_ready')
                await emit({'type':'audio_sentence','text':sentence,'chunks':audio,'language':locale,'pause_ms':200})
        except Exception as exc:
            trace.failure('tts',exc)
            await emit({'type':'text_only','text':text})
            await emit({'type':'audio_unavailable'})
        await emit({'type':'response_end'})
        if result.get('map') and location is None and not origin_asked:
            origin_asked=True
            if not re.search(r'(?i)where.*(?:now|are you)|कहाँ|ಎಲ್ಲಿ',text):
                questions={'en':'Where are you now?','hi':'आप अभी कहाँ हैं?','kn':'ನೀವು ಈಗ ಎಲ್ಲಿದ್ದೀರಿ?'}
                question=questions.get(result.get('lang'),'Where are you now?')
                history.append({'role':'assistant','content':question})
                await emit({'type':'location_question','text':question,'language':result.get('lang','en')})

    async def turn(identity, *, audio=None,text=None,aloud=False):
        nonlocal stage
        request_id.set(identity)
        trace.begin_turn();clock=timing.Timing();timing.current.set(clock)
        try:
            if audio is not None:
                if not mic_enabled:return
                stage='stt';clock.mark('audio_received')
                transcript,stt_lang=await transcribe(audio)
                audio=None
                if not mic_enabled:return
                if not transcript.strip():
                    await emit({'type':'error','text':'I did not hear anything. Please try again.'});return
                await emit({'type':'transcript','text':transcript,'language':language.detect(transcript,stt_lang)})
            else:
                clock.mark('text_received');transcript=(text or '').strip()[:2000]
                if not transcript:return
                await emit({'type':'transcript','text':transcript,'language':language.detect(transcript,None),'typed':True})
            await respond_and_speak(transcript,aloud)
            await emit({'type':'timing','events':clock.snapshot()})
        except asyncio.CancelledError:
            trace.event('voice_turn','cancelled',stage or 'unknown')
            raise
        except Exception as exc:
            trace.failure('voice_turn',exc)
            try:await emit({'type':'error','text':error_info(exc)['message']})
            except (RuntimeError,WebSocketDisconnect):pass
        finally:
            audio=None
            stage=None

    async def cancel_worker():
        nonlocal worker
        if worker and not worker.done():
            worker.cancel()
            try:await worker
            except asyncio.CancelledError:pass
        worker=None

    try:
        while True:
            msg=await ws.receive()
            if msg['type']=='websocket.disconnect':break
            if msg.get('bytes') is not None:
                if not mic_enabled:
                    trace.event('microphone','dropped','muted_audio');continue
                await cancel_worker()
                worker_id=audio_id;worker_voice=True
                worker=asyncio.create_task(turn(audio_id,audio=msg['bytes'],aloud=audio_aloud))
                audio_id=None
            elif msg.get('text'):
                try:data=json.loads(msg['text'])
                except ValueError:continue
                kind=data.get('type')
                if kind=='mic_state':
                    mic_enabled=data.get('enabled') is True
                    if not mic_enabled and worker_voice and stage in ('stt','llm',None):
                        identity=worker_id
                        await cancel_worker()
                        await emit({'type':'turn_cancelled','reason':'microphone_muted','request_id':identity})
                    trace.event('microphone','enabled' if mic_enabled else 'muted')
                    await emit({'type':'mic_state','enabled':mic_enabled})
                elif kind=='web_preference':
                    web_enabled=data.get('enabled') is True;web_asking=web_enabled and data.get('asking') is True
                elif kind=='turn':
                    audio_id=str(data.get('request_id',''))[:64];audio_aloud=data.get('aloud',True) is True
                elif kind in ('interrupt','stop_talking'):
                    identity=worker_id
                    if data.get('request_id') is not None and data['request_id']!=worker_id:continue
                    await cancel_worker()
                    await emit({'type':'turn_cancelled','reason':'interrupted','request_id':identity})
                elif kind=='location':
                    location=gps_from(data);accuracy=gps_accuracy(data);location_event.set()
                    trace.event('location','ok' if location else 'none','position_received' if location else 'no_position')
                elif kind=='location_permission':
                    state=data.get('state');trace.event('permission',state if state in ('granted','denied','prompt','unknown') else 'unknown')
                elif kind=='nav':
                    value=data.get('nav');nav=None
                    if isinstance(value,dict) and value.get('mode')=='walk':
                        try:
                            remaining=float(value['remaining_m']);minutes=float(value['remaining_min'])
                            if math.isfinite(remaining) and math.isfinite(minutes) and remaining>=0 and minutes>=0:
                                nav={'remaining_m':round(remaining),'remaining_min':round(minutes),'next_instruction':str(value.get('next_instruction',''))[:400],'destination':str(value.get('destination',''))[:160],'mode':'walk'}
                        except (KeyError,TypeError,ValueError):pass
                elif kind in ('location_denied','location_unavailable'):
                    location_event.set();trace.event('location','denied' if kind=='location_denied' else 'unavailable')
                elif kind=='text':
                    await cancel_worker()
                    worker_id=str(data.get('request_id',''))[:64];worker_voice=False
                    worker=asyncio.create_task(turn(worker_id,text=data.get('text',''),aloud=data.get('aloud') is True))
                elif kind=='step':
                    await cancel_worker()
                    try:index=max(0,min(11,int(data.get('index',0))))
                    except (TypeError,ValueError):index=0
                    worker_id=str(data.get('request_id',''))[:64];worker_voice=False
                    worker=asyncio.create_task(turn(worker_id,text='repeat step '+str(index+1),aloud=data.get('aloud',True) is True))
                elif kind=='playback':
                    try:
                        elapsed=int(data.get('elapsed_eos_ms',0))
                        if 0<=elapsed<=300000:timing.logger.warning('stage=playback_start elapsed_eos_ms=%s',elapsed)
                    except (TypeError,ValueError):pass
                elif kind=='panel_step':
                    try:
                        if panel:panel_step=max(0,min(len(panel.get('steps',[]))-1,int(data.get('index',0))))
                    except (TypeError,ValueError):pass
    except (WebSocketDisconnect,RuntimeError):pass
    finally:await cancel_worker()

# Production: serve the compiled client after all API routes on the same origin.
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
_client = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
if _client.is_dir():
    if (_client / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=_client / 'assets'), name='assets')
    @app.get('/{path:path}', include_in_schema=False)
    async def client_page(path: str):
        if path == 'api' or path.startswith(('api/', 'ws')):
            return JSONResponse({'detail': 'Not found'}, status_code=404)
        candidate = (_client / path).resolve()
        if candidate.is_relative_to(_client.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_client / 'index.html')
