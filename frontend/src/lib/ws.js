const WS_URL = (() => {
  const env = import.meta.env.VITE_BACKEND_WS
  if (env) return env
  const proto = location.protocol === "https:" ? "wss" : "ws"
  return `${proto}://${location.host}/ws`
})()
export function connect(handlers) {
  const ws = new WebSocket(WS_URL)
  ws.onmessage = e => { let msg; try { msg = JSON.parse(e.data) } catch { return }; handlers[msg.type]?.(msg) }
  ws.onclose = () => handlers.close?.()
  ws.onerror = err => handlers.error?.(err)
  return {
    sendText: (text, voice) => ws.send(JSON.stringify({ type: "text", text, voice })),
    sendAudio: (audio_b64, voice) => ws.send(JSON.stringify({ type: "audio", audio_b64, voice })),
    reset: () => ws.send(JSON.stringify({ type: "reset" })),
    close: () => ws.close(), raw: ws,
  }
}