import { useEffect, useState } from "react"

/**
 * Wake acknowledgement. When the wake word fires the shell flips `active` true
 * and this drops a full-screen glass veil with expanding rings, so it is
 * unmistakable that Wednesday is now hearing you. It fades itself out shortly
 * after `active` goes false (the armed window closing, or a reply starting).
 */
export default function WakeOverlay({ active, label, transcript }) {
  const [show, setShow] = useState(false)
  useEffect(() => {
    if (active) { setShow(true); return }
    const t = setTimeout(() => setShow(false), 450)
    return () => clearTimeout(t)
  }, [active])

  if (!show) return null
  return (
    <div role="status" aria-live="polite"
      className={`fixed inset-0 z-50 flex flex-col items-center justify-center transition-opacity duration-300 ${
        active ? "opacity-100" : "opacity-0"}`}>
      <div className="absolute inset-0 bg-void/65 backdrop-blur-2xl backdrop-saturate-150" />

      <div className="relative flex flex-col items-center">
        <div className="relative flex h-56 w-56 items-center justify-center">
          <span className="animate-wake-ring absolute inset-0 rounded-full border border-iris-400/45" />
          <span className="animate-wake-ring absolute inset-6 rounded-full border border-iris-400/30 [animation-delay:.4s]" />
          <span className="animate-wake-ring absolute inset-12 rounded-full border border-iris-400/20 [animation-delay:.8s]" />
          <div className="flex h-28 w-28 items-center justify-center rounded-full border border-white/15
            bg-white/[0.06] shadow-[0_0_70px_rgba(168,85,247,0.55)] backdrop-blur-md">
            <span className="animate-breathe h-4 w-4 rounded-full"
              style={{ background: "radial-gradient(circle at 35% 30%, #fff, #c4a4ff 40%, #7c3aed 100%)" }} />
          </div>
        </div>

        <div className="mt-8 text-center">
          <div className="text-[22px] font-semibold tracking-[-0.02em] text-ink">Listening</div>
          <div className="mt-1.5 text-[12.5px] font-book text-muted">
            {label ? `“${label.toLowerCase()}” · go ahead` : "Go ahead"}
          </div>
          {transcript && <div className="mt-5 max-w-md text-[15px] text-body">{transcript}</div>}
        </div>
      </div>
    </div>
  )
}
