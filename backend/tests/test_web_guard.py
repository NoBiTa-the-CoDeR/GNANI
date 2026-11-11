import os
os.environ['GNANI_TESTING']='1'
import asyncio,json,socket,unittest
from unittest.mock import patch,AsyncMock,MagicMock
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.web_guard import *
from backend import web_assistant as web
class Guard(unittest.TestCase):
 def test_private_and_sensitive_urls(self):
  for url in ['http://example.com','https://localhost/','https://127.0.0.1','file:///etc/passwd','https://[::1]/','https://foo.local/','https://user:pass@example.com/','https://example.com:8000/','https://example.com/?api_key=abc','https://example.com/checkout','https://example.com/file.pdf']:
   with self.subTest(url=url),self.assertRaises(Blocked):clean_url(url)
  self.assertEqual(clean_url('https://en.wikipedia.org/wiki/Dosa#x'),'https://en.wikipedia.org/wiki/Dosa')
 def test_actions_and_private_typing(self):
  for value in [{'action':'type','i':1,'text':'123456'},{'action':'type','i':1,'text':'my password is secret'},{'action':'click','i':0},{'action':'click','i':True},{'action':'download'},{'action':'goto','url':'https://example.com/payment'}]:
   with self.assertRaises(Blocked):action_json(value,1)
  self.assertEqual(action_json({'action':'type','i':1,'text':'dosa'},1)['text'],'dosa');self.assertTrue(PAY.search('Pay'))
 def test_dns_mixed_private_answer_is_rejected(self):
  async def run():
   with patch.object(asyncio.get_running_loop(),'getaddrinfo',AsyncMock(return_value=[(2,1,6,'',('93.184.216.34',443)),(2,1,6,'',('127.0.0.1',443))])):
    with self.assertRaises(Blocked):await public_ips('example.com')
  asyncio.run(run())
 def test_secret_scrub(self):
  with patch.dict(os.environ,{'SOME_API_KEY':'private-value-abcdef'}):self.assertNotIn('private-value-abcdef',scrub('private-value-abcdef'))
 def test_new_domain_is_not_opened_without_approval(self):
  async def run():
   events=[];run=web.WebRun(lambda m:asyncio.sleep(0),'task');run.approval=AsyncMock(return_value=False)
   with patch.object(web,'public_ips',AsyncMock(return_value=['93.184.216.34'])):
    with self.assertRaises(Blocked):await run.authorize('https://example.com/')
   self.assertEqual(run.approved,set())
  asyncio.run(run())
 def test_redirect_and_post_are_blocked_without_tickets(self):
  async def run():
   w=web.WebRun(AsyncMock(),'task');route=MagicMock();route.abort=AsyncMock();route.continue_=AsyncMock();r=MagicMock(url='https://example.com/',method='GET');r.is_navigation_request.return_value=True
   await w.route(route,r);route.abort.assert_awaited_once();route.continue_.assert_not_awaited();self.assertEqual(w.pending_navigation,'https://example.com/')
   w.approved.add('example.com');r.method='POST';await w.route(route,r);route.continue_.assert_not_awaited()
  asyncio.run(run())
 def test_approval_ids_cannot_be_replayed(self):
  async def run():
   w=web.WebRun(AsyncMock(),'task');w.approval_id='good';w.waiter=asyncio.get_running_loop().create_future();w.answer('wrong',True);self.assertFalse(w.waiter.done());w.answer('good',False);self.assertFalse(await w.waiter)
  asyncio.run(run())
 def test_submit_requires_yes(self):
  async def run():
   w=web.WebRun(AsyncMock(),'task');w.authorize=AsyncMock(return_value='https://example.com/search');w.approval=AsyncMock(return_value=False)
   with self.assertRaises(Blocked):await w.submit_permission('https://example.com/search','search')
   self.assertIsNone(w.ticket)
  asyncio.run(run())
 def test_off_does_not_start_browser(self):
  app=FastAPI();web.install(app)
  with patch.object(web.WebRun,'run',AsyncMock()) as run:
   with TestClient(app).websocket_connect('/api/web/session') as ws:
    ws.send_json({'type':'start','task':'search Wikipedia','consent':False});self.assertIn('enable',ws.receive_json()['text'])
   run.assert_not_awaited()
 def test_model_fallback_and_payload_no_credentials(self):
  async def run():
   calls=[]
   def handler(req):
    d=json.loads(req.content);calls.append(d);self.assertNotIn('test-secret-abcdef',str(d))
    if req.url.host=='api.groq.com':return httpx.Response(429)
    return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'action':'goto','url':'https://en.wikipedia.org/wiki/Dosa'})}}]})
   with patch.dict(os.environ,{'GEMINI_API_KEY':'','GROQ_API_KEY':'test-secret-abcdef','OPENROUTER_API_KEY':'test-secret-abcdef'}):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:out,p=await web.model_action('search dosa',{'elements':[]},[],'en',c)
   self.assertEqual(p,'openrouter');self.assertEqual(out['action'],'goto');self.assertEqual(calls[-1]['model'],'openrouter/free')
  asyncio.run(run())
 def test_payment_button_never_clicks(self):
  async def run():
   w=web.WebRun(AsyncMock(),'task');element=MagicMock();element.count=AsyncMock(return_value=1);element.evaluate=AsyncMock(return_value={'tag':'button','type':'submit','label':'Pay','form':None});element.click=AsyncMock();w.page=MagicMock();w.page.locator.return_value=element
   with self.assertRaises(Blocked):await w.execute({'action':'click','i':1},{'elements':[{'blocked':False}]})
   element.click.assert_not_awaited()
  asyncio.run(run())
 def test_watchdog_cancels_work(self):
  import threading,time
  cancelled=threading.Event()
  async def stalled(run):
   try:await asyncio.sleep(10)
   finally:cancelled.set()
  app=FastAPI();web.install(app)
  with patch.object(web,'TIME_LIMIT',.1),patch.object(web.WebRun,'run',stalled):
   with TestClient(app).websocket_connect('/api/web/session') as ws:
    started=time.monotonic();ws.send_json({'type':'start','task':'read Wikipedia','consent':True})
    while ws.receive_json()['type']!='stopped':pass
    self.assertLess(time.monotonic()-started,2);self.assertTrue(cancelled.is_set())
 def test_proxy_connects_validated_ip_not_hostname(self):
  class Writer:
   def __init__(self):self.data=b'';self.closed=False
   def write(self,value):self.data+=value
   async def drain(self):pass
   def close(self):self.closed=True
  async def run():
   proxy=PublicProxy({'example.com'});reader=asyncio.StreamReader();writer=Writer();up_reader=asyncio.StreamReader();up_reader.feed_eof();up=Writer()
   auth=base64.b64encode(('gnani:'+proxy.token).encode()).decode();reader.feed_data(('CONNECT example.com:443 HTTP/1.1\r\nProxy-Authorization: Basic '+auth+'\r\n\r\n').encode());reader.feed_eof()
   with patch('backend.web_guard.public_ips',AsyncMock(return_value=['93.184.216.34'])),patch('backend.web_guard.asyncio.open_connection',AsyncMock(return_value=(up_reader,up))) as connect:
    await proxy.handle(reader,writer)
   self.assertEqual(connect.call_args.args,('93.184.216.34',443));self.assertFalse(proxy.connections);self.assertIn(b'200 Connection Established',writer.data)
  asyncio.run(run())
 def test_alphanumeric_code_and_hidden_autocomplete_are_sensitive(self):
  self.assertTrue(BLOCK.search('one-time-code'));self.assertTrue(BLOCK.search('Verification code'))
  with self.assertRaises(Blocked):action_json({'action':'ask_user','text':'Please tell me your password.'},0)
 def test_codes_cannot_bypass_typing_through_query_urls(self):
  with self.assertRaises(Blocked):clean_url('https://example.com/search?q=123456')
 def test_login_and_booking_need_separate_permission(self):
  async def run():
   for label in ('Sign in','Book a table'):
    w=web.WebRun(AsyncMock(),'test');w.approval=AsyncMock(return_value=False);element=MagicMock();element.count=AsyncMock(return_value=1);element.evaluate=AsyncMock(return_value={'tag':'button','type':'button','label':label,'form':None});element.click=AsyncMock();w.page=MagicMock();w.page.locator.return_value=element
    with self.assertRaises(Blocked):await w.execute({'action':'click','i':1},{'elements':[{'blocked':False}]})
    self.assertEqual(w.approval.call_args.args[0],'login_booking');element.click.assert_not_awaited()
  asyncio.run(run())
