import {useState,useRef,useEffect} from 'react';
import {isEcho} from './echoGuard';
import {locale} from './i18n';
const privacy={en:{muted:"I'm not listening",still:'Still muted',unmute:'Tap to talk again'},hi:{muted:'मैं अभी नहीं सुन रही हूँ',still:'माइक अभी बंद है',unmute:'फिर बात करने के लिए दबाइए'},kn:{muted:'ನಾನು ಈಗ ಕೇಳುತ್ತಿಲ್ಲ',still:'ಮೈಕ್ ಇನ್ನೂ ಆಫ್ ಆಗಿದೆ',unmute:'ಮತ್ತೆ ಮಾತನಾಡಲು ಒತ್ತಿ'}};
function readSession(k,fallback){try{return sessionStorage.getItem(k)??fallback}catch{return fallback}}
function wav(samples,rate){const buf=new ArrayBuffer(44+samples.length*2),v=new DataView(buf);const str=(o,s)=>[...s].forEach((c,i)=>v.setUint8(o+i,c.charCodeAt(0)));str(0,'RIFF');v.setUint32(4,36+samples.length*2,true);str(8,'WAVE');str(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,rate,true);v.setUint32(28,rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);str(36,'data');v.setUint32(40,samples.length*2,true);samples.forEach((x,i)=>v.setInt16(44+i*2,Math.max(-1,Math.min(1,x))*32767,true));return buf}
export function useVoiceSession(options){
 const [active,setActive]=useState(false),[phase,setPhase]=useState('idle'),[line,setLine]=useState(''),[raw,setRaw]=useState(''),[error,setError]=useState(''),[userSpeaking,setUserSpeaking]=useState(false),[speaking,setSpeaking]=useState(false),[capturing,setCapturing]=useState(false),[muted,setMuted]=useState(()=>readSession('gnani_muted','0')==='1'),[stillMuted,setStillMuted]=useState(false),[repliesAloud,setAloudState]=useState(()=>readSession('gnani_replies_aloud','1')!=='0'),[reply,setReply]=useState(null);
 const opts=useRef(options);opts.current=options;
 const mutedRef=useRef(muted),aloudRef=useRef(repliesAloud),running=useRef(false),awaiting=useRef(false),userSpeech=useRef(false),socket=useRef(null),connecting=useRef(null),stream=useRef(null),ctx=useRef(null),processor=useRef(null),source=useRef(null),eraseCapture=useRef(()=>{}),queue=useRef([]),player=useRef(null),playing=useRef(false),latest=useRef([]),generation=useRef(0),audioCache=useRef(new Map()),guidanceEpoch=useRef(0),playingTemplate=useRef(false),currentId=useRef(null),sequence=useRef(0),requestInfo=useRef(new Map()),reference=useRef(null),referenceTime=useRef(0),lastOutputAt=useRef(0),fading=useRef(false),voiceTurn=useRef(false),playSerial=useRef(0),speechAbort=useRef(null);
 const diagnostics=useRef({level:0,vad:'idle',audioContext:'none',websocket:0,lowSince:0,lastTranscript:0,lastLog:0});
 function phaseTo(value){setPhase(value)}
 function idle(){if(!playing.current&&!awaiting.current)phaseTo(mutedRef.current?'muted':stream.current?'listening':'idle')}
 function context(){if(!ctx.current||ctx.current.state==='closed')ctx.current=new AudioContext();return ctx.current}
 function stopTalking(){speechAbort.current?.abort();playSerial.current++;queue.current=[];player.current?.pause();player.current=null;playing.current=false;setSpeaking(false);socket.current?.readyState===1&&socket.current.send(JSON.stringify({type:'stop_talking',request_id:currentId.current}));idle()}
 async function fadeOut(ms=150){
  const audio=player.current;if(!audio||fading.current)return;fading.current=true;const start=performance.now(),volume=audio.volume;
  await new Promise(resolve=>{function fade(){if(player.current!==audio){resolve();return}const amount=Math.min(1,(performance.now()-start)/ms);audio.volume=volume*(1-amount);if(amount<1)requestAnimationFrame(fade);else{audio.pause();resolve()}}fade()});fading.current=false;
 }
 async function drain(){
  if(playing.current||!running.current)return;
  queue.current.sort((a,b)=>(b.priority||0)-(a.priority||0));const item=queue.current[0];if(!item){idle();return}
  if(item.template&&(userSpeech.current||awaiting.current))return;
  queue.current.shift();if(item.requestId&&item.requestId!==currentId.current){drain();return}
  playing.current=true;playingTemplate.current=!!item.template;const serial=++playSerial.current;let url;
  try{
   const bytes=Uint8Array.from(atob(item.chunks[0]),c=>c.charCodeAt(0));const c=context();await c.resume();
   try{const decoded=await c.decodeAudioData(bytes.buffer.slice(0));reference.current=new Float32Array(decoded.getChannelData(0));referenceTime.current=0}catch{reference.current=null}
   url=URL.createObjectURL(new Blob([bytes],{type:'audio/wav'}));const audio=new Audio(url);player.current=audio;
   await new Promise(resolve=>{
    audio.onplaying=()=>{setLine(item.text);setSpeaking(true);phaseTo('speaking');lastOutputAt.current=performance.now();opts.current.onAssistantSpeech?.();
     const info=requestInfo.current.get(item.requestId);if(info?.eos&&!info.played){info.played=true;const elapsed=Math.round(performance.now()-info.eos);console.info('[gNani timing] playback_start',{request_id:item.requestId,end_to_first_audio_ms:elapsed});send('playback',{request_id:item.requestId,elapsed_eos_ms:elapsed})}
     try{const src=c.createMediaElementSource(audio),analyser=c.createAnalyser();analyser.fftSize=128;src.connect(analyser);analyser.connect(c.destination);opts.current.onAnalyser?.(analyser,audio)}catch{}
    };
    audio.ontimeupdate=()=>{referenceTime.current=audio.currentTime;lastOutputAt.current=performance.now()};
    audio.onended=audio.onpause=resolve;
    audio.onerror=()=>{setError('The voice could not play. Please tap Listen.');resolve()};audio.play().catch(()=>{setError('Please tap Listen to hear the reply.');resolve()});
   });
  }catch{setError('The voice could not play. Please try again.')}finally{if(url)URL.revokeObjectURL(url);lastOutputAt.current=performance.now();if(serial===playSerial.current){player.current=null;setSpeaking(false);if(item.pauseMs)await new Promise(r=>setTimeout(r,item.pauseMs));if(serial===playSerial.current){playing.current=false;drain()}}}
 }
 function send(type,value={}){if(socket.current?.readyState===1)socket.current.send(JSON.stringify({type,...value}))}
 async function connect(){
  if(socket.current?.readyState===1)return;
  if(connecting.current)return connecting.current;
  running.current=true;
  connecting.current=new Promise((resolve,reject)=>{
   const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/session`);socket.current=ws;let opened=false;const timeout=setTimeout(()=>{if(!opened){reject(new Error('Connection timed out'));ws.close()}},8000);
   ws.onopen=()=>{opened=true;clearTimeout(timeout);setActive(true);send('web_preference',opts.current.webPreferenceRef?.current||{enabled:false});send('mic_state',{enabled:!!stream.current&&!mutedRef.current});resolve()};
   ws.onerror=()=>{clearTimeout(timeout);setError('The voice service could not connect. Please try again.');reject(new Error('Connection unavailable'))};
   ws.onclose=()=>{clearTimeout(timeout);if(!opened)reject(new Error('Connection closed before opening'));connecting.current=null;if(running.current){setError('Connection lost. Please try again.');phaseTo(mutedRef.current?'muted':'idle')}};
   ws.onmessage=e=>{
    const m=JSON.parse(e.data);if(m.request_id&&m.request_id!==currentId.current)return;
    if(m.type==='transcript'){setRaw(m.text);console.info('[gNani STT]',{characters:m.text.length,language:m.language});diagnostics.current.lastTranscript=performance.now();diagnostics.current.lowSince=0;setError('')}
    if(m.type==='stt_empty'){setError(m.text);console.info('[gNani debug] STT empty')}
    if(m.type==='theme'){document.documentElement.dataset.theme=['default','cooking','music','travel','health','devotional','story','learning'].includes(m.theme)?m.theme:'default';opts.current.onTheme?.(m.theme)}
    if(m.type==='reply'){setReply({text:m.text,language:m.language,typed:!m.aloud,segments:m.segments});if(!m.aloud)setLine(m.text)}
    if(m.type==='audio_sentence'){const item={text:m.text,chunks:m.chunks,priority:80,requestId:m.request_id,pauseMs:m.pause_ms??200};latest.current.push(item);queue.current.push(item);drain()}
    if(m.type==='text_only')setLine(m.text);
    if(m.type==='tool_error'||m.type==='error')setError(m.text);
    if(m.type==='audio_unavailable')setError('gNani’s voice is unavailable. Please try Listen again.');
    if(m.type==='response_end'||m.type==='turn_cancelled'||m.type==='error'||m.type==='stt_empty'){awaiting.current=false;drain()}
    if(m.type==='timing')console.info('[gNani timing]',m.events);
    opts.current.onEvent?.(m);
   };
  }).finally(()=>connecting.current=null);
  return connecting.current;
 }
 function releaseMic(){diagnostics.current.lowSince=0;diagnostics.current.lowNotice=false;eraseCapture.current();processor.current?.disconnect();source.current?.disconnect();processor.current=null;source.current=null;stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;setCapturing(false);userSpeech.current=false;setUserSpeaking(false)}
 async function capture(){
  if(stream.current||mutedRef.current)return;
  const media=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
  if(mutedRef.current){media.getTracks().forEach(x=>x.stop());return}
  stream.current=media;setCapturing(true);const c=context();await c.resume();source.current=c.createMediaStreamSource(media);const node=c.createScriptProcessor(4096,1,1);processor.current=node;
  let frames=[],pre=[],count=0,speech=false,silence=0,barge=0;
  function clear(){frames=[];pre=[];count=0;speech=false;silence=0;barge=0}eraseCapture.current=clear;
  node.onaudioprocess=e=>{
   if(mutedRef.current||!stream.current||socket.current?.readyState!==1){diagnostics.current.lowSince=0;clear();return}
   const frame=new Float32Array(e.inputBuffer.getChannelData(0)),rms=Math.sqrt(frame.reduce((a,b)=>a+b*b,0)/frame.length),duration=frame.length/c.sampleRate;
   const now=performance.now(),d=diagnostics.current;
   Object.assign(d,{level:rms,vad:speech?'speech':silence?'silence':'idle',audioContext:c.state,websocket:socket.current?.readyState,secondsLow:d.lowSince?(now-d.lowSince)/1000:0});
   if(rms>.018||playing.current||awaiting.current)d.lowSince=0;
   else if(!d.lowSince)d.lowSince=now;
   // Silence is a normal listening state, not evidence of a microphone failure.
   if(now-d.lastLog>1000){d.lastLog=now;console.info('[gNani mic]',{level:Number(rms.toFixed(4)),vad:d.vad,low_ms:Math.round(d.secondsLow*1000),websocket:d.websocket,audioContext:d.audioContext})}
   const output=player.current,outputTime=output?.currentTime??referenceTime.current;
   if((playing.current||performance.now()-lastOutputAt.current<400)&&isEcho(frame,reference.current,outputTime,c.sampleRate)){if(!speech){pre=[];barge=0}return}
   if(awaiting.current&&!playing.current){clear();return}
   if(!speech){
    pre.push(frame);while(pre.length>4)pre.shift();
    if(playing.current){barge=rms>.028?barge+duration:0;if(barge<.25)return;speechAbort.current?.abort();guidanceEpoch.current++;queue.current=[];fadeOut(150);send('interrupt',{request_id:currentId.current});currentId.current=null;awaiting.current=false;}
    else if(rms<=.018)return;
    speech=true;frames=pre;count=frames.reduce((n,a)=>n+a.length,0);pre=[];userSpeech.current=true;setUserSpeaking(true);opts.current.onUserSpeech?.();
   }else{frames.push(frame);count+=frame.length;silence=rms>.018?0:silence+duration}
   if(speech&&(silence>.5||count/c.sampleRate>20)){
    const eos=performance.now()-silence*1000;console.info('[gNani timing] end_of_speech',{silence_ms:Math.round(silence*1000)});userSpeech.current=false;setUserSpeaking(false);
    const identity=String(++sequence.current);currentId.current=identity;voiceTurn.current=true;requestInfo.current.set(identity,{eos,played:false});if(requestInfo.current.size>20)requestInfo.current.delete(requestInfo.current.keys().next().value);awaiting.current=true;setRaw('');setLine('');phaseTo('thinking');latest.current=[];
    const all=new Float32Array(count);let offset=0;for(const f of frames){all.set(f,offset);offset+=f.length}
    send('location',{location:opts.current.positionRef.current||null});send('nav',{nav:opts.current.navRef.current||null});send('turn',{request_id:identity,aloud:aloudRef.current});socket.current.send(wav(all,c.sampleRate));clear();
   }
  };
  source.current.connect(node);node.connect(c.destination);send('mic_state',{enabled:true});idle();
 }
 async function start(){
  if(!window.isSecureContext){setError('Please open this page using HTTPS.');return false}
  try{await connect();if(!mutedRef.current)await capture();idle();return true}catch(e){releaseMic();setError(e.name==='NotAllowedError'?'Microphone access is blocked. Please enable it in your browser permissions.':e.name==='NotFoundError'?'No microphone was found. You can type your question instead.':e.message==='Connection unavailable'?'The local voice service is not reachable. Please try again.':'The microphone could not start. You can type your question instead.');return false}
 }
 function mute(){
  mutedRef.current=true;setMuted(true);try{sessionStorage.setItem('gnani_muted','1');sessionStorage.setItem('gnani_muted_at',String(Date.now()))}catch{}
  releaseMic();send('mic_state',{enabled:false});if(awaiting.current&&voiceTurn.current&&!playing.current){currentId.current=null;awaiting.current=false}if(!playing.current)phaseTo('muted');
 }
 async function unmute(){
  mutedRef.current=false;setMuted(false);setStillMuted(false);try{sessionStorage.setItem('gnani_muted','0');sessionStorage.removeItem('gnani_muted_at')}catch{}
  const okay=await start();if(!okay)mute();return okay;
 }
 async function sendText(text){
  const value=text.trim();if(!value)return;setError('');await connect();stopTalking();const identity=String(++sequence.current);currentId.current=identity;voiceTurn.current=false;awaiting.current=true;setRaw(value);setLine('');phaseTo('thinking');latest.current=[];send('text',{request_id:identity,text:value,aloud:false});
 }
 function cancelGuidance(){guidanceEpoch.current++;queue.current=queue.current.filter(x=>!x.template);if(playingTemplate.current)player.current?.pause()}
 function interrupt(){send('interrupt',{request_id:currentId.current});currentId.current=null;queue.current=[];fadeOut(150);awaiting.current=false;idle()}
 function prefetch(text,lang,settings={}){
  const key=lang+'|'+text+'|'+JSON.stringify(settings);if(!audioCache.current.has(key)){
   const promise=fetch('/api/speech',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,lang,...settings})}).then(async r=>{const value=await r.json();if(!r.ok)throw new Error(typeof value.message==='string'?value.message:'Voice is unavailable.');return value}).catch(e=>{audioCache.current.delete(key);throw e});audioCache.current.set(key,promise);if(audioCache.current.size>40)audioCache.current.delete(audioCache.current.keys().next().value);promise.catch(()=>{});
  }return audioCache.current.get(key);
 }
 async function say(text,lang='en',priority=10,kind='notice',settings={}){
  await connect();if(['now','arrival','weak','reroute'].includes(kind)){guidanceEpoch.current++;queue.current=queue.current.filter(x=>!x.template)}const epoch=guidanceEpoch.current,version=generation.current;
  try{if(['reply','song'].includes(kind)){
   speechAbort.current?.abort();const abort=new AbortController();speechAbort.current=abort;
   const response=await fetch('/api/speech/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,lang,...settings}),signal:abort.signal});
   if(!response.ok)throw new Error('Timbre returned HTTP '+response.status+'. Please try again.');const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
   while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});const lines=buffer.split('\n');buffer=lines.pop();for(const line of lines){if(!line.trim())continue;const item=JSON.parse(line);if(item.error)throw new Error(item.error);if(running.current&&version===generation.current){queue.current.push({...item,template:true,priority,kind});drain()}}if(done)break}return;
  }const value=await prefetch(text,lang,settings);if(!running.current||version!==generation.current||epoch!==guidanceEpoch.current)return;queue.current.push({...value,template:true,priority,kind});drain()}catch(e){if(e.name!=='AbortError')setError(e.message)}
 }
 function end(){speechAbort.current?.abort();playSerial.current++;releaseMic();running.current=false;generation.current++;queue.current=[];player.current?.pause();player.current=null;playing.current=false;setSpeaking(false);awaiting.current=false;socket.current?.close();socket.current=null;ctx.current?.close();setActive(false);setLine('');setRaw('');setError('');phaseTo(mutedRef.current?'muted':'idle')}
 function repeat(){if(!latest.current.length)return;queue.current=[...latest.current];drain()}
 async function listenReply(){if(!reply)return;if(reply.segments?.length){for(const part of reply.segments)await say(part.text,reply.language,80,'reply',{voice:part.voice})}else await say(reply.text,reply.language,80,'reply')}
 function acceptExternalReply(text,lang,aloud=false){setReply({text,language:lang,typed:!aloud});if(!aloud)setLine(text);else say(text,lang,80,'reply')}
 function setRepliesAloud(value){aloudRef.current=value;setAloudState(value);try{sessionStorage.setItem('gnani_replies_aloud',value?'1':'0')}catch{}if(!value)stopTalking()}
 function tap(){if(mutedRef.current)return unmute();if(!stream.current)return start();if(playing.current||awaiting.current)interrupt();else idle()}
 useEffect(()=>{if(!muted){setStillMuted(false);return}const since=Number(readSession('gnani_muted_at',String(Date.now())));const timer=setTimeout(()=>setStillMuted(true),Math.max(0,600000-(Date.now()-since)));return ()=>clearTimeout(timer)},[muted]);
 useEffect(()=>()=>end(),[]);
 return {diagnostics,active,phase,line,raw,error,setError,userSpeaking,speaking,capturing,muted,stillMuted,speechBusy:()=>playing.current||queue.current.length>0,userSpeechActive:()=>userSpeech.current||awaiting.current,privacy:privacy[locale(options.lang||'en')],repliesAloud,setRepliesAloud,reply,listenReply,acceptExternalReply,sendText,mute,unmute,tap,start,end,interrupt,stopTalking,repeat,say,prefetch,sendLocation:p=>send('location',{location:p}),send,cancelGuidance};
}
