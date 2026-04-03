import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  BookOpen,
  Check,
  ClipboardCopy,
  Code2,
  ExternalLink,
  Globe,
  Key,
  Server,
  Settings as SettingsIcon,
  Terminal,
  Workflow,
} from 'lucide-react'
import {
  Card,
  SectionTitle,
  ActionButton,
  Badge,
} from '../components/UIComponents'

// ---------------------------------------------------------------------------
// Copyable code block
// ---------------------------------------------------------------------------
function CodeBlock({ children, label }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(children)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="relative group">
      {label && (
        <p className="text-[10px] font-mono text-gray-600 uppercase tracking-wider mb-1.5">{label}</p>
      )}
      <div className="bg-surface-1 border border-white/[0.06] rounded-xl px-4 py-3 font-mono text-sm text-gray-300 overflow-x-auto">
        <pre className="whitespace-pre-wrap break-all">{children}</pre>
      </div>
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1.5 rounded-lg bg-white/[0.04] border border-white/[0.06] opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white/[0.08]"
      >
        {copied ? (
          <Check size={12} className="text-wed-green" />
        ) : (
          <ClipboardCopy size={12} className="text-gray-500" />
        )}
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Environment variable row
// ---------------------------------------------------------------------------
function EnvRow({ name, value, description }) {
  return (
    <div className="py-3 border-b border-white/[0.04] last:border-0">
      <div className="flex items-center gap-2 mb-1">
        <span className="font-mono text-xs text-wed-cyan">{name}</span>
        <span className="text-xs text-gray-600">=</span>
        <span className="font-mono text-xs text-gray-400">{value}</span>
      </div>
      {description && (
        <p className="text-xs text-gray-600">{description}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Settings page
// ---------------------------------------------------------------------------
export default function Settings() {
  const [n8nStatus, setN8nStatus] = useState(null)

  useEffect(() => {
    fetch('/n8n-status')
      .then(r => r.json())
      .then(setN8nStatus)
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <motion.h1
          className="text-3xl font-display font-bold text-gradient"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
        >
          Settings
        </motion.h1>
        <motion.p
          className="text-sm text-gray-500 mt-1"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
        >
          Configuration & setup guide
        </motion.p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* n8n Config */}
        <Card>
          <SectionTitle subtitle="Current n8n connection settings">
            n8n Configuration
          </SectionTitle>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 rounded-xl bg-surface-1 border border-white/[0.06]">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-wed-cyan/[0.06] border border-wed-cyan/10 flex items-center justify-center">
                  <Globe size={14} className="text-wed-cyan" />
                </div>
                <div>
                  <p className="text-xs text-gray-500">Webhook URL</p>
                  <p className="text-sm font-mono text-gray-300">
                    {n8nStatus?.webhook || 'Loading…'}
                  </p>
                </div>
              </div>
              <Badge color={n8nStatus?.healthy ? 'green' : 'red'}>
                {n8nStatus?.healthy ? 'Healthy' : 'Down'}
              </Badge>
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl bg-surface-1 border border-white/[0.06]">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-wed-purple/[0.06] border border-wed-purple/10 flex items-center justify-center">
                  <Server size={14} className="text-wed-purple" />
                </div>
                <div>
                  <p className="text-xs text-gray-500">Base URL</p>
                  <p className="text-sm font-mono text-gray-300">
                    {n8nStatus?.url || 'Loading…'}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {n8nStatus?.healthy && (
            <a
              href={`${n8nStatus.url}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 mt-4 text-xs text-wed-cyan hover:text-wed-cyan/80 transition-colors"
            >
              Open n8n Dashboard <ExternalLink size={11} />
            </a>
          )}
        </Card>

        {/* Environment variables */}
        <Card>
          <SectionTitle subtitle="Required .env variables">
            Environment
          </SectionTitle>
          <div>
            <EnvRow
              name="N8N_WEBHOOK_URL"
              value="http://n8n:5678"
              description="Base URL of the n8n instance"
            />
            <EnvRow
              name="N8N_WEBHOOK_PATH"
              value="/webhook/whatsapp-webhook"
              description="Path that the n8n workflow listens on"
            />
            <EnvRow
              name="N8N_TIMEOUT"
              value="120"
              description="Max seconds to wait for n8n response"
            />
            <EnvRow
              name="WAHA_URL"
              value="http://whatsapp-service:3000"
              description="WAHA / Baileys WhatsApp gateway"
            />
            <EnvRow
              name="FLASK_DEBUG"
              value="false"
              description="Enable Flask debug mode"
            />
          </div>
        </Card>

        {/* Quick start */}
        <Card className="lg:col-span-2">
          <SectionTitle subtitle="Get everything running in seconds">
            Quick Start
          </SectionTitle>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Step 1 */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0 }}
              className="space-y-3"
            >
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-full bg-wed-cyan/10 border border-wed-cyan/20 text-wed-cyan text-xs font-mono flex items-center justify-center">
                  1
                </div>
                <p className="text-sm font-medium text-gray-200">Start the stack</p>
              </div>
              <CodeBlock label="Terminal">docker compose up -d</CodeBlock>
              <p className="text-xs text-gray-500">
                Starts n8n, WAHA, and the relay service
              </p>
            </motion.div>

            {/* Step 2 */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="space-y-3"
            >
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-full bg-wed-cyan/10 border border-wed-cyan/20 text-wed-cyan text-xs font-mono flex items-center justify-center">
                  2
                </div>
                <p className="text-sm font-medium text-gray-200">Import workflow</p>
              </div>
              <CodeBlock label="n8n Dashboard">http://localhost:5678</CodeBlock>
              <p className="text-xs text-gray-500">
                Import <span className="font-mono text-gray-400">n8n/workflow-jarvis-whatsapp.json</span>
              </p>
            </motion.div>

            {/* Step 3 */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="space-y-3"
            >
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-full bg-wed-cyan/10 border border-wed-cyan/20 text-wed-cyan text-xs font-mono flex items-center justify-center">
                  3
                </div>
                <p className="text-sm font-medium text-gray-200">Connect WhatsApp</p>
              </div>
              <CodeBlock label="Scan QR">Go to /whatsapp tab</CodeBlock>
              <p className="text-xs text-gray-500">
                Scan the QR code with your phone
              </p>
            </motion.div>
          </div>
        </Card>

        {/* Testing */}
        <Card className="lg:col-span-2">
          <SectionTitle subtitle="Verify your setup is working">
            Test Commands
          </SectionTitle>
          <div className="space-y-3">
            <CodeBlock label="Health check">
              {`curl http://localhost:5000/health`}
            </CodeBlock>
            <CodeBlock label="n8n status">
              {`curl http://localhost:5000/n8n-status`}
            </CodeBlock>
            <CodeBlock label="WhatsApp status">
              {`curl http://localhost:5000/whatsapp-status`}
            </CodeBlock>
            <CodeBlock label="Webhook test">
              {`curl -X POST http://localhost:5000/webhook \\
  -H "Content-Type: application/json" \\
  -d '{"payload":{"chatId":"test","body":"hello","id":"1"}}'`}
            </CodeBlock>
          </div>
        </Card>
      </div>
    </div>
  )
}
