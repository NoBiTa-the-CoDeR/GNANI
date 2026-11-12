"""Language choices and short, localized service messages."""
import re

def detect(text, stt_language=None):
    """Use script and common code-mixing cues, with STT as a fallback hint."""
    if re.search(r'[\u0c80-\u0cff]', text):
        return 'kn-IN'
    devanagari=bool(re.search(r'[\u0900-\u0963\u0966-\u097f]', text))
    latin=bool(re.search(r'[A-Za-z]', text))
    if devanagari:
        return 'hi-en' if latin else 'hi-IN'
    words=set(re.findall(r'[a-z]+',text.lower()))
    hindi={'aap','aapko','mujhe','mera','meri','kaise','kaisa','hai','hain','hoon','ho','kya','chahiye','jaana','jana','accha','achha','bahut','namaste'}
    english={'hello','hi','how','are','you','the','what','is','and','please','weather','today','coffee','like','my','can','help'}
    kannada={'hegiddira','hegide','namaskara','beku','maadi','helಿ','hel kodi','hogi'}
    if words & kannada:
        return 'kn-IN'
    hindi.update({'batao','bataiye','banate','banao','karo','kijiye','gaana','suno','dikhaiye','dikhao','mujhko'})
    if words & hindi:
        return 'hi-en' if words & english else 'hi-IN'
    if latin:
        return 'en-IN'
    return stt_language if stt_language in ('hi-IN','en-IN','kn-IN','hi-en') else 'en-IN'

def matches(text, lang):
    """Reject obvious wrong-script replies; this is not a language fluency classifier."""
    if not text or not re.search(r'[A-Za-z\u0900-\u097f\u0c80-\u0cff]',text):
        return False
    if lang=='kn-IN': return bool(re.search(r'[\u0c80-\u0cff]',text))
    if lang=='hi-en': return bool(re.search(r'[\u0900-\u097f]',text))
    if lang=='hi-IN': return bool(re.search(r'[\u0900-\u097f]',text))
    return not bool(re.search(r'[\u0900-\u097f\u0c80-\u0cff]',text))

def retry_message(lang):
    return {'en-IN': 'Sorry, I could not reply in your language. Please try again.', 'hi-IN': 'माफ़ कीजिए, मैं आपकी भाषा में जवाब नहीं दे पाई। कृपया फिर पूछें।', 'hi-en': 'माफ़ कीजिए, मैं आपकी language में जवाब नहीं दे पाई। Please फिर पूछें।', 'kn-IN': 'ಕ್ಷಮಿಸಿ, ನಿಮ್ಮ ಭಾಷೆಯಲ್ಲಿ ಉತ್ತರಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಕೇಳಿ.'}.get(lang, 'Please try again.')

def provider_error(reason, lang):
    messages = {
        'en-IN': {'rate_limit': 'The assistant service has reached its request limit. Please try again later.', 'timeout': 'The assistant service took too long to respond. Please try again.', 'authentication': 'The assistant service rejected its access credentials. Please ask someone to check the setup.', 'network': "I can't reach my assistant service. Please check the internet and try again.", 'not_configured': 'My assistant service needs setup. Please ask someone to help.', 'invalid_response': "The assistant service returned a reply I couldn't read. Please try again.", 'partial_response': 'My reply was interrupted. Please try again.', 'provider_error': 'The assistant service returned an error. Please try again.'},
        'hi-IN': {'rate_limit': 'सहायक सेवा की अनुरोध सीमा पूरी हो गई है। कृपया थोड़ी देर बाद फिर पूछें।', 'timeout': 'सहायक सेवा से जवाब आने में बहुत देर हुई। कृपया फिर पूछें।', 'authentication': 'सहायक सेवा की अनुमति जाँचनी है। कृपया किसी अपने से मदद लें।', 'network': 'इंटरनेट से जुड़ नहीं पा रही हूँ। कृपया कनेक्शन जाँचें।', 'not_configured': 'मुझे शुरू करने के लिए सेटिंग में मदद चाहिए।', 'invalid_response': 'सहायक सेवा का जवाब पढ़ नहीं पाई। कृपया फिर पूछें।', 'partial_response': 'मेरा जवाब बीच में रुक गया। कृपया फिर पूछें।', 'provider_error': 'सहायक सेवा में त्रुटि आई है। कृपया फिर पूछें।'},
        'kn-IN': {'rate_limit': 'ಸಹಾಯಕ ಸೇವೆಯ ವಿನಂತಿ ಮಿತಿ ಮುಗಿದಿದೆ. ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಹೊತ್ತಿನ ನಂತರ ಕೇಳಿ.', 'timeout': 'ಸಹಾಯಕ ಸೇವೆಯಿಂದ ಉತ್ತರ ಬರಲು ತುಂಬಾ ಸಮಯವಾಯಿತು. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.', 'authentication': 'ಸೇವೆಯ ಅನುಮತಿ ಪರಿಶೀಲಿಸಬೇಕು. ದಯವಿಟ್ಟು ಮನೆಯವರ ಸಹಾಯ ಕೇಳಿ.', 'network': 'ಇಂಟರ್ನೆಟ್ ಸಂಪರ್ಕವಾಗುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ಸಂಪರ್ಕ ಪರಿಶೀಲಿಸಿ.', 'not_configured': 'ಸೇವೆ ಪ್ರಾರಂಭಿಸಲು ಸೆಟ್ಟಿಂಗ್ ಸಹಾಯ ಬೇಕಿದೆ.', 'invalid_response': 'ಸೇವೆಯ ಉತ್ತರ ಓದಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಕೇಳಿ.', 'partial_response': 'ನನ್ನ ಉತ್ತರ ಮಧ್ಯದಲ್ಲಿ ನಿಂತಿತು. ದಯವಿಟ್ಟು ಮತ್ತೆ ಕೇಳಿ.', 'provider_error': 'ಸಹಾಯಕ ಸೇವೆಯಲ್ಲಿ ದೋಷ ಉಂಟಾಗಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಕೇಳಿ.'},
        'hi-en': {'rate_limit': 'Assistant service की request limit पूरी हो गई है। Please थोड़ी देर बाद पूछिए।', 'timeout': 'Assistant service से जवाब आने में बहुत time लगा। Please फिर पूछिए।', 'authentication': 'Assistant service की access settings जाँचनी हैं। Please किसी अपने से मदद लें।', 'network': 'Internet से जुड़ नहीं पा रही हूँ। Please connection जाँचें।', 'not_configured': 'मुझे शुरू करने के लिए setup में मदद चाहिए।', 'invalid_response': 'Assistant service का जवाब पढ़ नहीं पाई। Please फिर पूछिए।', 'partial_response': 'मेरा जवाब बीच में रुक गया। Please फिर पूछिए।', 'provider_error': 'Assistant service में error आया है। Please फिर पूछिए।'},
    }
    selected = messages.get(lang, messages['hi-IN'])
    return selected.get(reason, selected['provider_error'])
