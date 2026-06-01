import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { fetchServiceLevel, fetchResilienceMetrics, runShock } from '../api/client'
import EmptyState from './EmptyState'
import { Shield, Zap, Clock, TrendingDown } from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'

function ResilienceMetricCard({ icon: Icon, label, value, unit }) {
  const hasValue = value != null && value !== 0
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 hover:border-zinc-700 transition-colors duration-150">
      <p className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-2">
        {label}
      </p>
      <p className="text-xl font-semibold text-zinc-50 font-mono">
        {hasValue ? (
          <>
            {typeof value === 'number' ? value.toFixed(1) : value}
            <span className="text-sm text-zinc-500 ml-1 font-sans">{unit}</span>
          </>
        ) : (
          <span className="text-zinc-700">—</span>
        )}
      </p>
    </div>
  )
}

function ShockControls({ onRun, isRunning }) {
  const [params, setParams] = useState({
    shock_day: 30,
    shock_magnitude: 0.5,
    shock_duration: 7,
    recovery_rate: 0.1,
  })

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
      <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4">
        Disruption Scenario
      </h3>
      <div className="space-y-4">
        <div>
          <div className="flex justify-between text-xs text-zinc-500 mb-2">
            <span>Shock Day</span>
            <span className="text-zinc-400 font-mono">Day {params.shock_day}</span>
          </div>
          <input
            type="range"
            min="10"
            max="70"
            value={params.shock_day}
            onChange={(e) => setParams({ ...params, shock_day: parseInt(e.target.value) })}
          />
        </div>
        <div>
          <div className="flex justify-between text-xs text-zinc-500 mb-2">
            <span>Magnitude</span>
            <span className="text-zinc-400 font-mono">{(params.shock_magnitude * 100).toFixed(0)}%</span>
          </div>
          <input
            type="range"
            min="10"
            max="100"
            value={params.shock_magnitude * 100}
            onChange={(e) => setParams({ ...params, shock_magnitude: parseInt(e.target.value) / 100 })}
          />
        </div>
        <div>
          <div className="flex justify-between text-xs text-zinc-500 mb-2">
            <span>Duration</span>
            <span className="text-zinc-400 font-mono">{params.shock_duration} days</span>
          </div>
          <input
            type="range"
            min="1"
            max="21"
            value={params.shock_duration}
            onChange={(e) => setParams({ ...params, shock_duration: parseInt(e.target.value) })}
          />
        </div>
        <button
          onClick={() => onRun(params)}
          disabled={isRunning}
          className="w-full mt-2 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          <Zap size={14} />
          {isRunning ? 'Simulating...' : 'Simulate Disruption'}
        </button>
      </div>
    </div>
  )
}

export default function ResiliencePanel() {
  const { data: slData, isLoading: slLoading, error: slError } = useQuery({
    queryKey: ['service-level'],
    queryFn: fetchServiceLevel,
  })

  const { data: metricsData, isLoading: metricsLoading } = useQuery({
    queryKey: ['resilience-metrics'],
    queryFn: fetchResilienceMetrics,
  })

  const shockMutation = useMutation({
    mutationFn: runShock,
  })

  if (slLoading || metricsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 rounded-full border-2 border-zinc-700 border-t-blue-600 animate-spin" />
      </div>
    )
  }

  if (slError) {
    return (
      <div className="space-y-8">
        <div>
          <h2 className="text-xl font-semibold text-zinc-50 tracking-tight">Resilience</h2>
          <p className="text-sm text-zinc-500 mt-1">DES simulation — service level under disruption</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <EmptyState
            icon={Shield}
            title="Waiting for simulation results"
            description="Run DES simulation to analyze supply chain resilience under disruption scenarios."
          />
        </div>
      </div>
    )
  }

  const serviceData = shockMutation.data?.service_level || slData?.data || []
  const metrics = shockMutation.data?.metrics || metricsData?.metrics || {}
  const isMock = slData?.is_mock
  const hasServiceData = serviceData.length > 0 && !isMock

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-semibold text-zinc-50 tracking-tight">Resilience</h2>
        <p className="text-sm text-zinc-500 mt-1">
          DES simulation — service level under disruption
        </p>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <ResilienceMetricCard
          icon={Clock}
          label="Time to Survive"
          value={metrics.time_to_survive?.value}
          unit={metrics.time_to_survive?.unit || 'days'}
        />
        <ResilienceMetricCard
          icon={Clock}
          label="Time to Recover"
          value={metrics.time_to_recover?.value}
          unit={metrics.time_to_recover?.unit || 'days'}
        />
        <ResilienceMetricCard
          icon={TrendingDown}
          label="Max Service Drop"
          value={metrics.max_service_drop?.value}
          unit={metrics.max_service_drop?.unit || '%'}
        />
        <ResilienceMetricCard
          icon={Shield}
          label="Resilience Index"
          value={metrics.resilience_index?.value}
          unit=""
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Chart */}
        <div className="lg:col-span-3 bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          {!hasServiceData ? (
            <EmptyState
              icon={Shield}
              title="No simulation data yet"
              description="Run a disruption scenario to see service level over time."
            />
          ) : (
            <>
              <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4">
                Service Level Timeline
              </h3>
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={serviceData} margin={{ top: 10, right: 30, bottom: 20, left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis
                    dataKey="day"
                    stroke="#3f3f46"
                    fontSize={11}
                    tick={{ fill: '#71717a' }}
                  />
                  <YAxis
                    stroke="#3f3f46"
                    fontSize={11}
                    domain={[50, 100]}
                    tick={{ fill: '#71717a' }}
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#18181b',
                      border: '1px solid #3f3f46',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    labelStyle={{ color: '#a1a1aa' }}
                    itemStyle={{ color: '#2563eb' }}
                  />
                  <ReferenceLine
                    y={95}
                    stroke="#16a34a"
                    strokeDasharray="5 5"
                    strokeWidth={1}
                  />
                  <Line
                    type="monotone"
                    dataKey="service_level"
                    stroke="#2563eb"
                    strokeWidth={1.5}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </>
          )}
        </div>

        {/* Controls */}
        <ShockControls
          onRun={(params) => shockMutation.mutate(params)}
          isRunning={shockMutation.isPending}
        />
      </div>
    </div>
  )
}
