// HTTP + SSE base for the backend. In dev the Vite proxy forwards /logs,
// /telemetry, /doctor, /voice to :8000, so an empty base (same origin) works;
// VITE_BACKEND_HTTP overrides it for a split deployment. Token, if any, rides
// as a query param because EventSource can't set headers.
const BASE = import.meta.env.VITE_BACKEND_HTTP || ""
const TOKEN = import.meta.env.VITE_API_TOKEN || ""

export function apiUrl(path) {
  const url = `${BASE}${path}`
  if (!TOKEN) return url
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(TOKEN)}`
}

export async function apiGet(path) {
  const r = await fetch(apiUrl(path), TOKEN ? {} : undefined)
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  return r.json()
}

export async function ttsSpeak(text) {
  const r = await fetch(apiUrl("/voice/tts"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  })
  if (!r.ok) throw new Error(`tts → ${r.status}`)
  const buf = await r.arrayBuffer()
  let bin = ""
  const bytes = new Uint8Array(buf)
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
  return btoa(bin)
}
