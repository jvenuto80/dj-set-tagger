import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import Dashboard from './pages/Dashboard'
import Tracks from './pages/Tracks'
import TrackDetail from './pages/TrackDetail'
import Scan from './pages/Scan'
import Series from './pages/Series'
import Duplicates from './pages/Duplicates'
import LibraryScan from './pages/LibraryScan'
import Settings from './pages/Settings'
import ReviewQueue from './pages/ReviewQueue'
import NotFound from './pages/NotFound'
import { JobProvider } from './contexts/JobContext'
import { AudioProvider } from './contexts/AudioContext'

function App() {
  return (
    <ErrorBoundary>
      <JobProvider>
        <AudioProvider>
          <Layout>
            <ErrorBoundary>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/tracks" element={<Tracks />} />
                <Route path="/tracks/:id" element={<TrackDetail />} />
                <Route path="/scan" element={<Scan />} />
                <Route path="/series" element={<Series />} />
                <Route path="/duplicates" element={<Duplicates />} />
                <Route path="/library" element={<LibraryScan />} />
                <Route path="/review" element={<ReviewQueue />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </ErrorBoundary>
          </Layout>
        </AudioProvider>
      </JobProvider>
    </ErrorBoundary>
  )
}

export default App
