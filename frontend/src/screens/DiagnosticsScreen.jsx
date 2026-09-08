import { Panel, PanelHead, Meter, ListRow, Dot } from "../hud/primitives"

const fmtBytes = b => {
  if (!b) return "—"
  const gb = b / 1073741824
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(b / 1048576).toFixed(0)} MB`
}
const fmtUptime = s => {
  if (s == null) return "—"
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60)
  return h ? `${h}h ${m}m` : m ? `${m}m ${sec}s` : `${sec}s`
}
const shortHost = h => {
  if (!h) return "—"
  try { return new URL(h).host } catch { return h }
}

// /doctor returns free-text status strings; these classify them without the
// backend having to promise a schema.
const isBad = v => typeof v === "string" &&
  (v.startsWith("unreachable") || v.startsWith("error") || v.includes("not pulled") || v.includes("not trained"))
const isWarn = v => typeof v === "string" &&
  (v.includes("up, but") || v.includes("OPEN") || v.includes("degrade"))

// Some checks (mcp) report an object rather than a string. Render those as
// readable pairs instead of letting String() turn them into "[object Object]",
// and let a nested failure still colour the row.
const asText = v => {
  if (v == null) return "—"
  if (typeof v === "string") return v
  if (typeof v === "object") {
    return Object.entries(v).map(([k, x]) => `${k}: ${typeof x === "object" ? JSON.stringify(x) : x}`).join(" · ")
  }
  return String(v)
}
const classify = v => {
  const t = asText(v)
  return isBad(t) || /\bfail|error|unreachable\b/i.test(t) ? "bad" : isWarn(t) ? "warn" : "ok"
}

export default function DiagnosticsScreen({ telemetry, doctor, error }) {
  const t = telemetry
  const mem = t?.memory

  const cards = [
    { label: "CPU", value: t?.cpu_percent, unit: "%", sub: t ? `${t.cores} cores` : "—", accent: true },
    { label: "Memory", value: mem?.percent, unit: "%", sub: mem ? `${fmtBytes(mem.used)} of ${fmtBytes(mem.total)}` : "—" },
    { label: "Clients", value: t?.clients, sub: "websockets attached", raw: true },
    { label: "Uptime", text: fmtUptime(t?.uptime_s), sub: "since last restart" },
  ]

  return (
    <div className="scroll-thin flex h-full flex-col gap-4 overflow-y-auto p-[18px]">

      {/* Live vitals. Percentages get a meter; counts and durations don't —
          a bar under "3 clients" would imply a ceiling that doesn't exist. */}
      <div className="grid shrink-0 grid-cols-2 gap-4 xl:grid-cols-4">
        {cards.map(c => (
          <Panel key={c.label} flavour="lite" radius="rounded-panel" className="px-5 pb-5 pt-[18px]">
            <div className="mb-2.5 text-[12px] font-book text-muted">{c.label}</div>
            <div className={`text-[32px] font-semibold tabular-nums tracking-[-0.03em] ${
              c.accent ? "text-iris-400" : "text-ink"}`}>
              {c.text ?? (c.value == null ? "—" : Math.round(c.value))}
              {c.unit && c.value != null && <span className="text-[22px]">{c.unit}</span>}
            </div>
            {c.raw || c.text ? null : (
              <Meter className="mt-3.5" value={c.value ?? 0} accent={c.accent} warn={(c.value ?? 0) >= 85} />
            )}
            <div className="mt-2.5 text-[11.5px] text-faint">{c.sub}</div>
          </Panel>
        ))}
      </div>

      <div className="grid shrink-0 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHead title="Host" />
          <ListRow label="Load average" value={t ? t.load.join("  ") : "—"} />
          <ListRow label="Memory" value={mem ? `${fmtBytes(mem.used)} / ${fmtBytes(mem.total)}` : "—"} />
          <ListRow label="API uptime" value={fmtUptime(t?.uptime_s)} />
          <ListRow label="WebSocket clients" tone={t?.clients > 0 ? "on" : undefined}
            value={t?.clients ?? "—"} last />
        </Panel>

        <Panel>
          <PanelHead title="Inference" />
          <ListRow label="Language model" tone="on" value={t?.ollama?.model ?? "—"} />
          <ListRow label="Ollama host" value={shortHost(t?.ollama?.host)} />
          <ListRow label="Speech chain" tone="on" value={t?.tts ?? "—"} last />
        </Panel>
      </div>

      {/* The /doctor audit. */}
      <Panel flavour="lite" radius="rounded-[30px]" className="min-h-0">
        <PanelHead title="System audit" className="px-[22px]"
          right={
            <span className="flex items-center gap-2 text-[11.5px] text-muted">
              <Dot on={doctor?.status === "ok"} tone={doctor && doctor.status !== "ok" ? "warn" : undefined} />
              {doctor ? String(doctor.status) : "probing…"}
            </span>
          } />

        <div className="p-[22px]">
          {error && <p className="mb-4 text-[13px] text-alert-500">Telemetry error: {error}</p>}
          {!doctor && <p className="text-[13px] text-faint">Running diagnostics…</p>}

          {doctor && (
            <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
              {Object.entries(doctor.checks).map(([k, v]) => {
                const state = classify(v)
                return (
                  <div key={k} className="flex items-start gap-2.5 rounded-card border border-white/10
                    bg-black/20 px-3.5 py-3">
                    <span className="pt-[5px]">
                      <Dot on={state === "ok"} tone={state === "ok" ? undefined : state} />
                    </span>
                    <div className="min-w-0">
                      <div className="text-[11.5px] font-book text-muted">{k.replace(/_/g, " ")}</div>
                      <div className={`break-words text-[13px] ${
                        state === "bad" ? "text-alert-500" : state === "warn" ? "text-alert-400" : "text-soft"}`}>
                        {asText(v)}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {doctor?.warnings?.length > 0 && (
            <div className="mt-5 border-t border-white/10 pt-4">
              <div className="mb-2.5 text-[11.5px] font-book text-alert-400">Advisories</div>
              <ul className="flex flex-col gap-2">
                {doctor.warnings.map((w, i) => (
                  <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed text-body">
                    <span className="text-alert-400">▲</span>{w}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Panel>
    </div>
  )
}
