const AC = window.AudioContext || window.webkitAudioContext
export function makeAnalyser() {
  let ctx=null,analyser=null,raf=0,attached=false; const subs=new Set(); let level=0
  const tick=()=>{ if(!analyser)return; const data=new Uint8Array(analyser.frequencyBinCount)
    analyser.getByteTimeDomainData(data); let sum=0
    for(let i=0;i<data.length;i++){const v=(data[i]-128)/128;sum+=v*v}
    level=Math.min(1,Math.sqrt(sum/data.length)*2.5); subs.forEach(cb=>cb(level)); raf=requestAnimationFrame(tick) }
  return {
    attach(src){attached=true;ctx=src.context;analyser=ctx.createAnalyser();analyser.fftSize=512;src.connect(analyser);cancelAnimationFrame(raf);tick()},
    detach(){attached=false;cancelAnimationFrame(raf);analyser=null;level=0;subs.forEach(cb=>cb(0))},
    // Feed an externally measured level (e.g. the mic while listening) so the
    // orb tracks the user's voice — ignored while a real audio node is attached
    // (Wednesday's own playback drives it then).
    push(l){ if(attached)return; level=Math.min(1,l); subs.forEach(cb=>cb(level)) },
    subscribe(cb){subs.add(cb);return()=>subs.delete(cb)},
  }
}
export async function recordUntilStop(onStop) {
  const stream=await navigator.mediaDevices.getUserMedia({audio:true})
  const ctx=new AC(); const source=ctx.createMediaStreamSource(stream)
  const analyser=makeAnalyser(); analyser.attach(source)
  const mr=new MediaRecorder(stream,{mimeType:"audio/webm"}); const chunks=[]
  mr.ondataavailable=e=>e.data.size&&chunks.push(e.data)
  mr.onstop=async()=>{ analyser.detach(); stream.getTracks().forEach(t=>t.stop()); await ctx.close(); onStop(new Blob(chunks,{type:"audio/webm"})) }
  mr.start(); return {stop:()=>mr.state!=="inactive"&&mr.stop(),analyser}
}
// `armed` (optional) decides whether an utterance is actually delivered — the
// wake word uses it to keep the room's conversation out of the transcript.
// `speaking` (optional) reports when Wednesday's own TTS is playing so we run
// half-duplex: while she talks we raise the bar to a barge-in threshold (so her
// voice bleeding into the mic doesn't feed a self-conversation), and we never
// deliver a segment that ended while she was still speaking. A loud, deliberate
// interruption still clears the bar → onSpeechStart barges her, then your words
// land once she's stopped.
export async function listenContinuously(onUtterance,{threshold=0.06,bargeThreshold=0.15,hangoverMs=900,minMs=420,onSpeechStart,onLevel,armed,speaking}={}){
  const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}})
  const ctx=new AC(); const source=ctx.createMediaStreamSource(stream)
  const analyser=ctx.createAnalyser(); analyser.fftSize=512; source.connect(analyser)
  const data=new Uint8Array(analyser.frequencyBinCount)
  let mr=null,chunks=[],speechStart=0,lastVoice=0,stopped=false
  const level=()=>{ analyser.getByteTimeDomainData(data); let s=0
    for(let i=0;i<data.length;i++){const v=(data[i]-128)/128;s+=v*v}
    return Math.sqrt(s/data.length)*2.5 }
  const loop=()=>{ if(stopped)return
    const now=performance.now(), l=level()
    onLevel?.(l)
    // While Wednesday speaks, only a loud interruption should register.
    const th=(speaking&&speaking())?bargeThreshold:threshold
    if(l>th){ lastVoice=now
      if(!mr){ speechStart=now; chunks=[]
        mr=new MediaRecorder(stream,{mimeType:"audio/webm"})
        mr.ondataavailable=e=>e.data.size&&chunks.push(e.data)
        mr.onstop=()=>{ const dur=lastVoice-speechStart
          // Deliver only real, armed speech that didn't end mid-playback (which
          // would be Wednesday hearing herself).
          if(dur>=minMs&&!stopped&&(!armed||armed())&&!(speaking&&speaking()))onUtterance(new Blob(chunks,{type:"audio/webm"}))
          mr=null }
        // Recording always runs so the wake word's own utterance is captured;
        // only delivery and barge-in wait for the gate.
        mr.start(); if(!armed||armed())onSpeechStart?.() } }
    else if(mr&&now-lastVoice>hangoverMs)mr.stop()
    requestAnimationFrame(loop) }
  loop()
  // `stream` is exposed so the wake word can read the same mic rather than
  // opening a second one (two getUserMedia streams fight over the device).
  return {stream, stop(){ stopped=true; if(mr&&mr.state!=="inactive")mr.stop()
    stream.getTracks().forEach(t=>t.stop()); ctx.close() }}
}
let currentAudio=null
export function playAudio(b64,analyser,mime="audio/wav"){
  return new Promise((resolve,reject)=>{
    const audio=new Audio(`data:${mime};base64,`+b64)
    const ctx=new AC(); const source=ctx.createMediaElementSource(audio)
    source.connect(ctx.destination); if(analyser)analyser.attach(source)
    currentAudio=audio
    audio.onended=async()=>{if(currentAudio===audio)currentAudio=null
      if(analyser)analyser.detach();await ctx.close();resolve()}
    audio.onerror=reject; audio.play().catch(reject)
  })
}
export function stopAudio(){
  const a=currentAudio; if(!a)return
  currentAudio=null; a.pause(); a.onended?.()
}
export async function blobToBase64(blob){
  const buf=await blob.arrayBuffer(); const bytes=new Uint8Array(buf); let bin=""
  for(let i=0;i<bytes.length;i++)bin+=String.fromCharCode(bytes[i]); return btoa(bin)
}