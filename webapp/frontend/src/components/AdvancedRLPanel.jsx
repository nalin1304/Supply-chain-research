import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { fetchLearningCurves } from '../api/client'
import { BrainCircuit, Zap, Server } from 'lucide-react'

export default function AdvancedRLPanel() {
  const [data, setData] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchLearningCurves().then(res => {
      setData(res.data)
      setMetrics(res.metrics)
      setLoading(false)
    })
  }, [])

  if (loading) return <div className="text-cyber-blue animate-pulse">Loading Advanced RL Models...</div>

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-light tracking-wide text-white drop-shadow-cyber">
            Advanced Multi-Agent & Offline RL
          </h2>
          <div className="flex gap-4">
            <span className="px-4 py-1 text-sm rounded-full bg-cyber-blue/10 text-cyber-blue border border-cyber-blue/30 backdrop-blur-md">
              Phase 7: MAPPO
            </span>
            <span className="px-4 py-1 text-sm rounded-full bg-cyber-purple/10 text-cyber-purple border border-cyber-purple/30 backdrop-blur-md">
              Phase 12: Decision Transformers
            </span>
          </div>
        </div>

        {/* Educational Context Banner */}
        <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-4 flex gap-4">
          <div className="text-blue-400 mt-1">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-blue-300 mb-1">What is this?</h4>
            <p className="text-xs text-blue-200/70 leading-relaxed">
              Normally, an AI (PPO) learns by trial and error, which takes a long time. In <strong>Phase 7 (MAPPO)</strong>, we break the problem down so multiple AI agents work together at different warehouses. In <strong>Phase 12 (Decision Transformers)</strong>, we give the AI an 'offline' cheat sheet of expert human decisions so it doesn't have to start learning from scratch. This graph shows how much faster our advanced models learn compared to the baseline.
            </p>
          </div>
        </div>

        {/* Deep Academic Specs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">Architecture</h5>
            <div className="text-xs text-zinc-300 font-mono">Attention-LSTM<br/>256 hidden × 3 layers</div>
          </div>
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">Forecasting (7-Day)</h5>
            <div className="text-xs text-zinc-300 font-mono">MAPE: 23.46%<br/>RMSE: 56.46 kg</div>
          </div>
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">RL Algorithms</h5>
            <div className="text-xs text-zinc-300 font-mono">MAPPO (Phase 7)<br/>Decision Transformer (Phase 12)</div>
          </div>
          <div className="p-3 bg-black/40 border border-zinc-800 rounded-md">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-1">Cloud Training</h5>
            <div className="text-xs text-zinc-300 font-mono">1,000,000 steps<br/>Modal Tesla T4 ($1.80)</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 rounded-xl bg-cyber-panel border border-cyber-blue/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-cyber-blue">
            <BrainCircuit className="w-5 h-5" />
            <h3 className="font-semibold">MAPPO Final Reward</h3>
          </div>
          <div className="text-3xl font-light">{metrics?.mappo_final_reward?.toLocaleString()}</div>
        </div>
        
        <div className="p-6 rounded-xl bg-cyber-panel border border-cyber-purple/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-cyber-purple">
            <Server className="w-5 h-5" />
            <h3 className="font-semibold">DT Final Reward</h3>
          </div>
          <div className="text-3xl font-light">{metrics?.dt_final_reward?.toLocaleString()}</div>
        </div>

        <div className="p-6 rounded-xl bg-cyber-panel border border-emerald-500/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-emerald-400">
            <Zap className="w-5 h-5" />
            <h3 className="font-semibold">Convergence Speedup</h3>
          </div>
          <div className="text-3xl font-light">{metrics?.convergence_speedup}</div>
        </div>
      </div>

      <div className="h-[400px] w-full p-6 rounded-xl bg-cyber-panel border border-white/10 backdrop-blur-md shadow-cyber">
        <h3 className="text-lg text-white/70 mb-4">Training Reward Curves (1M Steps)</h3>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
            <XAxis 
              dataKey="step" 
              stroke="#ffffff50" 
              tickFormatter={(v) => `${(v/1000).toFixed(0)}k`} 
            />
            <YAxis stroke="#ffffff50" domain={['auto', 'auto']} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#38bdf8', borderRadius: '8px' }}
              itemStyle={{ color: '#e2e8f0' }}
            />
            <Legend />
            <Line 
              type="monotone" 
              dataKey="PPO" 
              stroke="#64748b" 
              strokeWidth={2}
              dot={false} 
              name="Base PPO"
            />
            <Line 
              type="monotone" 
              dataKey="MAPPO" 
              stroke="#38bdf8" 
              strokeWidth={3}
              dot={false} 
              name="MAPPO (Multi-Agent)"
            />
            <Line 
              type="monotone" 
              dataKey="Decision_Transformer" 
              stroke="#c084fc" 
              strokeWidth={3}
              dot={false} 
              name="Offline DT (Pre-trained)"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </motion.div>
  )
}
