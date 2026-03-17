import { motion } from 'framer-motion'

export default function ArcReactor({ toolsCount, isOnline }) {
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
export function StatusDot({ status, size = 'md' }) {
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
export function ServiceCard({ name, status, icon: Icon, onClick }) {
  return (
    <motion.div 
      className="flex items-center justify-between p-4 rounded-lg bg-jarvis-blue/5 border border-jarvis-blue/20 hover:bg-jarvis-blue/10 hover:border-jarvis-blue transition-all cursor-pointer"
      whileHover={{ x: 4 }}
      onClick={onClick}
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
export function StatCard({ value, label, icon: Icon }) {
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
export function ActionButton({ label, icon: Icon, to, onClick }) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center gap-2 p-4 rounded-lg bg-gradient-to-br from-jarvis-blue/10 to-jarvis-blue/5 border border-jarvis-blue/30 hover:from-jarvis-blue/20 hover:to-jarvis-blue/10 hover:border-jarvis-blue transition-all group"
    >
      <Icon className="w-6 h-6 text-jarvis-blue group-hover:scale-110 transition-transform" />
      <span className="text-sm font-medium">{label}</span>
    </button>
  )
}

// Console Output
export function Console({ lines }) {
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

// Tool Category Tag
export function ToolTag({ name }) {
  return (
    <span className="font-mono text-xs px-3 py-1.5 rounded bg-jarvis-blue/10 border border-jarvis-blue/20 text-jarvis-blue">
      {name}
    </span>
  )
}

// Activity Item
export function ActivityItem({ time, message, type }) {
  return (
    <div className="py-3 border-b border-jarvis-blue/10 last:border-0">
      <div className="font-mono text-xs text-jarvis-blue">{time}</div>
      <div className="text-sm text-gray-400 mt-1">{message}</div>
    </div>
  )
}
