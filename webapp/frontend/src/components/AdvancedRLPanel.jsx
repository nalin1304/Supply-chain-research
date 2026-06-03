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
          <div>
            <h2 className="text-xs font-bold uppercase tracking-widest text-premium-accent mb-1">Phase 7 & 12: MAPPO & Offline Decision Transformers</h2>
            <h2 className="text-3xl font-light tracking-wide text-white drop-shadow-cyber">
              Advanced Multi-Agent & Offline RL
            </h2>
          </div>
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
        <div className="bg-premium-accent/10 border-l-4 border-premium-accent rounded-r-lg p-5 flex gap-4">
          <div className="text-premium-accent mt-1">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-premium-text mb-1">Methodology Overview</h4>
            <p className="text-sm text-premium-textMuted leading-relaxed">
              Normally, an AI (PPO) learns by trial and error, which takes a long time. In <strong>Phase 7 (MAPPO)</strong>, we break the problem down so multiple AI agents work together at different warehouses. In <strong>Phase 12 (Decision Transformers)</strong>, we give the AI an 'offline' cheat sheet of expert human decisions so it doesn't have to start learning from scratch. This graph shows how much faster our advanced models learn compared to the baseline.
            </p>
          </div>
        </div>

        {/* Deep Academic Specs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
          <div className="p-4 bg-premium-panel border border-premium-border rounded-xl">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-2">Architecture</h5>
            <div className="text-xs text-zinc-300 font-mono">Attention-LSTM<br/>256 hidden × 3 layers</div>
          </div>
          <div className="p-4 bg-premium-panel border border-premium-border rounded-xl">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-2">Forecasting (7-Day)</h5>
            <div className="text-xs text-zinc-300 font-mono">MAPE: 23.46%<br/>RMSE: 56.46 kg</div>
          </div>
          <div className="p-4 bg-premium-panel border border-premium-border rounded-xl">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-2">RL Algorithms</h5>
            <div className="text-xs text-zinc-300 font-mono">MAPPO (Phase 7)<br/>Decision Transformer</div>
          </div>
          <div className="p-4 bg-premium-panel border border-premium-border rounded-xl">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-2">Cloud Training</h5>
            <div className="text-xs text-zinc-300 font-mono">1,000,000 steps<br/>Modal Tesla T4 ($1.80)</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 rounded-xl bg-premium-panel border border-premium-border">
          <div className="flex items-center gap-3 mb-2 text-premium-accent">
            <BrainCircuit className="w-5 h-5" />
            <h3 className="font-semibold">MAPPO Final Reward</h3>
          </div>
          <div className="text-3xl font-light text-premium-text">{metrics?.mappo_final_reward?.toLocaleString() || '-250,765'}</div>
        </div>
        
        <div className="p-6 rounded-xl bg-premium-panel border border-premium-border">
          <div className="flex items-center gap-3 mb-2 text-premium-accent">
            <Server className="w-5 h-5" />
            <h3 className="font-semibold">DT Final Reward</h3>
          </div>
          <div className="text-3xl font-light text-premium-text">{metrics?.dt_final_reward?.toLocaleString() || '-135,651'}</div>
        </div>

        <div className="p-6 rounded-xl bg-premium-panel border border-emerald-500/20">
          <div className="flex items-center gap-3 mb-2 text-emerald-400">
            <Zap className="w-5 h-5" />
            <h3 className="font-semibold">Convergence Speedup</h3>
          </div>
          <div className="text-3xl font-light text-emerald-400">{metrics?.convergence_speedup || '4.2x'}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <div className="bg-premium-panel border border-premium-border rounded-xl p-6 relative overflow-hidden group">
          <div className="absolute inset-0 bg-premium-accent/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"></div>
          <h3 className="text-sm font-semibold text-zinc-100 mb-4 flex justify-between items-center relative z-10">
            RL Training Convergence (1M Steps)
            <span className="text-[10px] bg-premium-accent/20 text-premium-accent px-2 py-1 rounded-full uppercase tracking-wider">Publication Fig. 6</span>
          </h3>
          <div className="h-[400px] w-full rounded-lg overflow-hidden border border-zinc-800 bg-[#111] flex items-center justify-center relative z-10">
            <img src="/assets/figures/fig6_ppo_training.png" alt="PPO Training Convergence" className="max-w-full max-h-full object-contain hover:scale-105 transition-transform duration-500" />
          </div>
        </div>

        <div className="bg-premium-panel border border-premium-border rounded-xl p-6 relative overflow-hidden group">
          <div className="absolute inset-0 bg-emerald-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"></div>
          <h3 className="text-sm font-semibold text-zinc-100 mb-4 flex justify-between items-center relative z-10">
            LSTM Demand Forecast Validation
            <span className="text-[10px] bg-emerald-500/20 text-emerald-400 px-2 py-1 rounded-full uppercase tracking-wider">Publication Fig. 5</span>
          </h3>
          <div className="h-[400px] w-full rounded-lg overflow-hidden border border-zinc-800 bg-[#111] flex items-center justify-center relative z-10">
            <img src="/assets/figures/fig5_lstm_forecast.png" alt="LSTM Forecast Validation" className="max-w-full max-h-full object-contain hover:scale-105 transition-transform duration-500" />
          </div>
        </div>
      </div>
    </motion.div>
  )
}
