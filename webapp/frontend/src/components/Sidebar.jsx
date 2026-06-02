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
    <aside className="w-[240px] h-screen border-r border-premium-border flex flex-col bg-premium-panel/50 backdrop-blur-xl">
      {/* Logo */}
      <div className="px-5 h-16 flex items-center gap-3 border-b border-premium-border">
        <div className="w-8 h-8 rounded-lg bg-premium-background flex items-center justify-center border border-premium-border">
          <span className="text-xs font-bold text-premium-accent tracking-widest">AGY</span>
        </div>
        <span className="text-sm font-semibold text-zinc-100 tracking-wider">
          SUPPLY CHAIN AI
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-6 space-y-1">
        {sections.map((section) => {
          const isActive = activeSection === section.id
          const Icon = iconMap[section.id] || LayoutDashboard

          return (
            <motion.button
              key={section.id}
              onClick={() => onSectionChange(section.id)}
              whileHover={{ x: 4 }}
              whileTap={{ scale: 0.98 }}
              className={`w-full text-left px-4 py-2.5 rounded-lg text-sm flex items-center gap-3 cursor-pointer transition-colors duration-200 ${
                isActive
                  ? 'text-premium-accent bg-premium-accent/10 font-medium'
                  : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5'
              }`}
            >
              <Icon size={18} className={isActive ? "text-premium-accent" : "opacity-70"} />
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
