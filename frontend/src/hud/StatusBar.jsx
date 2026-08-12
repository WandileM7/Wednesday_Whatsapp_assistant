/**
 * Footer. The design's version is set dressing ("Malibu · workshop floor 2");
 * this one carries the same weight of text but every field is real, so a glance
 * at the bottom edge tells you whether Wednesday can actually hear and answer.
 */
export default function StatusBar({ a, logLive, logCount }) {
  return (
    <footer className="glass-chrome relative z-30 flex items-center gap-6 overflow-hidden
      whitespace-nowrap border-t border-white/10 px-5 text-[11.5px] text-[#8078a0]"
      style={{ background: "linear-gradient(0deg, rgba(255,255,255,.1), rgba(255,255,255,.03))" }}>
      <span className={a.connected ? "text-muted" : "text-alert-500"}>
        {a.connected ? "Link established" : "Reconnecting…"}
      </span>
      <span>{a.voice ? "Voice on" : "Voice muted"}</span>
      <span className="hidden sm:inline">
        {a.wakeModel ? `Wake word “${a.wakeLabel.toLowerCase()}”` : "Wake word off"}
      </span>
      <span className="hidden font-mono tabular-nums md:inline">
        {a.messages.length} message{a.messages.length === 1 ? "" : "s"}
      </span>
      <span className="hidden font-mono tabular-nums lg:inline">
        {logCount} log line{logCount === 1 ? "" : "s"}
      </span>
      <span className={`ml-auto ${logLive ? "text-iris-400" : "text-faint"}`}>
        {logLive ? "Activity feed live" : "Activity feed down"}
      </span>
    </footer>
  )
}
