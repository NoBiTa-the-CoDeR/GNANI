"""Public YouTube search with server-only credentials and bounded cached quota."""
import asyncio,os,time
from typing import Literal
import httpx
from fastapi import HTTPException,Query,Request
from backend.api import Cache,Limits

def install(app,brain):
 cache=Cache(ttl=86400,maximum=512);limits=Limits();lock=asyncio.Lock()
 @app.get('/api/youtube')
 async def search(request:Request,q:str=Query(min_length=1,max_length=100),kind:Literal['videos','shorts','streams','playlists']='videos'):
  limits.check(request,'youtube_search',8)
  q=q.strip()
  if not q:raise HTTPException(422,'Please enter a search.')
  identity=(q.casefold(),kind)
  async with lock:
   found=cache.get(identity)
   if found is not None:return {**found,'cached':True}
   key=os.getenv('YOUTUBE_API_KEY','')
   if not key:return {'items':[],'reason':'no_key'}
   if not cache.has_room():return {'items':[],'reason':'cache_capacity'}
   today=time.strftime('%Y-%m-%d',time.gmtime());usage=brain._yt_usage
   if usage['day']!=today:usage.update(day=today,n=0)
   if usage['n']>=int(os.getenv('YT_DAILY_SEARCH_LIMIT','90')):return {'items':[],'reason':'daily_limit'}
   usage['n']+=1
   params={'part':'snippet','q':q,'type':'playlist' if kind=='playlists' else 'video','maxResults':12,'safeSearch':'strict','regionCode':'IN','key':key}
   if kind!='playlists':params['videoEmbeddable']='true'
   if kind=='streams':params['eventType']='live'
   if kind=='shorts':params['videoDuration']='short' # YouTube means under four minutes, not Shorts classification.
   try:
    async with httpx.AsyncClient(timeout=12) as client:r=await client.get('https://www.googleapis.com/youtube/v3/search',params=params)
    if r.status_code!=200:
     result={'items':[],'reason':'quota_or_key' if r.status_code==403 else 'unavailable','status':r.status_code}
    else:
     items=[]
     for item in r.json().get('items',[]):
      snippet=item.get('snippet',{});is_list=kind=='playlists';id=item.get('id',{}).get('playlistId' if is_list else 'videoId')
      if id:items.append({'id':id,'type':'playlist' if is_list else 'video','title':snippet.get('title',''),'channel':snippet.get('channelTitle',''),'thumb':(snippet.get('thumbnails',{}).get('medium') or snippet.get('thumbnails',{}).get('default') or {}).get('url',''),'live':kind=='streams'})
     result={'items':items,'shorts_note':kind=='shorts'}
   except httpx.TimeoutException:result={'items':[],'reason':'timeout'}
   except (httpx.HTTPError,ValueError):result={'items':[],'reason':'unavailable'}
   cache.put(identity,result);return {**result,'cached':False}
