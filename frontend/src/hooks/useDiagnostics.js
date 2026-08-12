import { useEffect, useRef, useState } from "react"
import { apiGet } from "../lib/api"

/**
 * Polls /telemetry (fast) and /doctor (slow) for the Diagnostics screen.
 * Telemetry drives the live gauges; doctor is the deeper system audit and is
 * refreshed less often because it probes external services.
 */
export function useDiagnostics(active) {
  const [telemetry, setTelemetry] = useState(null)
  const [doctor, setDoctor] = useState(null)
  const [error, setError] = useState(null)
  const doctorAt = useRef(0)

  useEffect(() => {
    if (!active) return
    let stopped = false

    const tickTelemetry = async () => {
      try { const t = await apiGet("/telemetry"); if (!stopped) { setTelemetry(t); setError(null) } }
      catch (e) { if (!stopped) setError(String(e.message || e)) }
    }
    const tickDoctor = async () => {
      if (Date.now() - doctorAt.current < 12000) return
      doctorAt.current = Date.now()
      try { const d = await apiGet("/doctor"); if (!stopped) setDoctor(d) } catch {}
    }

    tickTelemetry(); tickDoctor()
    const t = setInterval(tickTelemetry, 2000)
    const d = setInterval(tickDoctor, 12000)
    return () => { stopped = true; clearInterval(t); clearInterval(d) }
  }, [active])

  return { telemetry, doctor, error }
}
