"""OpenAI-compatible LLM failover. Never log keys, prompts, or responses."""
import asyncio
import json
import os
from dataclasses import dataclass, field
import httpx
from backend import timing, trace

DEFAULTS={
 'groq':('https://api.groq.com/openai/v1','qwen/qwen3.8-27b'),
 'cerebras':('https://api.cerebras.ai/v1','qwen-3.8-27b'),
 'gemini':('https://generativelanguage.googleapis.com/v1beta/openai','gemini-2.5-flash-lite'),
 'openrouter':('https://openrouter.ai/api/v1','openrouter/free'),
}
@dataclass(frozen=True)
class Provider:
    name:str
    base_url:str
    model:str
    key:str=field(repr=False)


def configured_providers():
    order=os.getenv('LLM_PROVIDERS','groq,cerebras,gemini').split(',')
    names=[]
    for value in order:
        name=value.strip().lower()
        if name in DEFAULTS and name!='openrouter' and name not in names: names.append(name)
    names.append('openrouter')
    providers=[]
    for name in names:
        prefix=name.upper(); key=os.getenv(prefix+'_API_KEY','').strip()
        if not key:
            trace.event('llm_'+name,'skipped','missing_key');continue
        default_url,default_model=DEFAULTS[name]
        base=os.getenv(prefix+'_BASE_URL',default_url).strip().rstrip('/') or default_url
        model=os.getenv(prefix+'_MODEL',default_model).strip() or default_model
        providers.append(Provider(name,base,model,key))
        if name=='openrouter':
            fallback=os.getenv('OPENROUTER_FALLBACK_MODEL','').strip()
            if fallback and fallback!=model and fallback.endswith(':free'):
                providers.append(Provider('openrouter_fallback',base,fallback,key))
    return providers


def payload_for(provider,messages,plain=False):
    payload={'model':provider.model,'messages':messages,'temperature':0.1,'stream':True,'max_tokens':240}
    if not plain: payload['response_format']={'type':'json_object'}
    # Only send switches explicitly documented for the selected model family.
    if provider.name=='groq' and provider.model.startswith('qwen/qwen3'):
        payload['reasoning_effort']='none'
    elif provider.name=='cerebras' and provider.model.startswith('qwen-3'):
        payload['reasoning_effort']='none'
    elif provider.name=='gemini' and provider.model.startswith('gemini-2.5-flash'):
        payload['reasoning_effort']='none'
    elif provider.name.startswith('openrouter') and provider.model.startswith('google/gemma-'):
        payload['reasoning']={'enabled':False}
    return payload


async def call_stream(provider,messages,on_sentence=None,extract_sentence=None,deadline=3.0,client_factory=httpx.AsyncClient,plain=False):
    loop=asyncio.get_running_loop();first=loop.create_future(); chunks=[]; offered=False
    async def consume():
        nonlocal offered
        try:
            async with client_factory(timeout=45) as client:
                async with client.stream('POST',provider.base_url+'/chat/completions',headers={'Authorization':'Bearer '+provider.key},json=payload_for(provider,messages,plain)) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith('data:'): continue
                        data=line[5:].strip()
                        if data=='[DONE]': break
                        obj=json.loads(data)
                        if obj.get('error'):
                            error=obj['error'] if isinstance(obj['error'],dict) else {}
                            code=str(error.get('code','')).lower()
                            message=str(error.get('message','')).lower()
                            # Log only known provider error codes, never the response body.
                            for known in ('json_validate_failed','tool_use_failed','rate_limit_exceeded','invalid_api_key','model_decommissioned'):
                                if known in code or known in message:
                                    trace.event('llm_'+provider.name,'provider_error_code',known)
                                    break
                            reason=('rate_limit' if code=='429' or 'rate limit' in message or 'rate_limit' in code else 'authentication' if code in ('401','403') else 'provider_error')
                            raise ProviderStreamError(reason)
                        choices=obj.get('choices') or []
                        part=(choices[0].get('delta') or {}).get('content') if choices else None
                        if not isinstance(part,str) or not part: continue
                        if not first.done(): first.set_result(None)
                        timing.mark('llm_first_token'); chunks.append(part)
                        if on_sentence and extract_sentence and not offered:
                            sentence=extract_sentence(''.join(chunks))
                            if sentence: offered=(on_sentence(sentence) is not False)
            if not first.done(): first.set_exception(ProviderStreamError('empty_stream'))
            if plain:
                text=''.join(chunks).strip()
                if not text: raise ValueError('empty_text_response')
                return {'intent':'chat','reply':text}
            result=json.loads(''.join(chunks))
            if isinstance(result,list) and len(result)==1: result=result[0]
            if not isinstance(result,dict): raise ValueError('invalid_json_object')
            return result
        except BaseException as exc:
            if not first.done(): first.set_exception(exc)
            raise
    task=asyncio.create_task(consume())
    try:
        await asyncio.wait_for(asyncio.shield(first),deadline)
        return await task
    except Exception as exc:
        if not task.done(): task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        if first.done() and not first.cancelled():
            try: first.exception()
            except BaseException: pass
        # A sentence already sent for speech cannot safely be replaced with another answer.
        if offered: raise PartialSpeechError() from exc
        raise

class PartialSpeechError(Exception): pass
class ProviderStreamError(Exception):
    def __init__(self,reason):
        self.reason=reason
        super().__init__(reason)
class ProvidersUnavailable(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)

def failure_kind(exc):
    if isinstance(exc,ProviderStreamError): return exc.reason
    if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)): return 'timeout'
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429: return 'rate_limit'
        if code in (401, 403): return 'authentication'
        return 'provider_error'
    if isinstance(exc, httpx.RequestError): return 'network'
    if isinstance(exc, (ValueError, KeyError, TypeError)): return 'invalid_response'
    return 'provider_error'

async def complete(messages,on_sentence=None,extract_sentence=None,providers=None,deadline=3.0,client_factory=httpx.AsyncClient,validator=None,plain=False):
    timing.mark('llm_start')
    candidates=configured_providers() if providers is None else providers
    if not candidates:
        trace.event('llm_all','error','not_configured')
        raise ProvidersUnavailable('not_configured')
    failures=[]
    for provider in candidates:
        trace.event('llm_'+provider.name,'start')
        try:
            result=await call_stream(provider,messages,on_sentence,extract_sentence,deadline,client_factory,plain)
            if validator:
                validator(result)
            trace.event('llm_'+provider.name,'ok');timing.mark('llm_complete')
            return result
        except PartialSpeechError as exc:
            trace.event('llm_'+provider.name,'error','partial_response')
            raise ProvidersUnavailable('partial_response') from exc
        except Exception as exc:
            reason=failure_kind(exc); failures.append(reason)
            trace.failure('llm_'+provider.name,exc)
            trace.event('llm_'+provider.name,'failure_kind',reason)
    # Report the primary provider's actual failure when fallbacks also fail.
    reason=failures[0]
    trace.event('llm_all','error',reason)
    raise ProvidersUnavailable(reason)
