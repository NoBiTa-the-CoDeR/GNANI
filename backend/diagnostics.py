"""Check configured services with real requests. Never prints provider response bodies."""
import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / '.env')
GNANI = os.getenv('GNANI_API_BASE_URL', 'https://api.vachana.ai').rstrip('/')
OPENROUTER = os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1').rstrip('/')
KEY = os.getenv('GNANI_API_KEY', '').strip()
ORKEY = os.getenv('OPENROUTER_API_KEY', '').strip()


def sse_audio(body):
    chunks, event, completed = [], '', False
    for line in body.splitlines():
        if line.startswith('event:'):
            event = line[6:].strip()
        elif line.startswith('data:'):
            data = json.loads(line[5:].strip())
            if event == 'error' or data.get('type') == 'error':
                raise ValueError('TTS stream returned an error')
            if data.get('audio'):
                chunks.append(base64.b64decode(data['audio'], validate=True))
            if event == 'complete' or data.get('is_final') is True:
                completed = True
    audio = b''.join(chunks)
    if not completed or len(audio) <= 44 or not audio.startswith(b'RIFF') or audio[8:12] != b'WAVE':
        raise ValueError('TTS did not return complete WAV audio')
    return audio


def failure(exc):
    if isinstance(exc, httpx.HTTPStatusError):
        return ('FAIL', str(exc.response.status_code), 'service rejected request')
    if isinstance(exc, httpx.TimeoutException):
        return ('FAIL', 'none', 'request timed out')
    if isinstance(exc, httpx.RequestError):
        return ('FAIL', 'none', 'network error')
    return ('FAIL', 'none', 'invalid service response')


async def check_tts(client):
    if not KEY:
        return ('FAIL', 'none', 'GNANI_API_KEY missing'), None
    status = 'none'
    try:
        r = await client.post(GNANI + '/api/v1/tts/sse', headers={'X-API-Key-ID': KEY}, json={
            'text': 'नमस्ते, मुझे घर जाना है।', 'language': 'hi-IN',
            'model': os.getenv('GNANI_TTS_MODEL', 'timbre-v2.5'),
            'voice': os.getenv('GNANI_TTS_VOICE', 'Nalini'),
            'audio_config': {'encoding': 'linear_pcm', 'container': 'wav', 'num_channels': 1, 'sample_rate': 48000, 'sample_width': 2}})
        status = str(r.status_code)
        r.raise_for_status()
        audio = sse_audio(r.text)
        return ('OK', status, '-'), audio
    except httpx.HTTPStatusError as exc:
        return failure(exc), None
    except (ValueError, KeyError, TypeError):
        return ('FAIL', status, 'invalid or incomplete audio'), None
    except httpx.RequestError as exc:
        return failure(exc), None


async def check_stt(client, audio):
    if not KEY:
        return ('FAIL', 'none', 'GNANI_API_KEY missing')
    if audio is None:
        return ('FAIL', 'none', 'no test audio; TTS failed')
    status = 'none'
    try:
        r = await client.post(GNANI + '/stt/v3', headers={'X-API-Key-ID': KEY},
            files={'audio_file': ('speech.wav', audio, 'audio/wav')},
            data={'model': os.getenv('GNANI_STT_MODEL', 'prisma-v3.0'), 'language_code': 'indic-auto', 'format': 'codemix'})
        status = str(r.status_code)
        r.raise_for_status()
        body = r.json()
        if body.get('success') is not True or not isinstance(body.get('transcript'), str) or not body['transcript'].strip():
            return ('FAIL', status, 'empty or invalid transcript')
        return ('OK', status, '-')
    except httpx.HTTPStatusError as exc:
        return failure(exc)
    except (ValueError, KeyError, TypeError):
        return ('FAIL', status, 'invalid service response')
    except httpx.RequestError as exc:
        return failure(exc)


async def check_openrouter(client):
    if not ORKEY:
        return ('FAIL', 'none', 'OPENROUTER_API_KEY missing')
    status = 'none'
    try:
        r = await client.post(OPENROUTER + '/chat/completions', headers={'Authorization': 'Bearer ' + ORKEY}, json={
            'model': os.getenv('OPENROUTER_MODEL', 'openrouter/free'),
            'messages': [{'role': 'system', 'content': 'Return only a JSON object with a short reply field.'},
                         {'role': 'user', 'content': 'Say hello.'}],
            'temperature': 0.1, 'response_format': {'type': 'json_object'}})
        status = str(r.status_code)
        r.raise_for_status()
        content = r.json()['choices'][0]['message']['content']
        if not isinstance(json.loads(content), dict):
            raise ValueError('not an object')
        return ('OK', status, '-')
    except httpx.HTTPStatusError as exc:
        return failure(exc)
    except (ValueError, KeyError, IndexError, TypeError):
        return ('FAIL', status, 'invalid JSON response')
    except httpx.RequestError as exc:
        return failure(exc)


async def check_google(client):
    key=os.getenv('GOOGLE_MAPS_API_KEY','').strip()
    if not key: return False
    try:
        r=await client.get('https://geocode.googleapis.com/v4/geocode/address/Bengaluru',headers={'X-Goog-Api-Key':key})
        return r.status_code==200 and bool(r.json().get('results'))
    except (httpx.RequestError, ValueError): return False


async def check_llm_provider(name):
    from backend.llm_providers import configured_providers,call_stream
    provider=next((p for p in configured_providers() if p.name==name),None)
    if not provider: return False
    try:
        out=await call_stream(provider,[{'role':'system','content':'Return a JSON object containing a short reply.'},{'role':'user','content':'Say hello.'}])
        return bool(out)
    except Exception: return False


async def main():
    parser = argparse.ArgumentParser(description='Run real service checks; optional WAV file tests STT independently.')
    parser.add_argument('--audio', help='Path to a short spoken WAV file')
    args = parser.parse_args()
    async with httpx.AsyncClient(timeout=45) as client:
        tts, audio = await check_tts(client)
        if args.audio:
            try:
                audio = Path(args.audio).read_bytes()
            except OSError:
                audio = None
        stt = await check_stt(client, audio)
        router = await check_openrouter(client)
        google = await check_google(client)
        llm_checks = [(name, await check_llm_provider(name)) for name in ('groq','cerebras','gemini')]
    for name, result in [('Gnani STT', stt), ('Gnani TTS', tts), ('OpenRouter', router)]:
        print(f'{name}: {result[0]} | HTTP {result[1]} | {result[2]}')
    print('Google Maps: ' + ('OK' if google else 'FAIL'))
    for name,ok in llm_checks: print(name.capitalize()+': '+('OK' if ok else 'FAIL'))
    return 0 if all(r[0] == 'OK' for r in (stt, tts, router)) and (google or not os.getenv('GOOGLE_MAPS_API_KEY','').strip()) and all(ok for name,ok in llm_checks if os.getenv(name.upper()+'_API_KEY','').strip()) else 1

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
