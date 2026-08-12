import { useEffect, useRef, useState } from "react"
import { apiUrl } from "../lib/api"

const MAX_LOGS = 500

/**
 * Live tail of the backend logs over SSE (/logs/stream). Keeps a bounded ring
 * of the most recent records and a connection flag. The backend replays a
 * buffer on connect, so the screen is populated immediately.
 */
export function useLogs(enabled = true) {
  const [logs, setLogs] = useState([])
  const [live, setLive] = useState(false)
  const esRef = useRef(null)

  useEffect(() => {
    if (!enabled) return
    let stopped = false
    const es = new EventSource(apiUrl("/logs/stream"))
    esRef.current = es
    es.onopen = () => !stopped && setLive(true)
    es.onmessage = e => {
      if (stopped || !e.data) return
      let entry; try { entry = JSON.parse(e.data) } catch { return }
      setLogs(xs => {
        const next = xs.length >= MAX_LOGS ? xs.slice(xs.length - MAX_LOGS + 1) : xs
        return [...next, entry]
      })
    }
    es.onerror = () => setLive(false)
    return () => { stopped = true; es.close(); esRef.current = null }
  }, [enabled])

  return { logs, live, clear: () => setLogs([]) }
}
