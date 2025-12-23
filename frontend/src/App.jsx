import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Tracks from './pages/Tracks'
import TrackDetail from './pages/TrackDetail'
import Scan from './pages/Scan'
import Series from './pages/Series'
import Settings from './pages/Settings'
import { JobProvider } from './contexts/JobContext'
import { AudioProvider } from './contexts/AudioContext'

function App() {
  return (
    <JobProvider>
      <AudioProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/tracks" element={<Tracks />} />
            <Route path="/tracks/:id" element={<TrackDetail />} />
            <Route path="/scan" element={<Scan />} />
            <Route path="/series" element={<Series />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </Layout>
      </AudioProvider>
    </JobProvider>
  )
}

export default App
