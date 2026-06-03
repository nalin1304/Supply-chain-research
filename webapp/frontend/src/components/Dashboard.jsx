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

import { motion } from 'framer-motion'

function TrainingStatus({ status }) {
  const items = [
    { key: 'nsga2_complete', label: 'NSGA-II Optimization', icon: TrendingUp },
    { key: 'lstm_complete', label: 'LSTM Forecasting', icon: Brain },
    { key: 'ppo_complete', label: 'PPO Reinforcement Learning', icon: Zap },
    { key: 'des_complete', label: 'DES Simulation', icon: Activity },
  ]

  return (
    <motion.div 
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="bg-cyber-panel backdrop-blur-xl border border-cyber-border rounded-xl p-6 relative overflow-hidden"
    >
      <div className="absolute -bottom-20 -right-20 w-40 h-40 bg-cyber-purple/10 rounded-full blur-3xl"></div>
      
      <h3 className="text-xs font-bold uppercase tracking-widest text-cyber-purple mb-6 drop-shadow-[0_0_8px_rgba(176,38,255,0.4)]">
        Training Status
      </h3>
      <div className="space-y-4 relative z-10">
        {items.map((item, idx) => {
          const isComplete = status?.[item.key]
          const Icon = item.icon
          return (
            <motion.div 
              key={item.key} 
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.1 }}
              className="flex items-center justify-between p-3 rounded-lg bg-black/20 border border-cyber-border/50"
            >
              <div className="flex items-center gap-3">
                <Icon size={16} className={isComplete ? "text-cyber-cyan drop-shadow-[0_0_5px_rgba(0,240,255,0.8)]" : "text-zinc-600"} />
                <span className={`text-sm font-medium ${isComplete ? 'text-zinc-200' : 'text-zinc-500'}`}>{item.label}</span>
              </div>
              {isComplete ? (
                <span className="inline-flex items-center gap-1.5 text-xs font-bold text-cyber-cyan drop-shadow-[0_0_5px_rgba(0,240,255,0.4)]">
                  <CheckCircle2 size={14} />
                  Complete
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-600">
                  <Clock size={14} />
                  Pending
                </span>
              )}
            </motion.div>
          )
        })}
      </div>
    </motion.div>
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
      <div className="space-y-8 scroll-animate">
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
    <div className="space-y-8 scroll-animate">
      {/* Welcome Banner */}
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-premium-panel border border-premium-border rounded-xl p-6 relative overflow-hidden"
      >
        <div className="absolute top-0 right-0 w-64 h-64 bg-premium-accent/5 rounded-full blur-3xl transform translate-x-1/2 -translate-y-1/2 pointer-events-none"></div>
        <div className="flex items-start gap-4">
          <div className="p-3 bg-premium-accent/10 rounded-lg text-premium-accent shrink-0">
            <LayoutDashboard size={24} />
          </div>
          <div>
            <h2 className="text-xs font-bold uppercase tracking-widest text-premium-accent mb-1">Phase 1: Baseline Heuristics & Overview</h2>
            <h1 className="text-2xl font-medium text-premium-text tracking-wide mb-2">
              Multi-Objective Resilient Supply Chain Dashboard
            </h1>
            <p className="text-premium-textMuted leading-relaxed text-sm max-w-4xl">
              This project tackles the massive challenge of balancing <strong>logistics cost</strong> against <strong>carbon emissions (CO₂)</strong> across Indian logistics networks. Using cutting-edge Artificial Intelligence (Reinforcement Learning), we train virtual 'agents' to make inventory and routing decisions that are both green and highly resilient to real-world supply chain shocks.
            </p>
          </div>
        </div>
      </motion.div>

      {/* Primary KPIs (Moved up for F-Pattern / North Star visibility) */}
      {hasKpis && !isMock ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 scroll-animate">
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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 scroll-animate">
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

      {/* Action-Oriented UI: Next Best Action */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="bg-premium-background border border-premium-accent/30 rounded-xl p-5 scroll-animate relative overflow-hidden"
      >
        <div className="absolute top-0 right-0 w-32 h-32 bg-premium-accent/10 rounded-full blur-2xl transform translate-x-1/2 -translate-y-1/2 pointer-events-none"></div>
        <div className="flex items-center gap-3 mb-4">
          <Zap className="text-premium-accent" size={20} />
          <h3 className="text-sm font-semibold text-zinc-100 uppercase tracking-wide">Next Best Action</h3>
        </div>
        <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
          <div>
            <p className="text-sm text-zinc-300 font-medium">Elevated Tail-Risk Detected (CVaR)</p>
            <p className="text-xs text-zinc-500 mt-1">High variance in supply shock recovery during Phase 10 evaluation. Recommend re-running robust optimization.</p>
          </div>
          <button className="px-4 py-2 bg-premium-accent text-white text-xs font-semibold rounded-lg hover:bg-premium-accent/90 transition-colors border border-transparent">
            Run Phase 10 CVaR Op
          </button>
        </div>
      </motion.div>

      {/* Progressive Disclosure: Academic Methodology & Datasets */}
      <details className="group border border-premium-border bg-premium-panel rounded-xl scroll-animate">
        <summary className="px-5 py-4 cursor-pointer list-none flex items-center justify-between text-sm font-medium text-zinc-300 hover:text-zinc-100 transition-colors">
          <div className="flex items-center gap-2">
            <span className="text-premium-accent">▸</span> Deep Academic Specs & Experimental Setup
          </div>
          <span className="text-xs text-zinc-500 font-normal">Click to expand</span>
        </summary>
        <div className="px-5 pb-5 pt-2 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 border-t border-premium-border/50">
          <div>
            <h4 className="text-[11px] font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Primary Datasets</h4>
            <ul className="text-xs text-zinc-500 space-y-1.5 font-mono">
              <li>• Delhivery (144,867 records)</li>
              <li>• DataCo Smart SC (180K orders)</li>
              <li>• CVRPLIB Augerat Set-A</li>
              <li>• SVRPBench (Stochastic VRP)</li>
            </ul>
          </div>
          <div>
            <h4 className="text-[11px] font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Network Scope</h4>
            <ul className="text-xs text-zinc-500 space-y-1.5 font-mono">
              <li>• 5 Distribution Warehouses</li>
              <li>• 101 Customer Demand Points</li>
              <li>• 20 Indian Cities</li>
              <li>• OSRM v5 Real Road Distances</li>
            </ul>
          </div>
          <div>
            <h4 className="text-[11px] font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Experimental Setup</h4>
            <ul className="text-xs text-zinc-500 space-y-1.5 font-mono">
              <li>• 1,000,000 RL Timesteps</li>
              <li>• 50-Seed Monte Carlo Evals</li>
              <li>• $H_\infty$ Minimax Adversarial</li>
              <li>• Cloud Env: Modal (Tesla T4)</li>
            </ul>
          </div>
          <div>
            <h4 className="text-[11px] font-semibold text-zinc-400 mb-2 uppercase tracking-wider">Statistical Validation</h4>
            <ul className="text-xs text-zinc-500 space-y-1.5 font-mono">
              <li>• Friedman Omnibus Test</li>
              <li>• Paired Wilcoxon post-hoc</li>
              <li>• Holm-Bonferroni correction</li>
              <li>• Sobol Global Sensitivity</li>
            </ul>
          </div>
        </div>
      </details>

      {/* Training Status */}
      <div className="scroll-animate">
        <TrainingStatus status={data?.training_status} />
      </div>
    </div>
  )
}
