"""Deterministic spoken text. No model calls and no SSML interpolation."""
import json,re,unicodedata
from pathlib import Path
LEXICON=json.loads(Path(__file__).with_name('pronunciation.json').read_text())
HI='शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उनासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सतासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पंचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे'.split()
KN='ಸೊನ್ನೆ ಒಂದು ಎರಡು ಮೂರು ನಾಲ್ಕು ಐದು ಆರು ಏಳು ಎಂಟು ಒಂಬತ್ತು ಹತ್ತು ಹನ್ನೊಂದು ಹನ್ನೆರಡು ಹದಿಮೂರು ಹದಿನಾಲ್ಕು ಹದಿನೈದು ಹದಿನಾರು ಹದಿನೇಳು ಹದಿನೆಂಟು ಹತ್ತೊಂಬತ್ತು ಇಪ್ಪತ್ತು ಇಪ್ಪತ್ತೊಂದು ಇಪ್ಪತ್ತೆರಡು ಇಪ್ಪತ್ತಮೂರು ಇಪ್ಪತ್ತನಾಲ್ಕು ಇಪ್ಪತ್ತೈದು ಇಪ್ಪತ್ತಾರು ಇಪ್ಪತ್ತೇಳು ಇಪ್ಪತ್ತೆಂಟು ಇಪ್ಪತ್ತೊಂಬತ್ತು ಮೂವತ್ತು ಮೂವತ್ತೊಂದು ಮೂವತ್ತೆರಡು ಮೂವತ್ತಮೂರು ಮೂವತ್ತನಾಲ್ಕು ಮೂವತ್ತೈದು ಮೂವತ್ತಾರು ಮೂವತ್ತೇಳು ಮೂವತ್ತೆಂಟು ಮೂವತ್ತೊಂಬತ್ತು ನಲವತ್ತು ನಲವತ್ತೊಂದು ನಲವತ್ತೆರಡು ನಲವತ್ತಮೂರು ನಲವತ್ತನಾಲ್ಕು ನಲವತ್ತೈದು ನಲವತ್ತಾರು ನಲವತ್ತೇಳು ನಲವತ್ತೆಂಟು ನಲವತ್ತೊಂಬತ್ತು ಐವತ್ತು ಐವತ್ತೊಂದು ಐವತ್ತೆರಡು ಐವತ್ತಮೂರು ಐವತ್ತನಾಲ್ಕು ಐವತ್ತೈದು ಐವತ್ತಾರು ಐವತ್ತೇಳು ಐವತ್ತೆಂಟು ಐವತ್ತೊಂಬತ್ತು ಅರವತ್ತು ಅರವತ್ತೊಂದು ಅರವತ್ತೆರಡು ಅರವತ್ತಮೂರು ಅರವತ್ತನಾಲ್ಕು ಅರವತ್ತೈದು ಅರವತ್ತಾರು ಅರವತ್ತೇಳು ಅರವತ್ತೆಂಟು ಅರವತ್ತೊಂಬತ್ತು ಎಪ್ಪತ್ತು ಎಪ್ಪತ್ತೊಂದು ಎಪ್ಪತ್ತೆರಡು ಎಪ್ಪತ್ತಮೂರು ಎಪ್ಪತ್ತನಾಲ್ಕು ಎಪ್ಪತ್ತೈದು ಎಪ್ಪತ್ತಾರು ಎಪ್ಪತ್ತೇಳು ಎಪ್ಪತ್ತೆಂಟು ಎಪ್ಪತ್ತೊಂಬತ್ತು ಎಂಭತ್ತು ಎಂಭತ್ತೊಂದು ಎಂಭತ್ತೆರಡು ಎಂಭತ್ತಮೂರು ಎಂಭತ್ತನಾಲ್ಕು ಎಂಭತ್ತೈದು ಎಂಭತ್ತಾರು ಎಂಭತ್ತೇಳು ಎಂಭತ್ತೆಂಟು ಎಂಭತ್ತೊಂಬತ್ತು ತೊಂಬತ್ತು ತೊಂಬತ್ತೊಂದು ತೊಂಬತ್ತೆರಡು ತೊಂಬತ್ತಮೂರು ತೊಂಬತ್ತನಾಲ್ಕು ತೊಂಬತ್ತೈದು ತೊಂಬತ್ತಾರು ತೊಂಬತ್ತೇಳು ತೊಂಬತ್ತೆಂಟು ತೊಂಬತ್ತೊಂಬತ್ತು'.split()
EN='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split();TENS='zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split()
WORDS={'hi':{'hundred':'सौ','thousand':'हज़ार','lakh':'लाख','crore':'करोड़','point':'दशमलव','minus':'ऋण','m':'मीटर','km':'किलोमीटर','min':'मिनट','hr':'घंटे','₹':'रुपये','$':'डॉलर','time':'बजकर','am':'सुबह','pm':'शाम'},'kn':{'hundred':'ನೂರು','thousand':'ಸಾವಿರ','lakh':'ಲಕ್ಷ','crore':'ಕೋಟಿ','point':'ದಶಮಾಂಶ','minus':'ಋಣ','m':'ಮೀಟರ್','km':'ಕಿಲೋಮೀಟರ್','min':'ನಿಮಿಷ','hr':'ಗಂಟೆ','₹':'ರೂಪಾಯಿ','$':'ಡಾಲರ್','time':'ಗಂಟೆ','am':'ಬೆಳಿಗ್ಗೆ','pm':'ಸಂಜೆ'},'en':{'hundred':'hundred','thousand':'thousand','lakh':'lakh','crore':'crore','point':'point','minus':'minus','m':'metres','km':'kilometres','min':'minutes','hr':'hours','₹':'rupees','$':'dollars','time':'','am':'a m','pm':'p m'}}
def locale(lang):return 'hi' if lang.startswith('hi') else 'kn' if lang.startswith('kn') else 'en'
def integer(n,lang):
 w=WORDS[lang]
 if n<0:return w['minus']+' '+integer(-n,lang)
 if n<100:
  if lang=='hi':return HI[n]
  if lang=='kn':return KN[n]
  return EN[n] if n<20 else TENS[n//10]+(' '+EN[n%10] if n%10 else '')
 for size,name in [(10000000,'crore'),(100000,'lakh'),(1000,'thousand'),(100,'hundred')]:
  if n>=size:return integer(n//size,lang)+' '+w[name]+(' '+integer(n%size,lang) if n%size else '')
def number(s,lang):
 s=s.replace(',','');parts=s.split('.')
 try:return integer(int(parts[0]),lang)+(' '+WORDS[lang]['point']+' '+' '.join(integer(int(c),lang) for c in parts[1]) if len(parts)>1 else '')
 except (ValueError,IndexError):return s

def normalize(text,lang='en',script='native'):
 lang=locale(lang);w=WORDS[lang];text=''.join(str(unicodedata.digit(c)) if c.isdecimal() else c for c in str(text))
 text=re.sub(r'```.*?```',' ',text,flags=re.S);text=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',text)
 text=re.sub(r'https?://\S+','',text);text=re.sub(r'(?m)^\s*(?:#{1,6}\s*|[-*•]\s+|\d+[.)]\s+)','',text)
 text=re.sub(r'<[^>]*>','',text);text=re.sub(r'[*_`#~]','',text)
 text=''.join(c for c in text if not (unicodedata.category(c) in ('So','Cs') or '\ufe00'<=c<='\ufe0f' or c=='\u200d'))
 if script!='latin':
  for name,forms in sorted(LEXICON.items(),key=lambda p:-len(p[0])):text=re.sub(r'(?i)\b'+re.escape(name)+r'\b',forms[lang],text)
 abbr={'Dr':('Doctor','डॉक्टर','ಡಾಕ್ಟರ್'),'Mr':('Mister','श्री','ಶ್ರೀ'),'Mrs':('Missus','श्रीमती','ಶ್ರೀಮತಿ'),'ATM':('A T M','ए टी एम','ಎ ಟಿ ಎಂ'),'BP':('blood pressure','रक्तचाप','ರಕ್ತದೊತ್ತಡ'),'kmph':('kilometres per hour','किलोमीटर प्रति घंटा','ಗಂಟೆಗೆ ಕಿಲೋಮೀಟರ್')}
 for key,values in abbr.items():text=re.sub(r'(?i)\b'+key+r'\b\.?',values[{'en':0,'hi':1,'kn':2}[lang]],text)
 text=re.sub(r'\b(\d{1,2}):(\d{2})\s*(am|pm)?\b',lambda m:' '.join(x for x in [number(m[1],lang),w['time'],number(m[2],lang),w['min'] if lang!='en' else '',w.get((m[3] or '').lower(),'')] if x),text,flags=re.I)
 num=r'-?\d+(?:,\d{2,3})*(?:\.\d+)?'
 text=re.sub(r'(₹|\$|INR\s*|Rs\.?\s*)('+num+')',lambda m:number(m[2],lang)+' '+w['$' if m[1]=='$' else '₹'],text,flags=re.I)
 text=re.sub(r'('+num+r')\s*(km|m|min(?:utes?)?|hrs?|hours?)\b',lambda m:number(m[1],lang)+' '+w['km' if m[2].lower()=='km' else 'm' if m[2].lower()=='m' else 'min' if m[2].lower().startswith('min') else 'hr'],text,flags=re.I)
 text=re.sub(num,lambda m:number(m[0],lang),text)
 return ' '.join(text.split()).strip()

def sentences(text,lang='en',script='native'):
 text=normalize(text,lang,script);out=[]
 for part in re.split(r'(?<=[.!?।])\s+|\n+',text):
  words=part.split()
  while words:
   take=min(20,len(words))
   if take<len(words):
    commas=[i+1 for i in range(7,take) if words[i].endswith((',', ';', ':'))]
    if commas:take=commas[-1]
   chunk=' '.join(words[:take]);words=words[take:]
   out.append(chunk.rstrip(',;:')+(',' if words else '' ))
 return out
