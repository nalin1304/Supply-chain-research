import {
  LayoutDashboard,
  Map,
  TrendingUp,
  Shield,
  Brain,
  Leaf,
  Network,
  Activity,
  Lightbulb,
  Crosshair
} from 'lucide-react'
import { motion } from 'framer-motion'

const iconMap = {
  overview: LayoutDashboard,
  network: Map,
  optimization: TrendingUp,
  resilience: Shield,
  forecasting: Brain,
  advanced_rl: Network,
  robustness: Activity,
  xai: Lightbulb,
  morl: Crosshair,
  carbon: Leaf,
}

export default function Sidebar({ sections, activeSection, onSectionChange }) {
  return (
    <aside className="w-[240px] h-screen border-r border-cyber-border flex flex-col bg-cyber-panel backdrop-blur-xl">
      {/* Logo */}
      <div className="px-5 h-16 flex items-center gap-3 border-b border-cyber-border shadow-[0_4px_30px_rgba(0,0,0,0.1)]">
        <div className="w-8 h-8 rounded-lg bg-cyber-border flex items-center justify-center border border-cyber-cyan/30 shadow-[0_0_15px_rgba(0,240,255,0.2)]">
          <span className="text-xs font-bold text-cyber-cyan tracking-widest">AGY</span>
        </div>
        <span className="text-sm font-semibold text-zinc-100 tracking-wider">
          SUPPLY CHAIN AI
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-6 space-y-2">
        {sections.map((section) => {
          const isActive = activeSection === section.id
          const Icon = iconMap[section.id] || LayoutDashboard

          return (
            <motion.button
              key={section.id}
              onClick={() => onSectionChange(section.id)}
              whileHover={{ scale: 1.02, x: 4 }}
              whileTap={{ scale: 0.98 }}
              className={`w-full text-left px-4 py-3 rounded-xl text-sm flex items-center gap-3 cursor-pointer transition-all duration-300 ${
                isActive
                  ? 'text-cyber-cyan bg-cyber-cyan/10 font-medium border border-cyber-cyan/20 shadow-[0_0_15px_rgba(0,240,255,0.15)]'
                  : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5 border border-transparent'
              }`}
            >
              <Icon size={18} className={isActive ? "drop-shadow-[0_0_8px_rgba(0,240,255,0.8)]" : ""} />
              {section.label}
            </motion.button>
          )
        })}
      </nav>

      {/* Footer status */}
      <div className="px-5 py-5 border-t border-cyber-border bg-black/20">
        <div className="flex items-center gap-3">
          <div className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyber-purple opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyber-purple"></span>
          </div>
          <span className="text-xs tracking-wider uppercase font-medium text-cyber-purple drop-shadow-[0_0_5px_rgba(176,38,255,0.5)]">
            Models Active
          </span>
        </div>
      </div>
    </aside>
  )
}
