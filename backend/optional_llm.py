"""Serialize optional requests per provider to avoid overlapping free calls."""
import asyncio
_locks={}
async def post(provider,client,*args,**kwargs):
 loop=asyncio.get_running_loop();key=(loop,provider)
 lock=_locks.setdefault(key,asyncio.Lock())
 async with lock:return await client.post(*args,**kwargs)
