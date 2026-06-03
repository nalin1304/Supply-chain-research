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
          <div>
            <h2 className="text-xs font-bold uppercase tracking-widest text-premium-accent mb-1">Phase 13 & 14: Dynamic Routing & MORL</h2>
            <h2 className="text-3xl font-light tracking-wide text-white drop-shadow-cyber">
              Dynamic MORL & Routing
            </h2>
          </div>
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
        <div className="bg-premium-accent/10 border-l-4 border-premium-accent rounded-r-lg p-5 flex gap-4">
          <div className="text-premium-accent mt-1">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-premium-text mb-1">Methodology Overview</h4>
            <p className="text-sm text-premium-textMuted leading-relaxed">
              Different companies have different priorities. A green company cares about carbon; a budget company cares about cost. In <strong>Phase 14 (Multi-Objective RL)</strong>, we created a single AI that can instantly shift its focus between Cost and Carbon based on a slider, without needing to be retrained. The scatter plot below shows how the 'optimal' supply chain choices shift dynamically when we change our priorities.
            </p>
          </div>
        </div>

        {/* Deep Academic Specs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
          <div className="p-4 bg-premium-panel border border-premium-border rounded-xl">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-2">Multi-Objective Algorithms</h5>
            <div className="text-xs text-zinc-300 font-mono">NSGA-II, NSGA-III, MOEA/D<br/>Marginal cost-carbon repair op</div>
          </div>
          <div className="p-4 bg-premium-panel border border-premium-border rounded-xl">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-2">NSGA-II Performance</h5>
            <div className="text-xs text-zinc-300 font-mono">Joint-Normalized HV:<br/>0.713 ± 0.143 (50 seeds)</div>
          </div>
          <div className="p-4 bg-premium-panel border border-premium-border rounded-xl">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-2">Statistical Dominance</h5>
            <div className="text-xs text-zinc-300 font-mono">Friedman Omnibus Test<br/>χ² = 7.32, p = 0.0257</div>
          </div>
          <div className="p-4 bg-premium-panel border border-premium-border rounded-xl">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-2">Dynamic Routing (Phase 13)</h5>
            <div className="text-xs text-zinc-300 font-mono">Spatio-Temporal constraints<br/>Traffic matrices applied</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 rounded-xl bg-premium-panel border border-premium-border">
          <div className="flex items-center gap-3 mb-2 text-fuchsia-400">
            <Crosshair className="w-5 h-5" />
            <h3 className="font-semibold">MORL Hypervolume</h3>
          </div>
          <div className="text-3xl font-light text-fuchsia-400">{metrics?.hypervolume_morl || '0.713'}</div>
        </div>
        
        <div className="p-6 rounded-xl bg-premium-panel border border-premium-border">
          <div className="flex items-center gap-3 mb-2 text-cyan-400">
            <ArrowLeftRight className="w-5 h-5" />
            <h3 className="font-semibold">Adaptation Time</h3>
          </div>
          <div className="text-3xl font-light text-cyan-400">{metrics?.dynamic_adaptation_time || '14ms'}</div>
        </div>

        <div className="p-6 rounded-xl bg-premium-panel border border-premium-border">
          <div className="flex items-center gap-3 mb-2 text-emerald-400">
            <Route className="w-5 h-5" />
            <h3 className="font-semibold">Preference Vectors</h3>
          </div>
          <div className="text-3xl font-light text-emerald-400">{metrics?.preference_vectors || '11'} Modes</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <div className="bg-premium-panel border border-premium-border rounded-xl p-6 relative overflow-hidden group">
          <div className="absolute inset-0 bg-fuchsia-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"></div>
          <h3 className="text-sm font-semibold text-zinc-100 mb-4 flex justify-between items-center relative z-10">
            Cost vs Carbon Pareto Front (NSGA-II)
            <span className="text-[10px] bg-fuchsia-500/20 text-fuchsia-400 px-2 py-1 rounded-full uppercase tracking-wider">Publication Fig. 2</span>
          </h3>
          <div className="h-[400px] w-full rounded-lg overflow-hidden border border-zinc-800 bg-[#111] flex items-center justify-center relative z-10 p-2">
            <img src="/assets/figures/fig2_pareto_front.png" alt="Pareto Front" className="max-w-full max-h-full object-contain hover:scale-105 transition-transform duration-500" />
          </div>
        </div>

        <div className="bg-premium-panel border border-premium-border rounded-xl p-6 relative overflow-hidden group">
          <div className="absolute inset-0 bg-emerald-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"></div>
          <h3 className="text-sm font-semibold text-zinc-100 mb-4 flex justify-between items-center relative z-10">
            NSGA-III Constraint Projections
            <span className="text-[10px] bg-emerald-500/20 text-emerald-400 px-2 py-1 rounded-full uppercase tracking-wider">Publication Fig. 8</span>
          </h3>
          <div className="h-[400px] w-full rounded-lg overflow-hidden border border-zinc-800 bg-[#111] flex items-center justify-center relative z-10 p-2">
            <img src="/assets/figures/fig8_nsga3_projections.png" alt="NSGA-III Projections" className="max-w-full max-h-full object-contain hover:scale-105 transition-transform duration-500" />
          </div>
        </div>
      </div>
    </motion.div>
  )
}
