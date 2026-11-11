"""Rules enforced outside the model. Consent never overrides a hard block."""
import asyncio,base64,ipaddress,json,os,re,socket,time
from urllib.parse import urlsplit,urlunsplit,parse_qs
from pathlib import Path
BLOCK=re.compile(r'(?i)password|passcode|verification.?code|security.?code|auth(?:entication)?.?code|access.?code|one.?time.?code|api.?key|secret.?key|access.?token|card.?holder|\bpin\b|\biban\b|\bifsc\b|\bswift\b|\botp\b|one[ -]?time[ -]?(?:code|password)|aadhaa?r|aadhar|credit.?card|debit.?card|card.?number|cvv|cvc|upi|bank.?account|account.?number|routing.?number|social.?security|पासवर्ड|ओटीपी|आधार|ಪಾಸ್.?ವರ್ಡ್|ಒಟಿಪಿ|ಆಧಾರ್')
PAY=re.compile(r'(?i)(?:^|[/_?&= -])(?:checkout|payment|payments|pay|purchase|buy|paynow|pay-now|wallet|banking|transfer|buy-now|place-order)(?:$|[/_?&= -])')
LOGIN=re.compile(r'(?i)\blog[ -]?in\b|\bsign[ -]?in\b|\bbook(?:ing)?\b|\breserv(?:e|ation)\b')
class Blocked(Exception):pass

def secret_values():return [v for k,v in os.environ.items() if k.upper().endswith(('_KEY','_TOKEN','_CLIENT_ID')) and v and len(v)>=6]
def scrub(value,maximum=16000):
 text=str(value)
 for value in secret_values():text=text.replace(value,'[private value hidden]')
 text=re.sub(r'(?i)(?:gsk_|sk-or-v1-|AIza|AQ\.)[A-Za-z0-9_-]{10,}','[private value hidden]',text)
 text=re.sub(r'(?<!\d)(?:\d[ -]?){12,19}(?!\d)','[private number hidden]',text)
 text=re.sub(r'(?i)((?:password|otp|passcode|one.time.code)\s*[:=]\s*)\S+',r'\1[hidden]',text)
 return text[:maximum]
def sensitive(text):return bool(BLOCK.search(text) or re.search(r'(?<!\d)(?:\d[ -]?){4,}(?!\d)',text) or any(v in text for v in secret_values()) or re.search(r'(?:gsk_|sk-or-v1-|AIza|AQ\.)[A-Za-z0-9_-]{10,}',text))
def clean_url(url):
 if not isinstance(url,str) or len(url)>1800:raise Blocked('Please use a shorter public website address.')
 try:p=urlsplit(url);port=p.port
 except ValueError:raise Blocked('That website address is invalid.')
 if p.scheme!='https' or not p.hostname or p.username or p.password or port not in (None,443):raise Blocked('Only public HTTPS websites are allowed.')
 host=p.hostname.encode('idna').decode('ascii').lower()
 if host=='localhost' or '.' not in host or host.endswith(('.local','.localhost','.internal','.lan')):raise Blocked('Private and local network addresses are blocked.')
 try:ipaddress.ip_address(host)
 except ValueError:pass
 else:raise Blocked('Direct IP addresses are blocked. Please use a public website name.')
 if BLOCK.search(url) or any(k.lower() in ('key','token','code','secret','auth','password','otp','access_token','api_key') for k in parse_qs(p.query)) or any(v in url for v in secret_values()):raise Blocked('Private credentials and sensitive addresses are blocked.')
 if any(sensitive(v) for values in parse_qs(p.query).values() for v in values):raise Blocked('Private credentials and codes cannot be submitted in a website address.')
 if PAY.search(p.path+'?'+p.query):raise Blocked('Payments and checkout flows are blocked.')
 if re.search(r'(?i)\.(?:exe|dmg|zip|pdf|apk|msi|csv|docx?|xlsx?|mp3|mp4)(?:$|\?)',p.path):raise Blocked('Downloads are blocked. I can read public web pages instead.')
 return urlunsplit(('https',host,p.path or '/',p.query,''))
async def public_ips(host):
 try:items=await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host,443,type=socket.SOCK_STREAM),5)
 except (OSError,asyncio.TimeoutError):raise Blocked('The website address could not be resolved.')
 ips=list(dict.fromkeys(x[4][0] for x in items))
 if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):raise Blocked('Private or reserved network addresses are blocked.')
 return ips

def action_json(value,count):
 if isinstance(value,str):
  value=re.sub(r'^```(?:json)?\s*|\s*```$','',value.strip());value=json.loads(value)
 if not isinstance(value,dict):raise Blocked('The model returned an invalid action.')
 kind=value.get('action')
 if kind not in ('click','type','scroll','goto','done','ask_user'):raise Blocked('The model returned an unsupported action.')
 out={'action':kind}
 if kind in ('click','type'):
  i=value.get('i')
  if not isinstance(i,int) or isinstance(i,bool) or not 1<=i<=count:raise Blocked('The model chose an element that is no longer available.')
  out['i']=i
 if kind=='type':
  text=value.get('text')
  if not isinstance(text,str) or not 1<=len(text)<=300 or sensitive(text):raise Blocked('Passwords, codes, account details and private numbers cannot be typed.')
  out['text']=text
 if kind=='goto':out['url']=clean_url(value.get('url'))
 if kind=='scroll':
  direction=value.get('direction','down')
  if direction not in ('up','down'):raise Blocked('The model returned an invalid scroll direction.')
  out['direction']=direction
 if kind in ('done','ask_user'):out['text']=scrub(value.get('text',''),1500)
 if kind=='ask_user' and BLOCK.search(out['text']):raise Blocked('The web helper cannot ask for private credentials.')
 if kind=='done':out['evidence']=scrub(value.get('evidence',''),1800)
 return out

class PublicProxy:
 """HTTPS CONNECT only. Resolve, reject private IPs, then connect that IP.
 Pinning the resolved IP prevents a second DNS lookup/rebinding by Chromium.
 """
 def __init__(self,approved):self.approved=approved;self.server=None;self.connections=set();self.tasks=set();self.token=os.urandom(24).hex()
 async def start(self):
  self.server=await asyncio.start_server(self.handle,'127.0.0.1',0,limit=16384);port=self.server.sockets[0].getsockname()[1]
  return {'server':f'http://127.0.0.1:{port}','username':'gnani','password':self.token}
 async def handle(self,reader,writer):
  task=asyncio.current_task();self.tasks.add(task);up=None;self.connections.add(writer)
  try:
   header=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),5)
   lines=header.decode('latin1').split('\r\n');method,target,_=lines[0].split(' ',2);headers={x.split(':',1)[0].lower():x.split(':',1)[1].strip() for x in lines[1:] if ':' in x}
   auth='Basic '+base64.b64encode(('gnani:'+self.token).encode()).decode()
   if headers.get('proxy-authorization')!=auth:
    writer.write(b'HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm="gNani"\r\nConnection: close\r\nContent-Length: 0\r\n\r\n');await writer.drain();return
   if method!='CONNECT':raise Blocked('HTTPS only')
   url=clean_url('https://'+target);host=urlsplit(url).hostname
   if host not in self.approved:raise Blocked('domain not approved')
   ips=await public_ips(host);other=None
   for ip in sorted(ips,key=lambda x:':' in x):
    try:other,up=await asyncio.wait_for(asyncio.open_connection(ip,443),4);break
    except (OSError,asyncio.TimeoutError):continue
   if up is None:raise Blocked('public connection failed')
   self.connections.add(up);writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n');await writer.drain()
   async def pipe(src,dest):
    size=0
    while True:
     chunk=await src.read(65536)
     if not chunk:break
     size+=len(chunk)
     if size>20_000_000:break
     dest.write(chunk);await dest.drain()
   a=asyncio.create_task(pipe(reader,up));b=asyncio.create_task(pipe(other,writer))
   try:await asyncio.wait([a,b],return_when=asyncio.FIRST_COMPLETED)
   finally:
    for t in (a,b):t.cancel()
    await asyncio.gather(a,b,return_exceptions=True)
  except (Exception,asyncio.CancelledError):
   try:writer.write(b'HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n');await writer.drain()
   except Exception:pass
  finally:
   for connection in (writer,up):
    if connection:connection.close();self.connections.discard(connection)
   self.tasks.discard(task)
 async def close(self):
  if self.server:self.server.close();await self.server.wait_closed()
  for writer in list(self.connections):writer.close()
  for t in list(self.tasks):t.cancel()
  if self.tasks:await asyncio.gather(*list(self.tasks),return_exceptions=True)
  self.connections.clear()
