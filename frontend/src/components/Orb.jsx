import { useEffect, useRef, useState } from "react"
import { Hand } from "lucide-react"
import { createOrbScene } from "../lib/orbScene"

// Holographic orb centerpiece. Visuals + gesture control adapted from ULTRON
// (github.com/SAGAR-TAMANG/ultron-by-sagar-builds, MIT © Sagar Tamang).
// Continuous: pinch-drag spins, two pinches zoom, open palm swats/push-pulls,
// fist drags. Held: fist hushes, victory resets, pointing up = mic, thumbs
// up/down = voice, ILoveYou = flare. Toggle tracking with the hand button or "g".
export default function Orb({ analyser, active, talking, onGesture }) {
  const containerRef = useRef(null)
  const sceneRef = useRef(null)
  const videoRef = useRef(null)
  const overlayRef = useRef(null)
  const trackerRef = useRef(null)
  const onGestureRef = useRef(onGesture)
  onGestureRef.current = onGesture
  const [gestures, setGestures] = useState(false)
  const [gStatus, setGStatus] = useState({ hands: 0, mode: "idle", gesture: null, fps: 0 })

  useEffect(() => {
    const scene = createOrbScene(containerRef.current)
    sceneRef.current = scene
    return () => { scene.dispose(); sceneRef.current = null }
  }, [])

  useEffect(() => {
    if (!analyser) return
    return analyser.subscribe(level => sceneRef.current?.setEnergy(level))
  }, [analyser])

  useEffect(() => { sceneRef.current?.setEnergy(active ? 0.3 : 0) }, [active])

  // Pulse while Wednesday is streaming a reply (no audio level to follow)
  useEffect(() => {
    if (!talking) return
    let raf
    const t0 = performance.now()
    const loop = () => {
      sceneRef.current?.setEnergy(0.35 + 0.3 * Math.sin((performance.now() - t0) / 160))
      raf = requestAnimationFrame(loop)
    }
    loop()
    return () => { cancelAnimationFrame(raf); sceneRef.current?.setEnergy(0) }
  }, [talking])

  useEffect(() => {
    if (!gestures) return
    let cancelled = false
    ;(async () => {
      const { HandTracker } = await import("../lib/handTracker")
      if (cancelled) return
      const tracker = new HandTracker(videoRef.current, overlayRef.current, {
        onRotate: (dt, dp) => sceneRef.current?.rotateBy(dt, dp),
        onZoom: f => sceneRef.current?.zoomBy(f),
        onGesture: action => {
          if (action === "reset") sceneRef.current?.resetView()
          else if (action === "flare") {
            const t0 = performance.now()
            const surge = () => {
              const t = (performance.now() - t0) / 1200
              if (t >= 1 || !sceneRef.current) { sceneRef.current?.setEnergy(0); return }
              sceneRef.current.setEnergy(1 - t * t)
              requestAnimationFrame(surge)
            }
            surge()
          }
          else onGestureRef.current?.(action)
        },
        onStatus: setGStatus,
      })
      trackerRef.current = tracker
      try { await tracker.start() }
      catch (err) { console.error("hand tracking unavailable", err); if (!cancelled) setGestures(false) }
    })()
    return () => { cancelled = true; trackerRef.current?.stop(); trackerRef.current = null }
  }, [gestures])

  useEffect(() => {
    const onKey = e => {
      const s = sceneRef.current
      if (!s || e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === "+" || e.key === "=") s.zoomIn()
      else if (e.key === "-" || e.key === "_") s.zoomOut()
      else if (e.key === "r" || e.key === "R") s.resetView()
      else if (e.key === "g" || e.key === "G") setGestures(v => !v)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <div className="orb-wrap">
      <div ref={containerRef} className="orb-root" />
      <div className="orb-vignette" />
      <div className="orb-scanlines" />
      <button onClick={() => setGestures(v => !v)} title="Hand gestures (g)"
        className={`absolute right-3 top-3 z-10 rounded-md p-2 transition ${
          gestures ? "bg-amber-500/20 text-amber-300" : "text-white/40 hover:bg-white/5 hover:text-white"}`}>
        <Hand size={16}/>
      </button>
      {gestures && (
        <div className="absolute bottom-3 right-3 z-10 overflow-hidden rounded-lg border border-amber-500/20">
          <video ref={videoRef} muted playsInline
            className="h-[120px] w-[160px] object-cover [transform:scaleX(-1)] opacity-70"/>
          <canvas ref={overlayRef} width={160} height={120} className="absolute inset-0"/>
          <div className="absolute bottom-0 left-0 right-0 bg-black/50 px-2 py-0.5 text-[10px] text-amber-300/80">
            {(gStatus.gesture ? gStatus.gesture.replace("_", " ").toLowerCase()
              : gStatus.hands ? `${gStatus.hands} hand${gStatus.hands > 1 ? "s" : ""} · ${gStatus.mode}`
              : "✋swat ✊grab·hush ✌reset ☝mic 👍👎 🤟")
              + (gStatus.fps ? ` · ${gStatus.fps}fps` : "")}
          </div>
        </div>
      )}
    </div>
  )
}
