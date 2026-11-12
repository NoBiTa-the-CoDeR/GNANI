import {EnhancedOrb,EffectBackground,CalmControl,VoiceControl} from './Effects';
import SelfTest from './SelfTest';
import DebugOverlay from './DebugOverlay';
import React,{useState,useRef,useEffect} from 'react';
import {createRoot} from 'react-dom/client';import {Mic,Volume2,PhoneOff,MapPin,Keyboard,MicOff,Square} from 'lucide-react';
import WebAssistant from './WebAssistant';import CameraReader from './CameraReader';import MyPeople from './MyPeople';import ActionCards from './ActionCards';import {useReminders} from './useReminders';import {PEOPLE,TODAY,readLocal,schedule} from './localActions';import Waves from './Waves';import MusicCard from './MusicCard';import VoiceTest from './VoiceTest';import './style.css';import {createLocationController} from './location';import {useVoiceSession} from './useVoiceSession';import MapSection from './MapSection';import HelperPanel from './HelperPanel';import {useGuidance,GuidanceBanner} from './navigation/useGuidance';import {t,locale,calmScroll} from './i18n';

function App(){
 const [lang,setLang]=useState('en'),[mapData,setMapData]=useState(null),[panel,setPanel]=useState(null),[step,setStep]=useState(0),[position,setPosition]=useState(null),[locationStatus,setLocationStatus]=useState(''),[journeyRequested,setJourneyRequested]=useState(false),[hint,setHint]=useState(''),[stopVideoToken,setStopVideoToken]=useState(0),[floating,setFloating]=useState(false),[keyboard,setKeyboard]=useState(false),[draft,setDraft]=useState(''),[music,setMusic]=useState(null),[musicKey,setMusicKey]=useState(0),[people,setPeople]=useState(()=>readLocal(PEOPLE)),[peopleOpen,setPeopleOpen]=useState(false),[addName,setAddName]=useState(''),[actions,setActions]=useState([]),[actionsKey,setActionsKey]=useState(0),[actionsAloud,setActionsAloud]=useState(false),[today,setToday]=useState(()=>readLocal(TODAY));
 const positionRef=useRef(null),navRef=useRef(null),controller=useRef(null),guidanceRef=useRef(null),voiceRef=useRef(null),orb=useRef(null),orbSection=useRef(null),animation=useRef(null),mapVersion=useRef(0),[mapKey,setMapKey]=useState(0),routeRef=useRef(null),waveSignal=useRef({}),webRef=useRef(null),webPreference=useRef({enabled:false,asking:false});
 const voice=useVoiceSession({positionRef,navRef,lang,webPreferenceRef:webPreference,onUserSpeech:()=>setStopVideoToken(n=>n+1),onAssistantSpeech:()=>setStopVideoToken(n=>n+1),onAnalyser:(analyser,audio)=>{waveSignal.current.speechAnalyser=analyser;waveSignal.current.speechAudio=audio;cancelAnimationFrame(animation.current);const data=new Uint8Array(analyser.frequencyBinCount);function frame(){if(audio.paused){orb.current?.style.setProperty('--level','0');return}analyser.getByteFrequencyData(data);const level=data.reduce((a,b)=>a+b,0)/(data.length*255);orb.current?.style.setProperty('--level',String(Math.min(1,level*3)));animation.current=requestAnimationFrame(frame)}frame()},onEvent:m=>{
  if(m.type==='transcript'){if(locale(m.language)!==lang)voiceRef.current?.cancelGuidance();setLang(locale(m.language));setHint('')}
  if(m.type==='web_task')webRef.current?.start(m.text,{lang:locale(m.language),aloud:m.aloud});
  if(m.type==='location_needed'){setJourneyRequested(true);startLocation()}
  if(m.type==='map'){setJourneyRequested(true);voiceRef.current?.cancelGuidance();guidanceRef.current?.end({keepLocation:true});setMapData(m.map);setMapKey(++mapVersion.current);setLang(locale(m.language));setHint(t(m.language).mapBelow);startLocation()}
  if(m.type==='panel'){setPanel(m.panel);setStep(0);setLang(locale(m.language));setHint(t(m.language).below)}
  if(m.type==='step')setStep(m.index);
  if(m.type==='music'){setMusic(m.music.source==='stop'?null:m.music);setMusicKey(n=>n+1);setLang(locale(m.language))}
  if(m.type==='music_stop')setMusic(null);
  if(m.type==='actions'){setActions(m.actions);setActionsAloud(!!m.aloud);setActionsKey(n=>n+1);setLang(locale(m.language))}
  if(m.type==='location_question')voiceRef.current?.say(m.text,m.language,20);
 }});voiceRef.current=voice;
 const reminders=useReminders(voice,()=>setToday(readLocal(TODAY)));
 function openPeople(name=''){voice.mute();setAddName(name);setPeopleOpen(true)}
 function stopLocation(){controller.current?.stop()}
 function startLocation(){
  if(!controller.current)controller.current=createLocationController(navigator,p=>{positionRef.current=p;setPosition(p);voiceRef.current?.sendLocation(p);guidanceRef.current?.update(p)},setLocationStatus,reason=>{positionRef.current=null;setPosition(null);voiceRef.current?.send(reason==='denied'?'location_denied':'location_unavailable',{});guidanceRef.current?.update({lat:0,lon:0,accuracy:999})},state=>voiceRef.current?.send('location_permission',{state}));
  controller.current.start();
 }
 const guidance=useGuidance({lang,say:voice.say,prefetch:voice.prefetch,navRef,requestLocation:startLocation,stopLocation});guidanceRef.current=guidance;
 async function startWalking(route,dest){if(!voice.active&&!(await voice.start()))return;setStopVideoToken(n=>n+1);await guidance.start(route,dest,mapData.destination);if(positionRef.current)guidance.update(positionRef.current)}
 function endJourney(settings={}){if(!settings.keepLocation){setJourneyRequested(false);setLocationStatus('')}voice.cancelGuidance();guidance.end(settings);navRef.current=null;voice.send('nav',{nav:null})}
 function endConversation(){endJourney();voice.end();controller.current=null;setPosition(null);positionRef.current=null;setLocationStatus('');setHint('');setMapData(null);setPanel(null);setStep(0);setMusic(null)}
 function tapOrb(){setStopVideoToken(n=>n+1);voice.tap()}
 function panelStep(index){if(!panel?.steps?.[index])return;setStep(index);voice.say(panel.steps[index],lang,40);voice.send('panel_step',{index})}
 useEffect(()=>{const observer=new IntersectionObserver(entries=>setFloating(!entries[0].isIntersecting),{threshold:.1});if(orb.current)observer.observe(orb.current);return ()=>observer.disconnect()},[]);
 useEffect(()=>()=>{controller.current?.stop();cancelAnimationFrame(animation.current)},[]);
 const w=t(lang),labels={idle:locale(lang)==='hi'?'बात करने के लिए दबाइए':locale(lang)==='kn'?'ಮಾತನಾಡಲು ಒತ್ತಿ':'Tap to talk',listening:locale(lang)==='hi'?'मैं सुन रही हूँ':locale(lang)==='kn'?'ಕೇಳುತ್ತಿದ್ದೇನೆ':'I’m listening',thinking:w.thinking,speaking:locale(lang)==='hi'?'आपसे बात कर रही हूँ':locale(lang)==='kn'?'ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ':'Speaking to you'};
 return <div className="app"><EffectBackground/><Waves signal={waveSignal}/><DebugOverlay voice={voice}/>
  <GuidanceBanner state={guidance.state} active={guidance.active} lang={lang} onEnd={endJourney}/>
  <header className="top"><div className="brand"><span className="brand-icon">✳</span><span>gNani <i>AI</i></span></div><CalmControl/><button className="people-open" onClick={()=>openPeople()}>My people</button></header>
  <main><section className="stage" ref={orbSection}><div className="intro"><h1>Namaste! Main hoon <em>gNani.</em></h1><p>Aap mujhe kuch bhi poochiye.</p></div>
   <button ref={orb} className={'orb-button '+(voice.muted?'muted':voice.phase)} onClick={tapOrb} aria-label={voice.muted?'Unmute and talk':voice.capturing?'Interrupt or continue listening':'Start talking'}><EnhancedOrb voice={voice} signal={waveSignal}/></button>
   <div className="status"><span className="status-dot"/>{voice.muted?voice.privacy.muted:labels[voice.phase]}</div><div className="current-text" aria-live="polite">{voice.phase==='thinking'?w.thinking:voice.line}</div>
   {voice.reply&&!voice.speaking&&(voice.reply.typed||!voice.repliesAloud)&&<button className="listen-reply primary-action" onClick={voice.listenReply}>▶ {locale(lang)==='hi'?'सुनिए':locale(lang)==='kn'?'ಕೇಳಿ':'Listen'}</button>}
   {voice.raw&&<div className="transcript"><span>{locale(lang)==='hi'?'आपने कहा':locale(lang)==='kn'?'ನೀವು ಹೇಳಿದ್ದು':'You said'}</span><p>{voice.raw}</p></div>}
   {voice.error&&<p className="error" role="alert">{voice.error}</p>}
   {hint&&<button className="below-hint" onClick={()=>calmScroll(document.querySelector(hint===w.mapBelow?'.journey-section':'.helper-section'))}>↓ {hint}</button>}
   {(mapData||journeyRequested)&&locationStatus&&<p className="location-status"><MapPin size={22}/>{locationStatus}</p>}
   <div className="controls">{voice.active&&<button onClick={voice.repeat} aria-label="Repeat last response"><Volume2 size={24}/>{w.repeat}</button>}{voice.active&&<button onClick={endConversation} aria-label="End conversation"><PhoneOff size={24}/>{locale(lang)==='hi'?'बात समाप्त करें':locale(lang)==='kn'?'ಮಾತು ಮುಗಿಸಿ':'End conversation'}</button>}</div>
  </section>
  <CameraReader lang={lang} voice={voice} onReply={(text,language,aloud)=>{setLang(locale(language));voice.acceptExternalReply(text,language,aloud)}}/>
  <WebAssistant ref={webRef} lang={lang} voice={voice} onReply={(text,language,aloud)=>{setLang(locale(language));voice.acceptExternalReply(text,language,aloud)}} onPreference={value=>{webPreference.current=value;voice.send('web_preference',value)}}/>
  {mapData&&<MapSection key={mapKey} data={mapData} position={position} lang={lang} onClose={()=>setMapData(null)} onRoute={r=>{routeRef.current=r;guidance.acceptRoute(r)}} onStart={startWalking} onEnd={endJourney} guiding={guidance.active} guidanceState={guidance.state} onSpeak={voice.say} rerouteToken={guidance.rerouteToken}/>}
  {music&&<MusicCard key={musicKey} request={music} lang={lang} voice={voice} signal={waveSignal} onClose={()=>setMusic(null)}/>}
  {actions.length>0&&<ActionCards key={actionsKey} actions={actions} aloud={actionsAloud} lang={lang} people={people} voice={voice} onAdd={openPeople} onChange={reminders.refresh} onHistory={()=>setToday(readLocal(TODAY))}/>}
  {panel&&<HelperPanel onTimer={(minutes,text)=>{schedule({kind:'timer',minutes,text},lang);reminders.refresh();voice.setError('Timer set. Reminders work while this app is open.')}} panel={panel} lang={lang} index={step} onStep={panelStep} onClose={()=>setPanel(null)} stopVideoToken={stopVideoToken}/>}
  <section className="local-notes content-section"><details><summary>Reminders &amp; what I did today</summary><p>Reminders work while the app is open. They may be late if your phone sleeps. This app cannot reliably alert you after it is closed.</p><button onClick={reminders.enable}>Enable notifications</button>{reminders.notice&&<p role="status">{reminders.notice}</p>}{reminders.entries.filter(x=>x.status==='pending').map(x=><article key={x.id}><p>{x.text} — {new Date(x.at).toLocaleTimeString()}</p><button onClick={()=>reminders.cancel(x.id)}>Cancel reminder</button></article>)}<h3>What I did today</h3>{today.filter(x=>new Date(x.at).toDateString()===new Date().toDateString()).map((x,i)=><p key={i}>{new Date(x.at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}: {x.text}</p>)}</details></section>
  </main>
  {peopleOpen&&<MyPeople voice={voice} initialName={addName} onClose={()=>setPeopleOpen(false)} onChange={setPeople}/>}
  {reminders.alert&&<aside className="reminder-alert" role="alertdialog" aria-label="Your reminder"><h2>Your reminder</h2><p>{reminders.alert.text}</p><button onClick={reminders.dismiss}>Done</button></aside>}
  {(mapData&&!guidance.active&&!guidance.state?.arrived)&&<button className="end-journey-fixed" onClick={()=>{endJourney();setMapData(null)}}>{w.end}</button>}
  {floating&&<button className={'floating-mic '+voice.phase} onClick={tapOrb} aria-label="Talk to gNani"><Mic size={30}/><span>{labels[voice.phase]}</span></button>}
  {voice.stillMuted&&voice.muted&&<aside className="still-muted" role="status"><strong>{voice.privacy.still}</strong><button onClick={voice.unmute}>{voice.privacy.unmute}</button></aside>}
  {keyboard&&<form className="typing-panel" onSubmit={async e=>{e.preventDefault();try{await voice.sendText(draft);setDraft('')}catch{voice.setError('Your message could not be sent. Please try again.')}}}><label htmlFor="typed-message">{locale(lang)==='hi'?'अपना सवाल लिखिए':locale(lang)==='kn'?'ನಿಮ್ಮ ಪ್ರಶ್ನೆ ಬರೆಯಿರಿ':'Type your question'}</label><div><input id="typed-message" value={draft} onChange={e=>setDraft(e.target.value)} maxLength={2000} autoComplete="off"/><button type="submit" disabled={!draft.trim()}>Send</button></div><label className="aloud-toggle"><input type="checkbox" checked={voice.repliesAloud} onChange={e=>voice.setRepliesAloud(e.target.checked)}/>Replies aloud (voice messages)</label><button type="button" onClick={()=>setKeyboard(false)}>Close keyboard</button></form>}
  <nav className="privacy-controls" aria-label="Voice and keyboard controls"><VoiceControl voice={voice}/><button onClick={()=>setKeyboard(v=>!v)} aria-expanded={keyboard} aria-label="Keyboard"><Keyboard size={28}/><span>Keyboard</span></button>{voice.speaking&&<button className="stop-talking" onClick={voice.stopTalking}><Square size={22}/>Stop talking</button>}</nav>
  <footer><span>Made for conversations that feel like home</span><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a></footer>
 </div>
}
createRoot(document.getElementById('root')).render(location.pathname==='/selftest'?<SelfTest/>:location.pathname==='/voice-test'?<VoiceTest/>:<App/>);
