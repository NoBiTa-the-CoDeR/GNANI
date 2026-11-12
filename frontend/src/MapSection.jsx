import {JourneyModes} from './Design';
import {ProgressSteps,LoadingStatus} from './Polish';
import React,{useEffect,useRef,useState} from 'react';
import L from 'leaflet';import 'leaflet/dist/leaflet.css';
import {t,calmScroll,locale} from './i18n';
const tooltipText=s=>{const el=document.createElement('span');el.textContent=String(s||'');return el};
const point=p=>p&&Number.isFinite(p.lat)&&Number.isFinite(p.lon)?[p.lat,p.lon]:null;
export default function MapSection({data,position,lang,onClose,onRoute,onStart,onEnd,guiding,onSpeak,rerouteToken=0,guidanceState,onRequestLocation}){
 const w=t(lang),section=useRef(null),container=useRef(null),map=useRef(null),layer=useRef(null),dot=useRef(null),line=useRef(null),pin=useRef(null),asked=useRef(false),askedCandidates=useRef(false);
 const [dest,setDest]=useState(data.dest),[origin,setOrigin]=useState(position||data.origin),[mode,setMode]=useState('walk'),[route,setRoute]=useState(null),[candidates,setCandidates]=useState([]),[error,setError]=useState(''),[loading,setLoading]=useState(false),[retry,setRetry]=useState(0),[originName,setOriginName]=useState(''),[originQuery,setOriginQuery]=useState(''),[originCandidates,setOriginCandidates]=useState([]),[manualOrigin,setManualOrigin]=useState(false),[destinationName,setDestinationName]=useState(data.destination),[destinationInput,setDestinationInput]=useState(data.destination);
 useEffect(()=>{calmScroll(section.current)},[]);
 useEffect(()=>{if(!manualOrigin)setOrigin(position||null)},[position,manualOrigin]);
 useEffect(()=>{
  if(!container.current)return;const instance=L.map(container.current,{scrollWheelZoom:false}).setView(point(dest)||point(origin)||[20.59,78.96],dest||origin?13:4);map.current=instance;
  layer.current=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(instance);
  const timer=setTimeout(()=>instance.invalidateSize(),200);return ()=>{clearTimeout(timer);instance.remove();map.current=null};
 },[]);
 useEffect(()=>{if(!map.current)return;if(dot.current)dot.current.remove();if(point(origin))dot.current=L.circleMarker(point(origin),{radius:9,color:'white',weight:3,fillColor:'#1976b9',fillOpacity:1}).addTo(map.current).bindTooltip(position&&!manualOrigin?'Your location':'Starting place')},[origin?.lat,origin?.lon]);
 useEffect(()=>{if(!map.current)return;if(pin.current)pin.current.remove();if(point(dest)){pin.current=L.marker(point(dest),{icon:L.divIcon({className:'destination-pin',html:'<span aria-hidden="true">📍</span>',iconSize:[56,56],iconAnchor:[28,48]})}).addTo(map.current).bindTooltip(tooltipText(destinationName));if(!route)map.current.setView(point(dest),14,{animate:false})}},[dest?.lat,dest?.lon,destinationName]);
 useEffect(()=>{if(!map.current)return;if(line.current)line.current.remove();if(route?.coords?.length){line.current=L.polyline(route.coords,{color:'#a65a34',weight:6}).addTo(map.current);map.current.fitBounds(line.current.getBounds(),{padding:[30,30],animate:false})}},[route]);
 useEffect(()=>{
  if(mode==='transit')return;let alive=true;const abort=new AbortController();setLoading(true);setError('');setRoute(null);onRoute(null);
  fetch('/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin:origin?{lat:origin.lat,lon:origin.lon}:null,dest:dest?{lat:dest.lat,lon:dest.lon}:null,destination:destinationName,origin_name:originQuery,mode}),signal:abort.signal}).then(async r=>({ok:r.ok,data:await r.json()})).then(({ok,data:value})=>{
   if(!alive)return;
   if(value.dest&&!dest)setDest(value.dest);
   if(value.origin_candidates){setOriginCandidates(value.origin_candidates);return}
   if(value.origin&&!origin){setOrigin(value.origin);setOriginCandidates([]);}
   if(value.candidates){setCandidates(value.candidates);if(!askedCandidates.current){askedCandidates.current=true;onSpeak(w.which,lang)}return}
   if(!ok){setError(typeof value.message==='string'?value.message:typeof value.detail==='string'?value.detail:w.routeError);if(value.error==='location_unavailable')asked.current=true;return}
   setCandidates([]);setRoute(value);onRoute(value);
  }).catch(e=>{if(alive&&e.name!=='AbortError')setError(w.routeError)}).finally(()=>{if(alive)setLoading(false)});
  return ()=>{alive=false;abort.abort()};
 },[mode,dest?.lat,dest?.lon,Boolean(origin),originQuery,destinationName,retry,rerouteToken]);
 const validTransit=(()=>{try{let u=point(dest)?new URL('https://www.google.com/maps/dir/?api=1&travelmode=transit&destination='+dest.lat+','+dest.lon+(origin?'&origin='+origin.lat+','+origin.lon:'')):new URL(data.links?.transit);return u.protocol==='https:'&&u.hostname==='www.google.com'&&u.pathname==='/maps/dir/'?u.href:null}catch{return null}})();
 function choose(candidate){setCandidates([]);setDestinationName(candidate.name);setDestinationInput(candidate.name);setDest({lat:candidate.lat,lon:candidate.lon});askedCandidates.current=false}
 return <section ref={section} className="content-section journey-section" aria-label={w.journey}>
  <div className="section-heading"><div><p className="section-kicker">{w.journey}</p><h2>{destinationName}</h2></div><button aria-label="Close journey" onClick={()=>{onEnd();onClose()}}>×</button></div>
  <form className="map-origin-form" onSubmit={e=>{e.preventDefault();setDestinationName(destinationInput.trim());setDest(null);setCandidates([]);setRetry(n=>n+1)}}><label htmlFor="destination-place">Where do you want to go?</label><div><input id="destination-place" aria-label="Destination place" value={destinationInput} onChange={e=>setDestinationInput(e.target.value)} maxLength={160}/><button type="submit" disabled={!destinationInput.trim()||loading}>Search place</button></div></form>
  <JourneyModes items={[{value:'walk',label:w.walk},{value:'drive',label:w.drive},{value:'transit',label:w.transit}]} value={mode} onChange={key=>{onEnd({keepLocation:true});setMode(key)}}/>
  <button onClick={()=>{setManualOrigin(false);setOrigin(position||null);setOriginQuery('');onRequestLocation?.();setRetry(n=>n+1)}}>Use my location</button>
  <div className="journey-map" ref={container} aria-label="Journey map"/>
  <p className="map-credit"><a href="https://www.geoapify.com/" target="_blank" rel="noreferrer">Place search powered by Geoapify</a> · © OpenStreetMap contributors</p>
  {candidates.length>0&&<div className="destination-options"><h3>{w.which}</h3>{candidates.map((c,i)=><button key={i} onClick={()=>choose(c)}>{c.name}</button>)}</div>}
  {loading&&<LoadingStatus text={w.loading}/>}
  {error&&<div className="help-message" role="alert"><p>{error}</p><button onClick={()=>setRetry(n=>n+1)}>{w.retry}</button></div>}
  <form className="map-origin-form" onSubmit={e=>{e.preventDefault();setManualOrigin(true);setOrigin(null);setOriginQuery(originName.trim());setRetry(n=>n+1)}}><label htmlFor="origin-place">{locale(lang)==='hi'?'आप कहाँ से चलेंगे?':locale(lang)==='kn'?'ನೀವು ಎಲ್ಲಿಂದ ಹೊರಡುತ್ತೀರಿ?':'Where are you starting from?'}</label><div><input id="origin-place" aria-label="Starting place" value={originName} onChange={e=>setOriginName(e.target.value)} maxLength={160} placeholder="Area, city or nearby landmark"/><button disabled={!originName.trim()||loading} type="submit">Find route</button></div></form>
  {originCandidates.length>0&&<div className="origin-options"><h3>Which starting place?</h3>{originCandidates.map((c,i)=><button key={i} onClick={()=>{setManualOrigin(true);setOrigin({lat:c.lat,lon:c.lon});setOriginQuery('');setOriginCandidates([]);setRetry(n=>n+1)}}>{c.name}</button>)}</div>}
  {!position&&<p className="help-message">{origin?'Route starts at your chosen place. Live walking guidance needs an accurate GPS fix.':w.noGps}</p>}

  {route&&mode!=='transit'&&<><ProgressSteps steps={route.steps} index={Math.max(0,route.steps.findIndex(s=>s.lat===guidanceState?.next_step?.lat&&s.lon===guidanceState?.next_step?.lon))}/><p className="route-total"><strong>{route.distance_m<1000?`${route.distance_m} m`:`${(route.distance_m/1000).toFixed(1)} km`}</strong><span> · {route.duration_min} {locale(lang)==='hi'?'मिनट':locale(lang)==='kn'?'ನಿಮಿಷ':'min'}</span></p>{mode==='walk'&&<button className="primary-action" disabled={manualOrigin||!position||position.accuracy>50} onClick={()=>guiding?onEnd():onStart(route,dest)}>{guiding?w.end:w.start}</button>}{mode==='drive'&&<p>{locale(lang)==='en'?'Enjoy the ride as a passenger.':locale(lang)==='hi'?'आप यात्री हैं। आराम से सफ़र कीजिए।':'ಪ್ರಯಾಣಿಕರಾಗಿ ಆರಾಮವಾಗಿ ಪ್ರಯಾಣಿಸಿ.'}</p>}</>}
  {mode==='transit'&&<div className="transit-content"><p>{w.transitNote}</p>{validTransit?<a className="primary-action" href={validTransit} target="_blank" rel="noopener noreferrer">{w.openMaps}</a>:<p>{w.noGps}</p>}</div>}
 </section>
}
