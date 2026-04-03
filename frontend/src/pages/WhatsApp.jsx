import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  CheckCircle2,
  Loader2,
  MessageCircle,
  QrCode,
  RefreshCw,
  Smartphone,
  Unplug,
  Wifi,
  WifiOff,
} from 'lucide-react'
import {
  Card,
  SectionTitle,
  ActionButton,
  Badge,
  StatusDot,
  Skeleton,
} from '../components/UIComponents'

// ---------------------------------------------------------------------------
// QR display
// ---------------------------------------------------------------------------
function QRDisplay({ qrData, loading }) {
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }}
        >
          <Loader2 size={24} className="text-wed-cyan" />
        </motion.div>
        <p className="text-xs text-gray-500 mt-3">Fetching QR code…</p>
      </div>
    )
  }

  if (!qrData) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="w-14 h-14 rounded-2xl bg-white/[0.04] flex items-center justify-center mb-4">
          <QrCode size={24} className="text-gray-600" />
        </div>
        <p className="text-sm text-gray-400">No QR code available</p>
        <p className="text-xs text-gray-600 mt-1">Click refresh below to fetch one</p>
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="flex flex-col items-center py-6"
    >
      <div className="relative p-4 rounded-2xl bg-white">
        <img
          src={qrData.startsWith('data:') ? qrData : `data:image/png;base64,${qrData}`}
          alt="WhatsApp QR Code"
          className="w-56 h-56 rounded-lg"
        />
        {/* Corner accents */}
        <div className="absolute top-0 left-0 w-6 h-6 border-t-2 border-l-2 border-wed-cyan rounded-tl-2xl" />
        <div className="absolute top-0 right-0 w-6 h-6 border-t-2 border-r-2 border-wed-cyan rounded-tr-2xl" />
        <div className="absolute bottom-0 left-0 w-6 h-6 border-b-2 border-l-2 border-wed-cyan rounded-bl-2xl" />
        <div className="absolute bottom-0 right-0 w-6 h-6 border-b-2 border-r-2 border-wed-cyan rounded-br-2xl" />
      </div>
      <p className="text-xs text-gray-500 mt-4">
        Scan with WhatsApp to connect
      </p>
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// Connection status card
// ---------------------------------------------------------------------------
function ConnectionInfo({ status, loading }) {
  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-5 w-64" />
        <Skeleton className="h-5 w-48" />
      </div>
    )
  }

  const session = status?.name || status?.session || 'default'
  const state = status?.status || 'unknown'
  const isConnected = state === 'WORKING' || state === 'CONNECTED' || state === 'AUTHENTICATED'

  return (
    <div className="space-y-4">
      {/* Status header */}
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
          isConnected
            ? 'bg-wed-green/10 border border-wed-green/20'
            : 'bg-wed-red/10 border border-wed-red/20'
        }`}>
          {isConnected ? (
            <Wifi size={18} className="text-wed-green" />
          ) : (
            <WifiOff size={18} className="text-wed-red" />
          )}
        </div>
        <div>
          <h3 className="text-lg font-display font-semibold text-white">
            {isConnected ? 'Connected' : 'Disconnected'}
          </h3>
          <p className="text-xs text-gray-500">
            Session: <span className="font-mono text-gray-400">{session}</span>
          </p>
        </div>
      </div>

      {/* Details */}
      <div className="space-y-2">
        <div className="flex items-center justify-between py-2 border-b border-white/[0.04]">
          <span className="text-xs text-gray-500">State</span>
          <Badge color={isConnected ? 'green' : 'red'}>{state}</Badge>
        </div>
        {status?.me && (
          <div className="flex items-center justify-between py-2 border-b border-white/[0.04]">
            <span className="text-xs text-gray-500">Phone</span>
            <span className="text-sm font-mono text-gray-300">{status.me.id || status.me}</span>
          </div>
        )}
        {status?.engine && (
          <div className="flex items-center justify-between py-2 border-b border-white/[0.04]">
            <span className="text-xs text-gray-500">Engine</span>
            <span className="text-xs font-mono text-gray-400">{status.engine}</span>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Steps card
// ---------------------------------------------------------------------------
function SetupSteps({ isConnected }) {
  const steps = [
    { label: 'WAHA service running', done: true },
    { label: 'QR code generated', done: true },
    { label: 'Phone scanned QR', done: isConnected },
    { label: 'Session authenticated', done: isConnected },
  ]

  return (
    <div className="space-y-3">
      {steps.map((step, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.05 }}
          className="flex items-center gap-3"
        >
          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-mono ${
            step.done
              ? 'bg-wed-green/10 text-wed-green border border-wed-green/20'
              : 'bg-white/[0.04] text-gray-600 border border-white/[0.06]'
          }`}>
            {step.done ? <CheckCircle2 size={12} /> : i + 1}
          </div>
          <span className={`text-sm ${step.done ? 'text-gray-300' : 'text-gray-500'}`}>
            {step.label}
          </span>
        </motion.div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// WhatsApp page
// ---------------------------------------------------------------------------
export default function WhatsApp() {
  const [waStatus, setWaStatus] = useState(null)
  const [qrData, setQrData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [qrLoading, setQrLoading] = useState(false)

  const fetchAll = useCallback(async () => {
    try {
      const [sRes, qRes] = await Promise.all([
        fetch('/whatsapp-status').then(r => r.json()).catch(() => null),
        fetch('/whatsapp-qr').then(r => r.json()).catch(() => null),
      ])
      setWaStatus(sRes)
      if (qRes && !qRes.error) {
        setQrData(qRes.qr || qRes.data || qRes.image || null)
      }
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 15000)
    return () => clearInterval(interval)
  }, [fetchAll])

  const handleRefreshQR = async () => {
    setQrLoading(true)
    try {
      const res = await fetch('/whatsapp-qr')
      const data = await res.json()
      if (data && !data.error) {
        setQrData(data.qr || data.data || data.image || null)
      }
    } catch {
      // silently fail
    } finally {
      setQrLoading(false)
    }
  }

  const state = waStatus?.status || 'unknown'
  const isConnected = state === 'WORKING' || state === 'CONNECTED' || state === 'AUTHENTICATED'

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <motion.h1
            className="text-3xl font-display font-bold text-gradient"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
          >
            WhatsApp
          </motion.h1>
          <motion.p
            className="text-sm text-gray-500 mt-1"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
          >
            Connection management & QR pairing
          </motion.p>
        </div>
        <div className="flex items-center gap-2">
          <StatusDot status={isConnected ? 'connected' : 'offline'} size="lg" />
          <span className="text-sm text-gray-400 font-medium">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* QR code */}
        <Card>
          <SectionTitle
            subtitle="Scan to pair your WhatsApp"
            action={
              <ActionButton
                onClick={handleRefreshQR}
                loading={qrLoading}
                icon={RefreshCw}
                variant="ghost"
              >
                Refresh
              </ActionButton>
            }
          >
            QR Code
          </SectionTitle>
          <QRDisplay qrData={qrData} loading={qrLoading} />
        </Card>

        {/* Status & steps */}
        <div className="space-y-6">
          <Card>
            <SectionTitle subtitle="Current session info">
              Connection
            </SectionTitle>
            <ConnectionInfo status={waStatus} loading={loading} />
          </Card>

          <Card>
            <SectionTitle subtitle="Pairing checklist">
              Setup Progress
            </SectionTitle>
            <SetupSteps isConnected={isConnected} />
          </Card>
        </div>
      </div>

      {/* Tips */}
      <Card>
        <SectionTitle subtitle="Helpful reminders">
          Tips
        </SectionTitle>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            { icon: Smartphone, title: 'Open WhatsApp', desc: 'Go to Settings → Linked Devices → Link a Device' },
            { icon: QrCode, title: 'Scan QR', desc: 'Point your phone camera at the QR code above' },
            { icon: MessageCircle, title: 'Start chatting', desc: 'Send a message — Wednesday will respond via n8n' },
          ].map((tip, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 * i }}
              className="flex gap-3 p-3 rounded-xl bg-white/[0.02]"
            >
              <div className="w-8 h-8 rounded-lg bg-wed-cyan/[0.06] border border-wed-cyan/10 flex items-center justify-center shrink-0">
                <tip.icon size={14} className="text-wed-cyan" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-200">{tip.title}</p>
                <p className="text-xs text-gray-500 mt-0.5">{tip.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </Card>
    </div>
  )
}
