import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { 
  Activity, Zap, MessageSquare, Clock, Settings, 
  Brain, Mic, Home, Heart, Mail, Calendar,
  Music, RefreshCw, Shield
} from 'lucide-react'
import ArcReactor, { 
  StatusDot, ServiceCard, StatCard, ActionButton, 
  Console, ToolTag, ActivityItem 
} from '../components/UIComponents'

const iconMap = {
  Brain, Zap, MessageSquare, Music, Mail, Calendar, Home, Mic, Shield, Activity
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    try {
      const response = await fetch('/api/dashboard/data')
      if (!response.ok) throw new Error('Failed to fetch')
      const json = await response.json()
      setData(json)
    } catch (err) {
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
        ],
        tool_categories: ['Core', 'Workflows', 'Smart Home', 'Voice', 'Memory', 'Security'],
        stats: { messages_today: 0, active_sessions: 0, uptime: '—', response_time: 0 },
        google_auth: false,
        spotify_auth: false,
        owner_configured: false,
        recent_activity: []
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

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
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
    <div className="space-y-6">
      {/* Page Header */}
      <div className="text-center mb-8">
        <motion.h1 
          className="font-orbitron text-4xl font-black tracking-[0.2em] bg-gradient-to-r from-jarvis-blue via-white to-jarvis-blue bg-clip-text text-transparent"
          animate={{ filter: ['brightness(1)', 'brightness(1.2)', 'brightness(1)'] }}
          transition={{ duration: 3, repeat: Infinity }}
        >
          COMMAND CENTER
        </motion.h1>
        <p className="font-mono text-sm text-gray-500 mt-2">
          SYSTEM STATUS: {data?.system_status?.toUpperCase() || 'UNKNOWN'}
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[300px_1fr_300px] gap-6">
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
                  onClick={() => navigate('/services')}
                />
              ))}
            </div>
            <Link 
              to="/services" 
              className="block mt-4 text-center font-mono text-xs text-jarvis-blue hover:underline"
            >
              VIEW ALL SERVICES →
            </Link>
          </div>

          {/* Authentication */}
          <div className="panel p-5">
            <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4 flex items-center gap-2">
              <span className="text-xs">◆</span> AUTHENTICATION
            </h2>
            <div className="space-y-3">
              {[
                { name: 'Google', auth: data?.google_auth, href: '/api/google-login' },
                { name: 'Spotify', auth: data?.spotify_auth, href: '/api/spotify-login' },
                { name: 'Owner', auth: data?.owner_configured }
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
              <ActionButton label="Health Check" icon={Heart} onClick={() => window.open('/health', '_blank')} />
              <ActionButton label="WhatsApp QR" icon={MessageSquare} onClick={() => navigate('/whatsapp')} />
              <ActionButton label="Services" icon={Settings} onClick={() => navigate('/services')} />
              <ActionButton label="MCP Tools" icon={Brain} onClick={() => window.open('/api/mcp/tools', '_blank')} />
              <ActionButton label="Google Auth" icon={Mail} onClick={() => window.location.href = '/api/google-login'} />
              <ActionButton label="Spotify Auth" icon={Music} onClick={() => window.location.href = '/api/spotify-login'} />
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
              {data?.recent_activity?.length > 0 ? (
                data.recent_activity.map((item, i) => (
                  <ActivityItem key={i} {...item} />
                ))
              ) : (
                <p className="text-gray-500 text-sm">No recent activity</p>
              )}
            </div>
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
      </div>
    </div>
  )
}
