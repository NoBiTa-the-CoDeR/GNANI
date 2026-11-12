import YouTubeSearch from './YouTubeSearch';
import {RevealTitle} from './TextDesign';
import {Ingredient,ProgressSteps,LoadingStatus} from './Polish';
import {stepMinutes} from './duration';
import React,{useEffect,useRef,useState} from 'react';import {t,calmScroll,locale} from './i18n';import {imageQueries,videoQuery} from './content';
const titleText=value=>(value||'').replace(/&(quot|amp|apos|lt|gt|#39);/g,(_,key)=>({quot:'"',amp:'&',apos:"'",lt:'<',gt:'>','#39':"'"}[key]));
function photoUrl(value){return /^\/api\/photo\/[a-f0-9]{32}$/.test(value||'')?value:safeHttps(value)}
function safeHttps(value){try{const u=new URL(value);return u.protocol==='https:'?u.href:null}catch{return null}}
export default function HelperPanel({panel,lang,index,onStep,onClose,stopVideoToken,onTimer}){
 const section=useRef(null),cards=useRef([]);const [photos,setPhotos]=useState([]),[loading,setLoading]=useState(true);const w=t(lang);
 useEffect(()=>{calmScroll(section.current);let alive=true;const abort=new AbortController();setLoading(true);setPhotos([]);
  Promise.all(imageQueries(panel).map(q=>fetch('/api/images?q='+encodeURIComponent(q.slice(0,80)),{signal:abort.signal}).then(r=>r.ok?r.json():{photos:[]}).catch(()=>({photos:[]})))).then(values=>{if(alive){const urls=new Set();setPhotos(values.flatMap(v=>v.photos||[]).filter(p=>{if(urls.has(p.url)||!photoUrl(p.url))return false;urls.add(p.url);return true}).slice(0,6));setLoading(false)}});
  return ()=>{alive=false;abort.abort()};
 },[panel]);
 useEffect(()=>{if(index>0)calmScroll(cards.current[index])},[index]);
 return <section className="content-section helper-section" ref={section} aria-label={w.helpful}>
  <div className="section-heading"><div><p className="section-kicker">{w.helpful}</p><h2><RevealTitle>{panel.title}</RevealTitle></h2></div><button aria-label="Close helper panel" onClick={onClose}>×</button></div>
  {panel.summary&&<p>{panel.summary}</p>}
  {panel.kind==='health'&&<p className="health-note">{w.health}</p>}
  {loading&&<div className="photo-row skeleton-row" role="status" aria-label="Loading photos"><LoadingStatus text={locale(lang)==='en'?'Loading photos…':'…'}/><div/><div/></div>}
  {!loading&&photos.length>0&&<div className="photo-row">{photos.map(p=><figure key={p.url}><img src={p.url} alt={p.alt||panel.title} loading="lazy" onError={e=>{e.currentTarget.closest('figure').hidden=true}}/><figcaption>{safeHttps(p.page)?<a href={p.page} target="_blank" rel="noreferrer">{p.credit||p.source}</a>:p.credit} · {p.source}{p.license?' · '+p.license:''}</figcaption></figure>)}</div>}
  {videoQuery(panel,lang)&&<YouTubeSearch lang={lang} initialQuery={videoQuery(panel,lang)} stopVideoToken={stopVideoToken}/>}
  {!!panel.ingredients?.length&&<fieldset className="ingredients"><legend>{locale(lang)==='hi'?'सामग्री':locale(lang)==='kn'?'ಸಾಮಗ್ರಿಗಳು':'What you need'}</legend>{panel.ingredients.map((item,i)=><Ingredient key={i} text={item}/>)}</fieldset>}
  {panel.steps?.length>0&&<ProgressSteps steps={panel.steps} index={index} onStep={onStep}/>}{panel.steps?.length>0&&<div className="step-list">{panel.steps.map((step,i)=><article key={i} ref={el=>cards.current[i]=el} className={'step-card '+(index===i?'current-step':'')} aria-current={index===i?'step':undefined}><span className="step-number">{w.step} {i+1}</span><p>{step}</p>{stepMinutes(step)&&<button onClick={()=>onTimer?.(stepMinutes(step),step)}>Start timer</button>}<button onClick={()=>onStep(i)} aria-label={`${w.repeat} ${w.step} ${i+1}`}>{w.repeat}</button></article>)}<button className="primary-action" disabled={index>=panel.steps.length-1} onClick={()=>onStep(index+1)}>{w.next}</button></div>}
  {panel.tips?.length>0&&<div className="tips-box">{panel.tips.map((tip,i)=><p key={i}>{tip}</p>)}</div>}
 </section>
}
