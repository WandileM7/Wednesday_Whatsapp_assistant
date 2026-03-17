import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { 
  Activity, Zap, MessageSquare, Brain, Music, Mail, 
  Calendar, Home, Mic, Shield, Database, Cpu, Globe,
  RefreshCw, CheckCircle, XCircle, AlertTriangle
} from 'lucide-react'
import { StatusDot } from '../components/UIComponents'

const serviceDetails = {
  whatsapp_service: { name: 'WhatsApp Gateway', icon: MessageSquare, description: 'Message handling and delivery' },
  gemini_ai: { name: 'Gemini AI', icon: Brain, description: 'Natural language processing' },
  database: { name: 'Database', icon: Database, description: 'Data persistence and storage' },
  media_generation: { name: 'Media Generation', icon: Zap, description: 'Image and video creation' },
  google_services: { name: 'Google Services', icon: Mail, description: 'Gmail, Calendar, Keep integration' },
  spotify: { name: 'Spotify', icon: Music, description: 'Music playback control' },
  mcp_agent: { name: 'MCP Agent', icon: Cpu, description: 'Model Context Protocol tools' },
  elevenlabs: { name: 'ElevenLabs', icon: Mic, description: 'Voice synthesis' },
  smart_home: { name: 'Smart Home', icon: Home, description: 'Home Assistant integration' },
}

export default function Services() {
  const [services, setServices] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [pinging, setPinging] = useState(null)

  const fetchServices = async () => {
    try {
      const [statusRes, healthRes] = await Promise.all([
        fetch('/api/services/status'),
        fetch('/api/services/health')
      ])
      
      if (statusRes.ok) {
        const statusData = await statusRes.json()
        setServices(statusData)
      }
      
      if (healthRes.ok) {
        const healthData = await healthRes.json()
        setHealth(healthData)
      }
    } catch (err) {
      console.error('Failed to fetch services:', err)
    } finally {
      setLoading(false)
    }
  }

  const pingService = async (serviceName) => {
    setPinging(serviceName)
    try {
      const res = await fetch(`/api/services/ping/${serviceName}`, { method: 'POST' })
      const data = await res.json()
      // Refresh services after ping
      fetchServices()
    } catch (err) {
      console.error('Ping failed:', err)
    } finally {
      setPinging(null)
    }
  }

  useEffect(() => {
    fetchServices()
    const interval = setInterval(fetchServices, 30000)
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

  const getStatusIcon = (status) => {
    switch (status) {
      case 'online': return <CheckCircle className="w-5 h-5 text-jarvis-green" />
      case 'warning': return <AlertTriangle className="w-5 h-5 text-jarvis-orange" />
      default: return <XCircle className="w-5 h-5 text-jarvis-red" />
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-orbitron text-2xl font-bold tracking-wider">SERVICES</h1>
          <p className="font-mono text-sm text-gray-500 mt-1">System service monitoring and control</p>
        </div>
        <button 
          onClick={fetchServices}
          className="flex items-center gap-2 px-4 py-2 bg-jarvis-blue/10 border border-jarvis-blue/30 rounded-lg hover:bg-jarvis-blue/20 transition-colors"
        >
          <RefreshCw className="w-4 h-4 text-jarvis-blue" />
          <span className="font-mono text-sm">REFRESH</span>
        </button>
      </div>

      {/* Health Summary */}
      {health && (
        <div className="panel p-5">
          <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4">SYSTEM HEALTH</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="font-orbitron text-2xl font-bold text-jarvis-green">{health.healthy_count || 0}</div>
              <div className="text-xs text-gray-400">HEALTHY</div>
            </div>
            <div className="text-center">
              <div className="font-orbitron text-2xl font-bold text-jarvis-orange">{health.warning_count || 0}</div>
              <div className="text-xs text-gray-400">WARNING</div>
            </div>
            <div className="text-center">
              <div className="font-orbitron text-2xl font-bold text-jarvis-red">{health.error_count || 0}</div>
              <div className="text-xs text-gray-400">ERROR</div>
            </div>
            <div className="text-center">
              <div className="font-orbitron text-2xl font-bold text-jarvis-blue">{health.total_services || 0}</div>
              <div className="text-xs text-gray-400">TOTAL</div>
            </div>
          </div>
        </div>
      )}

      {/* Services Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {services?.services && Object.entries(services.services).map(([key, service]) => {
          const details = serviceDetails[key] || { name: key, icon: Activity, description: 'Service' }
          const Icon = details.icon
          const status = service.status || 'offline'
          
          return (
            <motion.div 
              key={key}
              className="panel p-5"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-jarvis-blue/10 flex items-center justify-center">
                    <Icon className="w-5 h-5 text-jarvis-blue" />
                  </div>
                  <div>
                    <h3 className="font-semibold">{details.name}</h3>
                    <p className="text-xs text-gray-500">{details.description}</p>
                  </div>
                </div>
                {getStatusIcon(status)}
              </div>
              
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Status</span>
                  <span className={`font-mono ${
                    status === 'online' ? 'text-jarvis-green' : 
                    status === 'warning' ? 'text-jarvis-orange' : 'text-jarvis-red'
                  }`}>{status.toUpperCase()}</span>
                </div>
                {service.last_check && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Last Check</span>
                    <span className="font-mono text-xs">{new Date(service.last_check).toLocaleTimeString()}</span>
                  </div>
                )}
                {service.response_time && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Response</span>
                    <span className="font-mono">{service.response_time}ms</span>
                  </div>
                )}
              </div>
              
              <button 
                onClick={() => pingService(key)}
                disabled={pinging === key}
                className="mt-4 w-full py-2 bg-jarvis-blue/10 border border-jarvis-blue/30 rounded text-sm font-mono hover:bg-jarvis-blue/20 transition-colors disabled:opacity-50"
              >
                {pinging === key ? 'PINGING...' : 'PING'}
              </button>
            </motion.div>
          )
        })}
      </div>

      {/* API Endpoints */}
      <div className="panel p-5">
        <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4">API ENDPOINTS</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {[
            { path: '/health', label: 'Health Check' },
            { path: '/api/services/status', label: 'Services Status' },
            { path: '/api/mcp/tools', label: 'MCP Tools' },
            { path: '/api/dashboard/data', label: 'Dashboard Data' },
            { path: '/api/notifications/stats', label: 'Notification Stats' },
            { path: '/api/database/stats', label: 'Database Stats' },
          ].map((endpoint, i) => (
            <a 
              key={i}
              href={endpoint.path}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between p-3 bg-jarvis-blue/5 rounded-lg hover:bg-jarvis-blue/10 transition-colors"
            >
              <span className="font-mono text-sm">{endpoint.label}</span>
              <Globe className="w-4 h-4 text-jarvis-blue" />
            </a>
          ))}
        </div>
      </div>
    </div>
  )
}
