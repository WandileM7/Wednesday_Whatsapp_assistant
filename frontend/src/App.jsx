import { useCallback, useEffect, useRef, useState } from "react"
import Sidebar from "./hud/Sidebar"
import TopBar from "./hud/TopBar"
import StatusBar from "./hud/StatusBar"
import WakeOverlay from "./hud/WakeOverlay"
import OrbStage from "./hud/OrbStage"
import CommandScreen from "./screens/CommandScreen"
import LogsScreen from "./screens/LogsScreen"
import DiagnosticsScreen from "./screens/DiagnosticsScreen"
import { useAssistant } from "./hooks/useAssistant"
import { useLogs } from "./hooks/useLogs"
import { useDiagnostics } from "./hooks/useDiagnostics"

export default function App() {
  const [screen, setScreen] = useState("command")
  // Bumped each time a voice "run diagnostics" lands, so we read the panel out
  // loud once its data arrives (see the effect below).
  const [readDiag, setReadDiag] = useState(0)

  const stageRef = useRef(null)
  const parallaxRef = useRef(null)
  const orbRef = useRef(null)

  // The wake word yanks us to the command deck so the orb and the overlay are
  // what you see the instant Wednesday starts listening.
  const onWake = useCallback(() => setScreen("command"), [])
  // Voice HUD navigation: "show the logs", "run diagnostics", "back to command".
  const onNavigate = useCallback(target => {
    setScreen(target)
    if (target === "diagnostics") setReadDiag(n => n + 1)
  }, [])
  const a = useAssistant({ onWake, onNavigate })

  // The background wake daemon (backend/wake_daemon.py) opens the browser at
  // "…/?wake=1" when it hears the word with no tab open. Honour it: jump to the
  // command deck and arm hands-free so we're already listening for the command.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get("wake") !== "1") return
    setScreen("command")
    a.wakeNow()
    // Tidy the URL so a manual refresh doesn't re-trigger the arming.
    window.history.replaceState({}, "", window.location.pathname)
  }, [a.wakeNow])

  const { logs, live: logLive, clear } = useLogs(true)
  const diag = useDiagnostics(screen === "diagnostics")

  // Speak a summary of the diagnostics panel once, after a voice "run
  // diagnostics" request, as soon as telemetry has arrived.
  useEffect(() => {
    if (!readDiag || !diag.telemetry) return
    const t = diag.telemetry
    const pct = v => (v == null ? "unknown" : `${Math.round(v)} percent`)
    const parts = [
      `Systems ${diag.doctor?.status === "ok" ? "nominal" : "reporting"}.`,
      `CPU ${pct(t.cpu_percent)}, memory ${pct(t.memory?.percent)}.`,
      `Model ${t.ollama?.model || "unknown"} online.`,
      `${t.clients ?? 0} client${t.clients === 1 ? "" : "s"} connected.`,
    ]
    if (diag.doctor?.checks) {
      const bad = Object.entries(diag.doctor.checks)
        .filter(([, v]) => typeof v === "string" &&
          (v.startsWith("unreachable") || v.startsWith("error") || v.includes("not pulled") || v.includes("not trained")))
        .map(([k]) => k)
      parts.push(bad.length ? `Attention needed: ${bad.join(", ")}.` : "All subsystems green.")
    }
    a.speak(parts.join(" "))
    setReadDiag(0)
  }, [readDiag, diag.telemetry, diag.doctor, a.speak])

  // Pointer parallax — now the only motion on the surfaces, and held to half
  // its original throw so it reads as depth rather than wobble. Written
  // straight to style on an rAF: this fires on every mouse move, so it must
  // never go through React state.
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    let frame = 0, pending = null
    const apply = () => {
      frame = 0
      const stage = stageRef.current
      if (!stage || !pending) return
      const r = stage.getBoundingClientRect()
      const x = (pending.x - r.left) / r.width - 0.5
      const y = (pending.y - r.top) / r.height - 0.5
      if (parallaxRef.current) {
        parallaxRef.current.style.transform =
          `rotateY(${(x * 2).toFixed(2)}deg) rotateX(${(-y * 1.5).toFixed(2)}deg)`
      }
      if (orbRef.current) {
        orbRef.current.style.marginLeft = `${(x * -10).toFixed(1)}px`
        orbRef.current.style.marginTop = `${(y * -8).toFixed(1)}px`
      }
    }
    const onMove = e => {
      pending = { x: e.clientX, y: e.clientY }
      if (!frame) frame = requestAnimationFrame(apply)
    }
    window.addEventListener("mousemove", onMove, { passive: true })
    return () => { window.removeEventListener("mousemove", onMove); cancelAnimationFrame(frame) }
  }, [])

  return (
    <div className="relative grid h-full w-full grid-rows-[56px_minmax(0,1fr)_34px] overflow-hidden bg-void text-ink">
      {/* The light that the glass refracts. Everything above it is a surface. */}
      <div className="aurora" />
      <div className="vignette" />

      <TopBar a={a} />

      <main className="relative grid min-h-0 grid-cols-[84px_minmax(0,1fr)]">
        <Sidebar screen={screen} setScreen={setScreen} />

        <div ref={stageRef} className="relative min-h-0 overflow-hidden" style={{ perspective: "1600px" }}>
          {/* The orb is mounted once for the session and flies between screens,
              so the WebGL context is never rebuilt. */}
          <OrbStage ref={orbRef} screen={screen} a={a} />

          <div ref={parallaxRef}
            className="absolute inset-0 z-[2] transition-transform duration-[400ms] ease-out"
            style={{ transformStyle: "preserve-3d" }}>
            {screen === "command" && <CommandScreen a={a} logs={logs} />}
            {screen === "logs" && <LogsScreen logs={logs} live={logLive} clear={clear} />}
            {screen === "diagnostics" && <DiagnosticsScreen {...diag} />}
          </div>
        </div>
      </main>

      <StatusBar a={a} logLive={logLive} logCount={logs.length} />

      <WakeOverlay active={a.wakeFlash} label={a.wakeLabel} />
    </div>
  )
}
