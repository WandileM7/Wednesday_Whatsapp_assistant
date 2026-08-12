// Shared surfaces for the aurora-glass HUD. Everything here is presentational —
// the material (blur, specular edge, grain) comes from the .glass* classes in
// index.css, so these components only decide flavour, radius and layout.

const FLAVOUR = {
  dark: "glass-dark",   // violet-tinted — use whenever text density is high
  lite: "glass-lite",   // white-tinted — hero surfaces over the aurora
  hero: "glass-hero",   // the console: closest to the viewer
}

/**
 * A glass panel. Deliberately motionless: the surfaces used to drift on three
 * float cycles *and* tilt with the pointer, which read as wobble rather than
 * depth. Parallax alone carries the dimensionality now.
 */
export function Panel({ children, flavour = "dark", className = "", radius = "rounded-panel" }) {
  return (
    <section className={`glass ${FLAVOUR[flavour]} ${radius} ${className}`}>
      {children}
    </section>
  )
}

/** Panel header: title on the left, an optional badge or control on the right. */
export function PanelHead({ title, right, className = "" }) {
  return (
    <div className={`glass-divide flex shrink-0 items-center justify-between gap-3 px-5 pb-3 pt-4 ${className}`}>
      <span className="text-[13px] font-semibold text-ink">{title}</span>
      {right}
    </div>
  )
}

/** Solid lavender pill for the "on" state, hollow grey for "off". */
export function Badge({ on, children, tone }) {
  const cls = tone === "warn"
    ? "bg-alert-400 text-[#2a1a02]"
    : tone === "bad"
      ? "bg-alert-500 text-[#2a0410]"
      : on ? "badge-on" : "badge-off"
  return (
    <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${cls}`}>
      {children}
    </span>
  )
}

/**
 * Horizontal meter. `live` disables the width transition — required for the mic
 * level, where easing between frames smears the signal into mush.
 */
export function Meter({ value = 0, accent, warn, live, className = "" }) {
  const pct = Math.max(0, Math.min(100, value))
  return (
    <div className={`meter ${className}`}>
      <i
        className={`${warn ? "is-warn" : accent ? "is-accent" : ""} ${live ? "is-live" : ""}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

/** Label + value + meter, the design's primary readout block. */
export function MeterRow({ label, value, pct, accent, warn, live }) {
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-3 text-[12.5px]">
        <span className="text-lav">{label}</span>
        <span className="font-mono text-[11.5px] tabular-nums text-muted">{value}</span>
      </div>
      <Meter value={pct} accent={accent} warn={warn} live={live} />
    </div>
  )
}

/** Two-column key/value row used inside list panels. */
export function ListRow({ label, value, tone, last }) {
  const colour = tone === "on" ? "text-iris-400"
    : tone === "warn" ? "text-alert-400"
    : tone === "bad" ? "text-alert-500"
    : tone === "off" ? "text-faint"
    : "text-muted"
  return (
    <div className={`flex items-center justify-between gap-3 px-5 py-3.5 text-[12.5px] ${last ? "" : "glass-row"}`}>
      <span className="min-w-0 truncate text-soft">{label}</span>
      <span className={`shrink-0 text-[12px] ${colour}`}>{value}</span>
    </div>
  )
}

/** Small state dot. Breathes only while genuinely live, never decoratively. */
export function Dot({ on, tone }) {
  const bg = tone === "warn" ? "bg-alert-400" : tone === "bad" ? "bg-alert-500"
    : on ? "bg-iris-400" : "bg-faint"
  return <span className={`h-[7px] w-[7px] shrink-0 rounded-full ${bg} ${on ? "animate-breathe" : ""}`} />
}

/** Header/footer status chip. */
export function Chip({ on, tone, children, title }) {
  return (
    <span title={title}
      className="flex items-center gap-2 rounded-full border border-white/12 bg-white/[0.07] px-3 py-[5px] text-[12px] font-book text-muted">
      <Dot on={on} tone={tone} />
      {children}
    </span>
  )
}

export const fmtClock = (ts, secs) =>
  new Date(ts ?? Date.now()).toLocaleTimeString("en-GB", {
    hour12: false, hour: "2-digit", minute: "2-digit", ...(secs ? { second: "2-digit" } : {}),
  })
