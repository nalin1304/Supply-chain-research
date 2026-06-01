import { useQuery } from '@tanstack/react-query'
import { fetchForecast } from '../api/client'
import EmptyState from './EmptyState'
import { Brain } from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

function ForecastTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null

  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 text-xs">
      <p className="text-zinc-500 mb-1.5">Day {label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="text-zinc-300">
          <span style={{ color: entry.color }}>{entry.name}:</span>{' '}
          <span className="font-mono">{entry.value?.toFixed(1)}</span>
        </p>
      ))}
    </div>
  )
}

export default function TrainingProgress() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['forecast'],
    queryFn: fetchForecast,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 rounded-full border-2 border-zinc-700 border-t-blue-600 animate-spin" />
      </div>
    )
  }

  const hasData = data?.historical?.length > 0 && !data?.is_mock

  // Merge historical and forecast into one array for the chart
  const chartData = hasData
    ? data.historical.map((h, i) => ({
        day: h.day,
        actual: h.demand,
        forecast: data.forecast[i]?.demand ?? null,
      }))
    : []

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-semibold text-zinc-50 tracking-tight">Forecasting</h2>
        <p className="text-sm text-zinc-500 mt-1">
          LSTM demand predictions vs actuals
        </p>
      </div>

      {/* Forecast Chart */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        {!hasData ? (
          <EmptyState
            icon={Brain}
            title="Awaiting training results"
            description="Train the LSTM forecasting model to see demand predictions here."
          />
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                Demand Forecast — Customer 1
              </h3>
              <span className="text-xs text-zinc-600 font-mono">
                {data.data_info?.displayed_days} days
              </span>
            </div>
            <ResponsiveContainer width="100%" height={360}>
              <LineChart data={chartData} margin={{ top: 10, right: 30, bottom: 30, left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis
                  dataKey="day"
                  stroke="#3f3f46"
                  fontSize={11}
                  tick={{ fill: '#71717a' }}
                  label={{ value: 'Day', position: 'bottom', offset: 15, fill: '#71717a', fontSize: 11 }}
                />
                <YAxis
                  stroke="#3f3f46"
                  fontSize={11}
                  tick={{ fill: '#71717a' }}
                  label={{ value: 'Demand (units)', angle: -90, position: 'insideLeft', offset: -5, fill: '#71717a', fontSize: 11 }}
                />
                <Tooltip content={<ForecastTooltip />} />
                <Legend
                  verticalAlign="top"
                  height={36}
                  wrapperStyle={{ fontSize: '11px', color: '#a1a1aa' }}
                />
                <Line
                  type="monotone"
                  dataKey="actual"
                  name="Actual"
                  stroke="#71717a"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="forecast"
                  name="LSTM Forecast"
                  stroke="#2563eb"
                  strokeWidth={1.5}
                  dot={false}
                  strokeDasharray="4 2"
                />
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </div>

      {/* Error Metrics */}
      {hasData && data.metrics && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4">
            Model Performance
          </h3>
          <div className="grid grid-cols-3 gap-6">
            <div>
              <p className="text-2xl font-semibold text-zinc-100 font-mono">
                {data.metrics.mape}%
              </p>
              <p className="text-xs text-zinc-500 mt-1">MAPE</p>
            </div>
            <div>
              <p className="text-2xl font-semibold text-zinc-100 font-mono">
                {data.metrics.rmse.toFixed(1)}
              </p>
              <p className="text-xs text-zinc-500 mt-1">RMSE</p>
            </div>
            <div>
              <p className="text-2xl font-semibold text-zinc-100 font-mono">
                {data.metrics.mae.toFixed(1)}
              </p>
              <p className="text-xs text-zinc-500 mt-1">MAE</p>
            </div>
          </div>
        </div>
      )}

      {/* Data Info */}
      {hasData && data.data_info && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4">
            Dataset Info
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-zinc-500">Predictions shape</p>
              <p className="text-zinc-300 font-mono text-xs">
                {data.data_info.total_predictions_shape?.join(' × ')}
              </p>
            </div>
            <div>
              <p className="text-zinc-500">Forecast horizon</p>
              <p className="text-zinc-300 font-mono text-xs">
                {data.data_info.total_predictions_shape?.[1] || '—'} days
              </p>
            </div>
            <div>
              <p className="text-zinc-500">Customers</p>
              <p className="text-zinc-300 font-mono text-xs">
                {data.data_info.total_predictions_shape?.[2] || '—'}
              </p>
            </div>
            <div>
              <p className="text-zinc-500">Displayed</p>
              <p className="text-zinc-300 font-mono text-xs">
                Customer #{data.data_info.customer_index}, {data.data_info.displayed_days} days
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
