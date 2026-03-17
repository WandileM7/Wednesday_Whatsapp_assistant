import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { 
  MessageSquare, QrCode, RefreshCw, Check, X, AlertTriangle,
  Smartphone, Wifi, WifiOff, Send, LogOut, Power
} from 'lucide-react'
import { StatusDot } from '../components/UIComponents'

export default function WhatsApp() {
  const [status, setStatus] = useState(null)
  const [qrData, setQrData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sendingTest, setSendingTest] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [reconnecting, setReconnecting] = useState(false)
  const [actionResult, setActionResult] = useState(null)

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/whatsapp/status')
      if (res.ok) {
        const data = await res.json()
        setStatus(data)
      }
    } catch (err) {
      console.error('Failed to fetch WhatsApp status:', err)
    }
  }

  const fetchQR = async () => {
    try {
      const res = await fetch('/api/whatsapp/qr')
      if (res.ok) {
        const data = await res.json()
        setQrData(data)
      }
    } catch (err) {
      console.error('Failed to fetch QR:', err)
    } finally {
      setLoading(false)
    }
  }

  const sendTestMessage = async () => {
    setSendingTest(true)
    setTestResult(null)
    try {
      const res = await fetch('/api/whatsapp/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone: 'status@broadcast',
          message: 'JARVIS test message - system operational'
        })
      })
      const data = await res.json()
      setTestResult({ success: data.success, message: data.message || 'Message sent' })
    } catch (err) {
      setTestResult({ success: false, message: err.message })
    } finally {
      setSendingTest(false)
    }
  }

  const handleReconnect = async () => {
    setReconnecting(true)
    setActionResult(null)
    try {
      const res = await fetch('/api/whatsapp/reconnect', { method: 'POST' })
      const data = await res.json()
      setActionResult({ success: data.success, message: data.message || 'Reconnect initiated' })
      if (data.success) {
        // Poll for QR code - it takes a few seconds to generate
        const pollForQR = async (attempts = 0) => {
          if (attempts > 10) return // Max 10 attempts (20 seconds)
          
          await new Promise(r => setTimeout(r, 2000))
          fetchStatus()
          fetchQR()
          
          // Check if we got a QR code
          const qrRes = await fetch('/api/whatsapp/qr')
          const qrData = await qrRes.json()
          if (!qrData.qr_code && !qrData.connected) {
            pollForQR(attempts + 1)
          }
        }
        pollForQR()
      }
    } catch (err) {
      setActionResult({ success: false, message: err.message })
    } finally {
      setReconnecting(false)
    }
  }

  const handleLogout = async () => {
    if (!confirm('Are you sure you want to logout? You will need to scan the QR code again.')) return
    
    setReconnecting(true)
    setActionResult(null)
    try {
      const res = await fetch('/api/whatsapp/logout', { method: 'POST' })
      const data = await res.json()
      setActionResult({ success: data.success, message: data.message || 'Logged out' })
      // Refresh status
      setTimeout(() => {
        fetchStatus()
        fetchQR()
      }, 1000)
    } catch (err) {
      setActionResult({ success: false, message: err.message })
    } finally {
      setReconnecting(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    fetchQR()
    const interval = setInterval(() => {
      fetchStatus()
    }, 10000)
    return () => clearInterval(interval)
  }, [])

  const isConnected = status?.connected || status?.session_status === 'WORKING'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-orbitron text-2xl font-bold tracking-wider">WHATSAPP</h1>
          <p className="font-mono text-sm text-gray-500 mt-1">Gateway connection and management</p>
        </div>
        <button 
          onClick={() => { fetchStatus(); fetchQR(); }}
          className="flex items-center gap-2 px-4 py-2 bg-jarvis-blue/10 border border-jarvis-blue/30 rounded-lg hover:bg-jarvis-blue/20 transition-colors"
        >
          <RefreshCw className="w-4 h-4 text-jarvis-blue" />
          <span className="font-mono text-sm">REFRESH</span>
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Connection Status */}
        <div className="panel p-6">
          <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-6 flex items-center gap-2">
            <span className="text-xs">◆</span> CONNECTION STATUS
          </h2>
          
          <div className="flex items-center justify-center mb-8">
            <motion.div 
              className={`w-32 h-32 rounded-full flex items-center justify-center ${
                isConnected ? 'bg-jarvis-green/20 border-2 border-jarvis-green' : 'bg-jarvis-red/20 border-2 border-jarvis-red'
              }`}
              animate={{ 
                boxShadow: isConnected 
                  ? ['0 0 20px rgba(0, 255, 136, 0.3)', '0 0 40px rgba(0, 255, 136, 0.5)', '0 0 20px rgba(0, 255, 136, 0.3)']
                  : ['0 0 20px rgba(255, 68, 68, 0.3)', '0 0 40px rgba(255, 68, 68, 0.5)', '0 0 20px rgba(255, 68, 68, 0.3)']
              }}
              transition={{ duration: 2, repeat: Infinity }}
            >
              {isConnected ? (
                <Wifi className="w-16 h-16 text-jarvis-green" />
              ) : (
                <WifiOff className="w-16 h-16 text-jarvis-red" />
              )}
            </motion.div>
          </div>

          <div className="text-center mb-6">
            <div className={`font-orbitron text-xl font-bold ${isConnected ? 'text-jarvis-green' : 'text-jarvis-red'}`}>
              {isConnected ? 'CONNECTED' : 'DISCONNECTED'}
            </div>
            <p className="text-sm text-gray-400 mt-1">
              {status?.phone_number ? `Phone: ${status.phone_number}` : 'Awaiting connection'}
            </p>
          </div>

          <div className="space-y-3">
            {[
              { label: 'Session Status', value: status?.session_status || 'Unknown' },
              { label: 'WAHA Service', value: status?.waha_available ? 'Available' : 'Unavailable' },
              { label: 'Last Activity', value: status?.last_activity || 'N/A' },
            ].map((item, i) => (
              <div key={i} className="flex justify-between items-center p-3 bg-jarvis-blue/5 rounded-lg">
                <span className="text-gray-400">{item.label}</span>
                <span className="font-mono text-sm">{item.value}</span>
              </div>
            ))}
          </div>

          {/* Test Message Button */}
          <button
            onClick={sendTestMessage}
            disabled={!isConnected || sendingTest}
            className="mt-6 w-full py-3 bg-jarvis-blue/10 border border-jarvis-blue/30 rounded-lg font-mono text-sm hover:bg-jarvis-blue/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            <Send className="w-4 h-4" />
            {sendingTest ? 'SENDING...' : 'SEND TEST MESSAGE'}
          </button>

          {testResult && (
            <div className={`mt-4 p-3 rounded-lg text-sm ${
              testResult.success ? 'bg-jarvis-green/10 text-jarvis-green' : 'bg-jarvis-red/10 text-jarvis-red'
            }`}>
              {testResult.message}
            </div>
          )}

          {/* Connection Actions */}
          <div className="mt-6 grid grid-cols-2 gap-3">
            <button
              onClick={handleReconnect}
              disabled={reconnecting}
              className="py-3 bg-jarvis-orange/10 border border-jarvis-orange/30 rounded-lg font-mono text-sm hover:bg-jarvis-orange/20 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <Power className="w-4 h-4 text-jarvis-orange" />
              {reconnecting ? 'RECONNECTING...' : 'RECONNECT'}
            </button>
            <button
              onClick={handleLogout}
              disabled={reconnecting || !isConnected}
              className="py-3 bg-jarvis-red/10 border border-jarvis-red/30 rounded-lg font-mono text-sm hover:bg-jarvis-red/20 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <LogOut className="w-4 h-4 text-jarvis-red" />
              LOGOUT
            </button>
          </div>

          {actionResult && (
            <div className={`mt-4 p-3 rounded-lg text-sm ${
              actionResult.success ? 'bg-jarvis-green/10 text-jarvis-green' : 'bg-jarvis-red/10 text-jarvis-red'
            }`}>
              {actionResult.message}
            </div>
          )}
        </div>

        {/* QR Code */}
        <div className="panel p-6">
          <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-6 flex items-center gap-2">
            <span className="text-xs">◆</span> QR CODE
          </h2>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <motion.div
                className="w-12 h-12 rounded-full border-4 border-jarvis-blue/30 border-t-jarvis-blue"
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              />
            </div>
          ) : isConnected ? (
            <div className="text-center py-20">
              <Check className="w-20 h-20 text-jarvis-green mx-auto mb-4" />
              <p className="text-jarvis-green font-semibold">Already Connected</p>
              <p className="text-gray-500 text-sm mt-2">WhatsApp session is active</p>
            </div>
          ) : qrData?.qr_code ? (
            <div className="flex flex-col items-center">
              <div className="bg-white p-4 rounded-lg">
                <img 
                  src={`data:image/png;base64,${qrData.qr_code}`} 
                  alt="WhatsApp QR Code"
                  className="w-64 h-64"
                />
              </div>
              <p className="text-gray-400 text-sm mt-4 text-center">
                Scan this QR code with WhatsApp to connect
              </p>
              <button
                onClick={fetchQR}
                className="mt-4 px-4 py-2 bg-jarvis-blue/10 border border-jarvis-blue/30 rounded text-sm font-mono hover:bg-jarvis-blue/20 transition-colors"
              >
                REFRESH QR
              </button>
            </div>
          ) : (
            <div className="text-center py-12">
              <AlertTriangle className="w-16 h-16 text-jarvis-orange mx-auto mb-4" />
              <p className="text-jarvis-orange font-semibold">QR Not Available</p>
              <p className="text-gray-500 text-sm mt-2 mb-4">
                {qrData?.message || 'WAHA service may be unavailable'}
              </p>
              
              <div className="space-y-3">
                <button
                  onClick={() => { handleReconnect(); }}
                  disabled={reconnecting}
                  className="w-full py-3 bg-jarvis-blue/10 border border-jarvis-blue/30 rounded-lg font-mono text-sm hover:bg-jarvis-blue/20 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  <Power className="w-4 h-4 text-jarvis-blue" />
                  {reconnecting ? 'INITIATING...' : 'RECONNECT & GET QR'}
                </button>
                
                <button
                  onClick={fetchQR}
                  className="w-full py-2 bg-jarvis-blue/5 border border-jarvis-blue/20 rounded text-sm font-mono hover:bg-jarvis-blue/10 transition-colors"
                >
                  REFRESH STATUS
                </button>
                
                {qrData?.waha_url && (
                  <>
                    <a 
                      href={`${qrData.waha_url}/api/qr/image`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block w-full py-2 bg-jarvis-green/10 border border-jarvis-green/30 rounded text-sm font-mono text-jarvis-green hover:bg-jarvis-green/20 transition-colors text-center"
                    >
                      VIEW QR CODE IMAGE →
                    </a>
                    <a 
                      href={`${qrData.waha_url}/api/qr`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block w-full py-2 bg-gray-800 border border-gray-700 rounded text-sm font-mono text-gray-400 hover:text-white hover:border-gray-600 transition-colors text-center"
                    >
                      VIEW RAW QR DATA →
                    </a>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Setup Instructions */}
          <div className="mt-8 p-4 bg-jarvis-blue/5 rounded-lg">
            <h3 className="font-semibold text-sm mb-2 flex items-center gap-2">
              <Smartphone className="w-4 h-4 text-jarvis-blue" />
              Setup Instructions
            </h3>
            <ol className="text-sm text-gray-400 space-y-2 list-decimal list-inside">
              <li>Open WhatsApp on your phone</li>
              <li>Go to Settings → Linked Devices</li>
              <li>Tap "Link a Device"</li>
              <li>Scan the QR code above</li>
            </ol>
          </div>
        </div>
      </div>

      {/* WAHA Service Info */}
      <div className="panel p-6">
        <h2 className="font-orbitron text-sm font-semibold text-jarvis-blue tracking-widest mb-4">WAHA SERVICE</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 bg-jarvis-blue/5 rounded-lg">
            <div className="text-gray-400 text-sm">Service URL</div>
            <div className="font-mono text-sm mt-1 truncate">{status?.waha_url || 'Not configured'}</div>
          </div>
          <div className="p-4 bg-jarvis-blue/5 rounded-lg">
            <div className="text-gray-400 text-sm">Keep-Alive</div>
            <div className="flex items-center gap-2 mt-1">
              <StatusDot status={status?.keep_alive_active ? 'online' : 'offline'} size="sm" />
              <span className="font-mono text-sm">{status?.keep_alive_active ? 'Active' : 'Inactive'}</span>
            </div>
          </div>
          <div className="p-4 bg-jarvis-blue/5 rounded-lg">
            <div className="text-gray-400 text-sm">Messages Sent</div>
            <div className="font-orbitron text-xl mt-1">{status?.messages_sent || 0}</div>
          </div>
        </div>
      </div>
    </div>
  )
}
