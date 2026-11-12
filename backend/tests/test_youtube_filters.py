import unittest,types,os
from unittest.mock import patch
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.youtube import install
class YouTube(unittest.TestCase):
 def test_filters_cache_and_validation(self):
  app=FastAPI();brain=types.SimpleNamespace(_yt_usage={'day':'','n':0});install(app,brain);calls=[];real=httpx.AsyncClient
  def handler(req):
   calls.append(dict(req.url.params));playlist=req.url.params['type']=='playlist'
   return httpx.Response(200,json={'items':[{'id':{'playlistId':'PLabcdefghijklm'} if playlist else {'videoId':'abcdefghij0'},'snippet':{'title':'Test','channelTitle':'Channel','thumbnails':{}}}]})
  with patch.dict(os.environ,{'YOUTUBE_API_KEY':'private-test-key'}),patch('backend.youtube.httpx.AsyncClient',side_effect=lambda **kw:real(transport=httpx.MockTransport(handler),**kw)),TestClient(app) as client:
   for kind in ('videos','shorts','streams','playlists'):
    r=client.get('/api/youtube',params={'q':'dosa','kind':kind});self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['items']),1)
   self.assertTrue(client.get('/api/youtube?q=dosa&kind=videos').json()['cached']);self.assertEqual(len(calls),4)
   self.assertEqual(calls[1]['videoDuration'],'short');self.assertEqual(calls[2]['eventType'],'live');self.assertEqual(calls[3]['type'],'playlist');self.assertNotIn('videoEmbeddable',calls[3])
   self.assertEqual(client.get('/api/youtube',params={'q':'x'*101}).status_code,422);self.assertEqual(client.get('/api/youtube?q=x&kind=unknown').status_code,422)
if __name__=='__main__':unittest.main()
