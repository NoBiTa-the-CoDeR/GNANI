// One permission prompt, one live watch, and replayable fixes after reconnection.
export function createLocationController(browser,onPosition,onStatus,onFailure,onPermission=()=>{}){
 let requested=false,denied=false,watchId=null,starting=false,lastGoodAt=0,latest=null;
 function fail(reason){onFailure(reason)}
 return {
  async start(){
   if(starting)return;
   if(watchId!==null){if(latest&&Date.now()-lastGoodAt<30000)onPosition(latest);else if(lastGoodAt)fail('unavailable');return}
   starting=true;
   try{
    if(!browser.geolocation){onStatus('Location unavailable. Enter your starting place below.');fail('unavailable');return}
    let permission='unknown';
    try{permission=(await browser.permissions?.query({name:'geolocation'}))?.state||'unknown'}catch{}
    onPermission(permission);
    if(permission==='denied'||(denied&&permission!=='granted')){if(!denied)onStatus('Location is off. Enable it in browser settings, or enter your starting place below.');denied=true;fail('denied');return}
    if(requested&&permission==='prompt'){onStatus('Location permission has expired. Enable it in browser settings, or enter your starting place below.');fail('unavailable');return}
    denied=false;requested=true;onStatus('Location helps me guide you from where you are.');
    watchId=browser.geolocation.watchPosition(p=>{const c=p.coords;if(!Number.isFinite(c.latitude)||!Number.isFinite(c.longitude)||!Number.isFinite(c.accuracy)||Math.abs(c.latitude)>90||Math.abs(c.longitude)>180||c.accuracy<0)return;lastGoodAt=Date.now();latest={lat:c.latitude,lon:c.longitude,accuracy:c.accuracy,timestamp:p.timestamp||Date.now()};onStatus(c.accuracy>50?'GPS is weak. Please stand still, or enter a starting place.':'Location is on');onPosition(latest)},e=>{if(e.code!==1&&Date.now()-lastGoodAt<15000)return;if(e.code===1){denied=true;latest=null;if(watchId!==null)browser.geolocation.clearWatch(watchId);watchId=null}latest=null;onStatus(e.code===1?'Location is off. Enable it in browser settings, or enter your starting place below.':'Location is unavailable. Enter your starting place below.');fail(e.code===1?'denied':'unavailable')},{enableHighAccuracy:true,maximumAge:2000,timeout:20000});
   }finally{starting=false}
  },
  stop(){if(watchId!==null)browser.geolocation.clearWatch(watchId);watchId=null},
  latest:()=>latest
 }
}
