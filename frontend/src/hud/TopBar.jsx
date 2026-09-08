import { useEffect, useState } from "react"
import { Ear, Volume2, VolumeX, RotateCcw } from "lucide-react"
import { Chip, fmtClock } from "./primitives"
import LevelBars from "./LevelBars"

const MODE_LABEL = {
  STANDBY: "standby", LISTENING: "listening", THINKING: "thinking", SPEAKING: "speaking",
}

/**
 * The top chrome. It carries the state the old left rail used to hold — mode,
 * live level, link and voice — so the stage below can stay open.
 */
export default function TopBar({ a }) {
  const [now, setNow] = useState(() => fmtClock())
  useEffect(() => {
    const t = setInterval(() => setNow(fmtClock()), 1000)
    return () => clearInterval(t)
  }, [])

  const mode = MODE_LABEL[a.coreState] ?? "standby"
  const idle = a.coreState === "STANDBY"

  return (
    <header className="glass-chrome relative z-30 flex items-center justify-between gap-4 border-b border-white/12 px-5">
      <div className="flex min-w-0 items-center gap-3.5">
        {/* The mark is the orb in miniature, lit by the same violet. */}
        <span className="h-[11px] w-[11px] shrink-0 rounded-full shadow-[0_0_14px_rgba(168,85,247,0.8)]"
          style={{ background: "radial-gradient(circle at 35% 30%, #fff, #c4a4ff 40%, #7c3aed 100%)" }} />
        <span className="text-[16px] font-semibold text-ink">Wednesday</span>

        <span className={`hidden text-[12.5px] font-book transition-colors duration-300 sm:inline ${
          idle ? "text-muted" : "text-iris-400"}`}>
          {mode}
        </span>
        <LevelBars analyser={a.analyser} count={7} max={16} min={3} dim={idle} className="hidden h-5 sm:flex" />
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <div className="hidden items-center gap-3 lg:flex">
          <Chip on={a.connected} tone={a.connected ? undefined : "bad"}
            title={a.connected ? "WebSocket connected" : "Reconnecting to the backend"}>
            {a.connected ? "Connected" : "Offline"}
          </Chip>
          <Chip on={a.handsFree} title="Hands-free listening">
            {a.recording ? "Recording" : a.armed ? "Mic open" : a.handsFree ? "Hands-free" : "Mic idle"}
          </Chip>
          <span className="font-mono text-[12px] font-medium tabular-nums text-ink">{now}</span>
        </div>

        <div className="flex items-center gap-2">
          <IconBtn
            on={a.handsFree && (a.armed || !a.wakeModel)}
            onClick={() => { if (a.armed) a.sleep(); else a.setHandsFree(h => !h) }}
            label={a.armed
              ? "Close the mic (stays open until you cancel or say “close the mic”)"
              : a.wakeModel ? `Hands-free — say “${a.wakeLabel.toLowerCase()}”` : "Hands-free listening"}>
            <Ear size={16} className={a.armed ? "animate-pulse" : undefined} />
          </IconBtn>
          <IconBtn on={a.voice} onClick={() => a.setVoice(v => !v)}
            label={a.voice ? "Mute Wednesday's voice" : "Unmute Wednesday's voice"}>
            {a.voice ? <Volume2 size={16} /> : <VolumeX size={16} />}
          </IconBtn>
          <IconBtn onClick={a.reset} label="Start a new session">
            <RotateCcw size={16} />
          </IconBtn>
        </div>
      </div>
    </header>
  )
}

function IconBtn({ children, onClick, label, on }) {
  return (
    <button onClick={onClick} title={label} aria-label={label} aria-pressed={!!on}
      className={`btn-glass flex h-9 w-9 items-center justify-center ${on ? "is-on" : ""}`}>
      {children}
    </button>
  )
}
