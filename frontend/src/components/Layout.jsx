import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { 
  Home, Activity, MessageSquare, Settings, 
  Menu, X, Shield, Brain, 
  ChevronRight, Clock
} from 'lucide-react'

const navItems = [
  { path: '/', label: 'Dashboard', icon: Home },
  { path: '/services', label: 'Services', icon: Activity },
  { path: '/whatsapp', label: 'WhatsApp', icon: MessageSquare },
  { path: '/settings', label: 'Settings', icon: Settings },
]

export default function Layout({ children, currentTime }) {
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <div className="min-h-screen">
      {/* Background */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-br from-jarvis-dark via-[#1a1a2e] to-jarvis-dark" />
        <div className="absolute inset-0 bg-grid animate-grid-pulse opacity-50" />
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-jarvis-blue/5 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-jarvis-gold/5 rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <header className="sticky top-0 z-50 backdrop-blur-md bg-jarvis-dark/80 border-b border-jarvis-blue/20">
        <div className="max-w-[1800px] mx-auto px-4 py-3 flex items-center justify-between">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-3">
            <motion.div
              className="w-10 h-10 rounded-full border-2 border-jarvis-blue flex items-center justify-center"
              animate={{ boxShadow: ['0 0 10px #00d4ff', '0 0 20px #00d4ff', '0 0 10px #00d4ff'] }}
              transition={{ duration: 2, repeat: Infinity }}
            >
              <Brain className="w-5 h-5 text-jarvis-blue" />
            </motion.div>
            <span className="font-orbitron text-xl font-bold tracking-widest hidden sm:inline">J.A.R.V.I.S.</span>
          </Link>

          {/* Desktop Nav */}
          <nav className="hidden md:flex items-center gap-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg font-mono text-sm transition-all ${
                    isActive 
                      ? 'bg-jarvis-blue/20 text-jarvis-blue border border-jarvis-blue/30' 
                      : 'text-gray-400 hover:text-white hover:bg-jarvis-blue/10'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {item.label}
                </Link>
              )
            })}
          </nav>

          {/* Time & Mobile Menu */}
          <div className="flex items-center gap-4">
            <div className="hidden sm:flex items-center gap-2 font-mono text-sm text-gray-400">
              <Clock className="w-4 h-4" />
              {currentTime?.toLocaleTimeString()}
            </div>
            <button 
              className="md:hidden p-2 rounded-lg hover:bg-jarvis-blue/10"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
        </div>

        {/* Mobile Nav */}
        {mobileMenuOpen && (
          <motion.nav 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="md:hidden px-4 pb-4 space-y-1"
          >
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-3 px-4 py-3 rounded-lg font-mono text-sm ${
                    isActive 
                      ? 'bg-jarvis-blue/20 text-jarvis-blue border border-jarvis-blue/30' 
                      : 'text-gray-400 hover:text-white hover:bg-jarvis-blue/10'
                  }`}
                >
                  <Icon className="w-5 h-5" />
                  {item.label}
                  <ChevronRight className="w-4 h-4 ml-auto" />
                </Link>
              )
            })}
          </motion.nav>
        )}
      </header>

      {/* Main Content */}
      <main className="max-w-[1800px] mx-auto px-4 py-6">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-jarvis-blue/10 py-4 mt-8">
        <div className="max-w-[1800px] mx-auto px-4 flex justify-between items-center text-xs text-gray-500 font-mono">
          <span>JARVIS COMMAND CENTER v2.0</span>
          <span>© 2024 Stark Industries</span>
        </div>
      </footer>
    </div>
  )
}
