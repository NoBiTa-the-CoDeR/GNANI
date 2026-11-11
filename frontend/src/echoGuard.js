// AEC is the first line of defense. This rejects residual copies of the
// exact assistant PCM across a range of acoustic delays before VAD/upload.
export function echoCorrelation(input,reference,time,rate){
 if(!reference?.length)return 0;let best=0;
 const sample=8;
 for(let delay=0;delay<=.32;delay+=.008){
  const start=Math.round((time-delay)*rate)-input.length;if(start<0||start+input.length>=reference.length)continue;
  let xy=0,xx=0,yy=0;
  for(let i=0;i<input.length;i+=sample){const x=input[i],y=reference[start+i];xy+=x*y;xx+=x*x;yy+=y*y}
  if(xx>1e-7&&yy>1e-7)best=Math.max(best,Math.abs(xy/Math.sqrt(xx*yy)));
 }
 return best;
}
export function isEcho(input,reference,time,rate){return echoCorrelation(input,reference,time,rate)>.72}
