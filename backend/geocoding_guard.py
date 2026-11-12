"""Bound geocoder cost and avoid duplicate searches, without changing supplied brain logic."""
import asyncio,os,time,re
from backend.api import Cache
from backend import trace

def install(brain):
 async def checked_geoapify(query,client,location):
  key=os.getenv('GEOAPIFY_API_KEY')
  if not key:return []
  params={'text':query,'limit':5,'filter':'countrycode:in','apiKey':key}
  if location:params['bias']=f"proximity:{location['lon']},{location['lat']}"
  r=await client.get('https://api.geoapify.com/v1/geocode/search',params=params);r.raise_for_status();accepted=[]
  specific=bool(re.search(r'(?i)station|hospital|airport|bus stand|metro',query))
  for f in r.json().get('features',[]):
   p=f.get('properties',{});rank=p.get('rank',{});confidence=rank.get('confidence',0)
   if (specific and p.get('result_type') in ('city','county','state','country','postcode')) or (rank.get('match_type')!='full_match' and confidence<.6):
    trace.event('geocoding','rejected','geoapify_broad_match');continue
   if p.get('lat') is not None and p.get('lon') is not None:accepted.append({'name':p.get('formatted',query),'lat':float(p['lat']),'lon':float(p['lon'])})
  return accepted
 brain.GEOCODERS['geoapify']=checked_geoapify
 cache=Cache(ttl=3600,maximum=512);lock=asyncio.Lock();day='';used=0
 original=brain.search_place
 async def cached_search(query,client,location=None):
  nonlocal day,used
  key=(' '.join(query.casefold().split()),round(location['lat'],2) if location else None,round(location['lon'],2) if location else None)
  async with lock:
   found=cache.get(key)
   if found is not None:return {**found,'cached':True}
   today=time.strftime('%Y-%m-%d',time.gmtime())
   if day!=today:day=today;used=0
   if used>=int(os.getenv('GEOCODER_DAILY_LIMIT','500')):
    trace.event('geocoding','error','daily_limit');return {'error':'daily_limit','message':'Place-search daily limit reached. Try again tomorrow.'}
   used+=1
   try:value=await asyncio.wait_for(original(query,client,location),18)
   except asyncio.TimeoutError:
    trace.event('geocoding','error','timeout');return {'error':'timeout'}
   trace.event('geocoding','ok' if value.get('results') else 'empty_or_error',value.get('source','none'))
   if value.get('results'):cache.put(key,value)
   return value
 brain.search_place=cached_search
