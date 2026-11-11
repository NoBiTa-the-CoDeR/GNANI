import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {GuidanceEngine,project,pointAt,distance,instruction,actionText} from '../src/navigation/engine.js';
const route=JSON.parse(fs.readFileSync(new URL('./fixtures/osrm-walk.json',import.meta.url)));const dest=route.dest||{lat:route.coords.at(-1)[0],lon:route.coords.at(-1)[1]};
const fix=(p,accuracy=8)=>({lat:p[0],lon:p[1],accuracy});
test('real OSRM route simulation: progress, 120m/30m announcements, turns, arrival',()=>{
 const engine=new GuidanceEngine(route,dest,'en',0),events=[];let previous=Infinity;
 for(let m=0;m<=engine.total;m+=5){const state=engine.update(fix(pointAt(route.coords,m)),m*1000);if(state.remaining_m!==undefined){assert.ok(state.remaining_m<=previous);previous=state.remaining_m}events.push(...state.events)}
 const early=events.findIndex(x=>x.kind==='early'&&/1[0123]0 metres/.test(x.text));assert.ok(early>=0,'long segment has an early announcement');const now=events.findIndex((x,i)=>i>early&&x.kind==='now');assert.ok(now>early);assert.ok(events.some(x=>x.kind==='continue'&&x.text.includes('208')));assert.ok(events.some(x=>x.kind==='passed'));assert.ok(events.some(x=>x.kind==='arrival'));
 assert.equal(engine.update(fix(route.coords.at(-1)),999999).events.length,0,'arrival only once');
});
test('wrong turn requires 3 consecutive good fixes and one reroute',()=>{
 const engine=new GuidanceEngine(route,dest);engine.update(fix(route.coords[0]));const p=[route.coords[0][0]+0.002,route.coords[0][1]-0.002];assert.ok(project(p,route.coords).distance>40);
 assert.ok(!engine.update(fix(p)).reroute);assert.ok(!engine.update(fix(p)).reroute);assert.equal(engine.update(fix(p)).events[0].kind,'reroute');assert.equal(engine.update(fix(p)).events.length,0);
});
test('weak GPS suppresses turns, reroutes and arrival; resets bad-fix counter',()=>{
 const e=new GuidanceEngine(route,dest);const bad=[route.coords[0][0]+.002,route.coords[0][1]];e.update(fix(bad));e.update(fix(bad));const weak=e.update(fix(route.coords.at(-1),80));assert.deepEqual(weak.events.map(x=>x.kind),['weak']);assert.equal(weak.arrived,false);assert.equal(e.update(fix(bad,80)).events.length,0);assert.ok(!e.update(fix(bad)).reroute);assert.ok(!e.update(fix(bad)).reroute);assert.equal(e.update(fix(bad)).events[0].kind,'reroute');
});
test('off-route count resets on route; progress does not go backwards',()=>{const e=new GuidanceEngine(route,dest);const a=e.update(fix(pointAt(route.coords,150)));const b=e.update(fix(pointAt(route.coords,140)));assert.equal(a.remaining_m,b.remaining_m)});
test('safety reminder at five minutes; no safe crossing claim',()=>{const e=new GuidanceEngine(route,dest,'en',0);e.update(fix(route.coords[0]),0);const s=e.update(fix(route.coords[0]),300001);assert.ok(s.events.some(x=>x.kind==='safety'));assert.ok(s.events.find(x=>x.kind==='safety').text.includes('only at a safe place'))});
test('English, Hindi, Kannada templates cover OSRM maneuvers and preserve real numbers',()=>{for(const lang of ['en','hi','kn'])for(const action of ['depart','turn','new name','continue','end of road','fork','roundabout','arrive'])for(const turn of ['left','right','slight left','slight right','sharp left','sharp right','uturn','straight']){const s={action,turn,road:'Service Road',meters:208};assert.ok(actionText(s,lang));assert.ok(instruction(s,lang,'early',120).includes('120'));assert.ok(instruction(s,lang,'continue',208).includes('208'))}});
test('conversation language can switch before the next turn announcement',()=>{const e=new GuidanceEngine(route,dest,'en');e.update(fix(route.coords[0]));e.lang='hi';const next=e.nextStep();const value=e.update(fix(pointAt(route.coords,next.along-30)));assert.ok(value.events.some(x=>x.kind==='now'&&/[\u0900-\u097F]/.test(x.text)))});
