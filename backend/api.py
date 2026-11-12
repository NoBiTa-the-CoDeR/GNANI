"""Public application endpoints. Provider credentials stay on the server."""
import asyncio
from collections import OrderedDict, deque
import math
import hashlib
import os
import time
from urllib.parse import urlencode
import httpx
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Literal
from backend import trace, voices
from backend.tts_normalize import sentences
import json

class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

class RouteInput(BaseModel):
    origin: Optional[Point] = None
    dest: Optional[Point] = None
    destination: str = Field(default='', max_length=160)
    mode: Literal['walk','drive'] = 'walk'

class SpeechInput(BaseModel):
    text: str = Field(min_length=1,max_length=600)
    lang: str = Field(default='en',max_length=10)
    voice: Optional[str]=Field(default=None,max_length=30)
    speed: Optional[float]=Field(default=None,ge=.85,le=1.15)
    model: Optional[Literal['timbre-v2.5','timbre-v3.0']]=None
    script: Literal['native','latin']='native'

class StreamSpeechInput(SpeechInput):
    text: str = Field(min_length=1)

class TransitInput(BaseModel):
    origin: Optional[Point]=None
    destination: str=Field(min_length=1,max_length=160)

class Cache:
    def __init__(self, ttl=86400, maximum=256):
        self.ttl,self.maximum=ttl,maximum; self.items=OrderedDict()
    def get(self,key):
        item=self.items.get(key)
        if item and time.monotonic()-item[0]<self.ttl:
            self.items.move_to_end(key); return item[1]
        self.items.pop(key,None); return None
    def put(self,key,value):
        self.items[key]=(time.monotonic(),value)
        while len(self.items)>self.maximum:self.items.popitem(last=False)
    def has_room(self):
        now=time.monotonic()
        for key,(created,_) in list(self.items.items()):
            if now-created>=self.ttl:self.items.pop(key,None)
        return len(self.items)<self.maximum

class Limits:
    def __init__(self): self.clients=OrderedDict()
    def check(self,request,bucket,limit):
        key=(request.client.host if request.client else 'local',bucket);now=time.monotonic()
        values=self.clients.setdefault(key,deque())
        self.clients.move_to_end(key)
        while values and now-values[0]>60:values.popleft()
        if len(values)>=limit:raise HTTPException(429,'Please wait a minute before trying again.',headers={'Retry-After':'60'})
        values.append(now)
        while len(self.clients)>4096:self.clients.popitem(last=False)

# No raw request URL, response body, or exception string is emitted.
def error_info(exc):
    if isinstance(exc,httpx.HTTPStatusError):return {'error':'upstream_http','upstream_status':exc.response.status_code,'message':f'The service returned HTTP {exc.response.status_code} {exc.response.reason_phrase}. Please try again.'}
    if isinstance(exc,(asyncio.TimeoutError,httpx.TimeoutException)):return {'error':'timeout','message':'The service took too long to respond. Please try again.'}
    if isinstance(exc,httpx.RequestError):
        msg=str(exc).lower()
        label='TLS handshake failure' if 'handshake failure' in msg else 'TLS certificate verification failed' if 'certificate verify failed' in msg else 'network connection failed'
        return {'error':'connection_failed','message':f'The service connection failed: {label}. Please try again.'}
    return {'error':'invalid_service_response','message':'The service returned an unreadable response. Please try again.'}

class ObservedClient(httpx.AsyncClient):
    def __init__(self,**kwargs):
        self.origin_bias=kwargs.pop('origin_bias',None)
        super().__init__(**kwargs);self.failures=[]
    async def get(self,url,**kwargs):
        host=httpx.URL(url).host
        if self.origin_bias and (host.endswith('.locationiq.com') or host=='nominatim.openstreetmap.org'):
            params=dict(kwargs.get('params') or {})
            lat,lon=self.origin_bias['lat'],self.origin_bias['lon']
            params['viewbox']=f'{max(-180,lon-.3)},{max(-90,lat-.3)},{min(180,lon+.3)},{min(90,lat+.3)}'
            kwargs['params']=params
        provider={'pixabay.com':'Pixabay','commons.wikimedia.org':'Wikimedia Commons','www.googleapis.com':'YouTube','api.pexels.com':'Pexels'}.get(host,'LocationIQ' if host.endswith('.locationiq.com') else 'Jamendo' if host=='api.jamendo.com' else 'navigation')
        try:
            r=await super().get(url,**kwargs)
            if r.status_code>=400 and not(provider=='LocationIQ' and r.status_code==404):self.failures.append({'source':provider,'status':r.status_code,'message':r.reason_phrase})
            trace.event('http_'+provider.replace(' ','_'),'ok' if r.status_code<400 else 'error',f'http_{r.status_code}')
            return r
        except httpx.HTTPError as exc:
            self.failures.append({'source':provider,**error_info(exc)});trace.failure('http_service',exc);raise

def install(app,brain,synthesize):
    limits=Limits();images=Cache();videos=Cache();speech=Cache(ttl=600,maximum=64);music=Cache(ttl=3600,maximum=128);music_lock=asyncio.Lock();music_catalog=Cache(ttl=3600,maximum=640)
    photo_catalog={};photo_cache=Cache(maximum=64);photo_errors={};photo_lock=asyncio.Lock()
    photo_hosts={'pixabay.com','cdn.pixabay.com','images.pexels.com','upload.wikimedia.org','commons.wikimedia.org'}
    locks={kind:asyncio.Lock() for kind in ('images','videos','speech')}
    app.state.media_caches={'images':images,'videos':videos}

    @app.post('/api/route')
    async def route(body:RouteInput,request:Request):
        limits.check(request,'route',20)
        origin=body.origin.model_dump() if body.origin else None
        dest=body.dest.model_dump() if body.dest else None
        try:
            async def calculate():
                nonlocal dest
                async with ObservedClient(timeout=12,origin_bias=origin) as client:
                    if not dest:
                        if not body.destination.strip():raise HTTPException(422,'Please tell me the destination or a nearby landmark.')
                        found=await brain.search_place(body.destination.strip(),client,origin)
                        matches=found.get('results',[])
                        if origin:
                            matches.sort(key=lambda p:(p['lat']-origin['lat'])**2+((p['lon']-origin['lon'])*math.cos(math.radians(origin['lat'])))**2)
                        if len(matches)>1:return {'candidates':matches,'source':found.get('source'),'message':'Which one do you mean?'}
                        if not matches:
                            if client.failures:return JSONResponse({'error':'geocoding_failed','message':'The place search failed. Please try a nearby landmark.','failures':client.failures},status_code=502)
                            return JSONResponse({'error':'place_not_found','message':'I could not find that place. Please tell me a nearby landmark.'},status_code=404)
                        dest={'lat':matches[0]['lat'],'lon':matches[0]['lon']}
                    if not origin:return JSONResponse({'error':'location_unavailable','dest':dest,'message':'Where are you now? Tell me your area or a nearby landmark.'},status_code=409)
                    value=await brain.full_route(origin,dest,body.mode,client)
                    if value.get('error'):return JSONResponse({**value,'dest':dest,'message':'I could not find a route here. Please choose a nearby entrance or landmark.'},status_code=404)
                    return {**value,'dest':dest,'origin':origin}
            return await asyncio.wait_for(calculate(),20)
        except HTTPException:raise
        except Exception as exc:
            trace.failure('full_route',exc);return JSONResponse(error_info(exc),status_code=504 if isinstance(exc,(asyncio.TimeoutError,httpx.TimeoutException)) else 502)

    async def media(kind,q,request):
        limits.check(request,kind,12 if kind=='images' else 8)
        maxlen=80 if kind=='images' else 100
        q=' '.join(q.split())
        if not q or len(q)>maxlen:raise HTTPException(422,f'Search must contain 1 to {maxlen} characters.')
        cache=images if kind=='images' else videos;cache_key=q.casefold()
        async with locks[kind]:
            found=cache.get(cache_key)
            if found is not None:return {**found,'cached':True}
            # Retain all successful query results for the full 24 hours. At
            # capacity, omit new media instead of evicting and re-querying early.
            if not cache.has_room():
                return {'photos':[],'source':None,'reason':'cache_capacity'} if kind=='images' else {'videos':[],'reason':'cache_capacity'}
            try:
                async with ObservedClient(timeout=10) as client:
                    if kind=='images':
                        photos=await asyncio.wait_for(brain.image_search(q,client),18)
                        for identity,(created,_) in list(photo_catalog.items()):
                            if time.monotonic()-created>=86400:
                                photo_catalog.pop(identity,None);photo_errors.pop(identity,None)
                        for photo in photos:
                            url=httpx.URL(photo.get('url',''))
                            if url.scheme=='https' and url.host in photo_hosts:
                                # Provider download URLs can be signed differently
                                # for the same photo on separate searches.
                                stable=str(photo.get('source',''))+'|'+str(photo.get('page') or url)
                                identity=hashlib.sha256(stable.encode()).hexdigest()[:32]
                                photo_catalog[identity]=(time.monotonic(),str(url))
                                photo['url']='/api/photo/'+identity
                        value={'photos':photos,'source':photos[0].get('source') if photos else None,'failures':client.failures if not photos else []}
                    else:
                        value=await asyncio.wait_for(brain.video_search(q,client),12)
                        value['videos']=value.get('videos',[])[:2]
                        if not value['videos'] and client.failures:value['failures']=client.failures
            except Exception as exc:
                trace.failure(kind,exc)
                value={'photos':[],'source':None,'failures':[error_info(exc)]} if kind=='images' else {'videos':[],'reason':'unavailable'}
            cache.put(cache_key,value)
            return {**value,'cached':False}

    @app.get('/api/music')
    async def music_endpoint(request:Request,q:str='',mood:str='calm'):
        limits.check(request,'music',8)
        q=' '.join(q.split());mood=' '.join(mood.split())
        if len(q)>100 or len(mood)>40:raise HTTPException(422,'Please use a shorter music request.')
        key=(q.casefold(),mood.casefold())
        async with music_lock:
            value=music.get(key)
            if value is not None:return {**value,'cached':True}
            try:
                async with ObservedClient(timeout=10) as client:
                    value=await asyncio.wait_for(brain.music_search(q,client,mood),22)
                    if not value.get('tracks') and client.failures:value['failures']=client.failures
            except Exception as exc:
                trace.failure('music',exc);value={'tracks':[],'reason':'service_unavailable',**error_info(exc)}
            for track in value.get('tracks',[]):
                url=httpx.URL(track.get('url',''))
                if url.scheme=='https' and (url.host.endswith('.storage.jamendo.com') or url.host=='mp3l.jamendo.com'):
                    identity=hashlib.sha256(str(url).encode()).hexdigest()[:32]
                    music_catalog.put(identity,str(url));track['url']='/api/music-audio/'+identity
                else:track['url']=''
            value['tracks']=[t for t in value.get('tracks',[]) if t.get('url')]
            music.put(key,value)
            return {**value,'cached':False}

    @app.api_route('/api/music-audio/{identity}',methods=['GET','HEAD'])
    async def music_audio(identity:str,request:Request):
        limits.check(request,'music_audio',40)
        url=music_catalog.get(identity)
        if not url:raise HTTPException(404,'This track has expired. Please choose music again.')
        headers={}
        requested=request.headers.get('range','')
        if requested:
            import re
            if not re.fullmatch(r'bytes=\d+-\d*',requested):raise HTTPException(416,'This audio range is unavailable.')
            headers['Range']=requested
        client=httpx.AsyncClient(timeout=15)
        response=None
        try:
            for _ in range(4):
                parsed=httpx.URL(url)
                if parsed.scheme!='https' or not (parsed.host.endswith('.storage.jamendo.com') or parsed.host=='mp3l.jamendo.com'):raise HTTPException(502,'The music service returned an unsupported stream.')
                response=await client.send(client.build_request('GET',url,headers=headers),stream=True)
                if response.is_redirect:
                    url=str(response.url.join(response.headers.get('location','')));await response.aclose();continue
                break
            response.raise_for_status()
            mime=response.headers.get('content-type','').split(';')[0]
            if not mime.startswith('audio/'):raise HTTPException(502,'The music service did not return playable audio.')
            safe_headers={k:v for k,v in response.headers.items() if k in ('content-length','content-range','accept-ranges')}
            safe_headers['Cache-Control']='private, max-age=3600'
            if request.method=='HEAD':
                await response.aclose();await client.aclose();return Response(headers=safe_headers,media_type=mime)
            async def audio_stream():
                size=0
                try:
                    async for chunk in response.aiter_bytes():
                        size+=len(chunk)
                        if size>40_000_000:break
                        yield chunk
                finally:await response.aclose();await client.aclose()
            return StreamingResponse(audio_stream(),status_code=response.status_code,media_type=mime,headers=safe_headers)
        except Exception as exc:
            if response:await response.aclose()
            await client.aclose()
            if isinstance(exc,HTTPException):raise
            trace.failure('jamendo_audio',exc)
            return JSONResponse(error_info(exc),status_code=502)

    @app.get('/api/images')
    async def image_endpoint(request:Request,q:str=''):return await media('images',q,request)
    @app.get('/api/videos')
    async def video_endpoint(request:Request,q:str=''):return await media('videos',q,request)

    @app.get('/api/photo/{identity}')
    async def photo_endpoint(identity:str,request:Request):
        limits.check(request,'photo',120)
        entry=photo_catalog.get(identity)
        if not entry or time.monotonic()-entry[0]>=86400:raise HTTPException(404,'This photo has expired. Please ask for the topic again.')
        async with photo_lock:
            cached=photo_cache.get(identity)
            if cached:return Response(cached[0],media_type=cached[1],headers={'Cache-Control':'public, max-age=86400','X-Photo-Cache':'HIT'})
            failure=photo_errors.get(identity)
            if failure and time.monotonic()<failure[0]:
                return JSONResponse(failure[1],status_code=502,headers={'Retry-After':str(max(1,round(failure[0]-time.monotonic())))})
            photo_errors.pop(identity,None)
            if not photo_cache.has_room():raise HTTPException(503,'Photos are temporarily unavailable.')
            # Only URLs received from the configured photo services can be used.
            # Validate every redirect and keep downloads and memory bounded.
            try:
                async def download():
                    url=entry[1]
                    async with httpx.AsyncClient(timeout=10) as client:
                        for _ in range(4):
                            parsed=httpx.URL(url)
                            if parsed.scheme!='https' or parsed.host not in photo_hosts or parsed.username:raise HTTPException(502,'The photo service returned an unsupported address.')
                            async with client.stream('GET',url) as response:
                                if response.is_redirect:
                                    url=str(response.url.join(response.headers.get('location','')));continue
                                response.raise_for_status()
                                mime=response.headers.get('content-type','').split(';')[0]
                                if mime not in ('image/jpeg','image/png','image/webp'):raise HTTPException(502,'The photo service did not return a photo.')
                                chunks=[];size=0
                                async for chunk in response.aiter_bytes():
                                    size+=len(chunk)
                                    if size>2_000_000:raise HTTPException(502,'This photo is too large to load.')
                                    chunks.append(chunk)
                                return b''.join(chunks),mime
                        raise HTTPException(502,'The photo service redirected too many times.')
                cached=await asyncio.wait_for(download(),15)
            except HTTPException:raise
            except Exception as exc:
                trace.failure('photo_download',exc)
                delay=60
                if isinstance(exc,httpx.HTTPStatusError):
                    try:delay=max(60,min(3600,float(exc.response.headers.get('retry-after','60'))))
                    except ValueError:pass
                info=error_info(exc);photo_errors[identity]=(time.monotonic()+delay,info)
                return JSONResponse(info,status_code=502,headers={'Retry-After':str(round(delay))})
            photo_cache.put(identity,cached)
            return Response(cached[0],media_type=cached[1],headers={'Cache-Control':'public, max-age=86400','X-Photo-Cache':'MISS'})

    @app.post('/api/speech')
    async def speak(body:SpeechInput,request:Request):
        limits.check(request,'speech',40)
        locale={'en':'en-IN','hi':'hi-IN','kn':'kn-IN','hi-en':'hi-en','en-IN':'en-IN','hi-IN':'hi-IN','kn-IN':'kn-IN'}.get(body.lang)
        if not locale:raise HTTPException(422,'This voice language is not available.')
        try:effective=voices.settings(locale,body.voice,body.speed,body.model)
        except ValueError:raise HTTPException(422,'Choose a documented voice and speed.')
        key=(locale,body.text,*effective,body.script)
        async with locks['speech']:
            chunks=speech.get(key)
            if chunks is None:
                try:chunks=await asyncio.wait_for(synthesize(body.text,locale,voice=body.voice,speed=body.speed,model=body.model,script=body.script),45)
                except Exception as exc:
                    trace.failure('guidance_tts',exc);return JSONResponse(error_info(exc),status_code=502)
                speech.put(key,chunks)
        return {'text':body.text,'language':locale,'chunks':chunks}

    @app.post('/api/speech/stream')
    async def speech_stream(body:StreamSpeechInput,request:Request):
        limits.check(request,'speech',40)
        locale={'en':'en-IN','hi':'hi-IN','kn':'kn-IN','hi-en':'hi-en','en-IN':'en-IN','hi-IN':'hi-IN','kn-IN':'kn-IN'}.get(body.lang)
        if not locale:raise HTTPException(422,'This language is unavailable.')
        try:voices.settings(locale,body.voice,body.speed,body.model)
        except ValueError:raise HTTPException(422,'Choose a documented voice and speed.')
        async def stream():
            for sentence in sentences(body.text,locale,body.script):
                if await request.is_disconnected():break
                try:
                    audio=await asyncio.wait_for(synthesize(sentence,locale,voice=body.voice,speed=body.speed,model=body.model,script=body.script),45)
                    yield json.dumps({'text':sentence,'language':locale,'chunks':audio,'pauseMs':200},ensure_ascii=False)+'\n'
                except Exception as exc:
                    trace.failure('speech_stream',exc);yield json.dumps({'error':error_info(exc)['message']})+'\n';break
        return StreamingResponse(stream(),media_type='application/x-ndjson',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

    @app.get('/api/voice-test/catalog')
    async def voice_catalog():
        return {'catalog':{'timbre-v2.5':voices.V25,'timbre-v3.0':{k:voices.V3 for k in voices.V25}},'samples':voices.SAMPLES,'speeds':[.85,.93,1.0],'current':{lang:dict(zip(['model','voice','speed'],voices.settings(lang))) for lang in ('en-IN','hi-IN','kn-IN')},'note':'Speed is supported. Pitch and SSML are not documented. Timbre v3 supports audio tags.'}

    @app.post('/api/voice-test/save')
    async def voice_save(body:SpeechInput,request:Request):
        if request.client.host not in ('127.0.0.1','::1','testclient'):raise HTTPException(403,'Save voice choices from this computer.')
        if request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'Open the local voice test page.')
        if body.lang not in ('en-IN','hi-IN','kn-IN'):raise HTTPException(422,'Choose English, Hindi or Kannada.')
        try:voices.save(body.lang,body.voice,body.speed,body.model)
        except (ValueError,KeyError):raise HTTPException(422,'Choose a documented voice and speed.')
        return {'saved':True}

    @app.get('/api/config')
    async def config():return {'transit_embed_enabled':bool(os.getenv('GOOGLE_MAPS_EMBED_KEY'))}

    @app.post('/api/transit-embed')
    async def transit(body:TransitInput,request:Request):
        limits.check(request,'transit',12)
        key=os.getenv('GOOGLE_MAPS_EMBED_KEY')
        if not key:raise HTTPException(404,'Bus and metro timings come from Google Maps.')
        if not body.origin:raise HTTPException(409,'Tell me where you are now to show transit directions.')
        params={'key':key,'origin':f'{body.origin.lat},{body.origin.lon}','destination':body.destination,'mode':'transit'}
        return JSONResponse({'url':'https://www.google.com/maps/embed/v1/directions?'+urlencode(params)},headers={'Cache-Control':'no-store'})
