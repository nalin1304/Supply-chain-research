import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchNetworkNodes } from '../api/client'
import EmptyState from './EmptyState'
import { Map } from 'lucide-react'

function projectPoint(lat, lng) {
  const x = ((lng - 68) / (97 - 68)) * 100
  const y = ((35 - lat) / (35 - 8)) * 100
  return { x, y }
}

function MapVisualization({ warehouses, customers }) {
  const [hovered, setHovered] = useState(null)

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="relative w-full h-[500px]">
        <svg viewBox="0 0 100 100" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
          {/* Grid */}
          <defs>
            <pattern id="grid" width="5" height="5" patternUnits="userSpaceOnUse">
              <path d="M 5 0 L 0 0 0 5" fill="none" stroke="rgba(255,255,255,0.02)" strokeWidth="0.1" />
            </pattern>
          </defs>
          <rect width="100" height="100" fill="url(#grid)" />

          {/* India outline */}
          <path
            d="M 35 15 L 42 11 L 50 10 L 58 12 L 65 15 L 72 18 L 78 22 L 82 28 L 83 35 L 80 42 L 76 50 L 72 56 L 67 62 L 62 68 L 56 74 L 50 80 L 46 84 L 42 80 L 38 74 L 34 66 L 30 58 L 26 50 L 23 42 L 22 35 L 23 28 L 26 22 L 30 18 Z"
            fill="none"
            stroke="#3f3f46"
            strokeWidth="0.3"
          />

          {/* Customer dots */}
          {customers.map((customer) => {
            const pos = projectPoint(customer.lat, customer.lng)
            return (
              <circle
                key={customer.id}
                cx={pos.x}
                cy={pos.y}
                r="0.4"
                fill="#2563eb"
                opacity={0.35}
              />
            )
          })}

          {/* Warehouse squares */}
          {warehouses.map((wh) => {
            const pos = projectPoint(wh.lat, wh.lng)
            const isHovered = hovered?.id === wh.id
            return (
              <g
                key={wh.id}
                onMouseEnter={() => setHovered(wh)}
                onMouseLeave={() => setHovered(null)}
                className="cursor-pointer"
              >
                <rect
                  x={pos.x - 1}
                  y={pos.y - 1}
                  width="2"
                  height="2"
                  rx="0.3"
                  fill="#dc2626"
                  opacity={isHovered ? 1 : 0.8}
                />
                <text
                  x={pos.x + 2.5}
                  y={pos.y + 0.5}
                  fontSize="1.8"
                  fill={isHovered ? '#fafafa' : '#71717a'}
                  fontFamily="Inter, sans-serif"
                >
                  {wh.name.replace(' DC', '')}
                </text>
              </g>
            )
          })}
        </svg>

        {/* Tooltip */}
        {hovered && (
          <div className="absolute top-4 right-4 bg-zinc-900 border border-zinc-700 rounded-lg p-3 min-w-[160px]">
            <p className="text-sm font-medium text-zinc-200">{hovered.name}</p>
            <p className="text-xs text-zinc-500 mt-1 font-mono">
              {hovered.lat.toFixed(2)}°N, {hovered.lng.toFixed(2)}°E
            </p>
            {hovered.capacity && (
              <p className="text-xs text-zinc-500 mt-0.5">
                Capacity: {hovered.capacity.toLocaleString()} units
              </p>
            )}
          </div>
        )}

        {/* Legend */}
        <div className="absolute bottom-4 left-4 flex items-center gap-4 text-xs text-zinc-500">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm bg-red-600" />
            <span>Warehouse</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-blue-600 opacity-50" />
            <span>Customer</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function NetworkMap() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['network-nodes'],
    queryFn: fetchNetworkNodes,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 rounded-full border-2 border-zinc-700 border-t-blue-600 animate-spin" />
      </div>
    )
  }

  if (error || (!data?.warehouses?.length && !data?.customers?.length)) {
    return (
      <div className="space-y-8">
        <div>
          <h2 className="text-xl font-semibold text-zinc-50 tracking-tight">Network Map</h2>
          <p className="text-sm text-zinc-500 mt-1">Distribution centers and customer locations</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <EmptyState
            icon={Map}
            title="No network data available"
            description="Connect to backend to view warehouse and customer locations across India."
          />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-semibold text-zinc-50 tracking-tight">Network Map</h2>
        <p className="text-sm text-zinc-500 mt-1">
          {data.warehouses.length} warehouses · {data.customers.length} customers
        </p>
      </div>

      <MapVisualization warehouses={data.warehouses} customers={data.customers} />

      {/* Table */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4">
          Distribution Centers
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
                <th className="pb-3 font-medium">Name</th>
                <th className="pb-3 font-medium">Location</th>
                <th className="pb-3 font-medium text-right">Capacity</th>
              </tr>
            </thead>
            <tbody className="text-zinc-300">
              {data.warehouses.map((wh) => (
                <tr key={wh.id} className="border-b border-zinc-800/50">
                  <td className="py-3 font-medium">{wh.name}</td>
                  <td className="py-3 text-zinc-500 font-mono text-xs">
                    {wh.lat.toFixed(2)}°N, {wh.lng.toFixed(2)}°E
                  </td>
                  <td className="py-3 text-right font-mono text-xs">
                    {wh.capacity?.toLocaleString() || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
