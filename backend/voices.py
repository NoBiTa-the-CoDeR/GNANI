"""Gnani's documented catalogs; preferences are backend-only .env entries."""
import os,re
from pathlib import Path
from dotenv import set_key
V25={'en-IN':'Kaveri Trupti Devika Pranav Shlok Girish'.split(),'hi-IN':'Nalini Bhavna Yashvi Urmila Jwala Chitra Ambuja Deepak Roopesh Vikrant Hemraj Jalaj Omkar'.split(),'kn-IN':['Saanvi','Kavin'],'hi-en':['Poorvi']}
V3='Shivani Lakshmi Kalpana Chetana Vasudha Riyaa Tarika Avinash Shubham Prakash Devansh Yashraj Harshad'.split()
SAMPLES={'en':['Hello, I am here with you.','Please take your time, I am listening.','Walk for 150 m, then turn left.','Your tea costs ₹25 and takes 5 min.','We can visit Electronic City and Namma Metro.'],'hi':['नमस्ते, मैं आपके साथ हूँ।','आराम से बताइए, मैं सुन रही हूँ।','150 m चलिए, फिर बाएँ मुड़िए।','आपकी चाय ₹25 की है और 5 min लगेंगे।','हम Electronic City और Namma Metro जा सकते हैं।'],'kn':['ನಮಸ್ಕಾರ, ನಾನು ನಿಮ್ಮ ಜೊತೆಯಲ್ಲಿದ್ದೇನೆ.','ನಿಧಾನವಾಗಿ ಹೇಳಿ, ನಾನು ಕೇಳುತ್ತಿದ್ದೇನೆ.','150 m ನಡೆಯಿರಿ, ನಂತರ ಎಡಕ್ಕೆ ತಿರುಗಿ.','ನಿಮ್ಮ ಚಹಾಕ್ಕೆ ₹25 ಮತ್ತು 5 min ಬೇಕು.','ನಾವು Electronic City ಮತ್ತು Namma Metro ನೋಡಬಹುದು.']}
def choices(model,lang):return V3 if model=='timbre-v3.0' else V25.get(lang,[])
def settings(lang,voice=None,speed=None,model=None):
 suffix={'en-IN':'EN','hi-IN':'HI','kn-IN':'KN','hi-en':'MIXED'}.get(lang,'EN')
 model=model or os.getenv('GNANI_TTS_MODEL_'+suffix,os.getenv('GNANI_TTS_MODEL','timbre-v2.5'))
 if model not in ('timbre-v2.5','timbre-v3.0'):raise ValueError('unsupported_tts_model')
 voice=voice or os.getenv('GNANI_TTS_VOICE_'+suffix) or (os.getenv('GNANI_TTS_VOICE_V3','Shivani') if model=='timbre-v3.0' else choices(model,lang)[0])
 speed=float(speed if speed is not None else os.getenv('GNANI_TTS_SPEED_'+suffix,os.getenv('GNANI_TTS_SPEED','.93')))
 if voice not in choices(model,lang) or not .85<=speed<=1.15:raise ValueError('invalid_voice_or_speed')
 return model,voice,speed

def save(lang,voice,speed,model):
 model,voice,speed=settings(lang,voice,speed,model);suffix={'en-IN':'EN','hi-IN':'HI','kn-IN':'KN','hi-en':'MIXED'}[lang]
 path=Path(__file__).resolve().parent.parent/'.env'
 # Save only allowlisted values; never return or log the file contents.
 for key,value in [('GNANI_TTS_MODEL_'+suffix,model),('GNANI_TTS_VOICE_'+suffix,voice),('GNANI_TTS_SPEED_'+suffix,str(speed))]:
  set_key(str(path),key,value);os.environ[key]=value
 path.chmod(0o600)


def male(lang):
 suffix={'en-IN':'EN','hi-IN':'HI','kn-IN':'KN','hi-en':'MIXED'}.get(lang,'EN')
 model,normal,_=settings(lang)
 defaults={'en-IN':'Pranav','hi-IN':'Deepak','kn-IN':'Kavin'}
 fallback='Avinash' if model=='timbre-v3.0' else defaults.get(lang)
 choice=os.getenv('GNANI_TTS_VOICE_MALE_'+suffix,os.getenv('GNANI_TTS_VOICE_MALE',fallback or normal))
 return choice if choice in choices(model,lang) else normal
