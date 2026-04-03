import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Activity,
  ArrowRight,
  Bot,
  Clock,
  MessageSquare,
  Radio,
  RefreshCw,
  Send,
  Server,
  Smartphone,
  Workflow,
  Zap,
  CheckCircle2,
  XCircle,
  ChevronRight,
} from 'lucide-react'
import {
  Card,
  SectionTitle,
  ServiceRow,
  StatCard,
  ActionButton,
  Badge,
  Skeleton,
  StatusDot,
} from '../components/UIComponents'

// ---------------------------------------------------------------------------
// Data pipeline node
// ---------------------------------------------------------------------------
function PipelineNode({ label, icon: Icon, status, delay = 0 }) {
  const colorMap = {
    online:  'border-wed-green/30 bg-wed-green/[0.06]',
    offline: 'border-wed-red/30 bg-wed-red/[0.06]',
    loading: 'border-wed-cyan/30 bg-wed-cyan/[0.06]',
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay, duration: 0.3 }}
      className={`flex flex-col items-center gap-2`}
    >
      <div className={`w-14 h-14 rounded-2xl border ${colorMap[status] || colorMap.offline} flex items-center justify-center transition-all duration-300`}>
        <Icon size={20} className={
          status === 'online' ? 'text-wed-green' :
          status === 'loading' ? 'text-wed-cyan' :
          'text-wed-red'
        } />
      </div>
      <span className="text-xs text-gray-400 font-medium">{label}</span>
    </motion.div>
  )
}

function PipelineArrow({ active, delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay, duration: 0.3 }}
      className="flex items-center -mt-5"
    >
      <div className={`h-px w-8 ${active ? 'bg-gradient-to-r from-wed-cyan/40 to-wed-cyan/10' : 'bg-white/10'} transition-colors duration-500`} />
      <ChevronRight size={12} className={active ? 'text-wed-cyan/50' : 'text-white/10'} />
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// Message test panel
// ---------------------------------------------------------------------------
function TestPanel() {
  const [chatId, setChatId] = useState('')
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState(null)

  async function handleSend() {
    if (!chatId || !message) return
    setSending(true)
    setResult(null)
    try {
      const res = await fetch('/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chatId, text: message }),
      })
      const data = await res.json()
      setResult(data.success ? 'sent' : 'failed')
    } catch {
      setResult('failed')
    } finally {
      setSending(false)
      setTimeout(() => setResult(null), 3000)
    }
  }

  return (
    <Card className="col-span-full">
      <SectionTitle subtitle="Send a test message through WAHA">
        Quick Send
      </SectionTitle>
      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Chat ID (e.g. 1234567890@c.us)"
          value={chatId}
          onChange={(e) => setChatId(e.target.value)}
          className="flex-1 bg-surface-1 border border-white/[0.06] rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 font-mono focus:outline-none focus:border-wed-cyan/30 transition-colors"
        />
        <input
          type="text"
          placeholder="Message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          className="flex-[2] bg-surface-1 border border-white/[0.06] rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-wed-cyan/30 transition-colors"
        />
        <ActionButton onClick={handleSend} loading={sending} icon={Send} disabled={!chatId || !message}>
          Send
        </ActionButton>
      </div>
      <AnimatePresence>
        {result && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-3"
          >
            <div className={`flex items-center gap-2 text-xs font-mono ${
              result === 'sent' ? 'text-wed-green' : 'text-wed-red'
            }`}>
              {result === 'sent' ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
              {result === 'sent' ? 'Message sent successfully' : 'Failed to send message'}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Activity log
// ---------------------------------------------------------------------------
function ActivityLog({ logs }) {
  if (!logs.length) {
    return (
      <div className="py-8 text-center text-xs text-gray-600">
        No recent activity
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {logs.map((log, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.05 }}
          className="flex items-center gap-3 py-2 border-b border-white/[0.03] last:border-0"
        >
          <div className={`w-1.5 h-1.5 rounded-full ${
            log.type === 'success' ? 'bg-wed-green' :
            log.type === 'error' ? 'bg-wed-red' :
            'bg-wed-cyan'
          }`} />
          <span className="text-xs text-gray-400 font-mono w-16 shrink-0">{log.time}</span>
          <span className="text-xs text-gray-300 truncate">{log.message}</span>
        </motion.div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export default function Dashboard() {
  const [health, setHealth] = useState(null)
  const [n8nStatus, setN8nStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [logs, setLogs] = useState([])

  const fetchStatus = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    try {
      const [hRes, nRes] = await Promise.all([
        fetch('/health').then(r => r.json()).catch(() => null),
        fetch('/n8n-status').then(r => r.json()).catch(() => null),
      ])
      setHealth(hRes)
      setN8nStatus(nRes)

      // Add to activity log
      const now = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })
      setLogs(prev => [
        {
          time: now,
          message: `Status check — relay: ${hRes?.status || 'error'}, n8n: ${hRes?.n8n || 'unknown'}`,
          type: hRes?.status === 'healthy' ? 'success' : 'error',
        },
        ...prev,
      ].slice(0, 10))
    } catch {
      // silently fail
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(() => fetchStatus(), 30000)
    return () => clearInterval(interval)
  }, [fetchStatus])

  const relayOk = health?.status === 'healthy'
  const n8nOk = health?.n8n === 'connected'
  const waOk = health?.whatsapp === 'connected'

  const servicesOnline = [relayOk, n8nOk, waOk].filter(Boolean).length

  return (
    <div className="space-y-8">
      {/* Hero header */}
      <div className="flex items-end justify-between">
        <div>
          <motion.h1
            className="text-3xl font-display font-bold text-gradient"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            System Overview
          </motion.h1>
          <motion.p
            className="text-sm text-gray-500 mt-1"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
          >
            {health?.timestamp
              ? `Last checked ${new Date(health.timestamp).toLocaleTimeString()}`
              : 'Connecting…'}
          </motion.p>
        </div>
        <ActionButton
          onClick={() => fetchStatus(true)}
          loading={refreshing}
          icon={RefreshCw}
          variant="ghost"
        >
          Refresh
        </ActionButton>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))
        ) : (
          <>
            <StatCard
              label="Services"
              value={`${servicesOnline}/3`}
              sub={servicesOnline === 3 ? 'All systems operational' : 'Some services down'}
              icon={Activity}
              color={servicesOnline === 3 ? 'green' : 'orange'}
            />
            <StatCard
              label="Relay"
              value={relayOk ? 'Online' : 'Offline'}
              sub="Flask → n8n bridge"
              icon={Zap}
              color={relayOk ? 'cyan' : 'orange'}
            />
            <StatCard
              label="n8n"
              value={n8nOk ? 'Connected' : 'Down'}
              sub="Workflow engine"
              icon={Workflow}
              color={n8nOk ? 'green' : 'orange'}
            />
            <StatCard
              label="WhatsApp"
              value={waOk ? 'Connected' : 'Offline'}
              sub="WAHA gateway"
              icon={Smartphone}
              color={waOk ? 'green' : 'orange'}
            />
          </>
        )}
      </div>

      {/* Pipeline visualization */}
      <Card>
        <SectionTitle subtitle="Message flow through the system">
          Data Pipeline
        </SectionTitle>
        <div className="flex items-center justify-center py-6 gap-2">
          <PipelineNode label="WhatsApp" icon={MessageSquare} status={waOk ? 'online' : 'offline'} delay={0} />
          <PipelineArrow active={waOk} delay={0.1} />
          <PipelineNode label="WAHA" icon={Radio} status={waOk ? 'online' : 'offline'} delay={0.15} />
          <PipelineArrow active={waOk && relayOk} delay={0.2} />
          <PipelineNode label="Relay" icon={Server} status={relayOk ? 'online' : 'offline'} delay={0.25} />
          <PipelineArrow active={relayOk && n8nOk} delay={0.3} />
          <PipelineNode label="n8n" icon={Workflow} status={n8nOk ? 'online' : 'offline'} delay={0.35} />
          <PipelineArrow active={n8nOk} delay={0.4} />
          <PipelineNode label="AI Agent" icon={Bot} status={n8nOk ? 'online' : 'offline'} delay={0.45} />
        </div>
      </Card>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Services */}
        <Card className="lg:col-span-3">
          <SectionTitle subtitle="Infrastructure health">
            Services
          </SectionTitle>
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : (
            <div>
              <ServiceRow
                name="Flask Relay"
                status={relayOk ? 'connected' : 'unreachable'}
                detail="Port 5000 — webhook forwarding"
                icon={Server}
              />
              <ServiceRow
                name="n8n Workflow Engine"
                status={n8nOk ? 'connected' : 'unreachable'}
                detail={n8nStatus?.url || 'Port 5678'}
                icon={Workflow}
              />
              <ServiceRow
                name="WhatsApp (WAHA)"
                status={waOk ? 'connected' : 'unreachable'}
                detail="Baileys gateway — Port 3000"
                icon={Smartphone}
              />
            </div>
          )}
        </Card>

        {/* Activity log */}
        <Card className="lg:col-span-2">
          <SectionTitle subtitle="Recent status checks">
            Activity
          </SectionTitle>
          <ActivityLog logs={logs} />
        </Card>
      </div>

      {/* Test panel */}
      <TestPanel />
    </div>
  )
}
