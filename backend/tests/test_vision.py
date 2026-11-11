import os
os.environ['GNANI_TESTING']='1'
import unittest,io,base64,asyncio,json
from unittest.mock import patch,AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import httpx
from backend import vision

def photo():
 b=io.BytesIO();Image.new('RGB',(50,50),'white').save(b,'PNG');return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
class Vision(unittest.TestCase):
 def test_reencode_and_reject_nonimage(self):
  value=vision.prepare_image(photo());self.assertTrue(base64.b64decode(value).startswith(b'\xff\xd8'))
  with self.assertRaises(ValueError):vision.prepare_image('data:image/svg+xml;base64,PHN2Zz4=')
 def test_identity_is_refused_without_provider_call(self):
  result=asyncio.run(vision.read_image('', 'en','Who is this person?'));self.assertEqual(result['provider'],'none');self.assertIn('cannot identify',result['text'])
 def test_medicine_warning_and_redaction(self):
  async def run():
   def handler(req):
    body=json.loads(req.content);self.assertEqual(body['messages'][1]['content'][1]['type'],'image_url');return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'text':'The strip says paracetamol.','kind':'medicine','printed_text':'Aadhaar 1234 5678 9012','readable':True})}}]})
   with patch.dict(os.environ,{'GROQ_API_KEY':'private-test-key'}):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:return await vision.read_image('dummy','en',client=c)
  result=asyncio.run(run());self.assertIn('doctor or pharmacist',result['text']);self.assertNotIn('1234',result['printed_text'])
 def test_endpoint_returns_no_image_and_no_cache(self):
  app=FastAPI();vision.install(app)
  with patch.object(vision,'read_image',AsyncMock(return_value={'text':'Hello','printed_text':'Hello','lang':'en'})):
   r=TestClient(app).post('/api/vision',json={'image':photo(),'lang':'en'});self.assertEqual(r.status_code,200);self.assertEqual(r.headers['cache-control'],'no-store');self.assertNotIn('image',r.json())
 def test_invalid_language_and_bad_photo(self):
  app=FastAPI();vision.install(app);c=TestClient(app)
  self.assertEqual(c.post('/api/vision',json={'image':photo(),'lang':'bad'}).status_code,422);self.assertEqual(c.post('/api/vision',json={'image':'bad','lang':'en'}).status_code,422)
 def test_daily_quota_is_429_with_retry_hint(self):
  app=FastAPI();vision.install(app);req=httpx.Request('POST','https://example.com');r=httpx.Response(429,request=req,headers={'retry-after':'611'},json={'error':{'message':'tokens per day TPD'}})
  with patch.object(vision,'read_image',AsyncMock(side_effect=httpx.HTTPStatusError('rate',request=req,response=r))):
   out=TestClient(app).post('/api/vision',json={'image':photo(),'lang':'hi'})
  self.assertEqual(out.status_code,429);self.assertEqual(out.json()['limit_type'],'daily_tokens');self.assertEqual(out.headers['retry-after'],'611')
 def test_only_free_router_is_used_for_image_fallback(self):
  async def run():
   calls=[]
   def handler(req):
    d=json.loads(req.content);calls.append(d['model'])
    if req.url.host=='api.groq.com':return httpx.Response(429)
    return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'text':'A letter says hello.','printed_text':'Hello','kind':'letter','readable':True})}}]})
   with patch.dict(os.environ,{'GEMINI_API_KEY':'','GROQ_API_KEY':'test-groq-secret','OPENROUTER_API_KEY':'test-router-secret'}):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:out=await vision.read_image('dummy','en',client=c)
   self.assertEqual(out['provider'],'openrouter');self.assertEqual(calls[-1],'openrouter/free')
  asyncio.run(run())
 def test_photo_metadata_is_removed(self):
  exif=Image.Exif();exif[0x010E]='synthetic private metadata';buf=io.BytesIO();Image.new('RGB',(20,20),'white').save(buf,'JPEG',exif=exif)
  value=vision.prepare_image('data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode())
  with Image.open(io.BytesIO(base64.b64decode(value))) as image:self.assertEqual(len(image.getexif()),0)
