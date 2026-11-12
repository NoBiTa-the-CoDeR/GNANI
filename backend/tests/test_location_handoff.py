import unittest,asyncio
from unittest.mock import patch,AsyncMock
from fastapi.testclient import TestClient
from backend import main
class Handoff(unittest.TestCase):
 def test_null_fix_does_not_release_wait_and_real_fix_reaches_brain(self):
  respond=AsyncMock(return_value={'text':'Your route is ready.','lang':'en','error':None})
  with patch.object(main.brain,'respond',respond),TestClient(main.app) as client,client.websocket_connect('/api/session') as ws:
   ws.send_json({'type':'location','location':None})
   ws.send_json({'type':'text','text':'How do I reach Lalbagh?','aloud':False,'request_id':'gps'})
   for _ in range(8):
    event=ws.receive_json()
    if event['type']=='location_needed':break
   else:self.fail('No location request')
   self.assertFalse(respond.called)
   ws.send_json({'type':'location','location':{'lat':12.97,'lon':77.59,'accuracy':8}})
   while ws.receive_json()['type']!='response_end':pass
  self.assertEqual(respond.call_args.args[2],{'lat':12.97,'lon':77.59})
 def test_denied_stops_wait_without_asking_again_next_turn(self):
  respond=AsyncMock(return_value={'text':'Please enter a starting place below.','lang':'en','error':None})
  with patch.object(main.brain,'respond',respond),TestClient(main.app) as client,client.websocket_connect('/api/session') as ws:
   ws.send_json({'type':'text','text':'How do I reach Lalbagh?','aloud':False,'request_id':'one'})
   while ws.receive_json()['type']!='location_needed':pass
   ws.send_json({'type':'location_denied'})
   while ws.receive_json()['type']!='response_end':pass
   ws.send_json({'type':'text','text':'How do I reach Majestic?','aloud':False,'request_id':'two'})
   messages=[]
   while True:
    event=ws.receive_json();messages.append(event['type'])
    if event['type']=='response_end':break
   self.assertNotIn('location_needed',messages)
  self.assertIsNone(respond.call_args.args[2])
if __name__=='__main__':unittest.main()

class Freshness(unittest.TestCase):
 def test_old_browser_fix_is_not_reused_as_current_gps(self):
  import time
  self.assertIsNone(main.gps_from({'location':{'lat':12.9,'lon':77.6,'timestamp':time.time()*1000-60000}}))
  self.assertEqual(main.gps_from({'location':{'lat':12.9,'lon':77.6,'timestamp':time.time()*1000}}),{'lat':12.9,'lon':77.6})
