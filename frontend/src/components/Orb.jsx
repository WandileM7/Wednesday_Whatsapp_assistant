import { useEffect, useRef } from "react"
import { createOrbScene } from "../lib/orbScene"

// Holographic orb centerpiece. Visuals adapted from ULTRON Orb UI
// (github.com/SAGAR-TAMANG/ultron-by-sagar-builds, MIT © Sagar Tamang).
export default function Orb({ analyser, active }) {
  const containerRef = useRef(null)
  const sceneRef = useRef(null)

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

  useEffect(() => {
    const onKey = e => {
      const s = sceneRef.current
      if (!s || e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === "+" || e.key === "=") s.zoomIn()
      else if (e.key === "-" || e.key === "_") s.zoomOut()
      else if (e.key === "r" || e.key === "R") s.resetView()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <div className="orb-wrap">
      <div ref={containerRef} className="orb-root" />
      <div className="orb-vignette" />
      <div className="orb-scanlines" />
    </div>
  )
}
