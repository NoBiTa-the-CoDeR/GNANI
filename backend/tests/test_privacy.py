import os
os.environ['GNANI_TESTING']='1'
import asyncio, threading, unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend import main
class Privacy(unittest.TestCase):
 def test_mute_cancels_stt_and_drops_future_audio(self):
  entered=threading.Event();cancelled=threading.Event();calls=[]
  async def stt(audio):
   calls.append(1);entered.set()
   try:await asyncio.sleep(30)
   finally:cancelled.set()
  brain=AsyncMock()
  with patch.object(main,'transcribe',stt),patch.object(main.brain,'respond',brain):
   with TestClient(main.app).websocket_connect('/api/session') as ws:
    ws.send_json({'type':'mic_state','enabled':True});self.assertTrue(ws.receive_json()['enabled']);ws.send_bytes(b'fake audio')
    self.assertTrue(entered.wait(2));ws.send_json({'type':'mic_state','enabled':False})
    while ws.receive_json()['type']!='mic_state':pass
    self.assertTrue(cancelled.wait(1));ws.send_bytes(b'muted discarded')
    ws.send_json({'type':'mic_state','enabled':False})
    while ws.receive_json()['type']!='mic_state':pass
  self.assertEqual(len(calls),1);brain.assert_not_awaited()
 def test_typed_while_muted_is_text_only(self):
  answer=AsyncMock(return_value={'text':'Hello there.','lang':'en'});tts=AsyncMock()
  with patch.object(main.brain,'respond',answer),patch.object(main,'synthesize',tts):
   with TestClient(main.app).websocket_connect('/api/session') as ws:
    ws.send_json({'type':'text','text':'Hello','request_id':'typed'});events=[]
    while True:
     m=ws.receive_json();events.append(m)
     if m['type']=='response_end':break
  tts.assert_not_awaited();self.assertEqual(next(m['text'] for m in events if m['type']=='text_only'),'Hello there.')
 def test_first_sentence_emitted_before_next_is_ready(self):
  second=threading.Event()
  async def synth(text,lang):
   if text=='Second sentence.':second.set();await asyncio.sleep(30)
   return ['audio']
  with patch.object(main.brain,'respond',AsyncMock(return_value={'text':'First sentence. Second sentence.','lang':'en'})),patch.object(main,'synthesize',synth):
   with TestClient(main.app).websocket_connect('/api/session') as ws:
    ws.send_json({'type':'text','text':'Hello','aloud':True})
    while True:
     msg=ws.receive_json()
     if msg['type']=='audio_sentence':break
    self.assertEqual(msg['text'],'First sentence.');self.assertTrue(second.wait(2))
    ws.send_json({'type':'stop_talking'})
 def test_explicit_phone_request_requires_fresh_action_tool(self):
  import httpx
  captured=[]
  async def run():
   def handler(req):
    import json
    captured.append(json.loads(req.content));return httpx.Response(200,json={'choices':[{'message':{'content':'ok'}}]})
   async with main.ConversationClient(transport=httpx.MockTransport(handler)) as client:
    body={'model':'test','tools':[{'type':'function','function':{'name':'propose_action'}}],'messages':[{'role':'user','content':'remind me in 1 minute to take medicine'}]}
    await client.post('https://api.groq.com/openai/v1/chat/completions',json=body)
    body['messages'] += [{'role':'assistant','tool_calls':[]},{'role':'tool','content':'prepared'}]
    await client.post('https://api.groq.com/openai/v1/chat/completions',json=body)
    await client.post('https://api.groq.com/openai/v1/chat/completions',json={**body,'messages':[{'role':'user','content':'Hello'}]})
  asyncio.run(run());self.assertEqual(captured[0]['tool_choice']['function']['name'],'propose_action');self.assertNotIn('tool_choice',captured[1]);self.assertNotIn('tool_choice',captured[2])
 def test_web_tasks_route_only_when_enabled(self):
  respond=AsyncMock(return_value={'text':'Hello','lang':'en'})
  with patch.object(main.brain,'respond',respond):
   with TestClient(main.app).websocket_connect('/api/session') as ws:
    for enabled in (False,True):
     ws.send_json({'type':'web_preference','enabled':enabled});ws.send_json({'type':'text','text':"find today's weather in Bengaluru"});events=[]
     while True:
      m=ws.receive_json();events.append(m)
      if m['type']=='response_end':break
     self.assertEqual(any(m['type']=='web_task' for m in events),enabled)
   self.assertEqual(respond.await_count,1)
