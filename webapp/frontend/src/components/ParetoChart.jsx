import { useQuery } from '@tanstack/react-query'
import { fetchParetoFront, fetchHypervolume } from '../api/client'
import EmptyState from './EmptyState'
import { TrendingUp } from 'lucide-react'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from 'recharts'

function ParetoTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload

  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 text-xs">
      <div className="space-y-1">
        <p className="text-zinc-400">
          Cost: <span className="text-zinc-200 font-mono">₹{(point.cost / 1_000_000).toFixed(2)}M</span>
        </p>
        <p className="text-zinc-400">
          Carbon: <span className="text-zinc-200 font-mono">{point.carbon.toFixed(0)} tCO₂e</span>
        </p>
        {point.service_level != null && (
          <p className="text-zinc-400">
            Service: <span className="text-zinc-200 font-mono">{point.service_level.toFixed(1)}%</span>
          </p>
        )}
      </div>
    </div>
  )
}

export default function ParetoChart() {
  const { data: paretoData, isLoading: paretoLoading } = useQuery({
    queryKey: ['pareto-front'],
    queryFn: fetchParetoFront,
  })

  const { data: hvData } = useQuery({
    queryKey: ['hypervolume'],
    queryFn: fetchHypervolume,
  })

  if (paretoLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 rounded-full border-2 border-zinc-700 border-t-blue-600 animate-spin" />
      </div>
    )
  }

  const points = paretoData?.points || []
  const hasData = points.length > 0 && !paretoData?.is_mock

  return (
    <div className="space-y-8 scroll-animate">
      <div>
        <h2 className="text-xs font-bold uppercase tracking-widest text-premium-accent mb-1">Phase 4 & 5: Single-Agent RL & Multi-Echelon Optimization</h2>
        <h2 className="text-xl font-semibold text-zinc-50 tracking-tight">Optimization</h2>
        <p className="text-sm text-zinc-500 mt-1">
          NSGA-II Pareto front — cost vs carbon tradeoff
        </p>
      </div>

      {/* Pareto Front */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        {!hasData ? (
          <EmptyState
            icon={TrendingUp}
            title="Run optimization to see Pareto front"
            description="Once NSGA-II completes, the cost-carbon tradeoff frontier will appear here."
          />
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                Pareto Front
              </h3>
              <span className="text-xs text-zinc-600 font-mono">{points.length} solutions</span>
            </div>
            <ResponsiveContainer width="100%" height={400}>
              <ScatterChart margin={{ top: 10, right: 30, bottom: 40, left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis
                  dataKey="cost"
                  name="Cost"
                  type="number"
                  tickFormatter={(v) => `₹${(v / 1_000_000).toFixed(1)}M`}
                  stroke="#3f3f46"
                  fontSize={11}
                  tick={{ fill: '#71717a' }}
                  label={{ value: 'Total Cost (INR)', position: 'bottom', offset: 20, fill: '#71717a', fontSize: 11 }}
                />
                <YAxis
                  dataKey="carbon"
                  name="Carbon"
                  type="number"
                  stroke="#3f3f46"
                  fontSize={11}
                  tick={{ fill: '#71717a' }}
                  label={{ value: 'Carbon (tCO₂e)', angle: -90, position: 'insideLeft', offset: -5, fill: '#71717a', fontSize: 11 }}
                />
                <Tooltip content={<ParetoTooltip />} />
                <Scatter
                  data={points}
                  fill="#2563eb"
                  fillOpacity={0.6}
                  stroke="#2563eb"
                  strokeWidth={1}
                  strokeOpacity={0.8}
                />
              </ScatterChart>
            </ResponsiveContainer>
          </>
        )}
      </div>

      {/* Hypervolume Convergence */}
      {hvData?.history?.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Hypervolume Convergence
            </h3>
            <span className="text-xs text-zinc-600">Higher is better</span>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart
              data={hvData.history}
              margin={{ top: 5, right: 30, bottom: 5, left: 20 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis
                dataKey="generation"
                stroke="#3f3f46"
                fontSize={11}
                tick={{ fill: '#71717a' }}
              />
              <YAxis
                stroke="#3f3f46"
                fontSize={11}
                tick={{ fill: '#71717a' }}
                domain={[0, 1]}
              />
              <Area
                type="monotone"
                dataKey="hypervolume"
                stroke="#2563eb"
                strokeWidth={1.5}
                fill="#2563eb"
                fillOpacity={0.05}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
