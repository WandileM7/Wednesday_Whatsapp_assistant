import { useEffect, useRef } from "react"
import { createOrbScene } from "../lib/orbScene"

/**
 * Holographic orb centrepiece. Visuals + gesture control adapted from ULTRON
 * (github.com/SAGAR-TAMANG/ultron-by-sagar-builds, MIT © Sagar Tamang).
 * Continuous: pinch-drag spins, two pinches zoom, open palm swats/push-pulls,
 * fist drags. Held: fist hushes, victory resets, pointing up = mic, thumbs
 * up/down = voice, ILoveYou = flare.
 *
 * Tracking state and the camera preview are owned by OrbStage: this component
 * sits inside a transformed, scaled box, and anything rendered here would be
 * scaled with it — a 160px preview becomes 51px on the Systems screen. It takes
 * the preview nodes as refs and drives the tracker into them instead.
 */
export default function Orb({
  analyser, active, talking, onGesture,
  gestures, videoRef, overlayRef, onStatus, onUnavailable,
}) {
  const containerRef = useRef(null)
  const sceneRef = useRef(null)
  const trackerRef = useRef(null)
  const onGestureRef = useRef(onGesture)
  onGestureRef.current = onGesture
  const onStatusRef = useRef(onStatus)
  onStatusRef.current = onStatus
  const onUnavailableRef = useRef(onUnavailable)
  onUnavailableRef.current = onUnavailable

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

  // Pulse while Wednesday is streaming a reply (there's no audio level to
  // follow until the first TTS chunk lands).
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
        onStatus: s => onStatusRef.current?.(s),
      })
      trackerRef.current = tracker
      try { await tracker.start() }
      catch (err) {
        console.error("hand tracking unavailable", err)
        if (!cancelled) onUnavailableRef.current?.(err)
      }
    })()
    return () => { cancelled = true; trackerRef.current?.stop(); trackerRef.current = null }
  }, [gestures, videoRef, overlayRef])

  // "r" recentres the camera. "+"/"−" used to dolly it, which changed the
  // framing inside a fixed box but never the orb's size — OrbStage owns those
  // keys now and scales the orb itself.
  useEffect(() => {
    const onKey = e => {
      const s = sceneRef.current
      if (!s || e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === "r" || e.key === "R") s.resetView()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <div className="orb-wrap">
      <div ref={containerRef} className="orb-root" />
    </div>
  )
}
