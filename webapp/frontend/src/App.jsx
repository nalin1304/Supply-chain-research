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

const sections = [
  { id: 'overview', label: 'Overview' },
  { id: 'network', label: 'Network' },
  { id: 'optimization', label: 'Optimization' },
  { id: 'resilience', label: 'Resilience' },
  { id: 'forecasting', label: 'Forecasting' },
  { id: 'advanced_rl', label: 'Advanced RL (Ph 7 & 12)' },
  { id: 'robustness', label: 'Robustness (Ph 8, 10, 11)' },
  { id: 'xai', label: 'Explainable AI (Ph 9)' },
  { id: 'morl', label: 'Dynamic MORL (Ph 13 & 14)' },
  { id: 'carbon', label: 'Carbon' },
]

export default function App() {
  const [activeSection, setActiveSection] = useState('overview')

  const renderSection = () => {
    switch (activeSection) {
      case 'overview':
        return <Dashboard />
      case 'network':
        return <NetworkMap />
      case 'optimization':
        return <ParetoChart />
      case 'resilience':
        return <ResiliencePanel />
      case 'forecasting':
        return <TrainingProgress />
      case 'advanced_rl':
        return <AdvancedRLPanel />
      case 'robustness':
        return <RobustnessPanel />
      case 'xai':
        return <XAIPanel />
      case 'morl':
        return <MORLPanel />
      case 'carbon':
        return <CarbonBudget />
      default:
        return <Dashboard />
    }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-cyber-dark text-white bg-cyber-grid">
      <div className="absolute inset-0 bg-cyber-gradient pointer-events-none z-0"></div>
      <div className="relative z-10 flex h-full w-full">
        <Sidebar
          sections={sections}
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
