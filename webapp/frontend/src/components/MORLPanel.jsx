import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { fetchParetoShift } from '../api/client'
import { Route, Crosshair, ArrowLeftRight } from 'lucide-react'

export default function MORLPanel() {
  const [data, setData] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchParetoShift().then(res => {
      setData(res.data)
      setMetrics(res.metrics)
      setLoading(false)
    })
  }, [])

  if (loading) return <div className="text-fuchsia-400 animate-pulse">Loading MORL Preferences...</div>

  // Separate data into series based on preference
  const ecoData = data.filter(d => d.preference === 'Eco-Friendly')
  const balData = data.filter(d => d.preference === 'Balanced')
  const fastData = data.filter(d => d.preference === 'Cost-Optimized')

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-light tracking-wide text-white drop-shadow-cyber">
            Dynamic MORL & Routing
          </h2>
          <div className="flex gap-4">
            <span className="px-4 py-1 text-sm rounded-full bg-fuchsia-500/10 text-fuchsia-400 border border-fuchsia-500/30 backdrop-blur-md">
              Phase 14: MORL
            </span>
            <span className="px-4 py-1 text-sm rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 backdrop-blur-md">
              Phase 13: Dynamic Routing
            </span>
          </div>
        </div>

        {/* Educational Context Banner */}
        <div className="bg-fuchsia-900/20 border border-fuchsia-500/30 rounded-lg p-4 flex gap-4">
          <div className="text-fuchsia-400 mt-1">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-fuchsia-300 mb-1">What is this?</h4>
            <p className="text-xs text-fuchsia-200/70 leading-relaxed">
              Different companies have different priorities. A green company cares about carbon; a budget company cares about cost. In <strong>Phase 14 (Multi-Objective RL)</strong>, we created a single AI that can instantly shift its focus between Cost and Carbon based on a slider, without needing to be retrained. The scatter plot below shows how the 'optimal' supply chain choices shift dynamically when we change our priorities.
            </p>
          </div>
        </div>

        {/* Deep Academic Specs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">Multi-Objective Algorithms</h5>
            <div className="text-xs text-zinc-300 font-mono">NSGA-II, NSGA-III, MOEA/D<br/>Marginal cost-carbon repair op</div>
          </div>
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">NSGA-II Performance</h5>
            <div className="text-xs text-zinc-300 font-mono">Joint-Normalized HV:<br/>0.713 ± 0.143 (50 seeds)</div>
          </div>
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">Statistical Dominance</h5>
            <div className="text-xs text-zinc-300 font-mono">Friedman Omnibus Test<br/>χ² = 7.32, p = 0.0257</div>
          </div>
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">Dynamic Routing (Phase 13)</h5>
            <div className="text-xs text-zinc-300 font-mono">Spatio-Temporal constraints<br/>Traffic matrices applied</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 rounded-xl bg-cyber-panel border border-fuchsia-500/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-fuchsia-400">
            <Crosshair className="w-5 h-5" />
            <h3 className="font-semibold">MORL Hypervolume</h3>
          </div>
          <div className="text-3xl font-light">{metrics?.hypervolume_morl}</div>
        </div>
        
        <div className="p-6 rounded-xl bg-cyber-panel border border-cyan-500/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-cyan-400">
            <ArrowLeftRight className="w-5 h-5" />
            <h3 className="font-semibold">Adaptation Time</h3>
          </div>
          <div className="text-3xl font-light">{metrics?.dynamic_adaptation_time}</div>
        </div>

        <div className="p-6 rounded-xl bg-cyber-panel border border-emerald-500/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-emerald-400">
            <Route className="w-5 h-5" />
            <h3 className="font-semibold">Preference Vectors</h3>
          </div>
          <div className="text-3xl font-light">{metrics?.preference_vectors} Modes</div>
        </div>
      </div>

      <div className="h-[450px] w-full p-6 rounded-xl bg-cyber-panel border border-white/10 backdrop-blur-md shadow-cyber relative">
        <div className="absolute top-6 left-6 z-10 text-sm text-white/50">
          * Shift in Pareto optimal policies when the agent's internal scalarization changes.
        </div>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
            <XAxis 
              type="number" 
              dataKey="cost" 
              name="Logistics Cost" 
              unit=" INR" 
              stroke="#ffffff50" 
              tickFormatter={(v) => `${(v/1000000).toFixed(1)}M`}
              domain={['auto', 'auto']}
            />
            <YAxis 
              type="number" 
              dataKey="carbon" 
              name="Emissions" 
              unit=" tCO2" 
              stroke="#ffffff50" 
              tickFormatter={(v) => `${(v/1000).toFixed(0)}k`}
              domain={['auto', 'auto']}
            />
            <Tooltip 
              cursor={{ strokeDasharray: '3 3' }} 
              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#d946ef', borderRadius: '8px' }}
              itemStyle={{ color: '#e2e8f0' }}
            />
            <Legend />
            <Scatter name="Eco-Friendly Focus" data={ecoData} fill="#10b981" />
            <Scatter name="Balanced Focus" data={balData} fill="#3b82f6" />
            <Scatter name="Cost-Optimized Focus" data={fastData} fill="#ef4444" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </motion.div>
  )
}
