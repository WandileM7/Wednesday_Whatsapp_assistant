import { useEffect, useRef } from "react"

/**
 * Audio level meter driven straight off the analyser. Heights are written
 * through refs at frame rate — routing this through React state would re-render
 * whatever contains it sixty times a second.
 *
 * Centre bars react hardest, which is what makes the row read as a voice rather
 * than a row of sliders.
 */
export default function LevelBars({ analyser, count = 12, max = 34, min = 4, className = "", dim }) {
  const bars = useRef([])
  const weights = useRef([])

  if (weights.current.length !== count) {
    weights.current = Array.from({ length: count }, (_, i) =>
      0.45 + 0.55 * Math.sin(((i + 0.5) / count) * Math.PI))
  }

  useEffect(() => {
    if (!analyser) return
    return analyser.subscribe(level => {
      for (let i = 0; i < count; i++) {
        const el = bars.current[i]
        if (el) el.style.height = `${(min + level * max * weights.current[i]).toFixed(1)}px`
      }
    })
  }, [analyser, count, max, min])

  return (
    <div className={`flex items-center gap-1 ${className}`}
      style={{ opacity: dim ? 0.45 : 1, transition: "opacity .45s ease" }}>
      {Array.from({ length: count }, (_, i) => (
        <span key={i} ref={el => { bars.current[i] = el }}
          className={`w-[3px] rounded-full ${
            i > count * 0.3 && i < count * 0.7 ? "bg-white"
              : i > count * 0.15 && i < count * 0.85 ? "bg-iris-300" : "bg-iris-400"}`}
          style={{ height: `${min}px` }} />
      ))}
    </div>
  )
}
