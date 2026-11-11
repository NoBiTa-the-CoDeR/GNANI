"""Geocoding and routing providers. Logs contain no place names or coordinates."""
import asyncio, os, time, json
from collections import OrderedDict
import httpx
from backend import trace

# Google policies restrict converting Maps text driving times into synthetic speech.
# Keep the key for diagnostics, but do not feed Google results to voice navigation.
GOOGLE_KEY='' 
GEO=os.getenv('NOMINATIM_URL','https://nominatim.openstreetmap.org').rstrip('/')
AGENT=os.getenv('GEOCODER_USER_AGENT','gNaniAI/1.0 (local navigation app; contact: configure-in-env)')
FOOT=os.getenv('OSRM_FOOT_URL','https://routing.openstreetmap.de/routed-foot').rstrip('/')
CAR=os.getenv('OSRM_CAR_URL','https://routing.openstreetmap.de/routed-car').rstrip('/')
_lock=asyncio.Lock(); _last=0.0; _cache=OrderedDict(); TTL=300; MAX=128

def cached(key):
    item=_cache.get(key)
    if item and time.monotonic()-item[0]<TTL:
        _cache.move_to_end(key); return item[1]
    _cache.pop(key,None); return None

def save(key,value):
    _cache[key]=(time.monotonic(),value); _cache.move_to_end(key)
    while len(_cache)>MAX: _cache.popitem(last=False)

async def limited():
    global _last
    await asyncio.sleep(max(0,1.1-(time.monotonic()-_last)))
    _last=time.monotonic()

async def search(query,loc=None):
    bias=(round(float(loc['lat']),2),round(float(loc['lon']),2)) if loc else None
    key=('search',query.casefold().strip(),bias); hit=cached(key)
    if hit is not None: trace.event('geocoding','ok','cache_hit'); return hit
    async with _lock:
        hit=cached(key)
        if hit is not None: return hit
        await limited()
        if GOOGLE_KEY:
            trace.event('geocoding','start','google')
            try:
                async with httpx.AsyncClient(timeout=12) as c:
                    r=await c.get('https://maps.googleapis.com/maps/api/geocode/json',params={'address':query},headers={'X-Goog-Api-Key':GOOGLE_KEY});r.raise_for_status(); data=r.json()
                if data.get('status') not in ('OK','ZERO_RESULTS'): raise ValueError('google_geocoding_error')
                out=[{'display_name':x['formatted_address'],'lat':x['geometry']['location']['lat'],'lon':x['geometry']['location']['lng'],'place_id':x.get('place_id')} for x in data.get('results',[])[:4]]
                trace.event('geocoding','ok','google_results_'+str(len(out)));save(key,out);return out
            except Exception as exc: trace.failure('geocoding_google',exc)
        trace.event('geocoding','start','nominatim')
        try:
            async with httpx.AsyncClient(timeout=15,headers={'User-Agent':AGENT}) as c:
                params={'q':query,'format':'jsonv2','limit':4,'addressdetails':1}
                if bias:
                    lat,lon=bias;params.update({'viewbox':f'{lon-.35},{lat+.35},{lon+.35},{lat-.35}','bounded':1})
                r=await c.get(GEO+'/search',params=params);r.raise_for_status();out=r.json()
            trace.event('geocoding','ok','nominatim_results_'+str(len(out)));save(key,out);return out
        except Exception as exc: trace.failure('geocoding_nominatim',exc);raise

async def google_route(loc,dest,mode):
    point=lambda lat,lon:{'location':{'latLng':{'latitude':float(lat),'longitude':float(lon)}}}
    fields='routes.distanceMeters,routes.duration,routes.legs.steps.distanceMeters,routes.legs.steps.navigationInstruction,routes.legs.steps.startLocation,routes.polyline.geoJsonLinestring'
    if mode=='TRANSIT': fields='routes.duration,routes.distanceMeters,routes.legs.steps.transitDetails,routes.travelAdvisory.transitFare'
    payload={'origin':point(loc['lat'],loc['lon']),'destination':point(dest['lat'],dest['lon']),'travelMode':mode}
    if mode!='TRANSIT': payload['polylineEncoding']='GEO_JSON_LINESTRING'
    async with httpx.AsyncClient(timeout=20) as c:
        r=await c.post('https://routes.googleapis.com/directions/v2:computeRoutes',headers={'X-Goog-Api-Key':GOOGLE_KEY,'X-Goog-FieldMask':fields},json=payload);r.raise_for_status(); data=r.json()
    if not data.get('routes'): raise ValueError('no_route')
    return data['routes'][0]

def normalize_google(r):
    steps=[]
    mapping={'TURN_LEFT':'left','TURN_RIGHT':'right','TURN_SLIGHT_LEFT':'slight left','TURN_SLIGHT_RIGHT':'slight right','STRAIGHT':'straight','UTURN_LEFT':'uturn','UTURN_RIGHT':'uturn'}
    for i,step in enumerate((r.get('legs') or [{}])[0].get('steps',[])):
        p=step.get('startLocation',{}).get('latLng',{}); maneuver=step.get('navigationInstruction',{}).get('maneuver','')
        steps.append({'distance':step.get('distanceMeters',0),'name':'','maneuver':{'type':'depart' if i==0 else 'turn','modifier':mapping.get(maneuver,''),'location':[p.get('longitude',0),p.get('latitude',0)]}})
    coords=r.get('polyline',{}).get('geoJsonLinestring',{}).get('coordinates',[])
    if not steps or not coords: raise ValueError('incomplete_google_route')
    return {'distance':r['distanceMeters'],'duration':float(r['duration'].rstrip('s')),'legs':[{'steps':steps}],'geometry':{'coordinates':coords}}

async def route(loc,dest,mode='walking'):
    key=('route',mode,round(float(loc['lat']),4),round(float(loc['lon']),4),round(float(dest['lat']),4),round(float(dest['lon']),4))
    hit=cached(key)
    if hit is not None: trace.event('routing','ok',mode+'_cache');return hit
    if GOOGLE_KEY:
        trace.event('routing','start','google_'+mode)
        try:
            out=normalize_google(await google_route(loc,dest,'WALK' if mode=='walking' else 'DRIVE'))
            trace.event('routing','ok','google_'+mode);save(key,out);return out
        except Exception as exc: trace.failure('routing_google_'+mode,exc)
    trace.event('routing','start','osrm_'+mode)
    base=FOOT if mode=='walking' else CAR
    try:
        url=base+f"/route/v1/{'foot' if mode=='walking' else 'driving'}/{float(loc['lon'])},{float(loc['lat'])};{float(dest['lon'])},{float(dest['lat'])}?steps=true&overview=full&geometries=geojson"
        try:
            async with httpx.AsyncClient(timeout=25) as c:
                r=await c.get(url);r.raise_for_status();data=r.json()
        except httpx.ConnectError as exc:
            # Some macOS Python builds cannot negotiate this server's TLS; curl uses system TLS.
            # The URL (including coordinates) goes through stdin, not process arguments or logs.
            if 'SSLV3_ALERT_HANDSHAKE_FAILURE' not in str(exc): raise
            trace.event('routing','retry','system_tls')
            proc=await asyncio.create_subprocess_exec('curl','--config','-',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
            if any(c in url for c in ('\n','\r','"')): raise ValueError('invalid_router_url')
            config=f'url = "{url}"\nsilent\nshow-error\nfail\nmax-time = 25\n'.encode()
            output,_=await proc.communicate(config)
            if proc.returncode: raise ConnectionError('system_tls_route_failed')
            data=json.loads(output)
        if data.get('code')!='Ok' or not data.get('routes'): raise ValueError('no_route')
        out=data['routes'][0]; trace.event('routing','ok','osrm_'+mode);save(key,out);return out
    except Exception as exc: trace.failure('routing_osrm_'+mode,exc);raise

async def transit(loc,dest):
    if not GOOGLE_KEY: trace.event('transport','unavailable','google_key_missing'); return None
    trace.event('transport','start','google_transit')
    try:
        r=await google_route(loc,dest,'TRANSIT');trace.event('transport','ok','google_transit');return r
    except Exception as exc: trace.failure('transport_google',exc);return None
