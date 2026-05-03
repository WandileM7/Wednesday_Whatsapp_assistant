import { useEffect, useRef, useState } from "react"
import { Mic, Send, Square, Volume2, VolumeX, RotateCcw } from "lucide-react"
import PixelSprite from "./PixelSprite"
import { connect } from "../lib/ws"
import { recordUntilStop, blobToBase64, playMp3, makeAnalyser } from "../lib/audio"

export default function Chat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [voice, setVoice] = useState(true)
  const [recording, setRecording] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [connected, setConnected] = useState(false)
  const [micError, setMicError] = useState(null)
  const [analyser] = useState(() => makeAnalyser())

  const wsRef = useRef(null)
  const recRef = useRef(null)
  const pendingRef = useRef('')
  const scrollRef = useRef(null)

  useEffect(() => {
    const ws = connect({
      transcript: m => setMessages(xs => [...xs, { role: 'user', text: m.text }]),
      delta: m => {
        pendingRef.current += m.text
        setMessages(xs => {
          const last = xs[xs.length - 1]
          if (last?.role === 'assistant' && last.streaming)
            return [...xs.slice(0, -1), { ...last, text: pendingRef.current }]
          return [...xs, { role: 'assistant', text: pendingRef.current, streaming: true }]
        })
      },
      audio: async m => {
        setSpeaking(true)
        try { await playMp3(m.audio_b64, analyser) } finally { setSpeaking(false) }
      },
      done: () => {
        pendingRef.current = ''
        setMessages(xs => xs.map(m => ({ ...m, streaming: false })))
      },
      error: m => setMessages(xs => [...xs, { role: 'system', text: m.message || String(m) }]),
      close: () => setConnected(false),
    })
    ws.raw.onopen = () => setConnected(true)
    wsRef.current = ws
    return () => ws.close()
  }, [analyser])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const sendText = () => {
    const t = input.trim()
    if (!t || !wsRef.current) return
    if (wsRef.current.raw.readyState !== WebSocket.OPEN) return
    setMessages(xs => [...xs, { role: 'user', text: t }])
    wsRef.current.sendText(t, voice)
    setInput('')
  }

  const toggleRecord = async () => {
    if (recording) {
      recRef.current?.stop()
      setRecording(false)
      return
    }
    setMicError(null)
    try {
      const rec = await recordUntilStop(async blob => {
        const b64 = await blobToBase64(blob)
        wsRef.current?.sendAudio(b64, voice)
      })
      recRef.current = rec
      setRecording(true)
    } catch (err) {
      const msg = err.name === 'NotAllowedError'
        ? 'Microphone permission denied.'
        : `Mic error: ${err.message}`
      setMicError(msg)
      setMessages(xs => [...xs, { role: 'system', text: msg }])
    }
  }

  const reset = () => {
    wsRef.current?.reset()
    setMessages([])
    pendingRef.current = ''
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
          <span className="text-sm tracking-widest text-white/60">WEDNESDAY</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setVoice(v => !v)}
            className="rounded-md p-2 text-white/60 hover:bg-white/5 hover:text-white">
            {voice ? <Volume2 size={16} /> : <VolumeX size={16} />}
          </button>
          <button onClick={reset}
            className="rounded-md p-2 text-white/60 hover:bg-white/5 hover:text-white">
            <RotateCcw size={16} />
          </button>
        </div>
      </header>

      <div className="flex flex-1 items-center justify-center">
        <PixelSprite analyser={analyser} speaking={speaking || recording} />
      </div>

      <div ref={scrollRef} className="max-h-[36vh] overflow-y-auto px-4 pb-2">
        {messages.map((m, i) => (
          <div key={i} className={`my-2 flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-relaxed
              ${m.role === 'user'
                ? 'bg-white/[0.06] text-white'
                : m.role === 'system'
                ? 'bg-red-500/10 text-red-300'
                : 'bg-purple-500/10 text-purple-100'}`}>
              {m.text}
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 border-t border-white/5 bg-black/20 p-3">
        <button onClick={toggleRecord}
          className={`rounded-full p-3 transition ${recording
            ? 'bg-red-500 text-white'
            : 'bg-white/[0.06] text-white/70 hover:bg-white/10'}`}>
          {recording ? <Square size={18} /> : <Mic size={18} />}
        </button>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && sendText()}
          placeholder="Talk to Wednesday..."
          className="flex-1 rounded-full border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm
                     text-white placeholder-white/30 outline-none focus:border-purple-400/40"
        />
        <button onClick={sendText} disabled={!input.trim() || !connected}
          className="rounded-full bg-purple-500 p-3 text-white disabled:opacity-30 hover:bg-purple-400">
          <Send size={18} />
        </button>
      </div>
    </div>
  )
}
