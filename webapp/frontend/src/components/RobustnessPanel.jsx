import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { fetchAttackSurface } from '../api/client'
import { ShieldAlert, ShieldCheck, Activity } from 'lucide-react'

export default function RobustnessPanel() {
  const [data, setData] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchAttackSurface().then(res => {
      setData(res.data)
      setMetrics(res.metrics)
      setLoading(false)
    })
  }, [])

  if (loading) return <div className="text-red-400 animate-pulse">Loading Adversarial Metrics...</div>

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-light tracking-wide text-white drop-shadow-cyber">
            Adversarial & CVaR Robustness
          </h2>
          <div className="flex gap-4">
            <span className="px-4 py-1 text-sm rounded-full bg-red-500/10 text-red-400 border border-red-500/30 backdrop-blur-md">
              Phase 11: Minimax Attacks
            </span>
            <span className="px-4 py-1 text-sm rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30 backdrop-blur-md">
              Phase 10: CVaR Optimization
            </span>
          </div>
        </div>

        {/* Educational Context Banner */}
        <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4 flex gap-4">
          <div className="text-red-400 mt-1">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-red-300 mb-1">What is this?</h4>
            <p className="text-xs text-red-200/70 leading-relaxed">
              Supply chains face random shocks (like delays). But what if a malicious attacker intentionally disrupted our most critical routes? In <strong>Phase 11 (Adversarial Robustness)</strong>, we train our AI against a 'hacker' AI that tries to break our supply chain. We also use <strong>Phase 10 (CVaR)</strong>, a financial risk metric, to ensure that even in the absolute worst 5% of disaster scenarios, our service level never drops below a safe bound. The graph below proves our system stays strong even when actively attacked.
            </p>
          </div>
        </div>

        {/* Deep Academic Specs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">Simulation Engine</h5>
            <div className="text-xs text-zinc-300 font-mono">SimPy DES<br/>100 Monte Carlo Reps</div>
          </div>
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">Severe Disruption Test</h5>
            <div className="text-xs text-zinc-300 font-mono">Horizon: 365 days<br/>(R,s,S) Baseline: Fails at 61d</div>
          </div>
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">PPO Stress Survival</h5>
            <div className="text-xs text-zinc-300 font-mono">Survives 91 days<br/>SL drops to 95.4% max</div>
          </div>
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">Risk Bounds (CVaR)</h5>
            <div className="text-xs text-zinc-300 font-mono">99th percentile<br/>Stockouts strictly capped</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 rounded-xl bg-cyber-panel border border-red-500/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-red-400">
            <ShieldAlert className="w-5 h-5" />
            <h3 className="font-semibold">Max Adversarial Drop</h3>
          </div>
          <div className="text-3xl font-light">{metrics?.max_adversarial_drop}</div>
        </div>
        
        <div className="p-6 rounded-xl bg-cyber-panel border border-emerald-500/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-emerald-400">
            <ShieldCheck className="w-5 h-5" />
            <h3 className="font-semibold">CVaR Guarantee</h3>
          </div>
          <div className="text-3xl font-light">{metrics?.cvar_bound}</div>
        </div>

        <div className="p-6 rounded-xl bg-cyber-panel border border-blue-500/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-blue-400">
            <Activity className="w-5 h-5" />
            <h3 className="font-semibold">Minimax Gap</h3>
          </div>
          <div className="text-3xl font-light">{metrics?.minimax_gap}</div>
        </div>
      </div>

      <div className="h-[400px] w-full p-6 rounded-xl bg-cyber-panel border border-white/10 backdrop-blur-md shadow-cyber">
        <h3 className="text-lg text-white/70 mb-4">Service Level vs Attack Strength</h3>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
            <XAxis dataKey="attack_strength" stroke="#ffffff50" />
            <YAxis stroke="#ffffff50" domain={[0, 100]} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#ef4444', borderRadius: '8px' }}
              itemStyle={{ color: '#e2e8f0' }}
            />
            <Legend />
            <Area 
              type="monotone" 
              dataKey="PPO_Adversarial" 
              stackId="1" 
              stroke="#ef4444" 
              fill="#ef4444" 
              fillOpacity={0.2} 
              name="Base PPO (Adversarial)"
            />
            <Area 
              type="monotone" 
              dataKey="CVaR_Adversarial" 
              stackId="2" 
              stroke="#10b981" 
              fill="#10b981" 
              fillOpacity={0.2} 
              name="CVaR-MAPPO (Adversarial)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </motion.div>
  )
}
