const AC = window.AudioContext || window.webkitAudioContext
export function makeAnalyser() {
  let ctx=null,analyser=null,raf=0; const subs=new Set(); let level=0
  const tick=()=>{ if(!analyser)return; const data=new Uint8Array(analyser.frequencyBinCount)
    analyser.getByteTimeDomainData(data); let sum=0
    for(let i=0;i<data.length;i++){const v=(data[i]-128)/128;sum+=v*v}
    level=Math.min(1,Math.sqrt(sum/data.length)*2.5); subs.forEach(cb=>cb(level)); raf=requestAnimationFrame(tick) }
  return {
    attach(src){ctx=src.context;analyser=ctx.createAnalyser();analyser.fftSize=512;src.connect(analyser);cancelAnimationFrame(raf);tick()},
    detach(){cancelAnimationFrame(raf);analyser=null;level=0;subs.forEach(cb=>cb(0))},
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
export function playMp3(b64,analyser){
  return new Promise((resolve,reject)=>{
    const audio=new Audio("data:audio/mpeg;base64,"+b64)
    const ctx=new AC(); const source=ctx.createMediaElementSource(audio)
    source.connect(ctx.destination); if(analyser)analyser.attach(source)
    audio.onended=async()=>{if(analyser)analyser.detach();await ctx.close();resolve()}
    audio.onerror=reject; audio.play().catch(reject)
  })
}
export async function blobToBase64(blob){
  const buf=await blob.arrayBuffer(); const bytes=new Uint8Array(buf); let bin=""
  for(let i=0;i<bytes.length;i++)bin+=String.fromCharCode(bytes[i]); return btoa(bin)
}