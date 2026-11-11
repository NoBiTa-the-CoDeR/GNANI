// One browser permission request per controller lifetime, with one reusable watch.
export function createLocationController(browser,onPosition,onStatus,onFailure,onPermission=()=>{}){
 let requested=false,denied=false,watchId=null,starting=false,lastGoodAt=0;
 return {
  async start(){
   if(watchId!==null||starting||denied)return;starting=true;
   try{
    if(!browser.geolocation){onStatus('Location unavailable');onFailure('unavailable');return}
    let permission='unknown';
    try{permission=(await browser.permissions?.query({name:'geolocation'}))?.state||'unknown'}catch{}
    onPermission(permission);
    if(permission==='denied'){denied=true;onStatus('Location is off. You can enable it in browser settings.');onFailure('denied');return}
    if(requested&&permission==='prompt'){onStatus('Location permission has expired. Please enable it in browser settings.');onFailure('unavailable');return}
    requested=true;onStatus('Location helps me guide you from where you are.');
    watchId=browser.geolocation.watchPosition(p=>{lastGoodAt=Date.now();const c=p.coords;onStatus(c.accuracy>50?'GPS is weak. Please stand still.':'Location is on');onPosition({lat:c.latitude,lon:c.longitude,accuracy:c.accuracy})},e=>{if(e.code!==1&&Date.now()-lastGoodAt<15000)return;if(e.code===1){denied=true;if(watchId!==null)browser.geolocation.clearWatch(watchId);watchId=null}onStatus(e.code===1?'Location is off. Enable it in browser settings.':'Location is unavailable. Please pause somewhere safe.');onFailure(e.code===1?'denied':'unavailable')},{enableHighAccuracy:true,maximumAge:2000,timeout:20000});
   }finally{starting=false}
  },
  stop(){if(watchId!==null)browser.geolocation.clearWatch(watchId);watchId=null}
 }
}
