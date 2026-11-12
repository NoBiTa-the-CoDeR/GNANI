import types,os,unittest
from unittest.mock import patch
import httpx
from backend.geocoding_guard import install
class Geocoding(unittest.IsolatedAsyncioTestCase):
 async def test_reject_city_for_station_and_cache_success(self):
  calls=[]
  async def search(query,client,location):
   results=await brain.GEOCODERS['geoapify'](query,client,location)
   return {'results':results,'source':'geoapify'}
  brain=types.SimpleNamespace(search_place=search,GEOCODERS={});install(brain)
  def handler(req):
   calls.append(req)
   return httpx.Response(200,json={'features':[{'properties':{'formatted':'Bengaluru','lat':12.9,'lon':77.5,'result_type':'city','rank':{'confidence':.25,'match_type':'match_by_city_or_district'}}},{'properties':{'formatted':'Test Metro Station','lat':12.9,'lon':77.6,'result_type':'amenity','rank':{'confidence':.9,'match_type':'full_match'}}}]})
  with patch.dict(os.environ,{'GEOAPIFY_API_KEY':'private-test-key'}):
   async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
    a=await brain.search_place('Test metro station',client,None);b=await brain.search_place('Test metro station',client,None)
  self.assertEqual(len(a['results']),1);self.assertEqual(a['results'][0]['name'],'Test Metro Station');self.assertTrue(b['cached']);self.assertEqual(len(calls),1)
if __name__=='__main__':unittest.main()
