import { useQuery } from '@tanstack/react-query'
import { fetchParetoFront } from '../api/client'
import EmptyState from './EmptyState'
import { Leaf } from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from 'recharts'

function GreenPremiumTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload

  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 text-xs">
      <div className="space-y-1">
        <p className="text-zinc-400">
          Carbon reduction: <span className="text-zinc-200 font-mono">{point.reduction.toFixed(1)}%</span>
        </p>
        <p className="text-zinc-400">
          Cost premium: <span className="text-zinc-200 font-mono">₹{(point.premium / 1000).toFixed(0)}K</span>
        </p>
        <p className="text-zinc-400">
          Cost per tCO₂e: <span className="text-zinc-200 font-mono">₹{point.costPerTon.toFixed(0)}/t</span>
        </p>
      </div>
    </div>
  )
}

function deriveGreenPremiumCurve(points) {
  if (!points || points.length < 2) return []

  // Sort by carbon (ascending) to trace the tradeoff
  const sorted = [...points].sort((a, b) => a.carbon - b.carbon)

  // The min-carbon solution is the "greenest" — max-carbon is cheapest
  const maxCarbon = sorted[sorted.length - 1].carbon
  const minCost = Math.min(...sorted.map((p) => p.cost))

  // Build the green premium curve: for each solution, how much extra cost
  // do you pay for how much carbon reduction vs the dirtiest solution?
  const curve = sorted.map((p) => {
    const reduction = ((maxCarbon - p.carbon) / maxCarbon) * 100
    const premium = p.cost - minCost
    const carbonSaved = maxCarbon - p.carbon
    const costPerTon = carbonSaved > 0 ? premium / carbonSaved : 0

    return {
      reduction: Math.round(reduction * 10) / 10,
      premium,
      costPerTon: Math.round(costPerTon * 100) / 100,
      cost: p.cost,
      carbon: p.carbon,
    }
  })

  return curve.sort((a, b) => a.reduction - b.reduction)
}

export default function CarbonBudget() {
  const { data: paretoData, isLoading } = useQuery({
    queryKey: ['pareto-front'],
    queryFn: fetchParetoFront,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 rounded-full border-2 border-zinc-700 border-t-blue-600 animate-spin" />
      </div>
    )
  }

  const points = paretoData?.points || []
  const hasData = points.length > 0 && !paretoData?.is_mock
  const curve = hasData ? deriveGreenPremiumCurve(points) : []

  // Summary stats
  const minCarbon = hasData ? Math.min(...points.map((p) => p.carbon)) : 0
  const maxCarbon = hasData ? Math.max(...points.map((p) => p.carbon)) : 0
  const minCost = hasData ? Math.min(...points.map((p) => p.cost)) : 0
  const maxCost = hasData ? Math.max(...points.map((p) => p.cost)) : 0
  const maxReduction = maxCarbon > 0 ? ((maxCarbon - minCarbon) / maxCarbon) * 100 : 0

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-semibold text-zinc-50 tracking-tight">Carbon Budget</h2>
        <p className="text-sm text-zinc-500 mt-1">
          Green premium curve — cost of decarbonization from Pareto front
        </p>
      </div>

      {/* Summary Cards */}
      {hasData && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <p className="text-xs text-zinc-500 uppercase tracking-wider">Max Reduction</p>
            <p className="text-2xl font-semibold text-zinc-100 font-mono mt-1">
              {maxReduction.toFixed(1)}%
            </p>
            <p className="text-xs text-zinc-600 mt-1">carbon vs baseline</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <p className="text-xs text-zinc-500 uppercase tracking-wider">Min Emissions</p>
            <p className="text-2xl font-semibold text-zinc-100 font-mono mt-1">
              {(minCarbon / 1000).toFixed(1)}K
            </p>
            <p className="text-xs text-zinc-600 mt-1">tCO₂e (greenest solution)</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <p className="text-xs text-zinc-500 uppercase tracking-wider">Cost Range</p>
            <p className="text-2xl font-semibold text-zinc-100 font-mono mt-1">
              ₹{((maxCost - minCost) / 1_000_000).toFixed(2)}M
            </p>
            <p className="text-xs text-zinc-600 mt-1">spread across Pareto front</p>
          </div>
        </div>
      )}

      {/* Green Premium Curve */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        {!hasData ? (
          <EmptyState
            icon={Leaf}
            title="Awaiting optimization results"
            description="Run NSGA-II optimization first. The green premium curve will be derived from the Pareto front."
          />
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                Green Premium Curve
              </h3>
              <span className="text-xs text-zinc-600">
                Cost premium vs carbon reduction
              </span>
            </div>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={curve} margin={{ top: 10, right: 30, bottom: 40, left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis
                  dataKey="reduction"
                  stroke="#3f3f46"
                  fontSize={11}
                  tick={{ fill: '#71717a' }}
                  label={{ value: 'Carbon Reduction (%)', position: 'bottom', offset: 20, fill: '#71717a', fontSize: 11 }}
                />
                <YAxis
                  dataKey="premium"
                  stroke="#3f3f46"
                  fontSize={11}
                  tick={{ fill: '#71717a' }}
                  tickFormatter={(v) => `₹${(v / 1_000_000).toFixed(1)}M`}
                  label={{ value: 'Cost Premium (INR)', angle: -90, position: 'insideLeft', offset: -5, fill: '#71717a', fontSize: 11 }}
                />
                <Tooltip content={<GreenPremiumTooltip />} />
                <Line
                  type="monotone"
                  dataKey="premium"
                  stroke="#16a34a"
                  strokeWidth={2}
                  dot={{ fill: '#16a34a', r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </div>

      {/* Cost per tCO₂e Bar Chart */}
      {hasData && curve.length > 1 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Marginal Abatement Cost
            </h3>
            <span className="text-xs text-zinc-600">₹ per tCO₂e reduced</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={curve.filter((c) => c.costPerTon > 0)} margin={{ top: 10, right: 30, bottom: 30, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis
                dataKey="reduction"
                stroke="#3f3f46"
                fontSize={11}
                tick={{ fill: '#71717a' }}
                label={{ value: 'Reduction (%)', position: 'bottom', offset: 15, fill: '#71717a', fontSize: 11 }}
              />
              <YAxis
                stroke="#3f3f46"
                fontSize={11}
                tick={{ fill: '#71717a' }}
                tickFormatter={(v) => `₹${v.toFixed(0)}`}
              />
              <Tooltip
                contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: '8px', fontSize: '11px' }}
                labelStyle={{ color: '#71717a' }}
                formatter={(value) => [`₹${value.toFixed(0)}/tCO₂e`, 'Abatement Cost']}
                labelFormatter={(label) => `${label}% reduction`}
              />
              <Bar dataKey="costPerTon" radius={[4, 4, 0, 0]}>
                {curve.filter((c) => c.costPerTon > 0).map((_, i) => (
                  <Cell key={i} fill={i % 2 === 0 ? '#16a34a' : '#15803d'} fillOpacity={0.7} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Pareto Solutions Table */}
      {hasData && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4">
            Pareto Solutions
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left py-2 px-3 text-xs text-zinc-500 font-medium">#</th>
                  <th className="text-right py-2 px-3 text-xs text-zinc-500 font-medium">Cost (INR)</th>
                  <th className="text-right py-2 px-3 text-xs text-zinc-500 font-medium">Carbon (tCO₂e)</th>
                  <th className="text-right py-2 px-3 text-xs text-zinc-500 font-medium">Reduction</th>
                </tr>
              </thead>
              <tbody>
                {[...points].sort((a, b) => a.carbon - b.carbon).map((p, i) => (
                  <tr key={p.id} className="border-b border-zinc-800/50">
                    <td className="py-2 px-3 text-zinc-400 font-mono text-xs">{i + 1}</td>
                    <td className="py-2 px-3 text-right text-zinc-300 font-mono text-xs">
                      ₹{(p.cost / 1_000_000).toFixed(2)}M
                    </td>
                    <td className="py-2 px-3 text-right text-zinc-300 font-mono text-xs">
                      {p.carbon.toFixed(0)}
                    </td>
                    <td className="py-2 px-3 text-right text-green-500 font-mono text-xs">
                      {maxCarbon > 0 ? ((maxCarbon - p.carbon) / maxCarbon * 100).toFixed(1) : 0}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
