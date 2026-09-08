import { useCallback, useEffect, useRef, useState } from "react"
import { connect } from "../lib/ws"
import { ttsSpeak } from "../lib/api"
import {
  recordUntilStop, listenContinuously, blobToBase64,
  playAudio, stopAudio, makeAnalyser,
} from "../lib/audio"
import { attachWakeWord } from "../lib/wakeWord"

const WAKE_MODEL = import.meta.env.VITE_WAKE_WORD || ""
// How long the wake acknowledgement overlay flashes. The audio session itself
// no longer auto-closes — it stays open until you cancel it or tell Wednesday
// to close the mic (matched server-side, see backend/voice_commands.py).
const WAKE_FLASH_MS = 2500

// Short, in-character things Wednesday says the instant the wake word lands —
// the Siri/Gemini "I'm listening" acknowledgement, spoken before you've even
// finished your sentence.
const WAKE_GREETINGS = ["Mm?", "Go on.", "I'm listening.", "You rang?", "Yes?"]

/**
 * The whole assistant: one persistent WebSocket, chat history, voice I/O and
 * the wake word. Lifted out of the old single-screen Chat so state survives
 * navigating between HUD screens. `onWake` lets the shell pop the command
 * screen up, Siri-style, the moment the wake word fires.
 */
export function useAssistant({ onWake, onNavigate } = {}) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [voice, setVoice] = useState(true)
  const [recording, setRecording] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [connected, setConnected] = useState(false)
  const [toolStatus, setToolStatus] = useState(null)
  const [talking, setTalking] = useState(false)
  const [handsFree, setHandsFree] = useState(false)
  const [armed, setArmed] = useState(false)
  const [wakeFlash, setWakeFlash] = useState(false)

  const listenerRef = useRef(null)
  const fireWakeRef = useRef(null)
  const sleepRef = useRef(null)
  const pendingWakeRef = useRef(false)
  const audioQueueRef = useRef(Promise.resolve())
  const audioEpochRef = useRef(0)
  const [analyser] = useState(() => makeAnalyser())
  const wsRef = useRef(null)
  const recRef = useRef(null)
  const pendingRef = useRef("")
  const onWakeRef = useRef(onWake)
  onWakeRef.current = onWake
  const onNavigateRef = useRef(onNavigate)
  onNavigateRef.current = onNavigate
  // Half-duplex: the mic listener reads this to know when Wednesday's own voice
  // is playing, so it doesn't transcribe her (or let her interrupt herself).
  const speakingRef = useRef(false)
  useEffect(() => { speakingRef.current = speaking }, [speaking])

  useEffect(() => {
    let closedByUs = false, retry = 0, timer = null
    const handlers = {
      transcript: m => setMessages(xs => [...xs, { role: "user", text: m.text, at: Date.now() }]),
      // Server-intercepted voice UI commands (run *before* the model, so they
      // navigate silently with no spoken reply). The backend is the single
      // source of truth for phrase matching — see backend/voice_commands.py.
      nav: m => onNavigateRef.current?.(m.target),
      command: m => { if (m.action === "close_mic") sleepRef.current?.() },
      notice: m => setMessages(xs => [...xs, { role: "assistant", text: m.text, at: Date.now() }]),
      delta: m => {
        setToolStatus(null); setTalking(true); pendingRef.current += m.text
        setMessages(xs => {
          const last = xs[xs.length - 1]
          if (last?.role === "assistant" && last.streaming)
            return [...xs.slice(0, -1), { ...last, text: pendingRef.current }]
          return [...xs, { role: "assistant", text: pendingRef.current, streaming: true, at: Date.now() }]
        })
      },
      tool: m => setToolStatus(m.name),
      audio: m => {
        const epoch = audioEpochRef.current
        audioQueueRef.current = audioQueueRef.current.then(async () => {
          if (epoch !== audioEpochRef.current) return
          setSpeaking(true)
          try { await playAudio(m.audio_b64, analyser) } catch {} finally { setSpeaking(false) }
        })
      },
      done: () => {
        setToolStatus(null); setTalking(false); pendingRef.current = ""
        setMessages(xs => xs.map(m => ({ ...m, streaming: false })))
      },
      error: m => {
        setTalking(false); setToolStatus(null)
        if (typeof m?.message === "string")
          setMessages(xs => [...xs, { role: "system", text: m.message, at: Date.now() }])
      },
      close: () => {
        setConnected(false); if (closedByUs) return
        const delay = Math.min(1000 * 2 ** retry, 15000); retry++; timer = setTimeout(open, delay)
      },
    }
    const open = () => {
      const ws = connect(handlers)
      ws.raw.onopen = () => { setConnected(true); retry = 0 }
      wsRef.current = ws
    }
    open()
    return () => { closedByUs = true; clearTimeout(timer); wsRef.current?.close() }
  }, [analyser])

  const bargeIn = useCallback(() => {
    audioEpochRef.current++; stopAudio(); setSpeaking(false)
  }, [])

  const speak = useCallback(async text => {
    try {
      const b64 = await ttsSpeak(text)
      const epoch = audioEpochRef.current
      audioQueueRef.current = audioQueueRef.current.then(async () => {
        if (epoch !== audioEpochRef.current) return
        setSpeaking(true)
        try { await playAudio(b64, analyser) } catch {} finally { setSpeaking(false) }
      })
    } catch {}
  }, [analyser])

  const sendText = useCallback(text => {
    const t = (typeof text === "string" ? text : input).trim()
    if (!t || !wsRef.current) return
    bargeIn()
    setMessages(xs => [...xs, { role: "user", text: t, at: Date.now() }])
    wsRef.current.sendText(t, voice); setInput("")
  }, [input, voice, bargeIn])

  const toggleRecord = useCallback(async () => {
    if (recording) { recRef.current?.stop(); setRecording(false); return }
    bargeIn()
    const rec = await recordUntilStop(async blob => {
      const b64 = await blobToBase64(blob); wsRef.current?.sendAudio(b64, voice)
    })
    recRef.current = rec; setRecording(true)
  }, [recording, voice, bargeIn])

  const reset = useCallback(() => {
    wsRef.current?.reset(); setMessages([]); pendingRef.current = ""
  }, [])

  const wakeLabel = WAKE_MODEL
    ? WAKE_MODEL.replace(/_v[\d.]+$/, "").replace(/_/g, " ").toUpperCase()
    : "DISABLED"

  // Hands-free continuous listening + wake word. When the wake word fires (or
  // the daemon hands off), we open the audio session, barge in on any playback,
  // greet the user out loud, and notify the shell to surface the command deck.
  // The session then STAYS open — streaming every utterance to the backend —
  // until you cancel it or tell Wednesday to close the mic. Saying the wake
  // word again just re-flashes the acknowledgement.
  useEffect(() => {
    if (!handsFree) { listenerRef.current?.stop(); listenerRef.current = null; fireWakeRef.current = null; sleepRef.current = null; setArmed(false); setWakeFlash(false); return }
    let cancelled = false, wake = null, flashTimer = null
    const armedUntil = { current: WAKE_MODEL ? 0 : Infinity }
    const barge = () => { audioEpochRef.current++; stopAudio(); setSpeaking(false) }
    const sys = text => setMessages(xs => [...xs, { role: "system", text, at: Date.now() }])
    // Open the persistent session: fired by the on-device wake word OR directly
    // by the background daemon (?wake=1) so you never say the word twice.
    const fireWake = () => {
      armedUntil.current = Infinity
      setArmed(true); setWakeFlash(true); barge()
      onWakeRef.current?.()
      speak(WAKE_GREETINGS[Math.floor(Math.random() * WAKE_GREETINGS.length)])
      clearTimeout(flashTimer); flashTimer = setTimeout(() => setWakeFlash(false), WAKE_FLASH_MS)
    }
    // Stand down: end the audio session and return to standby. With a wake word
    // configured we drop back to waiting for it; otherwise we stop streaming
    // until hands-free is re-armed.
    const sleep = () => {
      armedUntil.current = WAKE_MODEL ? 0 : -Infinity
      clearTimeout(flashTimer); setWakeFlash(false); setArmed(false)
      if (WAKE_MODEL) sys(`Mic closed — say “${wakeLabel.toLowerCase()}” to wake me again.`)
      else sys("Mic closed.")
    }
    fireWakeRef.current = fireWake
    sleepRef.current = sleep
    listenContinuously(
      async blob => { const b64 = await blobToBase64(blob); wsRef.current?.sendAudio(b64, true) },
      {
        onSpeechStart: barge,
        armed: () => performance.now() < armedUntil.current,
        speaking: () => speakingRef.current,
        // Drive the orb from the live mic level so it reacts to *you* while
        // listening (Wednesday's playback takes over the orb when she speaks).
        onLevel: l => { if (!speakingRef.current) analyser.push(l * 1.4) },
      },
    ).then(async l => {
      if (cancelled) { l.stop(); return }
      listenerRef.current = l
      // Daemon-initiated wake: open the session immediately, no second word.
      const drainPending = () => { if (pendingWakeRef.current) { pendingWakeRef.current = false; fireWake() } }
      if (!WAKE_MODEL) { sys("Hands-free on — I'm listening to everything you say."); drainPending(); return }
      try {
        wake = await attachWakeWord(l.stream, {
          model: WAKE_MODEL,
          onWake: fireWake,
        })
        if (cancelled) { wake.stop(); return }
        // Confirm the wake word is actually live, so a silent mic looks
        // different from a broken pipeline. Without this a user can't tell
        // "say the word" from "it never loaded".
        sys(`Listening for “${wakeLabel.toLowerCase()}” — say it and I'll wake up.`)
        drainPending()
      } catch (err) {
        console.warn("wake word unavailable", err)
        armedUntil.current = Infinity
        sys("Wake word failed to load — listening to everything instead.")
        drainPending()
      }
    }).catch(err => {
      // getUserMedia rejects when the mic is blocked or missing; say so instead
      // of silently flipping hands-free back off (which looks like nothing).
      console.warn("hands-free mic error", err)
      sys("Microphone blocked — allow mic access in your browser, then arm hands-free again.")
      setHandsFree(false)
    })
    return () => {
      cancelled = true; clearTimeout(flashTimer); wake?.stop()
      fireWakeRef.current = null; sleepRef.current = null; setWakeFlash(false)
      listenerRef.current?.stop(); listenerRef.current = null; setArmed(false)
    }
  }, [handsFree, speak, wakeLabel])

  // Arm the audio session on demand, without a spoken wake word — used by the
  // background daemon's ?wake=1 hand-off so the user talks straight away. If
  // the listener isn't up yet we flag it and drain once hands-free is ready.
  const wakeNow = useCallback(() => {
    setHandsFree(true)
    if (fireWakeRef.current) fireWakeRef.current()
    else pendingWakeRef.current = true
  }, [])

  // Close the mic / stand down without leaving hands-free — the manual twin of
  // the spoken "close the mic" command. Ends the active session and returns to
  // wake-word standby (or fully idles streaming when no wake word is set).
  const sleep = useCallback(() => sleepRef.current?.(), [])

  const onGesture = useCallback(action => {
    if (action === "mic") toggleRecord()
    else if (action === "voice_on") setVoice(true)
    else if (action === "voice_off") setVoice(false)
    else if (action === "hush") bargeIn()
  }, [toggleRecord, bargeIn])

  const hfStatus = !handsFree ? "OFFLINE" : (WAKE_MODEL ? (armed ? "ARMED" : "LISTENING") : "OPEN")
  const coreState = speaking ? "SPEAKING" : talking ? "THINKING" : recording ? "LISTENING" : "STANDBY"

  return {
    messages, input, setInput, voice, setVoice,
    recording, speaking, connected, toolStatus, talking,
    handsFree, setHandsFree, armed, wakeFlash,
    analyser, wakeModel: WAKE_MODEL, wakeLabel, hfStatus, coreState,
    sendText, toggleRecord, reset, onGesture, bargeIn, speak, wakeNow, sleep,
  }
}
