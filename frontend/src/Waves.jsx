import React,{useRef,useEffect} from 'react';
export default function Waves({signal}){
 const canvas=useRef(null);
 useEffect(()=>{const c=canvas.current,ctx=c.getContext('2d'),reduced=matchMedia('(prefers-reduced-motion: reduce)');let raf,last=0,level=0;const data=new Uint8Array(128),bands=[0,0,0],interval=navigator.hardwareConcurrency<=4?50:34;
  function resize(){const ratio=Math.min(devicePixelRatio||1,1.5);c.width=innerWidth*ratio;c.height=innerHeight*ratio;ctx.setTransform(ratio,0,0,ratio,0,0)}resize();addEventListener('resize',resize);
  function draw(time){raf=requestAnimationFrame(draw);if(document.hidden||time-last<interval)return;const dt=Math.min(100,time-last);last=time;let target=0;const quiet=reduced.matches||document.documentElement.dataset.calm==='true',s=quiet?{}:signal.current,targets=[0,0,0];const readBands=(count,weight)=>{const width=Math.max(1,Math.floor(count/3));for(let i=0;i<3;i++){const part=data.slice(i*width,(i+1)*width);targets[i]=Math.max(targets[i],part.reduce((a,b)=>a+b,0)/(part.length*255)*weight)}};
   if(s?.analyser){s.analyser.getByteFrequencyData(data);target=data.reduce((a,b)=>a+b,0)/(data.length*255);readBands(s.analyser.frequencyBinCount,1)}
   if(s?.speechAnalyser&&s?.speechAudio&&!s.speechAudio.paused){s.speechAnalyser.getByteFrequencyData(data);target+=data.reduce((a,b)=>a+b,0)/(data.length*255)*.3;readBands(s.speechAnalyser.frequencyBinCount,.3)}
   if(s?.youtubePlaying)target=Math.max(target,.16+.07*Math.sin(time/700));level+=(target-level)*Math.min(1,dt/600);for(let i=0;i<3;i++)bands[i]+=(targets[i]-bands[i])*Math.min(1,dt/600);c.dataset.amplitude=level.toFixed(3);
   ctx.clearRect(0,0,innerWidth,innerHeight);const motion=(reduced.matches||document.documentElement.dataset.calm==='true')?0:time/4500,amplitude=(reduced.matches||document.documentElement.dataset.calm==='true')?12:16+Math.min(.7,level)*130;
   for(let layer=0;layer<4;layer++){const band=layer%3,wavelength=[.5,.32,.14][band],pace=[.7,1,1.5][band];ctx.beginPath();for(let x=0;x<=innerWidth+8;x+=8){const y=innerHeight*(.55+layer*.08)+Math.sin(x/(innerWidth*wavelength)-motion*pace+layer*.8)*amplitude*(quiet?1:1+bands[band])+Math.cos(x/(innerWidth*.22)-motion*.6)*amplitude*.3;x?ctx.lineTo(x,y):ctx.moveTo(x,y)}ctx.lineTo(innerWidth,innerHeight);ctx.lineTo(0,innerHeight);ctx.closePath();ctx.fillStyle=['#edba7f22','#e8a56d20','#d58b5f1c','#b7664d15'][layer];ctx.fill()}
  }raf=requestAnimationFrame(draw);return()=>{cancelAnimationFrame(raf);removeEventListener('resize',resize)};
 },[signal]);return <canvas ref={canvas} className="warm-waves" aria-hidden="true"/>;
}
