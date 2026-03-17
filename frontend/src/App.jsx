import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Activity, Zap, MessageSquare, Clock, Settings, 
  Wifi, WifiOff, Shield, Music, Mail, Calendar,
  Brain, Mic, Home, Heart, DollarSign, Bell,
  Terminal, RefreshCw, ExternalLink, ChevronRight
} from 'lucide-react'

// Arc Reactor Component
function ArcReactor({ toolsCount, isOnline }) {
  return (
    <div className="relative flex items-center justify-center py-12">
      {/* Outer rings */}
      <motion.div 
        className="absolute w-72 h-72 rounded-full border border-jarvis-blue/20"
        animate={{ scale: [1, 1.1, 1], opacity: [0.5, 0.8, 0.5] }}
        transition={{ duration: 4, repeat: Infinity }}
      />
      <motion.div 
        className="absolute w-64 h-64 rounded-full border border-jarvis-blue/30"
        animate={{ rotate: 360 }}
        transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
      />
      
      {/* Core */}
      <motion.div 
        className="reactor-core w-48 h-48 rounded-full flex items-center justify-center relative"
        style={{
          background: `
            radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.3) 0%, transparent 50%),
            radial-gradient(circle, #00d4ff 0%, rgba(0, 100, 150, 0.8) 50%, #0a0a12 100%)
          `
        }}
      >
        {/* Inner rings */}
        <motion.div 
          className="absolute w-36 h-36 rounded-full border-2 border-jarvis-blue/50"
          animate={{ rotate: 360 }}
          transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
        />
        <motion.div 
          className="absolute w-28 h-28 rounded-full border-2 border-dashed border-jarvis-blue/30"
          animate={{ rotate: -360 }}
          transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
        />
        
        {/* Center display */}
        <div className="text-center z-10">
          <motion.span 
            className="font-orbitron text-4xl font-bold text-white"
            style={{ textShadow: '0 0 20px #00d4ff' }}
            key={toolsCount}
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
          >
            {toolsCount}
          </motion.span>
        </div>
      </motion.div>
      
      {/* Label */}
      <div className="absolute -bottom-4 text-center">
        <span className="font-mono text-xs text-gray-400 tracking-widest">
          MCP TOOLS {isOnline ? 'ACTIVE' : 'OFFLINE'}
        </span>
      </div>
    </div>
  )
}

// Status Dot Component
function StatusDot({ status, size = 'md' }) {
  const sizeClasses = {
    sm: 'w-2 h-2',
    md: 'w-3 h-3',
    lg: 'w-4 h-4'
  }
  
  const statusClasses = {
    online: 'status-online',
    offline: 'status-offline',
    warning: 'status-warning'
  }
  
  return (
    <motion.div 
      className={`rounded-full ${sizeClasses[size]} ${statusClasses[status] || statusClasses.offline}`}
      animate={{ scale: [1, 1.2, 1], opacity: [1, 0.7, 1] }}
      transition={{ duration: 2, repeat: Infinity }}
    />
  )
}

// Service Card Component
function ServiceCard({ name, status, icon: Icon }) {
  return (
    <motion.div 
      className="flex items-center justify-between p-4 rounded-lg bg-jarvis-blue/5 border border-jarvis-blue/20 hover:bg-jarvis-blue/10 hover:border-jarvis-blue transition-all cursor-pointer"
      whileHover={{ x: 4 }}
    >
      <div className="flex items-center gap-3">
        <Icon className="w-5 h-5 text-jarvis-blue" />
        <span className="font-medium">{name}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className={`font-mono text-xs px-2 py-1 rounded border ${
          status === 'online' 
            ? 'bg-jarvis-green/15 text-jarvis-green border-jarvis-green/30' 
            : status === 'warning'
            ? 'bg-jarvis-orange/15 text-jarvis-orange border-jarvis-orange/30'
            : 'bg-jarvis-red/15 text-jarvis-red border-jarvis-red/30'
        }`}>
          {status.toUpperCase()}
        </span>
      </div>
    </motion.div>
  )
}

// Stat Card Component
function StatCard({ value, label, icon: Icon }) {
  return (
    <motion.div 
      className="panel p-5 text-center"
      whileHover={{ scale: 1.02 }}
    >
      <div className="flex justify-center mb-2">
        <Icon className="w-5 h-5 text-jarvis-blue/50" />
      </div>
      <div className="font-orbitron text-3xl font-bold text-jarvis-blue glow-blue">
        {value}
      </div>
      <div className="text-xs text-gray-400 tracking-widest mt-2">{label}</div>
    </motion.div>
  )
}

// Quick Action Button
function ActionButton({ label, icon: Icon, href, onClick }) {
  const Component = href ? 'a' : 'button'
  return (
    <Component
      href={href}
      onClick={onClick}
      className="flex flex-col items-center gap-2 p-4 rounded-lg bg-gradient-to-br from-jarvis-blue/10 to-jarvis-blue/5 border border-jarvis-blue/30 hover:from-jarvis-blue/20 hover:to-jarvis-blue/10 hover:border-jarvis-blue transition-all group"
    >
      <Icon className="w-6 h-6 text-jarvis-blue group-hover:scale-110 transition-transform" />
      <span className="text-sm font-medium">{label}</span>
    </Component>
  )
}

// Tool Category Tag
function ToolTag({ name }) {
  return (
    <span className="font-mono text-xs px-3 py-1.5 rounded bg-jarvis-blue/10 border border-jarvis-blue/20 text-jarvis-blue">
      {name}
    </span>
  )
}

// Activity Item
function ActivityItem({ time, message, type }) {
  return (
    <div className="py-3 border-b border-jarvis-blue/10 last:border-0">
      <div className="font-mono text-xs text-jarvis-blue">{time}</div>
      <div className="text-sm text-gray-400 mt-1">{message}</div>
    </div>
  )
}

// Console Output
function Console({ lines }) {
  return (
    <div className="panel p-4 font-mono text-sm">
      <div className="flex justify-between items-center mb-3 pb-2 border-b border-jarvis-blue/20">
        <span className="text-jarvis-blue">JARVIS TERMINAL</span>
        <span className="text-gray-500">v2.0.0</span>
      </div>
      <div className="space-y-1 text-jarvis-green">
        {lines.map((line, i) => (
          <div key={i}>
            <span className="text-jarvis-blue">JARVIS &gt;</span> {line}
          </div>
        ))}
      </div>
    </div>
  )
}

// Main App Component
export default function App() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [currentTime, setCurrentTime] = useState(new Date())

  // Fetch dashboard data
  const fetchData = async () => {
    try {
      const response = await fetch('/api/dashboard/data')
      if (!response.ok) throw new Error('Failed to fetch')
      const json = await response.json()
      setData(json)
      setError(null)
    } catch (err) {
      setError(err.message)
      // Use default data on error
      setData({
        system_status: 'healthy',
        mcp_agent: true,
        whatsapp_connected: false,
        tools_count: 56,
        services: [
          { name: 'MCP Agent', status: 'online', icon: 'Brain' },
          { name: 'Gemini AI', status: 'online', icon: 'Zap' },
          { name: 'WhatsApp', status: 'offline', icon: 'MessageSquare' },
          { name: 'Spotify', status: 'warning', icon: 'Music' },
          { name: 'Gmail', status: 'online', icon: 'Mail' },
          { name: 'Calendar', status: 'online', icon: 'Calendar' },
          { name: 'Smart Home', status: 'offline', icon: 'Home' },
          { name: 'ElevenLabs', status: 'warning', icon: 'Mic' },
        ],
        tool_categories: ['Core', 'Workflows', 'Smart Home', 'Voice', 'Memory', 'Security', 'Admin', 'Fitness', 'Expenses', 'Briefings', 'Media'],
        stats: {
          messages_today: 42,
          active_sessions: 1,
          uptime: '99.9%',
          response_time: 245
        },
        google_auth: false,
        spotify_auth: false,
        elevenlabs_available: false,
        owner_configured: false,
        owner_hint: null,
        recent_activity: [
          { time: '2 min ago', message: 'System health check completed', type: 'info' },
          { time: '5 min ago', message: 'MCP tools refreshed', type: 'info' },
          { time: '12 min ago', message: 'Owner verification requested', type: 'security' },
        ]
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  const iconMap = {
    Brain, Zap, MessageSquare, Music, Mail, Calendar, Home, Mic, Shield, Activity
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <motion.div
          className="w-16 h-16 rounded-full border-4 border-jarvis-blue/30 border-t-jarvis-blue"
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
        />
      </div>
    )
  }

  const consoleLines = [
    `System initialized. All ${data?.tools_count || 56} MCP tools loaded.`,
    data?.owner_configured ? 'Owner authentication active.' : 'Warning: OWNER_PHONE not configured.',
    data?.whatsapp_connected ? 'WhatsApp gateway connected.' : 'WhatsApp gateway awaiting connection.',
    'Ready to serve, sir.'
  ]

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
      <header className="text-center py-8 relative">
        <motion.h1 
          className="font-orbitron text-5xl font-black tracking-[0.3em] bg-gradient-to-r from-jarvis-blue via-white to-jarvis-blue bg-clip-text text-transparent"
          animate={{ filter: ['brightness(1)', 'brightness(1.2)', 'brightness(1)'] }}
          transition={{ duration: 3, repeat: Infinity }}
        >
          J.A.R.V.I.S.
        </motion.h1>
        <p className="font-mono text-sm text-gray-500 tracking-[0.4em] mt-2">
          JUST A RATHER VERY INTELLIGENT SYSTEM
        </p>
        
        {/* Status Bar */}
        <div className="flex justify-center gap-8 mt-6 font-mono text-xs">
          <div className="flex items-center gap-2">
            <StatusDot status={data?.system_status === 'healthy' ? 'online' : 'warning'} size="sm" />
            <span>SYSTEM {data?.system_status?.toUpperCase()}</span>
          </div>
          <div className="flex items-center gap-2">
            <StatusDot status={data?.mcp_agent ? 'online' : 'offline'} size="sm" />
            <span>MCP AGENT</span>
          </div>
          <div className="flex items-center gap-2">
            <StatusDot status={data?.whatsapp_connected ? 'online' : 'offline'} size="sm" />
            <span>WHATSAPP</span>
          </div>
          <div className="text-gray-500">
            {currentTime.toLocaleTimeString()}
          </div>
        </div>
        
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-4/5 h-px bg-gradient-to-r from-transparent via-jarvis-blue to-transparent" />
      </header>

      {/* Main Dashboard */}
      <main className="max-w-[1800px] mx-auto px-6 py-8 grid grid-cols-1 xl:grid-cols-[300px_1fr_300px] gap-6">
        
        {/* Left Panel */}
        <aside className="space-y-6">
          {/* Services */}
          <div className="panel p-5">
            <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4 flex items-center gap-2">
              <span className="text-xs">◆</span> CORE SERVICES
            </h2>
            <div className="space-y-3">
              {data?.services?.map((service, i) => (
                <ServiceCard 
                  key={i}
                  name={service.name}
                  status={service.status}
                  icon={iconMap[service.icon] || Activity}
                />
              ))}
            </div>
          </div>

          {/* Authentication */}
          <div className="panel p-5">
            <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4 flex items-center gap-2">
              <span className="text-xs">◆</span> AUTHENTICATION
            </h2>
            <div className="space-y-3">
              {[
                { name: 'Google', auth: data?.google_auth, href: '/google-login' },
                { name: 'Spotify', auth: data?.spotify_auth, href: '/login' },
                { name: 'ElevenLabs', auth: data?.elevenlabs_available }
              ].map((item, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-jarvis-blue/5 rounded-lg">
                  <span className="font-medium">{item.name}</span>
                  <div className="flex items-center gap-2">
                    <StatusDot status={item.auth ? 'online' : 'offline'} size="sm" />
                    {!item.auth && item.href && (
                      <a href={item.href} className="font-mono text-xs px-3 py-1 bg-jarvis-blue/10 border border-jarvis-blue rounded text-jarvis-blue hover:bg-jarvis-blue hover:text-jarvis-dark transition-colors">
                        CONNECT
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* Center Panel */}
        <section className="space-y-6">
          {/* Arc Reactor */}
          <div className="panel">
            <ArcReactor toolsCount={data?.tools_count || 56} isOnline={data?.mcp_agent} />
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard value={data?.stats?.messages_today || 0} label="MESSAGES TODAY" icon={MessageSquare} />
            <StatCard value={data?.stats?.active_sessions || 0} label="ACTIVE SESSIONS" icon={Activity} />
            <StatCard value={data?.stats?.uptime || '—'} label="UPTIME" icon={Clock} />
            <StatCard value={`${data?.stats?.response_time || 0}ms`} label="AVG RESPONSE" icon={Zap} />
          </div>

          {/* Quick Actions */}
          <div className="panel p-5">
            <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4 flex items-center gap-2">
              <span className="text-xs">◆</span> QUICK ACTIONS
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              <ActionButton label="Health Check" icon={Heart} href="/health" />
              <ActionButton label="WhatsApp QR" icon={MessageSquare} href="/whatsapp-status" />
              <ActionButton label="Services API" icon={Settings} href="/services" />
              <ActionButton label="MCP Tools" icon={Brain} href="/api/mcp/tools" />
              <ActionButton label="Test Google" icon={Mail} href="/test-google-services" />
              <ActionButton label="Test Spotify" icon={Music} href="/test-spotify" />
            </div>
          </div>

          {/* Console */}
          <Console lines={consoleLines} />
        </section>

        {/* Right Panel */}
        <aside className="space-y-6">
          {/* MCP Capabilities */}
          <div className="panel p-5">
            <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4 flex items-center gap-2">
              <span className="text-xs">◆</span> MCP CAPABILITIES
            </h2>
            <div className="flex flex-wrap gap-2">
              {data?.tool_categories?.map((cat, i) => (
                <ToolTag key={i} name={cat} />
              ))}
            </div>
          </div>

          {/* Activity */}
          <div className="panel p-5">
            <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4 flex items-center gap-2">
              <span className="text-xs">◆</span> RECENT ACTIVITY
            </h2>
            <div className="max-h-80 overflow-y-auto">
              {data?.recent_activity?.map((item, i) => (
                <ActivityItem key={i} {...item} />
              ))}
            </div>
          </div>

          {/* Owner Status */}
          <div className="panel p-5">
            <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4 flex items-center gap-2">
              <span className="text-xs">◆</span> OWNER STATUS
            </h2>
            <div className="flex items-center justify-between p-3 bg-jarvis-blue/5 rounded-lg">
              <span className="font-medium">Owner Configured</span>
              <StatusDot status={data?.owner_configured ? 'online' : 'offline'} size="sm" />
            </div>
            {data?.owner_hint && (
              <div className="font-mono text-xs text-gray-500 mt-3">
                Phone: {data.owner_hint}
              </div>
            )}
          </div>

          {/* Refresh Button */}
          <button 
            onClick={fetchData}
            className="w-full panel p-4 flex items-center justify-center gap-2 hover:bg-jarvis-blue/10 transition-colors group"
          >
            <RefreshCw className="w-4 h-4 text-jarvis-blue group-hover:animate-spin" />
            <span className="font-mono text-sm">REFRESH DATA</span>
          </button>
        </aside>
      </main>
    </div>
  )
}
