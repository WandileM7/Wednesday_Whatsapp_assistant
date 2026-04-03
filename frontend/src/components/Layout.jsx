import { NavLink, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  LayoutDashboard,
  MessageCircle,
  Settings,
  Zap,
} from 'lucide-react'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/whatsapp', label: 'WhatsApp', icon: MessageCircle },
  { to: '/settings', label: 'Settings', icon: Settings },
]

function NavItem({ to, label, icon: Icon }) {
  const location = useLocation()
  const active = location.pathname === to

  return (
    <NavLink to={to} className="relative">
      <motion.div
        className={`
          flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors duration-200
          ${active
            ? 'text-wed-cyan bg-wed-cyan/10'
            : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]'
          }
        `}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
      >
        <Icon size={16} strokeWidth={active ? 2.2 : 1.8} />
        <span>{label}</span>
        {active && (
          <motion.div
            layoutId="activeTab"
            className="absolute inset-0 rounded-xl border border-wed-cyan/20 bg-wed-cyan/[0.06]"
            style={{ zIndex: -1 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          />
        )}
      </motion.div>
    </NavLink>
  )
}

function Clock({ time }) {
  const h = time.getHours().toString().padStart(2, '0')
  const m = time.getMinutes().toString().padStart(2, '0')
  const s = time.getSeconds().toString().padStart(2, '0')

  return (
    <div className="font-mono text-sm tabular-nums tracking-wider text-gray-500">
      <span className="text-gray-300">{h}</span>
      <span className="animate-glow-pulse">:</span>
      <span className="text-gray-300">{m}</span>
      <span className="animate-glow-pulse">:</span>
      <span className="text-gray-400">{s}</span>
    </div>
  )
}

export default function Layout({ children, currentTime }) {
  return (
    <div className="min-h-screen bg-surface-0 bg-grid relative">
      {/* Ambient glow */}
      <div className="fixed top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-glow-radial opacity-40 pointer-events-none" />

      {/* Top bar */}
      <header className="sticky top-0 z-50 border-b border-white/[0.06] bg-surface-0/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          {/* Brand */}
          <div className="flex items-center gap-3">
            <div className="relative w-8 h-8 rounded-lg bg-gradient-to-br from-wed-cyan/20 to-wed-purple/20 flex items-center justify-center border border-wed-cyan/20">
              <Zap size={16} className="text-wed-cyan" />
              <div className="absolute inset-0 rounded-lg animate-border-glow border border-transparent" />
            </div>
            <div>
              <h1 className="text-base font-display font-bold text-gradient leading-tight">
                Wednesday
              </h1>
              <p className="text-[10px] font-mono text-gray-600 uppercase tracking-[0.2em] -mt-0.5">
                AI Command Center
              </p>
            </div>
          </div>

          {/* Nav */}
          <nav className="flex items-center gap-1">
            {navItems.map((item) => (
              <NavItem key={item.to} {...item} />
            ))}
          </nav>

          {/* Clock */}
          <Clock time={currentTime} />
        </div>
      </header>

      {/* Glow line under header */}
      <div className="glow-line" />

      {/* Content */}
      <main className="max-w-7xl mx-auto px-6 py-8 relative z-10">
        {children}
      </main>
    </div>
  )
}
