import { useState } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import NetworkMap from './components/NetworkMap'
import ParetoChart from './components/ParetoChart'
import ResiliencePanel from './components/ResiliencePanel'
import TrainingProgress from './components/TrainingProgress'
import CarbonBudget from './components/CarbonBudget'
import AdvancedRLPanel from './components/AdvancedRLPanel'
import RobustnessPanel from './components/RobustnessPanel'
import XAIPanel from './components/XAIPanel'
import MORLPanel from './components/MORLPanel'

const sectionGroups = [
  {
    title: 'Foundations',
    sections: [
      { id: 'phase1', label: 'Phase 1: Baselines' },
      { id: 'phase2', label: 'Phase 2: Digital Twin' },
      { id: 'phase3', label: 'Phase 3: Demand Forecast' },
    ]
  },
  {
    title: 'Standard Optimization',
    sections: [
      { id: 'phase4', label: 'Phase 4: Single-Agent RL' },
      { id: 'phase5', label: 'Phase 5: Multi-Echelon' },
      { id: 'phase6', label: 'Phase 6: Carbon Emissions' },
    ]
  },
  {
    title: 'Advanced RL',
    sections: [
      { id: 'phase7', label: 'Phase 7: MAPPO & ST-GNN' },
      { id: 'phase8', label: 'Phase 8: Sim-to-Real' },
      { id: 'phase9', label: 'Phase 9: Explainable AI' },
    ]
  },
  {
    title: 'Robustness & Risk',
    sections: [
      { id: 'phase10', label: 'Phase 10: CVaR-MAPPO' },
      { id: 'phase11', label: 'Phase 11: Adversarial RL' },
      { id: 'phase12', label: 'Phase 12: Offline RL' },
    ]
  },
  {
    title: 'Dynamic Networks',
    sections: [
      { id: 'phase13', label: 'Phase 13: Dynamic Routing' },
      { id: 'phase14', label: 'Phase 14: Multi-Objective RL' },
    ]
  }
]

export default function App() {
  const [activeSection, setActiveSection] = useState('phase1')

  const renderSection = () => {
    switch (activeSection) {
      case 'phase1': return <Dashboard />
      case 'phase2': return <NetworkMap />
      case 'phase3': return <TrainingProgress />
      case 'phase4': return <ParetoChart />
      case 'phase5': return <ParetoChart /> // Will update ParetoChart to handle these
      case 'phase6': return <CarbonBudget />
      case 'phase7': return <AdvancedRLPanel />
      case 'phase8': return <ResiliencePanel />
      case 'phase9': return <XAIPanel />
      case 'phase10': return <RobustnessPanel />
      case 'phase11': return <RobustnessPanel />
      case 'phase12': return <AdvancedRLPanel />
      case 'phase13': return <NetworkMap />
      case 'phase14': return <MORLPanel />
      default: return <Dashboard />
    }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-premium-background text-premium-text bg-subtle-grid">
      <div className="absolute inset-0 bg-premium-gradient pointer-events-none z-0"></div>
      <div className="relative z-10 flex h-full w-full">
        <Sidebar
          sectionGroups={sectionGroups}
          activeSection={activeSection}
          onSectionChange={setActiveSection}
        />
        <main className="flex-1 overflow-y-auto p-8 relative scrollbar-hide">
          <div className="max-w-6xl mx-auto pb-24">
            {renderSection()}
          </div>
        </main>
      </div>
    </div>
  )
}
