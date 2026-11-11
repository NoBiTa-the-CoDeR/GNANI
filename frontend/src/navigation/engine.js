import {locale,t} from '../i18n.js';
const R=6371000,rad=Math.PI/180;
export function distance(a,b){const lat1=a[0]*rad,lat2=b[0]*rad,dlat=(b[0]-a[0])*rad,dlon=(b[1]-a[1])*rad;return 2*R*Math.asin(Math.min(1,Math.sqrt(Math.sin(dlat/2)**2+Math.cos(lat1)*Math.cos(lat2)*Math.sin(dlon/2)**2)))}
export function project(point,coords){
 let best={distance:Infinity,along:0,point:coords[0],segment:0},along=0;
 const scale=Math.cos(point[0]*rad),xy=p=>[(p[1]-point[1])*rad*R*scale,(p[0]-point[0])*rad*R];
 for(let i=0;i<coords.length-1;i++){
  const a=xy(coords[i]),b=xy(coords[i+1]),dx=b[0]-a[0],dy=b[1]-a[1],len2=dx*dx+dy*dy,frac=len2?Math.max(0,Math.min(1,-(a[0]*dx+a[1]*dy)/len2)):0;
  const d=Math.hypot(a[0]+dx*frac,a[1]+dy*frac),len=distance(coords[i],coords[i+1]);
  if(d<best.distance)best={distance:d,along:along+len*frac,point:[coords[i][0]+(coords[i+1][0]-coords[i][0])*frac,coords[i][1]+(coords[i+1][1]-coords[i][1])*frac],segment:i};along+=len;
 }
 return {...best,total:along};
}
export function pointAt(coords,meters){let left=meters;for(let i=1;i<coords.length;i++){const len=distance(coords[i-1],coords[i]);if(left<=len){const f=len?left/len:0;return [coords[i-1][0]+(coords[i][0]-coords[i-1][0])*f,coords[i-1][1]+(coords[i][1]-coords[i-1][1])*f]}left-=len}return coords.at(-1)}
const directions={
 en:{left:'turn left',right:'turn right','slight left':'bear slightly left','slight right':'bear slightly right','sharp left':'turn sharply left','sharp right':'turn sharply right',uturn:'turn back',straight:'continue straight',fork:'keep to the indicated branch',roundabout:'follow the roundabout',depart:'start walking',arrive:'you have arrived','new name':'continue straight','end of road':'turn at the end of the road',continue:'continue straight'},
 hi:{left:'बाएँ मुड़िए',right:'दाएँ मुड़िए','slight left':'थोड़ा बाएँ चलिए','slight right':'थोड़ा दाएँ चलिए','sharp left':'तेज़ बाएँ मुड़िए','sharp right':'तेज़ दाएँ मुड़िए',uturn:'वापस मुड़िए',straight:'सीधे चलिए',fork:'बताई गई शाखा पर चलिए',roundabout:'गोल चक्कर के रास्ते चलिए',depart:'चलना शुरू कीजिए',arrive:'आप पहुँच गए हैं','new name':'सीधे चलिए','end of road':'सड़क के अंत पर मुड़िए',continue:'सीधे चलिए'},
 kn:{left:'ಎಡಕ್ಕೆ ತಿರುಗಿ',right:'ಬಲಕ್ಕೆ ತಿರುಗಿ','slight left':'ಸ್ವಲ್ಪ ಎಡಕ್ಕೆ ಹೋಗಿ','slight right':'ಸ್ವಲ್ಪ ಬಲಕ್ಕೆ ಹೋಗಿ','sharp left':'ತೀವ್ರ ಎಡಕ್ಕೆ ತಿರುಗಿ','sharp right':'ತೀವ್ರ ಬಲಕ್ಕೆ ತಿರುಗಿ',uturn:'ಹಿಂದಕ್ಕೆ ತಿರುಗಿ',straight:'ನೇರವಾಗಿ ಹೋಗಿ',fork:'ಸೂಚಿಸಿದ ಕವಲಿನಲ್ಲಿ ಹೋಗಿ',roundabout:'ವೃತ್ತದ ರಸ್ತೆಯಲ್ಲಿ ಹೋಗಿ',depart:'ನಡೆಯಲು ಪ್ರಾರಂಭಿಸಿ',arrive:'ನೀವು ತಲುಪಿದ್ದೀರಿ','new name':'ನೇರವಾಗಿ ಹೋಗಿ','end of road':'ರಸ್ತೆಯ ಕೊನೆಯಲ್ಲಿ ತಿರುಗಿ',continue:'ನೇರವಾಗಿ ಹೋಗಿ'}
};
export function actionText(step,lang){const l=locale(lang),d=directions[l];if(step.action==='arrive')return d.arrive;if(step.action==='depart')return d.depart;if(step.action==='roundabout'||step.action==='rotary')return d.roundabout;if(step.action==='fork')return step.turn?d[step.turn]||d.fork:d.fork;return d[step.turn]||d[step.action]||d.continue}
export function instruction(step,lang,stage='now',meters=0){
 const l=locale(lang),action=actionText(step,l),road=step.road?l==='en'?` onto ${step.road}`:l==='hi'?`। सड़क: ${step.road}`:`. ರಸ್ತೆ: ${step.road}`:'';
 if(stage==='continue'){const m=Math.max(0,Math.round(meters));return l==='hi'?`अब लगभग ${m} मीटर सीधे चलिए।`:l==='kn'?`ಈಗ ಸುಮಾರು ${m} ಮೀಟರ್ ನೇರವಾಗಿ ಹೋಗಿ.`:`Now continue straight for about ${m} metres.`}
 if(stage==='early'&&step.action==='arrive'){const m=Math.max(0,Math.round(meters/10)*10);return l==='hi'?`आपकी मंज़िल लगभग ${m} मीटर आगे है।`:l==='kn'?`ನಿಮ್ಮ ಗಮ್ಯಸ್ಥಾನ ಸುಮಾರು ${m} ಮೀಟರ್ ಮುಂದಿದೆ.`:`Your destination is about ${m} metres ahead.`}
 if(stage==='early'){const m=Math.max(10,Math.round(meters/10)*10);return l==='hi'?`लगभग ${m} मीटर आगे ${action}${road}।`:l==='kn'?`ಸುಮಾರು ${m} ಮೀಟರ್ ಮುಂದೆ ${action}${road}.`:`In about ${m} metres, ${action}${road}.`}
 return l==='hi'?`अब ${action}${road}।`:l==='kn'?`ಈಗ ${action}${road}.`:`Now ${action}${road}.`;
}
export function arrow(step){const m=step?.turn||'';return m.includes('left')?'←':m.includes('right')?'→':m==='uturn'?'↶':step?.action==='roundabout'?'↻':'↑'}
export class GuidanceEngine{
 constructor(route,dest,lang='en',now=Date.now()){
  if(!route?.coords?.length||!route.steps?.length)throw new Error('The route has no walking instructions.');
  this.route=route;this.dest=dest;this.lang=locale(lang);this.progress=0;this.next=1;this.off=0;this.weak=false;this.arrived=false;this.announced=new Set();this.lastSafety=now;this.recalculating=false;
  this.steps=route.steps.map(s=>({...s,along:project([s.lat,s.lon],route.coords).along}));
  this.total=project(route.coords[0],route.coords).total;
 }
 event(kind,text,priority=10){return {kind,text,priority,id:kind+':'+this.next+':'+Math.round(this.progress)}}
 nextStep(){return this.steps[Math.min(this.next,this.steps.length-1)]}
 prefetch(){const s=this.nextStep();return [instruction(s,this.lang,'early',120),instruction(s,this.lang,'now'),instruction(s,this.lang,'continue',s.meters)].filter(Boolean)}
 update(fix,now=Date.now()){
  const events=[];if(this.arrived)return {...this.last,events};
  const p=[fix.lat,fix.lon];if(!p.every(Number.isFinite)||!Number.isFinite(fix.accuracy)||fix.accuracy>50){
   if(!this.weak)events.push(this.event('weak',t(this.lang).weak,90));this.weak=true;this.off=0;return {...this.last,weak:true,events,arrived:false};
  }
  this.weak=false;const snap=project(p,this.route.coords);
  if(snap.distance>40){this.off++;if(this.off>=3&&!this.recalculating){this.recalculating=true;events.push(this.event('reroute',t(this.lang).reroute,90))}return {...this.last,weak:false,offRoute:true,offDistance:snap.distance,events,reroute:this.recalculating}}
  this.off=0;this.progress=Math.max(this.progress,snap.along);
  let remaining=Math.max(0,this.total-this.progress);
  if(distance(p,[this.dest.lat,this.dest.lon])<=25){this.arrived=true;events.push(this.event('arrival',t(this.lang).arrived,100));return this.last={remaining_m:0,remaining_min:0,next_instruction:t(this.lang).arrived,arrived:true,weak:false,events,snapped:snap.point}}
  while(this.next<this.steps.length-1 && distance(p,[this.nextStep().lat,this.nextStep().lon])<=20 && this.progress>=this.nextStep().along-20){
   const passed=this.nextStep();this.next++;
   const good=this.lang==='hi'?'अच्छा, सीधे चलते रहिए।':this.lang==='kn'?'ಸರಿ, ನೇರವಾಗಿ ಹೋಗಿ.':'Good, keep going straight.';
   events.push(this.event('passed',good,40));if(passed.meters>0)events.push(this.event('continue',instruction(passed,this.lang,'continue',passed.meters),30));
   if(['roundabout','fork','end of road','rotary'].includes(passed.action)){events.push(this.event('safety',t(this.lang).safety,20));this.lastSafety=now}
  }
  const s=this.nextStep(),toStep=Math.max(0,s.along-this.progress),key=this.next;
  if(s.action!=='arrive'){
   if(toStep<=120&&toStep>35&&!this.announced.has('early'+key)){this.announced.add('early'+key);events.push(this.event('early',instruction(s,this.lang,'early',toStep),50))}
   if(toStep<=35&&!this.announced.has('now'+key)){this.announced.add('now'+key);events.push(this.event('now',instruction(s,this.lang,'now'),100))}
  }
  if(now-this.lastSafety>=300000){events.push(this.event('safety',t(this.lang).safety,20));this.lastSafety=now}
  const eta=Math.max(1,Math.ceil(this.route.duration_min*remaining/Math.max(1,this.total)));
  return this.last={remaining_m:Math.round(remaining),remaining_min:eta,next_instruction:instruction(s,this.lang,'early',toStep),next_step:s,next_m:Math.round(toStep),arrow:arrow(s),snapped:snap.point,weak:false,offRoute:false,arrived:false,events};
 }
}
