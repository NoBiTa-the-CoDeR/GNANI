"""Speech language catalog and secondary provider. No browser speech fallback."""
import base64,os,re
import httpx
from backend import timing,trace
# Deliberately limited to documented Gemini Flash-Lite TTS + Whisper coverage.
NAMES=dict(en='English',hi='Hindi',kn='Kannada',ta='Tamil',te='Telugu',ml='Malayalam',mr='Marathi',bn='Bengali',gu='Gujarati',pa='Punjabi',es='Spanish',fr='French',de='German',it='Italian',pt='Portuguese',ar='Arabic',ja='Japanese',ko='Korean',zh='Chinese',ru='Russian',tr='Turkish',id='Indonesian',vi='Vietnamese',th='Thai',nl='Dutch',pl='Polish',uk='Ukrainian',ro='Romanian',cs='Czech',el='Greek',sv='Swedish',da='Danish',hu='Hungarian',he='Hebrew',fa='Persian',ur='Urdu',ne='Nepali',sw='Swahili')
REGIONS=dict(en='IN',hi='IN',kn='IN',ta='IN',te='IN',ml='IN',mr='IN',bn='IN',gu='IN',pa='IN',es='ES',fr='FR',de='DE',it='IT',pt='BR',ar='SA',ja='JP',ko='KR',zh='CN',ru='RU',tr='TR',id='ID',vi='VN',th='TH',nl='NL',pl='PL',uk='UA',ro='RO',cs='CZ',el='GR',sv='SE',da='DK',hu='HU',he='IL',fa='IR',ur='PK',ne='NP',sw='KE')
GNANI=set('en hi kn ta te ml mr bn gu pa'.split())
def canonical(value):
 if value=='hi-en':return value
 code=str(value or '').split('-')[0].lower()
 return code+'-'+REGIONS[code] if code in NAMES else None

def instruction(locale):
 code=locale.split('-')[0]
 return f'{NAMES.get(code,"English")}. Reply in this language and its native script. Preserve proper names. Keep answers warm and conversational.'

class SpeechError(RuntimeError):pass

def enabled():return os.getenv('GEMINI_SPEECH_FREE_TIER')=='1'

def clean(text):
 return re.sub(r'\s+',' ',''.join(c for c in re.sub(r'[*_`#]','',text) if not (0x1f000<=ord(c)<=0x1faff))).strip()

async def synthesize(text,lang,male=False,client=None):
 if not enabled():raise SpeechError('Extra-language speech is disabled until a billing-disabled Gemini Free-tier project is confirmed.')
 key=os.getenv('GEMINI_API_KEY','')
 if not key:raise SpeechError('Gemini speech key is missing. The reply is available as text.')
 model=os.getenv('GEMINI_TTS_MODEL','gemini-3.8-flash-lite-tts')
 if model not in ('gemini-3.8-flash-lite-tts','gemini-3.8-flash-tts'):raise SpeechError('Choose a documented free-tier Gemini speech model.')
 payload={'model':model,'input':[{'type':'user_input','content':[{'type':'text','text':clean(text),'annotations':[{'type':'speech_metadata','style':'Warm, patient and clear. Speak only the supplied text, in '+NAMES[lang.split('-')[0]]+'.'}]}]}], 'response_format':{'type':'audio'},'generation_config':{'speech_config':[{'voice':'Puck' if male else os.getenv('GEMINI_TTS_VOICE','Kore')}]},'store':False}
 own=client is None;client=client or httpx.AsyncClient(timeout=40)
 timing.mark('tts_start');trace.event('tts','start','gemini_'+lang)
 try:
  r=await client.post('https://generativelanguage.googleapis.com/v1beta/interactions',headers={'x-goog-api-key':key},json=payload)
  # Never include provider response bodies/URLs/headers in errors.
  if r.status_code!=200:
   trace.event('tts','error','gemini_http_'+str(r.status_code))
   reason={400:'request rejected',401:'key rejected',403:'access denied',404:'model unavailable',429:'free quota reached'}.get(r.status_code,'service error')
   raise SpeechError(f'Gemini speech HTTP {r.status_code}: {reason}. Your text reply is still available.')
  blocks=[b for step in r.json().get('steps',[]) if step.get('type')=='model_output' for b in step.get('content',[]) if b.get('type')=='audio' and b.get('data')]
  if not blocks:raise SpeechError('Gemini speech returned no audio. Your text reply is still available.')
  data=base64.b64decode(blocks[-1]['data'],validate=True)
  if not data.startswith(b'RIFF'):raise SpeechError('Gemini speech returned an unsupported audio format.')
  timing.mark('tts_first_audio');timing.mark('tts_complete');return [base64.b64encode(data).decode()]
 except httpx.TimeoutException:raise SpeechError('Gemini speech timed out. Please try Listen again.') from None
 except httpx.RequestError:raise SpeechError('Gemini speech network error. Please check your connection.') from None
 finally:
  if own:await client.aclose()

async def transcribe(audio,preferred=None,client=None):
 key=os.getenv('GROQ_API_KEY','')
 if not key:raise SpeechError('Multilingual recognition needs the Groq key. Please select an Indian language to use Gnani instead.')
 own=client is None;client=client or httpx.AsyncClient(timeout=35)
 data={'model':'whisper-large-v3-turbo','response_format':'verbose_json','temperature':'0'}
 if preferred:data['language']=preferred.split('-')[0]
 try:
  r=await client.post('https://api.groq.com/openai/v1/audio/transcriptions',headers={'Authorization':'Bearer '+key},files={'file':('speech.wav',audio,'audio/wav')},data=data)
  if r.status_code!=200:raise SpeechError(f'Multilingual recognition HTTP {r.status_code}: '+('free quota reached.' if r.status_code==429 else 'speech service rejected the request.'))
  value=r.json();hint=value.get('language','');code=next((c for c,n in NAMES.items() if n.lower()==hint.lower()),hint)
  return value.get('text',''),canonical(code)
 except httpx.TimeoutException:raise SpeechError('Multilingual recognition timed out. Please try again.') from None
 finally:
  if own:await client.aclose()
