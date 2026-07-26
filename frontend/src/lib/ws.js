const WS_URL = (() => {
  const env = import.meta.env.VITE_BACKEND_WS
  const base = env || `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`
  const token = import.meta.env.VITE_API_TOKEN
  return token ? `${base}${base.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}` : base
})()
export function connect(handlers) {
  const ws = new WebSocket(WS_URL)
  ws.onmessage = e => { let msg; try { msg = JSON.parse(e.data) } catch { return }
    const handler = Object.prototype.hasOwnProperty.call(handlers, msg.type) ? handlers[msg.type] : null
    if (typeof handler === "function") handler(msg) }
  ws.onclose = () => handlers.close?.()
  ws.onerror = err => handlers.error?.(err)
  return {
    sendText: (text, voice) => ws.send(JSON.stringify({ type: "text", text, voice })),
    // hands_free marks ambient audio: the backend only acts on it when the
    // wake word is present (see backend/wakeword.py).
    sendAudio: (audio_b64, voice, hands_free = false) =>
      ws.send(JSON.stringify({ type: "audio", audio_b64, voice, hands_free })),
    // A camera frame for the `look` tool. Fire-and-forget: kept in RAM on the
    // backend, expires in a minute, never persisted.
    sendFrame: image_b64 => ws.send(JSON.stringify({ type: "frame", image_b64 })),
    reset: () => ws.send(JSON.stringify({ type: "reset" })),
    close: () => ws.close(), raw: ws,
  }
}