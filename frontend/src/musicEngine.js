// Loaded only after a user taps Play. All music is generated on this device.
export async function createBacking(mood='calm'){
 const Tone=await import('tone');await Tone.start();
 const moods={calm:{bpm:56,notes:['C4','D4','E4','G4','A4'],chord:['C3','E3','G3']},happy:{bpm:82,notes:['G4','A4','B4','D5','E5'],chord:['G3','B3','D4']},sleepy:{bpm:42,notes:['C4','D4','F4','G4','A4'],chord:['F2','A2','C3']},devotional:{bpm:60,notes:['D4','E4','G4','A4','B4'],chord:['D3','G3','A3']}};
 const plan=moods[mood]||moods.calm,master=new Tone.Gain(.5).toDestination(),analyser=Tone.getContext().rawContext.createAnalyser();analyser.fftSize=256;Tone.connect(master,analyser);
 const reverb=new Tone.Reverb({decay:2,wet:.2}).connect(master),bass=new Tone.MonoSynth({oscillator:{type:'sine'},envelope:{attack:.05,decay:.3,sustain:.2,release:.4}}).connect(master),percussion=new Tone.MembraneSynth({volume:-30}).connect(master);
 const pad=new Tone.PolySynth(Tone.Synth,{oscillator:{type:'sine'},envelope:{attack:1.5,decay:.5,sustain:.55,release:2}}).connect(reverb),melody=new Tone.Synth({oscillator:{type:'triangle'},envelope:{attack:.3,decay:.5,sustain:.2,release:1.5}}).connect(master);
 let step=0,paused=false,timer,disposed=false;const pattern=[0,2,1,3,2,4,3,1];
 function tick(){if(disposed||paused)return;const now=Tone.now();if(step%8===0)pad.triggerAttackRelease(plan.chord,60/plan.bpm*7,now,.16);melody.triggerAttackRelease(plan.notes[pattern[step%8]],60/plan.bpm*1.2,now,.16);if(step%2===0)bass.triggerAttackRelease(plan.chord[0],.3,now,.13);if(step%4===0&&mood!=='sleepy')percussion.triggerAttackRelease('C1',.05,now,.08);step++;timer=setTimeout(tick,120000/plan.bpm)}tick();
 return {analyser,pause(){paused=true;clearTimeout(timer);pad.releaseAll();melody.triggerRelease()},play(){if(paused&&!disposed){paused=false;tick()}},volume(v){master.gain.rampTo(v,.2)},stop(){disposed=true;clearTimeout(timer);pad.dispose();melody.dispose();bass.dispose();percussion.dispose();reverb.dispose();master.dispose();analyser.disconnect()}};
}
