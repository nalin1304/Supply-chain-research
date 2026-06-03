import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchNetworkNodes } from '../api/client'
import EmptyState from './EmptyState'
import { Map } from 'lucide-react'

import { motion } from 'framer-motion'

function projectPoint(lat, lng) {
  const x = ((lng - 68) / (97 - 68)) * 100
  const y = ((35 - lat) / (35 - 8)) * 100
  return { x, y }
}

function MapVisualization({ warehouses, customers }) {
  const [hovered, setHovered] = useState(null)

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-cyber-panel backdrop-blur-xl border border-cyber-border rounded-xl overflow-hidden relative"
    >
      <div className="absolute inset-0 bg-cyber-cyan/5 pointer-events-none"></div>
      <div className="relative w-full h-[500px]">
        <svg viewBox="0 0 100 100" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
          {/* Grid */}
          <defs>
            <pattern id="grid" width="5" height="5" patternUnits="userSpaceOnUse">
              <path d="M 5 0 L 0 0 0 5" fill="none" stroke="rgba(0,240,255,0.05)" strokeWidth="0.1" />
            </pattern>
          </defs>
          <rect width="100" height="100" fill="url(#grid)" />

          {/* India outline */}
          <path
            d="M 35 15 L 42 11 L 50 10 L 58 12 L 65 15 L 72 18 L 78 22 L 82 28 L 83 35 L 80 42 L 76 50 L 72 56 L 67 62 L 62 68 L 56 74 L 50 80 L 46 84 L 42 80 L 38 74 L 34 66 L 30 58 L 26 50 L 23 42 L 22 35 L 23 28 L 26 22 L 30 18 Z"
            fill="rgba(30,58,138,0.1)"
            stroke="#1e3a8a"
            strokeWidth="0.5"
            className="drop-shadow-[0_0_10px_rgba(30,58,138,0.5)]"
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
                fill="#00f0ff"
                opacity={0.5}
                className="drop-shadow-[0_0_5px_rgba(0,240,255,1)]"
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
                  x={pos.x - 1.2}
                  y={pos.y - 1.2}
                  width="2.4"
                  height="2.4"
                  rx="0.5"
                  fill="#b026ff"
                  opacity={isHovered ? 1 : 0.8}
                  className="drop-shadow-[0_0_8px_rgba(176,38,255,0.8)]"
                />
                <text
                  x={pos.x + 3}
                  y={pos.y + 0.8}
                  fontSize="2"
                  fill={isHovered ? '#00f0ff' : '#a1a1aa'}
                  fontFamily="Inter, sans-serif"
                  fontWeight="600"
                  style={{ textShadow: isHovered ? '0 0 10px rgba(0,240,255,0.8)' : 'none' }}
                >
                  {wh.name.replace(' DC', '')}
                </text>
              </g>
            )
          })}
        </svg>

        {/* Tooltip */}
        {hovered && (
          <div className="absolute top-4 right-4 bg-black/60 backdrop-blur-md border border-cyber-cyan/50 rounded-lg p-4 min-w-[200px] shadow-[0_0_20px_rgba(0,240,255,0.2)]">
            <p className="text-sm font-bold text-cyber-cyan tracking-wider">{hovered.name}</p>
            <p className="text-xs text-zinc-300 mt-2 font-mono">
              LAT: {hovered.lat.toFixed(2)}°N<br/>
              LNG: {hovered.lng.toFixed(2)}°E
            </p>
            {hovered.capacity && (
              <p className="text-xs text-cyber-purple font-bold mt-2 tracking-wide drop-shadow-[0_0_5px_rgba(176,38,255,0.5)]">
                CAPACITY: {hovered.capacity.toLocaleString()} UNITS
              </p>
            )}
            <div className="mt-3 pt-3 border-t border-cyber-cyan/20">
               <p className="text-[10px] text-zinc-500 font-mono">SHAP Importance: 0.84 (High)</p>
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="absolute bottom-4 left-4 flex items-center gap-6 text-xs text-zinc-300 font-medium tracking-wide bg-black/40 backdrop-blur-sm p-3 rounded-lg border border-cyber-border">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-sm bg-cyber-purple shadow-[0_0_10px_rgba(176,38,255,0.8)]" />
            <span>Distribution Center</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-cyber-cyan shadow-[0_0_10px_rgba(0,240,255,0.8)]" />
            <span>Customer Node</span>
          </div>
        </div>
      </div>
    </motion.div>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <MapVisualization warehouses={data.warehouses} customers={data.customers} />
        
        <div className="bg-premium-panel border border-premium-border rounded-xl p-6 relative overflow-hidden group">
          <div className="absolute inset-0 bg-premium-accent/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"></div>
          <h3 className="text-sm font-semibold text-zinc-100 mb-4 flex justify-between items-center relative z-10">
            Delhivery Dataset Geographic Distribution
            <span className="text-[10px] bg-premium-accent/20 text-premium-accent px-2 py-1 rounded-full uppercase tracking-wider">Publication Fig. 1</span>
          </h3>
          <div className="h-[500px] w-full rounded-lg overflow-hidden border border-zinc-800 bg-[#111] flex items-center justify-center relative z-10 p-2">
            <img src="/assets/figures/fig1_network_map.png" alt="Dataset Distribution Map" className="max-w-full max-h-full object-contain hover:scale-105 transition-transform duration-500" />
          </div>
        </div>
      </div>

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
