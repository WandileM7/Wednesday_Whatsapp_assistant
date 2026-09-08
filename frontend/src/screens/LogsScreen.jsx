import { useEffect, useMemo, useRef, useState } from "react"
import { Pause, Play, Trash2, ArrowDownToLine } from "lucide-react"
import { Panel } from "../hud/primitives"

const LEVELS = ["All", "Info", "Warning", "Error"]
const toLevel = l => l.toUpperCase()

const levelTone = lvl =>
  lvl === "ERROR" || lvl === "CRITICAL" ? "text-alert-500"
    : lvl === "WARNING" ? "text-alert-400"
    : lvl === "DEBUG" ? "text-faint"
    : "text-iris-400"

export default function LogsScreen({ logs, live, clear }) {
  const [filter, setFilter] = useState("All")
  const [query, setQuery] = useState("")
  const [follow, setFollow] = useState(true)
  const scrollRef = useRef(null)

  const shown = useMemo(() => logs.filter(l => {
    if (filter !== "All") {
      const want = toLevel(filter)
      if (l.level !== want && !(want === "ERROR" && l.level === "CRITICAL")) return false
    }
    if (query && !`${l.logger} ${l.msg}`.toLowerCase().includes(query.toLowerCase())) return false
    return true
  }), [logs, filter, query])

  useEffect(() => {
    if (follow) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [shown, follow])

  const counts = useMemo(() => {
    const c = { Warning: 0, Error: 0 }
    for (const l of logs) {
      if (l.level === "WARNING") c.Warning++
      else if (l.level === "ERROR" || l.level === "CRITICAL") c.Error++
    }
    return c
  }, [logs])

  return (
    <div className="flex h-full flex-col p-[18px]">
      <Panel flavour="lite" radius="rounded-[30px]" className="flex min-h-0 flex-1 flex-col">

        <div className="glass-divide flex shrink-0 flex-wrap items-center gap-3 px-[22px] pb-3 pt-4">
          <span className="mr-auto text-[13px] font-semibold text-ink">
            Activity{" "}
            <span className="font-book text-muted">
              · {shown.length === logs.length ? `${logs.length} lines` : `${shown.length} of ${logs.length}`}
            </span>
          </span>

          <div className="seg-track">
            {LEVELS.map(l => (
              <button key={l} onClick={() => setFilter(l)}
                className={`seg-btn ${filter === l ? "is-on" : ""}`}>
                {l}{counts[l] ? ` ${counts[l]}` : ""}
              </button>
            ))}
          </div>

          <input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Filter…" aria-label="Filter log lines"
            className="input-glass w-40 px-4 py-2 text-[12.5px]" />

          <div className="flex items-center gap-1.5">
            <IconBtn on={follow} onClick={() => setFollow(f => !f)}
              label={follow ? "Auto-scroll on" : "Auto-scroll off"}>
              {follow ? <Pause size={14} /> : <Play size={14} />}
            </IconBtn>
            <IconBtn label="Jump to latest"
              onClick={() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })}>
              <ArrowDownToLine size={14} />
            </IconBtn>
            <IconBtn label="Clear the buffer" onClick={clear}>
              <Trash2 size={14} />
            </IconBtn>
          </div>
        </div>

        <div className="glass-divide grid shrink-0 grid-cols-[92px_92px_minmax(0,1fr)_140px] gap-3
          px-[26px] py-3 text-[11.5px] text-faint">
          <span>Time</span><span>Level</span><span>Event</span><span>Source</span>
        </div>

        <div ref={scrollRef} className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          {shown.length === 0 && (
            <p className="px-[26px] py-8 text-[13px] text-faint">
              {live ? "Waiting for log activity…" : "Log stream disconnected."}
            </p>
          )}
          {shown.map((l, i) => (
            <div key={l.seq ?? i}
              className="animate-rise glass-row grid grid-cols-[92px_92px_minmax(0,1fr)_140px] items-start gap-3
                px-[26px] py-3.5 text-[13px] hover:bg-white/[0.03]">
              <span className="font-mono tabular-nums text-faint">{l.time}</span>
              <span>
                <span className={`rounded-full bg-white/[0.08] px-2.5 py-[3px] text-[11.5px] ${levelTone(l.level)}`}>
                  {l.level ? l.level.charAt(0) + l.level.slice(1).toLowerCase() : "Info"}
                </span>
              </span>
              <span className="whitespace-pre-wrap break-words text-body">{l.msg}</span>
              <span className="truncate font-mono text-[12px] text-faint" title={l.logger}>{l.logger}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}

function IconBtn({ children, onClick, label, on }) {
  return (
    <button onClick={onClick} title={label} aria-label={label} aria-pressed={!!on}
      className={`btn-glass flex h-8 w-8 items-center justify-center ${on ? "is-on" : ""}`}>
      {children}
    </button>
  )
}
