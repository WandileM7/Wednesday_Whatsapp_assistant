import { motion } from 'framer-motion'

// ---------------------------------------------------------------------------
// StatusDot — pulsing colored indicator
// ---------------------------------------------------------------------------
export function StatusDot({ status = 'offline', size = 'md' }) {
  const sizes = { sm: 'w-1.5 h-1.5', md: 'w-2 h-2', lg: 'w-2.5 h-2.5' }
  const colors = {
    online:      'glow-dot-green',
    connected:   'glow-dot-green',
    healthy:     'glow-dot-green',
    offline:     'glow-dot-red',
    unreachable: 'glow-dot-red',
    error:       'glow-dot-red',
    warning:     'glow-dot-orange',
    loading:     'glow-dot-cyan',
  }
  const dotClass = colors[status] || 'glow-dot-red'
  const isAlive = ['online', 'connected', 'healthy', 'loading'].includes(status)

  return (
    <span className={`inline-block ${sizes[size]} ${dotClass} rounded-full ${isAlive ? 'pulse-live' : ''}`} />
  )
}

// ---------------------------------------------------------------------------
// Card — glass morphism container
// ---------------------------------------------------------------------------
export function Card({ children, className = '', hover = false, ...props }) {
  const Component = hover ? motion.div : 'div'
  const motionProps = hover
    ? { whileHover: { y: -2, transition: { duration: 0.2 } } }
    : {}

  return (
    <Component
      className={`${hover ? 'glass-hover' : 'glass'} p-5 ${className}`}
      {...motionProps}
      {...props}
    >
      {children}
    </Component>
  )
}

// ---------------------------------------------------------------------------
// SectionTitle
// ---------------------------------------------------------------------------
export function SectionTitle({ children, subtitle, action }) {
  return (
    <div className="flex items-end justify-between mb-5">
      <div>
        <h2 className="text-lg font-display font-semibold text-white tracking-tight">
          {children}
        </h2>
        {subtitle && (
          <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>
        )}
      </div>
      {action}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ServiceRow — status row for a service
// ---------------------------------------------------------------------------
export function ServiceRow({ name, status, detail, icon: Icon }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-white/[0.04] last:border-0">
      <div className="flex items-center gap-3">
        {Icon && (
          <div className="w-8 h-8 rounded-lg bg-white/[0.04] flex items-center justify-center">
            <Icon size={14} className="text-gray-400" />
          </div>
        )}
        <div>
          <p className="text-sm font-medium text-gray-200">{name}</p>
          {detail && <p className="text-xs text-gray-500 mt-0.5">{detail}</p>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className={`text-xs font-mono px-2 py-0.5 rounded-md ${
          status === 'connected' || status === 'healthy'
            ? 'text-wed-green bg-wed-green/10'
            : status === 'loading'
            ? 'text-wed-cyan bg-wed-cyan/10'
            : 'text-wed-red bg-wed-red/10'
        }`}>
          {status}
        </span>
        <StatusDot status={status} size="sm" />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// StatCard — key metric display
// ---------------------------------------------------------------------------
export function StatCard({ label, value, sub, icon: Icon, color = 'cyan' }) {
  const colorMap = {
    cyan:   'from-wed-cyan/10 to-transparent border-wed-cyan/10 text-wed-cyan',
    green:  'from-wed-green/10 to-transparent border-wed-green/10 text-wed-green',
    purple: 'from-wed-purple/10 to-transparent border-wed-purple/10 text-wed-purple',
    orange: 'from-wed-orange/10 to-transparent border-wed-orange/10 text-wed-orange',
  }

  return (
    <motion.div
      className="glass-hover p-4"
      whileHover={{ y: -2 }}
      transition={{ duration: 0.2 }}
    >
      <div className="flex items-start justify-between mb-3">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</p>
        {Icon && (
          <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${colorMap[color]} border flex items-center justify-center`}>
            <Icon size={14} />
          </div>
        )}
      </div>
      <p className="text-2xl font-display font-bold text-white tracking-tight">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// ActionButton
// ---------------------------------------------------------------------------
export function ActionButton({ children, onClick, variant = 'primary', icon: Icon, loading, disabled }) {
  const variants = {
    primary:   'bg-wed-cyan/10 text-wed-cyan border-wed-cyan/20 hover:bg-wed-cyan/20 hover:border-wed-cyan/30',
    success:   'bg-wed-green/10 text-wed-green border-wed-green/20 hover:bg-wed-green/20 hover:border-wed-green/30',
    danger:    'bg-wed-red/10 text-wed-red border-wed-red/20 hover:bg-wed-red/20 hover:border-wed-red/30',
    ghost:     'bg-transparent text-gray-400 border-white/[0.06] hover:bg-white/[0.04] hover:text-gray-200',
  }

  return (
    <motion.button
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      disabled={disabled || loading}
      className={`
        inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium
        border transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed
        ${variants[variant]}
      `}
    >
      {loading ? (
        <motion.div
          className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full"
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 0.8, ease: 'linear' }}
        />
      ) : Icon ? (
        <Icon size={14} />
      ) : null}
      {children}
    </motion.button>
  )
}

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------
export function Badge({ children, color = 'cyan' }) {
  const colors = {
    cyan:   'text-wed-cyan bg-wed-cyan/10 border-wed-cyan/20',
    green:  'text-wed-green bg-wed-green/10 border-wed-green/20',
    red:    'text-wed-red bg-wed-red/10 border-wed-red/20',
    orange: 'text-wed-orange bg-wed-orange/10 border-wed-orange/20',
    purple: 'text-wed-purple bg-wed-purple/10 border-wed-purple/20',
  }

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-mono border ${colors[color]}`}>
      {children}
    </span>
  )
}

// ---------------------------------------------------------------------------
// EmptyState
// ---------------------------------------------------------------------------
export function EmptyState({ icon: Icon, title, description }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {Icon && (
        <div className="w-12 h-12 rounded-2xl bg-white/[0.04] flex items-center justify-center mb-4">
          <Icon size={20} className="text-gray-500" />
        </div>
      )}
      <p className="text-sm font-medium text-gray-300">{title}</p>
      {description && <p className="text-xs text-gray-500 mt-1 max-w-xs">{description}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Skeleton loader
// ---------------------------------------------------------------------------
export function Skeleton({ className = '' }) {
  return <div className={`skeleton ${className}`} />
}
