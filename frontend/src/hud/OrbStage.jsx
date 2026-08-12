import { forwardRef, useEffect, useRef, useState } from "react"
import { Hand } from "lucide-react"
import Orb from "../components/Orb"

/**
 * The orb lives here rather than inside a screen: it is the app's spatial
 * anchor, so it stays mounted for the whole session and flies to a new position
 * when you change screens. The WebGL context is never torn down, and the
 * screens don't need the old always-mounted-but-hidden hack to protect it.
 *
 * Three scales multiply together, each on its own element so they can carry
 * different durations without fighting:
 *
 *   placement  per screen, 1s   — the long glide when you switch views
 *   state      per mode,  .45s  — grows while it listens and talks
 *   user       +/- keys, .25s   — a deliberate adjustment should feel instant
 */
const PLACEMENT = {
  command:     { x: "50%", y: "32%", s: 0.9 },
  logs:        { x: "90%", y: "86%", s: 0.36 },
  diagnostics: { x: "95%", y: "8%",  s: 0.32 },
}

// Size as a state signal: it swells when Wednesday is listening or speaking and
// settles back when idle, so you can read the mode from across the room.
const STATE_SCALE = { STANDBY: 1, LISTENING: 1.12, THINKING: 1.05, SPEAKING: 1.18 }

const USER_MIN = 0.5, USER_MAX = 1.8, USER_STEP = 1.12
const STORE_KEY = "wednesday.orbScale"

const OrbStage = forwardRef(function OrbStage({ screen, a }, ref) {
  const [gestures, setGestures] = useState(false)
  const [gStatus, setGStatus] = useState({ hands: 0, mode: "idle", gesture: null, fps: 0 })
  const [userScale, setUserScale] = useState(() => {
    const v = parseFloat(localStorage.getItem(STORE_KEY))
    return Number.isFinite(v) ? Math.min(USER_MAX, Math.max(USER_MIN, v)) : 1
  })
  const videoRef = useRef(null)
  const overlayRef = useRef(null)

  const p = PLACEMENT[screen] ?? PLACEMENT.command
  const stateScale = STATE_SCALE[a.coreState] ?? 1

  useEffect(() => {
    try { localStorage.setItem(STORE_KEY, String(userScale)) } catch { /* private mode */ }
  }, [userScale])

  // "+" / "−" resize the orb itself; "r" returns it to 1×; "g" toggles tracking.
  // These used to dolly the camera inside a fixed box, which changed the framing
  // but not the size — it never read as resizing.
  useEffect(() => {
    const onKey = e => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === "+" || e.key === "=") setUserScale(s => Math.min(USER_MAX, s * USER_STEP))
      else if (e.key === "-" || e.key === "_") setUserScale(s => Math.max(USER_MIN, s / USER_STEP))
      else if (e.key === "r" || e.key === "R") setUserScale(1)
      else if (e.key === "g" || e.key === "G") setGestures(v => !v)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <>
      <div ref={ref}
        className="pointer-events-none absolute z-[1] h-0 w-0 transition-[left,top] duration-1000 ease-stage"
        style={{ left: p.x, top: p.y }}>

        {/* placement scale */}
        <div className="absolute -left-[210px] -top-[210px] h-[420px] w-[420px] transition-transform duration-1000 ease-stage"
          style={{ transform: `scale(${p.s})` }}>
          {/* state scale */}
          <div className="h-full w-full transition-transform duration-[450ms] ease-out"
            style={{ transform: `scale(${stateScale})` }}>
            {/* user scale */}
            <div className="relative h-full w-full transition-transform duration-[250ms] ease-out"
              style={{ transform: `scale(${userScale})` }}>

              {/* WebGL core — the only part taking pointer input (drag to spin). */}
              <div className="pointer-events-auto absolute inset-0">
                <Orb
                  analyser={a.analyser}
                  active={a.speaking || a.recording || a.armed}
                  talking={a.talking && !a.speaking}
                  onGesture={a.onGesture}
                  gestures={gestures}
                  videoRef={videoRef}
                  overlayRef={overlayRef}
                  onStatus={setGStatus}
                  onUnavailable={() => setGestures(false)}
                />
              </div>

              {/* Glass shell + ring: the orb refracts the aurora the way the
                  console does, so it belongs to the same material world. */}
              <div className="orb-shell" />
              <div className="orb-ring animate-spin-slow" />
            </div>
          </div>
        </div>
      </div>

      {/* Gesture controls sit outside the scaled box — inside it they would
          shrink to a third on the Systems screen and become unusable. */}
      <div className="pointer-events-none absolute inset-0 z-[3]">
        <button onClick={() => setGestures(v => !v)} title="Hand gestures (g)"
          aria-pressed={gestures}
          className={`btn-glass pointer-events-auto absolute right-4 top-4 flex h-9 w-9 items-center justify-center ${
            gestures ? "is-on" : ""}`}>
          <Hand size={16} />
        </button>

        <div className={`pointer-events-auto absolute bottom-4 left-4 overflow-hidden rounded-card border border-white/15
            bg-black/40 shadow-[0_20px_50px_rgba(0,0,0,0.6)] ${gestures ? "" : "hidden"}`}>
          <video ref={videoRef} muted playsInline
            className="h-[120px] w-[160px] object-cover opacity-75 [transform:scaleX(-1)]" />
          <canvas ref={overlayRef} width={160} height={120} className="absolute inset-0" />
          <div className="absolute inset-x-0 bottom-0 bg-black/55 px-2.5 py-1 text-[10px] text-iris-400">
            {(gStatus.gesture
              ? gStatus.gesture.replace("_", " ").toLowerCase()
              : gStatus.hands
                ? `${gStatus.hands} hand${gStatus.hands > 1 ? "s" : ""} · ${gStatus.mode}`
                : "✋swat ✊hush ✌reset ☝mic 👍👎")
              + (gStatus.fps ? ` · ${gStatus.fps}fps` : "")}
          </div>
        </div>
      </div>
    </>
  )
})

export default OrbStage
