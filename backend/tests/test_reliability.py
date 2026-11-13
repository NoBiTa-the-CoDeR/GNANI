import types,os,unittest
from unittest.mock import patch
import httpx
from backend.reliability import install
class Failure(Exception):pass
class Reliability(unittest.IsolatedAsyncioTestCase):
 def module(self):return types.SimpleNamespace(load_providers=lambda:[{'name':p,'model':'test','key':'test-private','url':'https://'+p+'.test'} for p in ('groq','openrouter')],LLMError=Failure)
 async def test_rate_limit_falls_back_and_skips_until_cooldown(self):
  m=self.module();seen=[]
  def response(r):
   seen.append(r.url.host)
   return httpx.Response(429,headers={'retry-after':'60'}) if 'groq' in r.url.host else httpx.Response(200,json={'choices':[{'message':{'content':'A real answer'}}]})
  with patch.dict(os.environ,{'GEMINI_SPEECH_FREE_TIER':'0'}):
   install(m)
   async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as c:
    for _ in range(2):self.assertEqual((await m.chat([],client=c))['content'],'A real answer')
  self.assertEqual(seen,['groq.test','openrouter.test','openrouter.test'])
 async def test_all_limits_remain_an_honest_failure(self):
  m=self.module()
  with patch.dict(os.environ,{'GEMINI_SPEECH_FREE_TIER':'0'}):
   install(m)
   async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(429))) as c:
    with self.assertRaisesRegex(Failure,'rate_limit'):await m.chat([],client=c)
 async def test_empty_answer_uses_next_provider(self):
  m=self.module()
  def response(r):return httpx.Response(200,json={'choices':[{'message':{'content':'' if 'groq' in r.url.host else 'Answer'}}]})
  with patch.dict(os.environ,{'GEMINI_SPEECH_FREE_TIER':'0'}):
   install(m)
   async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as c:self.assertEqual((await m.chat([],client=c))['content'],'Answer')
