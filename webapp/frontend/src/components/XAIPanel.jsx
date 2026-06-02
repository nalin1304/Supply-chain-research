import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { fetchShapValues } from '../api/client'
import { Eye, Focus, Compass } from 'lucide-react'

export default function XAIPanel() {
  const [data, setData] = useState([])
  const [attention, setAttention] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchShapValues().then(res => {
      setData(res.shap_values)
      setAttention(res.attention_weights)
      setMetrics(res.metrics)
      setLoading(false)
    })
  }, [])

  if (loading) return <div className="text-amber-400 animate-pulse">Loading XAI Explanations...</div>

  const colors = ['#f59e0b', '#3b82f6', '#10b981', '#ec4899', '#8b5cf6', '#64748b']

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-3xl font-light tracking-wide text-white drop-shadow-cyber">
            Explainable AI (SHAP & ST-GNN)
          </h2>
          <div className="flex gap-4">
            <span className="px-4 py-1 text-sm rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30 backdrop-blur-md">
              Phase 9: SHAP Values
            </span>
            <span className="px-4 py-1 text-sm rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/30 backdrop-blur-md">
              Phase 7: ST-GNN Attention
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
              AI is often a 'black box'—we don't know why it made a decision. In <strong>Phase 9 (SHAP)</strong>, we force the AI to explain itself, showing exactly which factors (like Current Inventory or Forecasts) drove its decision to order more stock. In <strong>Phase 7 (ST-GNN)</strong>, the AI acts like a brain, paying 'attention' to other geographic hubs; the glowing bars show which cities are most closely communicating to predict demand.
            </p>
          </div>
        </div>

        {/* Deep Academic Specs */}
        <div className="grid grid-cols-2 gap-4 mt-2">
          <div className="p-4 bg-premium-panel border border-premium-border rounded-xl">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-2">Graph Neural Network</h5>
            <div className="text-xs text-zinc-300 font-mono">Spatio-Temporal GNN (ST-GNN)<br/>Extracts inter-hub spatial dependencies for traffic/demand propagation.</div>
          </div>
          <div className="p-4 bg-premium-panel border border-premium-border rounded-xl">
            <h5 className="text-[10px] uppercase text-zinc-500 font-bold tracking-wider mb-2">Explainability / Policy Extraction</h5>
            <div className="text-xs text-zinc-300 font-mono">SHapley Additive exPlanations (SHAP)<br/>100% interpretable operational rules extracted from black-box PPO.</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 rounded-xl bg-cyber-panel border border-amber-500/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-amber-400">
            <Eye className="w-5 h-5" />
            <h3 className="font-semibold">Interpretability Score</h3>
          </div>
          <div className="text-3xl font-light">{metrics?.interpretability_score}</div>
        </div>
        
        <div className="p-6 rounded-xl bg-cyber-panel border border-blue-500/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-blue-400">
            <Focus className="w-5 h-5" />
            <h3 className="font-semibold">Dominant Feature</h3>
          </div>
          <div className="text-2xl font-light truncate">{metrics?.dominant_feature}</div>
        </div>

        <div className="p-6 rounded-xl bg-cyber-panel border border-pink-500/20 backdrop-blur-md">
          <div className="flex items-center gap-3 mb-2 text-pink-400">
            <Compass className="w-5 h-5" />
            <h3 className="font-semibold">ST-GNN Active Edges</h3>
          </div>
          <div className="text-3xl font-light">{metrics?.gnn_active_edges}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="h-[400px] p-6 rounded-xl bg-cyber-panel border border-white/10 backdrop-blur-md shadow-cyber">
          <h3 className="text-lg text-white/70 mb-4">SHAP Feature Importance (Global)</h3>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ left: 50, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" horizontal={false} />
              <XAxis type="number" stroke="#ffffff50" />
              <YAxis dataKey="name" type="category" stroke="#ffffff50" width={120} tick={{ fill: '#e2e8f0', fontSize: 12 }} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#f59e0b', borderRadius: '8px' }}
                itemStyle={{ color: '#e2e8f0' }}
              />
              <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="h-[400px] p-6 rounded-xl bg-cyber-panel border border-white/10 backdrop-blur-md shadow-cyber overflow-y-auto scrollbar-hide">
          <h3 className="text-lg text-white/70 mb-4">ST-GNN Attention Weights</h3>
          <div className="space-y-4">
            {attention.map((edge, idx) => (
              <div key={idx} className="p-4 rounded-lg bg-black/40 border border-white/5 flex items-center justify-between">
                <div>
                  <div className="text-sm text-white/50">Source</div>
                  <div className="text-blue-400 font-medium">{edge.source}</div>
                </div>
                <div className="flex-1 px-4">
                  <div className="h-1 w-full bg-white/10 rounded-full overflow-hidden">
                    <motion.div 
                      initial={{ width: 0 }}
                      animate={{ width: `${edge.weight * 100}%` }}
                      transition={{ duration: 1, delay: idx * 0.2 }}
                      className="h-full bg-gradient-to-r from-blue-500 to-pink-500"
                    />
                  </div>
                  <div className="text-center text-xs text-white/50 mt-1">Weight: {edge.weight}</div>
                </div>
                <div className="text-right">
                  <div className="text-sm text-white/50">Target</div>
                  <div className="text-pink-400 font-medium">{edge.target}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  )
}
