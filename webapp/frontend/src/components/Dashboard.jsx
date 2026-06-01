import { useQuery } from '@tanstack/react-query'
import { fetchSummary } from '../api/client'
import MetricCard from './MetricCard'
import EmptyState from './EmptyState'
import {
  DollarSign,
  Cloud,
  Target,
  Truck,
  AlertCircle,
  CheckCircle2,
  Clock,
  TrendingUp,
  Brain,
  Zap,
  Activity,
  LayoutDashboard,
} from 'lucide-react'

const kpiConfig = {
  total_cost: { icon: DollarSign, label: 'Total Cost' },
  total_emissions: { icon: Cloud, label: 'Emissions' },
  service_level: { icon: Target, label: 'Service Level' },
  fleet_utilization: { icon: Truck, label: 'Fleet Utilization' },
}

function formatValue(value, unit) {
  if (value == null) return null
  if (unit === 'INR') return `₹${(value / 1_000_000).toFixed(2)}M`
  if (unit === 'tCO2e') return `${value.toFixed(0)} tCO₂e`
  if (unit === 'kgCO2e') return `${(value / 1000).toFixed(1)} tCO₂e`
  if (unit === '%') return `${value.toFixed(1)}%`
  return value.toString()
}

function TrainingStatus({ status }) {
  const items = [
    { key: 'nsga2_complete', label: 'NSGA-II Optimization', icon: TrendingUp },
    { key: 'lstm_complete', label: 'LSTM Forecasting', icon: Brain },
    { key: 'ppo_complete', label: 'PPO Reinforcement Learning', icon: Zap },
    { key: 'des_complete', label: 'DES Simulation', icon: Activity },
  ]

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
      <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4">
        Training Status
      </h3>
      <div className="space-y-3">
        {items.map((item) => {
          const isComplete = status?.[item.key]
          const Icon = item.icon
          return (
            <div key={item.key} className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Icon size={14} className="text-zinc-500" />
                <span className="text-sm text-zinc-400">{item.label}</span>
              </div>
              {isComplete ? (
                <span className="inline-flex items-center gap-1 text-xs text-green-600">
                  <CheckCircle2 size={12} />
                  Complete
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-xs text-zinc-600">
                  <Clock size={12} />
                  Pending
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['summary'],
    queryFn: fetchSummary,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 rounded-full border-2 border-zinc-700 border-t-blue-600 animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-8">
        <div>
          <h2 className="text-xl font-semibold text-zinc-50 tracking-tight">Overview</h2>
          <p className="text-sm text-zinc-500 mt-1">Supply chain optimization metrics</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <EmptyState
            icon={LayoutDashboard}
            title="No training results yet"
            description="Training is running on Modal — results will appear here automatically once complete."
          />
        </div>
      </div>
    )
  }

  const hasKpis = data?.kpis && Object.keys(data.kpis).length > 0
  const isMock = data?.is_mock_data

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-zinc-50 tracking-tight">Overview</h2>
        <p className="text-sm text-zinc-500 mt-1">Supply chain optimization metrics</p>
      </div>

      {/* KPI Cards */}
      {hasKpis && !isMock ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Object.entries(data.kpis).map(([key, kpi]) => {
            const config = kpiConfig[key] || { icon: Target, label: key }
            const isPositive = key === 'service_level' || key === 'fleet_utilization'
              ? kpi.change > 0
              : kpi.change < 0

            return (
              <MetricCard
                key={key}
                title={kpi.label || config.label}
                value={formatValue(kpi.value, kpi.unit)}
                change={kpi.change != null ? Math.abs(kpi.change) : null}
                changeType={isPositive ? 'up' : 'down'}
                icon={config.icon}
              />
            )
          })}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Object.entries(kpiConfig).map(([key, config]) => (
            <MetricCard
              key={key}
              title={config.label}
              value={null}
              icon={config.icon}
            />
          ))}
        </div>
      )}

      {/* Training Status */}
      <TrainingStatus status={data?.training_status} />
    </div>
  )
}
