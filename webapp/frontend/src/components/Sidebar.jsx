import {
  LayoutDashboard,
  Map,
  TrendingUp,
  Shield,
  Brain,
  Leaf,
} from 'lucide-react'

const iconMap = {
  overview: LayoutDashboard,
  network: Map,
  optimization: TrendingUp,
  resilience: Shield,
  forecasting: Brain,
  carbon: Leaf,
}

export default function Sidebar({ sections, activeSection, onSectionChange }) {
  return (
    <aside className="w-[220px] h-screen border-r border-zinc-800 flex flex-col bg-zinc-950">
      {/* Logo */}
      <div className="px-5 h-14 flex items-center gap-3 border-b border-zinc-800">
        <div className="w-7 h-7 rounded-md bg-zinc-800 flex items-center justify-center">
          <span className="text-xs font-semibold text-zinc-300">SC</span>
        </div>
        <span className="text-sm font-medium text-zinc-200 tracking-tight">
          Supply Chain AI
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {sections.map((section) => {
          const isActive = activeSection === section.id
          const Icon = iconMap[section.id] || LayoutDashboard

          return (
            <button
              key={section.id}
              onClick={() => onSectionChange(section.id)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2.5 cursor-pointer transition-colors duration-150 ${
                isActive
                  ? 'text-blue-500 bg-blue-500/10 font-medium'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
              }`}
            >
              <Icon size={16} />
              {section.label}
            </button>
          )
        })}
      </nav>

      {/* Footer status */}
      <div className="px-5 py-4 border-t border-zinc-800">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
          <span className="text-xs text-zinc-500">Training: Complete</span>
        </div>
      </div>
    </aside>
  )
}
