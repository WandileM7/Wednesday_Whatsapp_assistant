import { Circle, ScrollText, LayoutGrid } from "lucide-react"

const NAV = [
  { id: "command",     label: "Core",     Icon: Circle,     hint: "Talk to Wednesday" },
  { id: "logs",        label: "Activity", Icon: ScrollText, hint: "Live backend log stream" },
  { id: "diagnostics", label: "Systems",  Icon: LayoutGrid, hint: "Vitals and system audit" },
]

/**
 * The rail. Squircle buttons that lift on hover; the active one is the only lit
 * surface in the column, which is what keeps it readable at 84px wide.
 */
export default function Sidebar({ screen, setScreen }) {
  return (
    <nav aria-label="Screens"
      className="glass-chrome relative z-20 flex shrink-0 flex-col items-center gap-2 border-r border-white/10 py-3.5">
      {NAV.map(({ id, label, Icon, hint }) => {
        const on = screen === id
        return (
          <button key={id} onClick={() => setScreen(id)} title={hint}
            aria-current={on ? "page" : undefined}
            className={`flex w-[58px] flex-col items-center gap-1.5 rounded-[20px] border pb-2.5 pt-3
              text-[10px] font-medium transition-all duration-200 hover:-translate-y-0.5 ${
              on ? "border-white/[0.34] bg-white/[0.18] text-white shadow-[0_8px_26px_rgba(124,58,237,0.45),inset_0_1px_0_rgba(255,255,255,0.5)]"
                 : "border-white/10 bg-white/[0.04] text-muted hover:bg-white/[0.09] hover:text-soft"}`}>
            <Icon size={20} strokeWidth={1.7} />
            {label}
          </button>
        )
      })}

      {/* Shortcut legend. These keys belong to the orb, so they live beside it. */}
      <div className="mt-auto flex flex-col items-center gap-1.5 text-[10px] text-faint">
        <Key title="Toggle hand gestures">G</Key>
        <Key title="Resize the orb">±</Key>
        <Key title="Reset the orb's size and view">R</Key>
        <Key title="Focus the command input">/</Key>
      </div>
    </nav>
  )
}

function Key({ children, title }) {
  return (
    <span title={title}
      className="flex h-[26px] w-[26px] items-center justify-center rounded-[9px] border border-white/[0.14]">
      {children}
    </span>
  )
}
