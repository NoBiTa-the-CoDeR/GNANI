import unittest,re
from backend.tts_normalize import normalize,sentences,HI,KN
class Normalization(unittest.TestCase):
 def test_tables(self):self.assertEqual(len(HI),100);self.assertEqual(len(KN),100)
 def test_native_numbers_units_currency(self):
  self.assertIn('अस्सी मीटर',normalize('80 m and ₹150 in 20 min','hi'));self.assertIn('ಒಂದು ದಶಮಾಂಶ ಐದು ಕಿಲೋಮೀಟರ್',normalize('1.5 km','kn'));self.assertIn('ನೂರು ಐವತ್ತು ರೂಪಾಯಿ',normalize('₹150','kn'))
 def test_time_and_markdown(self):
  self.assertEqual(normalize('**Go** 🙂 at 9:30 am, Dr. Rao.','en'),'Go at nine thirty a m, Doctor Rao.')
  self.assertIn('नौ बजकर तीस मिनट सुबह',normalize('9:30 am','hi'))
 def test_lexicon_and_chunking(self):
  self.assertIn('इलेक्ट्रॉनिक सिटी',normalize('Electronic City 300 m','hi'));self.assertTrue(all(len(s.split())<=20 for s in sentences('word '*65)));self.assertNotRegex(normalize('२० मिनट ೩೦ m','kn'),r'\d')
