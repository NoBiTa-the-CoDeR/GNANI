import os
os.environ['GNANI_TESTING']='1'
import unittest
from unittest.mock import patch,AsyncMock
from fastapi.testclient import TestClient
from backend import main

class VoiceBridge(unittest.TestCase):
 def test_gps_nav_and_one_history_per_session(self):
  seen=[]
  async def respond(history,text,location,client=None,nav=None):
   seen.append((id(history),location,nav,text));history.extend([{'role':'user','content':text},{'role':'assistant','content':'Okay'}]);return {'text':'Okay','lang':'en','error':None}
  with patch.object(main.brain,'respond',respond),patch.object(main,'synthesize',AsyncMock(return_value=['audio'])):
   with TestClient(main.app).websocket_connect('/api/session') as ws:
    ws.send_json({'type':'location','location':{'lat':12.9,'lon':77.6,'accuracy':8}})
    ws.send_json({'type':'nav','nav':{'remaining_m':400,'remaining_min':6,'next_instruction':'Left in 80 m','destination':'Public test destination','mode':'walk'}})
    for text in ['How far?','Where am I going?']:
     ws.send_json({'type':'text','aloud':True,'text':text})
     while ws.receive_json()['type']!='response_end':pass
  self.assertEqual(seen[0][0],seen[1][0]);self.assertEqual(seen[0][1],{'lat':12.9,'lon':77.6});self.assertEqual(seen[0][2]['remaining_m'],400)
 def test_next_step_is_step_two_and_hindi_timbre(self):
  speak=AsyncMock(return_value=['audio'])
  async def respond(*a,**kw):return {'text':'नीचे तरीका है।','lang':'hi','error':None,'panel':{'kind':'recipe','title':'डोसा','steps':['पहला कदम।','दूसरा कदम।']}}
  with patch.object(main.brain,'respond',respond),patch.object(main,'synthesize',speak):
   with TestClient(main.app).websocket_connect('/api/session') as ws:
    ws.send_json({'type':'text','aloud':True,'text':'डोसा कैसे बनाते हैं?'})
    while ws.receive_json()['type']!='response_end':pass
    ws.send_json({'type':'text','aloud':True,'text':'अगला कदम'});events=[]
    while True:
     event=ws.receive_json();events.append(event)
     if event['type']=='response_end':break
  self.assertTrue(any(e.get('type')=='step' and e.get('index')==1 for e in events));self.assertEqual(speak.call_args.args,('दूसरा कदम।','hi-IN'))
 def test_long_reply_is_not_cut_off_and_matches_screen(self):
  speak=AsyncMock(return_value=['audio'])
  async def respond(*a,**kw):return {'text':'One. Two. Three. Four.','lang':'en','error':None}
  with patch.object(main.brain,'respond',respond),patch.object(main,'synthesize',speak):
   with TestClient(main.app).websocket_connect('/api/session') as ws:
    ws.send_json({'type':'text','aloud':True,'text':'Hello'});events=[]
    while True:
     event=ws.receive_json();events.append(event)
     if event['type']=='response_end':break
  self.assertEqual([c.args[0] for c in speak.call_args_list],['One.','Two.','Three.','Four.'])
  self.assertEqual([e['text'] for e in events if e['type']=='audio_sentence'],[c.args[0] for c in speak.call_args_list])
 def test_invalid_navigation_facts_are_not_forwarded(self):
  seen=[]
  async def respond(*a,**kw):seen.append(kw.get('nav'));return {'text':'Hello','lang':'en','error':None}
  with patch.object(main.brain,'respond',respond),patch.object(main,'synthesize',AsyncMock(return_value=['audio'])):
   with TestClient(main.app).websocket_connect('/api/session') as ws:
    ws.send_json({'type':'nav','nav':{'remaining_m':-1,'remaining_min':1,'mode':'walk'}});ws.send_json({'type':'text','aloud':True,'text':'Hello'})
    while ws.receive_json()['type']!='response_end':pass
  self.assertEqual(seen,[None])
 def test_model_cannot_choose_from_ambiguous_coordinates(self):
  import asyncio
  async def run():
   point={'lat':12.9,'lon':77.6};args={'destination':'A public place','dest_lat':point['lat'],'dest_lon':point['lon']}
   token=main.verified_places.set((point,{'lat':13.0,'lon':77.7}))
   try:
    sink={};await main.traced_tool('show_map',args,None,None,sink)
    self.assertIsNone(sink['map']['dest'])
    main.verified_places.set((point,));sink={};await main.traced_tool('show_map',args,None,None,sink)
    self.assertEqual(sink['map']['dest'],point)
   finally:main.verified_places.reset(token)
  asyncio.run(run())
 def test_assistant_step_mention_updates_current_card(self):
  async def respond(*a,**kw):return {'text':'Step 2. Grind the batter.','lang':'en','error':None,'panel':{'title':'Dosa','steps':['Soak.','Grind.']}}
  with patch.object(main.brain,'respond',respond),patch.object(main,'synthesize',AsyncMock(return_value=['audio'])):
   with TestClient(main.app).websocket_connect('/api/session') as ws:
    ws.send_json({'type':'text','aloud':True,'text':'How do I make dosa?'});events=[]
    while True:
     event=ws.receive_json();events.append(event)
     if event['type']=='response_end':break
  self.assertTrue(any(e.get('type')=='step' and e.get('index')==1 for e in events))
if __name__=='__main__':unittest.main()

class Segments(unittest.TestCase):
 def test_gender_segments_and_full_story_are_forwarded(self):
  parts=[{'voice':'f','text':'Grandmother began the story. ' * 12},{'voice':'m','text':'Grandfather answered kindly. ' * 12}]
  spoken=AsyncMock(return_value=['audio'])
  with patch.object(main.brain,'respond',AsyncMock(return_value={'text':' '.join(p['text'] for p in parts),'segments':parts,'lang':'en','theme':'story'})),patch.object(main,'synthesize',spoken):
   with TestClient(main.app).websocket_connect('/api/session') as ws:
    ws.send_json({'type':'text','aloud':True,'text':'Tell me a long story'});events=[]
    while True:
     value=ws.receive_json();events.append(value)
     if value['type']=='response_end':break
  audio=[e for e in events if e['type']=='audio_sentence']
  self.assertEqual(len(audio),24);self.assertEqual(audio[-1]['voice'],'m')
  self.assertTrue(any(c.kwargs.get('voice')=='Pranav' for c in spoken.call_args_list))
  self.assertTrue(any(e['type']=='theme' and e['theme']=='story' for e in events))

class CompletionBudget(unittest.TestCase):
 def test_truncated_story_is_continued_before_voice_parsing(self):
  import asyncio,json,httpx
  seen=[]
  def handle(req):
   seen.append(json.loads(req.content))
   return httpx.Response(200,json={'choices':[{'finish_reason':'length' if len(seen)==1 else 'stop','message':{'role':'assistant','content':'Once upon a time,' if len(seen)==1 else 'they found their way home. The end.'}}]})
  async def run():
   async with main.ConversationClient(transport=httpx.MockTransport(handle)) as c:
    r=await c.post('https://api.groq.com/openai/v1/chat/completions',json={'model':'test','messages':[{'role':'user','content':'Tell a long story'}],'max_tokens':900})
    self.assertTrue(r.json()['choices'][0]['message']['content'].endswith('The end.'))
  asyncio.run(run());self.assertEqual(len(seen),2);self.assertEqual(seen[1]['max_tokens'],900);self.assertNotIn('tools',seen[1])
