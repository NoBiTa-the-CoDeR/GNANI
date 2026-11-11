import {useRef,useState,useEffect} from 'react';import {GuidanceEngine,instruction} from './engine';import {t,locale} from '../i18n';
export function useGuidance({lang,say,prefetch,navRef,requestLocation,stopLocation}){
 const [state,setState]=useState(null),[active,setActive]=useState(false),[rerouteToken,setRerouteToken]=useState(0);const engine=useRef(null),wake=useRef(null),destination=useRef(null),name=useRef(''),enabled=useRef(false),currentRoute=useRef(null),prefetched=useRef(new Set()),options=useRef(null);options.current={lang,say,prefetch,requestLocation,stopLocation};
 async function lock(){try{wake.current=await navigator.wakeLock?.request('screen')}catch{}}
 function prepare(){if(!engine.current)return;for(const text of engine.current.prefetch())if(!prefetched.current.has(text)){prefetched.current.add(text);options.current.prefetch(text,options.current.lang).catch(()=>{})}}
 function end(settings={}){enabled.current=false;setActive(false);setState(null);engine.current=null;navRef.current=null;wake.current?.release();wake.current=null;if(!settings.keepLocation)options.current.stopLocation?.()}
 async function start(route,dest,title){destination.current=dest;name.current=title;currentRoute.current=route;engine.current=new GuidanceEngine(route,dest,options.current.lang);enabled.current=true;prefetched.current.clear();setActive(true);setState(null);options.current.requestLocation();await lock();prepare();const depart=route.steps[0];if(depart?.meters>0)options.current.say(instruction(depart,options.current.lang,'continue',depart.meters),options.current.lang,30)}
 function update(position){
  if(!enabled.current||!engine.current)return;engine.current.lang=locale(options.current.lang);const value=engine.current.update(position);setState(value);navRef.current={remaining_m:value.remaining_m??currentRoute.current.distance_m,remaining_min:value.remaining_min??currentRoute.current.duration_min,next_instruction:value.weak?t(options.current.lang).weak:value.next_instruction||'',destination:name.current,mode:'walk'};
  for(const event of value.events){console.info('[gNani guidance]',event.kind);options.current.say(event.text,options.current.lang,event.priority,event.kind)}
  if(value.events.some(e=>e.kind==='reroute'))setRerouteToken(n=>n+1);
  if(value.arrived){enabled.current=false;setActive(false);navRef.current=null;wake.current?.release();wake.current=null;options.current.stopLocation?.()}
  prepare();
 }
 function acceptRoute(route){if(!route)return;currentRoute.current=route;if(enabled.current&&route){engine.current=new GuidanceEngine(route,destination.current,options.current.lang);prefetched.current.clear();prepare()}}
 useEffect(()=>{if(engine.current){engine.current.lang=locale(lang);prefetched.current.clear();prepare()}},[lang]);
 useEffect(()=>{const visibility=()=>{if(enabled.current&&document.visibilityState==='visible')lock()};document.addEventListener('visibilitychange',visibility);return ()=>{document.removeEventListener('visibilitychange',visibility);wake.current?.release()}},[]);
 return {active,state,start,end,update,acceptRoute,rerouteToken};
}
export function GuidanceBanner({state,lang,onEnd,active}){if(!active&&!state?.arrived)return null;const w=t(lang);return <aside className={'guidance-banner '+(state?.arrived?'success':'')} aria-live="polite"><div><strong>{state?.arrived?w.arrived:state?.weak?w.weak:state?.offRoute?w.reroute:<><span aria-hidden="true">{state?.arrow||'↑'}</span> {state?.next_instruction||w.straight}</>}</strong>{!state?.arrived&&state?.remaining_m!==undefined&&<p>{state.remaining_m} m · {state.remaining_min} min</p>}</div><button onClick={onEnd}>{w.end}</button></aside>}
