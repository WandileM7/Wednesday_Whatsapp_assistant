import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { 
  Settings as SettingsIcon, Shield, Key, Database, 
  Mail, Music, Brain, Check, X, ExternalLink,
  RefreshCw, AlertTriangle, Info
} from 'lucide-react'
import { StatusDot } from '../components/UIComponents'

export default function Settings() {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetchConfig = async () => {
    try {
      const [dashboardRes, servicesRes] = await Promise.all([
        fetch('/api/dashboard/data'),
        fetch('/api/services/status')
      ])
      
      if (dashboardRes.ok) {
        const data = await dashboardRes.json()
        setConfig(prev => ({ ...prev, ...data }))
      }
      if (servicesRes.ok) {
        const data = await servicesRes.json()
        setConfig(prev => ({ ...prev, services_detail: data }))
      }
    } catch (err) {
      console.error('Failed to fetch config:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchConfig()
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

  const authServices = [
    { 
      name: 'Google Services', 
      icon: Mail, 
      configured: config?.google_auth,
      loginUrl: '/api/google-login',
      description: 'Gmail, Calendar, Keep, Contacts',
      features: ['Read/Send emails', 'Manage calendar', 'Sync tasks from Keep']
    },
    { 
      name: 'Spotify', 
      icon: Music, 
      configured: config?.spotify_auth,
      loginUrl: '/api/spotify-login',
      description: 'Music playback control',
      features: ['Play/pause music', 'Search tracks', 'Control playback']
    },
    { 
      name: 'Owner Authentication', 
      icon: Shield, 
      configured: config?.owner_configured,
      description: 'Admin access control',
      features: ['Whitelist management', 'Block users', 'Admin commands'],
      envVar: 'OWNER_PHONE'
    },
    { 
      name: 'ElevenLabs', 
      icon: Brain, 
      configured: config?.elevenlabs_available,
      description: 'Voice synthesis',
      features: ['Text-to-speech', 'Custom voices', 'Audio responses'],
      envVar: 'ELEVENLABS_API_KEY'
    },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-orbitron text-2xl font-bold tracking-wider">SETTINGS</h1>
          <p className="font-mono text-sm text-gray-500 mt-1">System configuration and authentication</p>
        </div>
        <button 
          onClick={fetchConfig}
          className="flex items-center gap-2 px-4 py-2 bg-jarvis-blue/10 border border-jarvis-blue/30 rounded-lg hover:bg-jarvis-blue/20 transition-colors"
        >
          <RefreshCw className="w-4 h-4 text-jarvis-blue" />
          <span className="font-mono text-sm">REFRESH</span>
        </button>
      </div>

      {/* Quick Setup Status */}
      <div className="panel p-6">
        <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4 flex items-center gap-2">
          <span className="text-xs">◆</span> QUICK STATUS
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center p-4 bg-jarvis-blue/5 rounded-lg">
            <div className={`font-orbitron text-2xl ${config?.google_auth ? 'text-jarvis-green' : 'text-jarvis-red'}`}>
              {config?.google_auth ? <Check className="w-8 h-8 mx-auto" /> : <X className="w-8 h-8 mx-auto" />}
            </div>
            <div className="text-xs text-gray-400 mt-2">GOOGLE</div>
          </div>
          <div className="text-center p-4 bg-jarvis-blue/5 rounded-lg">
            <div className={`font-orbitron text-2xl ${config?.spotify_auth ? 'text-jarvis-green' : 'text-jarvis-red'}`}>
              {config?.spotify_auth ? <Check className="w-8 h-8 mx-auto" /> : <X className="w-8 h-8 mx-auto" />}
            </div>
            <div className="text-xs text-gray-400 mt-2">SPOTIFY</div>
          </div>
          <div className="text-center p-4 bg-jarvis-blue/5 rounded-lg">
            <div className={`font-orbitron text-2xl ${config?.whatsapp_connected ? 'text-jarvis-green' : 'text-jarvis-red'}`}>
              {config?.whatsapp_connected ? <Check className="w-8 h-8 mx-auto" /> : <X className="w-8 h-8 mx-auto" />}
            </div>
            <div className="text-xs text-gray-400 mt-2">WHATSAPP</div>
          </div>
          <div className="text-center p-4 bg-jarvis-blue/5 rounded-lg">
            <div className={`font-orbitron text-2xl ${config?.owner_configured ? 'text-jarvis-green' : 'text-jarvis-orange'}`}>
              {config?.owner_configured ? <Check className="w-8 h-8 mx-auto" /> : <AlertTriangle className="w-8 h-8 mx-auto" />}
            </div>
            <div className="text-xs text-gray-400 mt-2">OWNER</div>
          </div>
        </div>
      </div>

      {/* Authentication Services */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {authServices.map((service, i) => {
          const Icon = service.icon
          return (
            <motion.div 
              key={i}
              className="panel p-6"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-lg bg-jarvis-blue/10 flex items-center justify-center">
                    <Icon className="w-6 h-6 text-jarvis-blue" />
                  </div>
                  <div>
                    <h3 className="font-semibold">{service.name}</h3>
                    <p className="text-xs text-gray-500">{service.description}</p>
                  </div>
                </div>
                <StatusDot status={service.configured ? 'online' : 'offline'} />
              </div>

              <div className="mb-4">
                <div className="text-xs text-gray-400 mb-2">FEATURES</div>
                <div className="flex flex-wrap gap-1">
                  {service.features.map((feature, j) => (
                    <span key={j} className="text-xs px-2 py-1 bg-jarvis-blue/5 rounded">
                      {feature}
                    </span>
                  ))}
                </div>
              </div>

              {service.envVar && !service.configured && (
                <div className="mb-4 p-3 bg-jarvis-orange/10 rounded-lg text-sm">
                  <div className="flex items-center gap-2 text-jarvis-orange">
                    <Info className="w-4 h-4" />
                    <span>Set <code className="font-mono">{service.envVar}</code> environment variable</span>
                  </div>
                </div>
              )}

              {service.loginUrl && !service.configured && (
                <a
                  href={service.loginUrl}
                  className="flex items-center justify-center gap-2 w-full py-3 bg-jarvis-blue/10 border border-jarvis-blue/30 rounded-lg font-mono text-sm hover:bg-jarvis-blue/20 transition-colors"
                >
                  <Key className="w-4 h-4" />
                  AUTHENTICATE
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}

              {service.configured && (
                <div className="flex items-center justify-center gap-2 py-3 bg-jarvis-green/10 border border-jarvis-green/30 rounded-lg text-jarvis-green text-sm">
                  <Check className="w-4 h-4" />
                  CONFIGURED
                </div>
              )}
            </motion.div>
          )
        })}
      </div>

      {/* Environment Variables */}
      <div className="panel p-6">
        <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4 flex items-center gap-2">
          <span className="text-xs">◆</span> ENVIRONMENT CONFIGURATION
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {[
            { name: 'GEMINI_API_KEY', required: true },
            { name: 'OWNER_PHONE', required: true },
            { name: 'WAHA_URL', required: true },
            { name: 'GOOGLE_CLIENT_ID', required: false },
            { name: 'GOOGLE_CLIENT_SECRET', required: false },
            { name: 'SPOTIFY_CLIENT_ID', required: false },
            { name: 'SPOTIFY_SECRET', required: false },
            { name: 'ELEVENLABS_API_KEY', required: false },
            { name: 'HOME_ASSISTANT_URL', required: false },
          ].map((env, i) => (
            <div key={i} className="flex items-center justify-between p-3 bg-jarvis-blue/5 rounded-lg">
              <code className="font-mono text-xs">{env.name}</code>
              <span className={`text-xs px-2 py-0.5 rounded ${env.required ? 'bg-jarvis-orange/20 text-jarvis-orange' : 'bg-gray-700 text-gray-400'}`}>
                {env.required ? 'REQUIRED' : 'OPTIONAL'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* MCP Tools Info */}
      <div className="panel p-6">
        <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4 flex items-center gap-2">
          <span className="text-xs">◆</span> MCP TOOLS
        </h2>
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-orbitron text-3xl text-jarvis-blue">{config?.tools_count || 0}</div>
            <div className="text-xs text-gray-400">TOOLS AVAILABLE</div>
          </div>
          <a
            href="/api/mcp/tools"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 bg-jarvis-blue/10 border border-jarvis-blue/30 rounded-lg font-mono text-sm hover:bg-jarvis-blue/20 transition-colors"
          >
            VIEW ALL TOOLS
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
        <div className="flex flex-wrap gap-2">
          {config?.tool_categories?.map((cat, i) => (
            <span key={i} className="font-mono text-xs px-3 py-1.5 rounded bg-jarvis-blue/10 border border-jarvis-blue/20 text-jarvis-blue">
              {cat}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
