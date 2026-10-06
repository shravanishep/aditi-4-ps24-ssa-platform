import { BrowserRouter, Routes, Route } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import DashboardPage from './pages/DashboardPage'
import SatelliteExplorerPage from './pages/SatelliteExplorerPage'
import ConjunctionAnalysisPage from './pages/ConjunctionAnalysisPage'
import GlobePage from './pages/GlobePage'

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/satellites" element={<SatelliteExplorerPage />} />
          <Route path="/conjunction" element={<ConjunctionAnalysisPage />} />
          <Route path="/globe" element={<GlobePage />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  )
}
