import { TrendingUp, TrendingDown } from 'lucide-react'

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
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 hover:border-zinc-700 transition-colors duration-150">
      <p className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-2">
        {title}
      </p>

      <p className="text-2xl font-semibold tracking-tight font-mono text-zinc-50">
        {hasValue ? value : <span className="text-zinc-700">—</span>}
      </p>

      <div className="mt-2 h-4">
        {hasValue && change != null ? (
          <span
            className={`inline-flex items-center gap-1 text-xs font-medium ${
              isPositive ? 'text-green-600' : 'text-red-600'
            }`}
          >
            {isPositive ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
            {change}%
          </span>
        ) : !hasValue ? (
          <span className="text-xs text-zinc-600">Awaiting training</span>
        ) : null}
      </div>
    </div>
  )
}
