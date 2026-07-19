import { useEffect, useRef, useState } from "react"
import { Mic, Send, Square, Volume2, VolumeX, RotateCcw } from "lucide-react"
import Orb from "./Orb"
import { connect } from "../lib/ws"
import { recordUntilStop, blobToBase64, playAudio, stopAudio, makeAnalyser } from "../lib/audio"

// Long URLs wreck the bubble layout, so render them as short clickable
// labels (domain + /… when there's a path) pointing at the full link.
const URL_RE=/https?:\/\/\S+/g
function renderText(text){
  if(typeof text!=="string"||!text)return text
  const parts=[]; let last=0, m
  const re=new RegExp(URL_RE)
  while((m=re.exec(text))){
    if(m.index>last)parts.push(text.slice(last,m.index))
    const trail=m[0].match(/[).,;:!?'"»]+$/)?.[0]??""
    const url=trail?m[0].slice(0,-trail.length):m[0]
    let label; try{ const u=new URL(url)
      label=u.hostname.replace(/^www\./,"")+(u.pathname!=="/"||u.search?"/…":"") }
    catch{ label=url.slice(0,32)+"…" }
    parts.push(<a key={parts.length} href={url} target="_blank" rel="noreferrer"
      className="underline decoration-dotted underline-offset-2 hover:text-white">{label}</a>)
    if(trail)parts.push(trail)
    last=m.index+m[0].length
  }
  if(last<text.length)parts.push(text.slice(last))
  return parts
}

export default function Chat() {
  const [messages,setMessages]=useState([]),[input,setInput]=useState(""),[voice,setVoice]=useState(true)
  const [recording,setRecording]=useState(false),[speaking,setSpeaking]=useState(false),[connected,setConnected]=useState(false)
  const [toolStatus,setToolStatus]=useState(null),[talking,setTalking]=useState(false)
  const audioQueueRef=useRef(Promise.resolve()),audioEpochRef=useRef(0)
  const [analyser]=useState(()=>makeAnalyser())
  const wsRef=useRef(null),recRef=useRef(null),pendingRef=useRef(""),scrollRef=useRef(null)

  useEffect(()=>{
    const ws=connect({
      transcript:m=>setMessages(xs=>[...xs,{role:"user",text:m.text}]),
      notice:m=>setMessages(xs=>[...xs,{role:"assistant",text:m.text}]),
      delta:m=>{ setToolStatus(null); setTalking(true); pendingRef.current+=m.text; setMessages(xs=>{ const last=xs[xs.length-1]
        if(last?.role==="assistant"&&last.streaming)return[...xs.slice(0,-1),{...last,text:pendingRef.current}]
        return[...xs,{role:"assistant",text:pendingRef.current,streaming:true}] }) },
      tool:m=>setToolStatus(m.name),
      audio:m=>{ const epoch=audioEpochRef.current
        audioQueueRef.current=audioQueueRef.current.then(async()=>{
          if(epoch!==audioEpochRef.current)return
          setSpeaking(true); try{await playAudio(m.audio_b64,analyser)}catch{}finally{setSpeaking(false)} }) },
      done:()=>{ setToolStatus(null); setTalking(false); pendingRef.current=""; setMessages(xs=>xs.map(m=>({...m,streaming:false}))) },
      error:m=>{ setTalking(false); setToolStatus(null); setMessages(xs=>[...xs,{role:"system",text:m.message??"connection lost — is the backend running?"}]) },
      close:()=>setConnected(false),
    })
    ws.raw.onopen=()=>setConnected(true); wsRef.current=ws; return()=>ws.close()
  },[analyser])

  useEffect(()=>{ scrollRef.current?.scrollTo({top:scrollRef.current.scrollHeight,behavior:"smooth"}) },[messages])

  const bargeIn=()=>{ audioEpochRef.current++; stopAudio(); setSpeaking(false) }

  const sendText=()=>{ const t=input.trim(); if(!t||!wsRef.current)return
    bargeIn()
    setMessages(xs=>[...xs,{role:"user",text:t}]); wsRef.current.sendText(t,voice); setInput("") }

  const toggleRecord=async()=>{
    if(recording){recRef.current?.stop();setRecording(false);return}
    bargeIn()
    const rec=await recordUntilStop(async blob=>{ const b64=await blobToBase64(blob); wsRef.current?.sendAudio(b64,voice) })
    recRef.current=rec; setRecording(true)
  }

  const reset=()=>{ wsRef.current?.reset(); setMessages([]); pendingRef.current="" }

  const onGesture=action=>{
    if(action==="mic")toggleRecord()
    else if(action==="voice_on")setVoice(true)
    else if(action==="voice_off")setVoice(false)
    else if(action==="hush")bargeIn()
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected?"bg-emerald-400":"bg-red-400"}`}/>
          <span className="text-sm tracking-widest text-white/60">WEDNESDAY</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={()=>setVoice(v=>!v)} className="rounded-md p-2 text-white/60 hover:bg-white/5 hover:text-white">
            {voice?<Volume2 size={16}/>:<VolumeX size={16}/>}
          </button>
          <button onClick={reset} className="rounded-md p-2 text-white/60 hover:bg-white/5 hover:text-white">
            <RotateCcw size={16}/>
          </button>
        </div>
      </header>
      <div className="min-h-0 flex-1">
        <Orb analyser={analyser} active={speaking||recording} talking={talking&&!speaking} onGesture={onGesture}/>
      </div>
      <div ref={scrollRef} className="mx-auto max-h-[36vh] w-full max-w-2xl overflow-y-auto px-4 pb-2">
        {messages.map((m,i)=>(
          <div key={i} className={`my-2 flex ${m.role==="user"?"justify-end":"justify-start"}`}>
            <div className={`max-w-[80%] break-words [overflow-wrap:anywhere] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
              m.role==="user"?"bg-white/[0.06] text-white":m.role==="system"?"bg-red-500/10 text-red-300":"bg-purple-500/10 text-purple-100"}`}>
              {renderText(m.text)}
            </div>
          </div>
        ))}
        {toolStatus&&(
          <div className="my-2 flex justify-start">
            <div className="max-w-[80%] rounded-2xl px-4 py-2 text-sm italic text-white/40">using {toolStatus}…</div>
          </div>
        )}
      </div>
      <div className="mx-auto flex w-full max-w-2xl items-center gap-2 border-t border-white/5 bg-black/20 p-3">
        <button onClick={toggleRecord}
          className={`rounded-full p-3 transition ${recording?"bg-red-500 text-white":"bg-white/[0.06] text-white/70 hover:bg-white/10"}`}>
          {recording?<Square size={18}/>:<Mic size={18}/>}
        </button>
        <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&sendText()}
          placeholder="Talk to Wednesdayâ€¦"
          className="flex-1 rounded-full border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-white placeholder-white/30 outline-none focus:border-purple-400/40"/>
        <button onClick={sendText} disabled={!input.trim()}
          className="rounded-full bg-purple-500 p-3 text-white disabled:opacity-30 hover:bg-purple-400">
          <Send size={18}/>
        </button>
      </div>
    </div>
  )
}