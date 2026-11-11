"""Privacy-preserving navigation traces: never log arguments or provider bodies."""
import logging
import os
import contextvars
import uuid
from pathlib import Path
import httpx

logger=logging.getLogger('gnani.tools')
turn_id=contextvars.ContextVar('gnani_turn_id',default='none')

def begin_turn():
    value=uuid.uuid4().hex[:10]
    turn_id.set(value)
    return value
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler=logging.FileHandler(Path(__file__).resolve().parent/'tools.log',encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    logger.addHandler(handler)

def event(tool,result,detail=''):
    # Only programmer-supplied enum labels are permitted, never user/provider text.
    if os.getenv('GNANI_TESTING')=='1':return
    safe=''.join(c for c in str(detail) if c.isalnum() or c in '_-.')[:48]
    logger.info('turn=%s tool=%s result=%s%s',turn_id.get(),tool,result,' detail='+safe if safe else '')

def failure(tool,exc):
    if isinstance(exc,httpx.HTTPStatusError): detail='http_'+str(exc.response.status_code)
    elif isinstance(exc,httpx.TimeoutException): detail='timeout'
    elif isinstance(exc,httpx.RequestError):
        message=str(exc).lower()
        if 'handshake failure' in message: detail='tls_handshake_failure'
        elif 'certificate verify failed' in message: detail='tls_certificate_verification_failed'
        else: detail='network_error'
    else: detail=type(exc).__name__
    event(tool,'error',detail)
