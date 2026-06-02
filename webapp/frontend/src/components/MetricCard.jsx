import { TrendingUp, TrendingDown } from 'lucide-react'
import { motion } from 'framer-motion'

export default function MetricCard({
  title,
  value,
  change,
  changeType = 'up',
  icon: Icon,
}) {
  const hasValue = value != null
  const isPositive = changeType === 'up'

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -5, boxShadow: '0 10px 30px -10px rgba(0, 240, 255, 0.2)' }}
      className="bg-cyber-panel backdrop-blur-md border border-cyber-border rounded-xl p-6 relative overflow-hidden group"
    >
      {/* Decorative Glow */}
      <div className="absolute -top-10 -right-10 w-24 h-24 bg-cyber-cyan/10 rounded-full blur-2xl group-hover:bg-cyber-cyan/20 transition-all duration-500"></div>

      <div className="flex justify-between items-start mb-4 relative z-10">
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
          {title}
        </p>
        {Icon && <Icon size={18} className="text-cyber-cyan opacity-70" />}
      </div>

      <p className="text-3xl font-bold tracking-tight font-mono text-zinc-50 relative z-10 drop-shadow-[0_0_10px_rgba(255,255,255,0.2)]">
        {hasValue ? value : <span className="text-zinc-700">—</span>}
      </p>

      <div className="mt-4 h-4 relative z-10">
        {hasValue && change != null ? (
          <span
            className={`inline-flex items-center gap-1.5 text-xs font-bold tracking-wide ${
              isPositive ? 'text-cyber-cyan drop-shadow-[0_0_5px_rgba(0,240,255,0.5)]' : 'text-rose-400 drop-shadow-[0_0_5px_rgba(251,113,133,0.5)]'
            }`}
          >
            {isPositive ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
            {change}%
          </span>
        ) : !hasValue ? (
          <span className="text-xs tracking-wider text-zinc-600 uppercase font-medium">Awaiting metrics</span>
        ) : null}
      </div>
    </motion.div>
  )
}
