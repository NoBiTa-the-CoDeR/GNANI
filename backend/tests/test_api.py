import os
os.environ['GNANI_TESTING']='1'
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import install, Cache

class Endpoints(unittest.TestCase):
    def setUp(self):
        self.brain=SimpleNamespace(search_place=AsyncMock(return_value={'results':[{'lat':12.9,'lon':77.6,'name':'One'},{'lat':13.0,'lon':77.5,'name':'Two'}],'source':'test'}),full_route=AsyncMock(return_value={'coords':[[12.9,77.6],[13,77.5]],'steps':[],'distance_m':100,'duration_min':2}),music_search=AsyncMock(return_value={'tracks':[{'title':'Calm','url':'https://prod-1.storage.jamendo.com/?trackid=123','page':'https://www.jamendo.com/track/123'}]}),image_search=AsyncMock(return_value=[{'source':'Pixabay','url':'https://example.com/photo'}]),video_search=AsyncMock(return_value={'videos':[{'id':'abcdefghijk'}]*3}))
        app=FastAPI();install(app,self.brain,AsyncMock(return_value=['audio']));self.client=TestClient(app)
    def test_route_candidates_never_pick_one(self):
        r=self.client.post('/api/route',json={'origin':{'lat':12.9,'lon':77.6},'destination':'A place','mode':'walk'})
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['candidates']),2);self.brain.full_route.assert_not_called()
    def test_real_coordinates_required(self):
        self.assertEqual(self.client.post('/api/route',json={'origin':{'lat':999,'lon':3},'dest':{'lat':3,'lon':4}}).status_code,422)
    def test_missing_gps_includes_destination(self):
        r=self.client.post('/api/route',json={'dest':{'lat':12.9,'lon':77.6}})
        self.assertEqual(r.status_code,409);self.assertEqual(r.json()['dest']['lat'],12.9)
    def test_cache_24_hours_and_video_cap(self):
        a=self.client.get('/api/images?q=masala%20dosa');b=self.client.get('/api/images?q=masala%20dosa')
        self.assertFalse(a.json()['cached']);self.assertTrue(b.json()['cached']);self.brain.image_search.assert_awaited_once()
        self.assertEqual(len(self.client.get('/api/videos?q=dosa').json()['videos']),2)
        self.assertEqual(Cache().ttl,86400)
    def test_music_cache_limits_and_no_key(self):
        first=self.client.get('/api/music?q=calm');second=self.client.get('/api/music?q=CALM')
        self.assertFalse(first.json()['cached']);self.assertTrue(second.json()['cached']);self.brain.music_search.assert_awaited_once()
        self.assertEqual(self.client.get('/api/music',params={'q':'x'*101}).status_code,422)
        self.brain.music_search.return_value={'tracks':[],'reason':'no_key'}
        self.assertEqual(self.client.get('/api/music?q=other').json()['reason'],'no_key')
    def test_music_proxy_preserves_real_http_failure(self):
        import httpx
        url=self.client.get('/api/music?q=calm').json()['tracks'][0]['url']
        original=httpx.AsyncClient
        with patch('backend.api.httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(lambda req:httpx.Response(404)),**kw)):
            reply=self.client.head(url)
        self.assertEqual(reply.status_code,502)
    def test_query_limits(self):
        self.assertEqual(self.client.get('/api/images',params={'q':'x'*81}).status_code,422)
        self.assertEqual(self.client.get('/api/videos',params={'q':'x'*101}).status_code,422)
    def test_per_ip_limit(self):
        statuses=[self.client.get('/api/videos?q=dosa').status_code for _ in range(9)]
        self.assertEqual(statuses[-1],429)
    def test_route_error_is_specific(self):
        import httpx
        request=httpx.Request('GET','https://example.com')
        response=httpx.Response(503,request=request)
        self.brain.full_route.side_effect=httpx.HTTPStatusError('service failed',request=request,response=response)
        r=self.client.post('/api/route',json={'origin':{'lat':12.9,'lon':77.6},'dest':{'lat':13,'lon':77.5}})
        self.assertEqual(r.status_code,502);self.assertEqual(r.json()['upstream_status'],503)
    def test_photo_download_cached_for_24h(self):
        import httpx
        self.brain.image_search.return_value=[{'source':'Pixabay','url':'https://cdn.pixabay.com/photo/test.jpg'}]
        url=self.client.get('/api/images?q=dosa').json()['photos'][0]['url']
        requests=[];original=httpx.AsyncClient
        def handler(request):
            requests.append(request);return httpx.Response(200,headers={'Content-Type':'image/jpeg'},content=b'image data')
        with patch('backend.api.httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            first=self.client.get(url);second=self.client.get(url)
        self.assertEqual(first.status_code,200);self.assertEqual(second.headers['X-Photo-Cache'],'HIT');self.assertEqual(len(requests),1);self.assertEqual(second.headers['Cache-Control'],'public, max-age=86400')
    def test_photo_rate_limit_respects_backoff(self):
        import httpx
        self.brain.image_search.return_value=[{'source':'Pixabay','url':'https://cdn.pixabay.com/photo/test.jpg'}]
        url=self.client.get('/api/images?q=dosa').json()['photos'][0]['url'];requests=[];original=httpx.AsyncClient
        def handler(request):requests.append(request);return httpx.Response(429,headers={'Retry-After':'120'})
        with patch('backend.api.httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            first=self.client.get(url);second=self.client.get(url)
        self.assertEqual(first.json()['upstream_status'],429);self.assertEqual(second.status_code,502);self.assertEqual(len(requests),1)
    def test_unknown_photo_cannot_proxy_an_arbitrary_url(self):
        self.assertEqual(self.client.get('/api/photo/unknown').status_code,404)
    def test_same_provider_photo_deduplicates_signed_urls(self):
        self.brain.image_search.side_effect=[
            [{'source':'Pixabay','page':'https://pixabay.com/photos/test-123/','url':'https://cdn.pixabay.com/a.jpg?sig=one'}],
            [{'source':'Pixabay','page':'https://pixabay.com/photos/test-123/','url':'https://cdn.pixabay.com/a.jpg?sig=two'}]]
        one=self.client.get('/api/images?q=dosa').json()['photos'][0]['url']
        two=self.client.get('/api/images?q=dosa%20recipe').json()['photos'][0]['url']
        self.assertEqual(one,two)
if __name__=='__main__':unittest.main()
