import asyncio,base64,io,os,unittest,wave
from unittest.mock import patch
import httpx
from backend import multilingual as m,language,voices
from backend.tts_normalize import normalize
class Languages(unittest.TestCase):
 def test_catalog(self):
  self.assertGreaterEqual(len(m.NAMES),30)
  for code in m.NAMES:
   locale=m.canonical(code);self.assertEqual(m.canonical(locale),locale)
   self.assertIn(m.NAMES[code],m.instruction(locale))
   if code in m.GNANI:self.assertTrue(voices.settings(locale)[1])
 def test_detection(self):
  for text,expected in [('How do I make dosa?','en-IN'),('Bonjour, comment allez-vous ?','fr-FR'),('Hola, ¿cómo estás?','es-ES'),('आप कैसे हैं?','hi-IN'),('ನೀವು ಹೇಗಿದ್ದೀರಿ?','kn-IN'),('こんにちは、お元気ですか？','ja-JP'),('你好，你好吗？','zh-CN'),('dosa kaise banate hain','hi-IN')]:self.assertEqual(language.detect(text),expected)
  self.assertEqual(language.detect('Hello','fr-FR'),'fr-FR')
 def test_normalization(self):
  self.assertIn('150',normalize('**Bonjour** 150 mètres.','fr-FR'))
  self.assertNotIn('one',normalize('150 mètres','fr-FR'))
class Provider(unittest.IsolatedAsyncioTestCase):
 async def test_all_secondary_languages_and_audio(self):
  buffer=io.BytesIO()
  with wave.open(buffer,'wb') as f:f.setparams((1,2,24000,0,'NONE',''));f.writeframes(b'\0\0'*240)
  seen=[]
  def handler(r):
   seen.append(r)
   return httpx.Response(200,json={'steps':[{'type':'model_output','content':[{'type':'audio','data':base64.b64encode(buffer.getvalue()).decode()}]}]})
  with patch.dict(os.environ,{'GEMINI_API_KEY':'test-private-key','GEMINI_SPEECH_FREE_TIER':'1'}):
   async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
    for code in m.NAMES:
     if code not in m.GNANI:self.assertTrue(await m.synthesize('Test',m.canonical(code),client=client))
  self.assertEqual(len(seen),len(m.NAMES)-len(m.GNANI))
  self.assertNotIn('test-private-key',str(seen[0].url))
 async def test_quota_and_opt_in(self):
  with patch.dict(os.environ,{'GEMINI_API_KEY':'test-private-key','GEMINI_SPEECH_FREE_TIER':'0'}):
   with self.assertRaises(m.SpeechError):await m.synthesize('Bonjour','fr-FR')
  with patch.dict(os.environ,{'GEMINI_API_KEY':'test-private-key','GEMINI_SPEECH_FREE_TIER':'1'}):
   async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(429,json={'secret':'must not leak'}))) as client:
    with self.assertRaisesRegex(m.SpeechError,'HTTP 429: free quota'):await m.synthesize('Bonjour','fr-FR',client=client)
 async def test_stt(self):
  with patch.dict(os.environ,{'GROQ_API_KEY':'private'}):
   async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'text':'Bonjour','language':'french'}))) as client:
    self.assertEqual(await m.transcribe(b'audio',client=client),('Bonjour','fr-FR'))
if __name__=='__main__':unittest.main()
