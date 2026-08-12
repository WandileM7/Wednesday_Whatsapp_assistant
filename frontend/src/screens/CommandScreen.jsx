import { useEffect, useRef, useState } from "react"
import { Mic, Square, Send, ChevronLeft, X } from "lucide-react"
import { Panel, PanelHead } from "../hud/primitives"

// Real prompts that exercise real tools. The design's presets were scripted
// replies, so there was nothing to carry over from them but the shape.
const PRESETS = [
  "What's on my calendar today?",
  "Summarise my unread email",
  "Run a system check",
  "What did we talk about yesterday?",
]

const URL_RE = /https?:\/\/\S+/g
function renderText(text) {
  if (typeof text !== "string" || !text) return text
  const parts = []; let last = 0, m
  const re = new RegExp(URL_RE)
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    const trail = m[0].match(/[).,;:!?'"»]+$/)?.[0] ?? ""
    const url = trail ? m[0].slice(0, -trail.length) : m[0]
    let label, safe = false
    try {
      const u = new URL(url)
      safe = u.protocol === "http:" || u.protocol === "https:"
      label = u.hostname.replace(/^www\./, "") + (u.pathname !== "/" || u.search ? "/…" : "")
    } catch { label = url.slice(0, 32) + "…" }
    if (safe) parts.push(
      <a key={parts.length} href={url} target="_blank" rel="noreferrer"
        className="text-iris-400 underline decoration-iris-400/40 underline-offset-2 hover:text-iris-300">{label}</a>)
    else parts.push(label)
    if (trail) parts.push(trail)
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}

/**
 * One console, one open stage. Status moved into the top bar and the log feed
 * into a slide-over, so the orb has the room it needs to be the subject rather
 * than something wedged between three cards.
 */
export default function CommandScreen({ a, logs }) {
  const [drawer, setDrawer] = useState(false)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [a.messages, a.toolStatus])

  // "/" focuses the input; Escape unwinds one layer at a time — drawer first,
  // then playback, then the open mic.
  useEffect(() => {
    const onKey = e => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement
      if (e.key === "/" && !typing) { e.preventDefault(); inputRef.current?.focus() }
      else if (e.key === "Escape") {
        if (typing) { e.target.blur(); return }
        if (drawer) setDrawer(false)
        else if (a.speaking) a.bargeIn()
        else if (a.armed) a.sleep()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [drawer, a.speaking, a.armed, a.bargeIn, a.sleep])

  // The newest assistant line is set at hero size, so the reply you're actually
  // waiting on is legible from across the room.
  const heroIdx = (() => {
    for (let i = a.messages.length - 1; i >= 0; i--) if (a.messages[i].role === "assistant") return i
    return -1
  })()

  const tail = logs.slice(-40).reverse()

  return (
    <div className="pointer-events-none relative h-full">

      {/* ── the console ──────────────────────────────────────────────────── */}
      <div className="absolute inset-x-0 bottom-0 flex justify-center px-[18px] pb-[18px]">
        <Panel flavour="hero" radius="rounded-hero"
          className="pointer-events-auto flex max-h-[58vh] w-full max-w-[820px] flex-col">

          <div className="flex shrink-0 items-center justify-between gap-3 px-6 pb-1 pt-4">
            <span className="text-[12px] font-book text-muted">Transcript</span>
            {a.toolStatus && (
              <span className="animate-rise text-[12px] font-book text-iris-400">
                running {a.toolStatus}…
              </span>
            )}
          </div>

          <div ref={scrollRef} className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 pb-3">
            {a.messages.length === 0 ? (
              <p className="py-2 text-[clamp(19px,2.1vw,25px)] font-semibold leading-[1.28] tracking-[-0.02em] text-ink/85">
                Standing by. Ask me anything.
                <span className="animate-blink ml-0.5 text-iris-400">|</span>
              </p>
            ) : (
              <div className="flex flex-col gap-3 py-1">
                {a.messages.map((m, i) => <Message key={i} m={m} hero={i === heroIdx} />)}
              </div>
            )}
          </div>

          <div className="flex shrink-0 flex-wrap gap-2 px-6 pb-3.5">
            {PRESETS.map(p => (
              <button key={p} onClick={() => a.sendText(p)} disabled={!a.connected}
                className="btn-glass px-[15px] py-2 text-[12.5px] font-book">
                {p}
              </button>
            ))}
          </div>

          <div className="flex shrink-0 gap-2.5 px-[18px] pb-[18px]">
            <input ref={inputRef} value={a.input} onChange={e => a.setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && a.sendText()}
              placeholder="Ask Wednesday anything…" aria-label="Message Wednesday"
              className="input-glass min-w-0 flex-1 px-5 py-3 text-[14.5px]" />
            <button onClick={() => a.sendText()} disabled={!a.input.trim() || !a.connected}
              className="btn-primary flex items-center justify-center px-[22px] text-[13.5px]">
              <span className="hidden sm:inline">Send</span>
              <Send size={16} className="sm:hidden" />
            </button>
            <button onClick={a.toggleRecord}
              title={a.recording ? "Stop recording" : "Record a voice message"}
              aria-label={a.recording ? "Stop recording" : "Record a voice message"}
              className={`btn-glass flex w-[46px] shrink-0 items-center justify-center ${a.recording ? "is-on" : ""}`}>
              {a.recording ? <Square size={17} /> : <Mic size={19} strokeWidth={1.8} />}
            </button>
          </div>
        </Panel>
      </div>

      {/* ── activity slide-over ──────────────────────────────────────────── */}
      <button onClick={() => setDrawer(true)} aria-expanded={drawer}
        title="Show the backend activity feed"
        className={`pointer-events-auto absolute right-0 top-1/2 z-10 flex -translate-y-1/2 items-center gap-2
          rounded-l-[14px] border-y border-l border-white/15 bg-white/[0.07] px-2 py-5 text-[11.5px]
          text-muted backdrop-blur-xl transition-all duration-300 hover:bg-white/[0.14] hover:text-ink
          ${drawer ? "translate-x-full opacity-0" : ""}`}>
        <ChevronLeft size={14} />
        <span className="[writing-mode:vertical-rl]">Activity</span>
      </button>

      <aside aria-label="Backend activity"
        className={`pointer-events-auto absolute right-0 top-0 z-20 h-full w-[340px] max-w-[85vw]
          p-[18px] pl-0 transition-transform duration-300 ease-out
          ${drawer ? "translate-x-0" : "translate-x-full"}`}>
        <Panel className="flex h-full flex-col">
          <PanelHead title="Activity"
            right={
              <button onClick={() => setDrawer(false)} aria-label="Close the activity feed"
                className="btn-glass flex h-7 w-7 items-center justify-center">
                <X size={14} />
              </button>
            } />
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
            {tail.length === 0 && (
              <p className="px-5 py-6 text-[12.5px] text-faint">Waiting for backend activity…</p>
            )}
            {tail.map((l, i) => (
              <div key={l.seq ?? i}
                className="glass-row grid grid-cols-[52px_minmax(0,1fr)] gap-2.5 px-5 py-[11px] text-[12px] leading-[1.45]">
                <span className="font-mono tabular-nums text-faint">{(l.time ?? "").slice(0, 8)}</span>
                <span className={
                  l.level === "ERROR" || l.level === "CRITICAL" ? "text-alert-500"
                    : l.level === "WARNING" ? "text-alert-400" : "text-body"
                }>{l.msg}</span>
              </div>
            ))}
          </div>
        </Panel>
      </aside>
    </div>
  )
}

function Message({ m, hero }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[82%] rounded-[18px] border border-white/15 bg-white/[0.09]
          px-4 py-2 text-[14px] text-ink [overflow-wrap:anywhere]">
          {m.text}
        </div>
      </div>
    )
  }
  if (m.role === "system") {
    return <p className="text-[13px] font-book text-alert-400 [overflow-wrap:anywhere]">{m.text}</p>
  }
  return (
    <p className={hero
      ? "text-[clamp(19px,2.1vw,25px)] font-semibold leading-[1.28] tracking-[-0.02em] text-ink [overflow-wrap:anywhere] [text-wrap:pretty]"
      : "text-[14px] leading-[1.55] text-body [overflow-wrap:anywhere]"}>
      {renderText(m.text)}
      {m.streaming && <span className="animate-blink ml-0.5 text-iris-400">|</span>}
    </p>
  )
}
