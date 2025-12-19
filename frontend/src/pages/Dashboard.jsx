import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { 
  Music, 
  CheckCircle2, 
  Clock, 
  AlertCircle, 
  Search,
  Tag
} from 'lucide-react'
import { getTrackStats, getTracks } from '../api'

function StatCard({ icon: Icon, label, value, color, to }) {
  const content = (
    <div className={`bg-gray-800 rounded-xl p-6 border border-gray-700 hover:border-${color}-500/50 transition-colors`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-gray-400 text-sm">{label}</p>
          <p className="text-3xl font-bold mt-1">{value}</p>
        </div>
        <Icon className={`w-10 h-10 text-${color}-500 opacity-80`} />
      </div>
    </div>
  )

  if (to) {
    return <Link to={to}>{content}</Link>
  }
  return content
}

function RecentTrackRow({ track }) {
  const statusColors = {
    pending: 'text-yellow-500',
    matched: 'text-blue-500',
    tagged: 'text-green-500',
    error: 'text-red-500',
  }

  return (
    <Link 
      to={`/tracks/${track.id}`}
      className="flex items-center gap-4 p-3 rounded-lg hover:bg-gray-700/50 transition-colors"
    >
      <div className="w-12 h-12 bg-gray-700 rounded flex items-center justify-center">
        <Music className="w-6 h-6 text-gray-400" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-medium truncate">{track.title || track.filename}</p>
        <p className="text-sm text-gray-400 truncate">
          {track.artist || 'Unknown Artist'}
        </p>
      </div>
      <span className={`text-sm capitalize ${statusColors[track.status]}`}>
        {track.status}
      </span>
    </Link>
  )
}

function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['track-stats'],
    queryFn: getTrackStats,
    refetchInterval: 5000,
  })

  const { data: recentTracks, isLoading: tracksLoading } = useQuery({
    queryKey: ['recent-tracks'],
    queryFn: () => getTracks({ limit: 5 }),
    refetchInterval: 10000,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="text-gray-400 mt-1">Overview of your music library</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          icon={Music}
          label="Total Tracks"
          value={statsLoading ? '...' : stats?.total || 0}
          color="primary"
          to="/tracks"
        />
        <StatCard
          icon={Clock}
          label="Pending"
          value={statsLoading ? '...' : stats?.pending || 0}
          color="yellow"
          to="/tracks?status=pending"
        />
        <StatCard
          icon={Search}
          label="Matched"
          value={statsLoading ? '...' : stats?.matched || 0}
          color="blue"
          to="/tracks?status=matched"
        />
        <StatCard
          icon={CheckCircle2}
          label="Tagged"
          value={statsLoading ? '...' : stats?.tagged || 0}
          color="green"
          to="/tracks?status=tagged"
        />
        <StatCard
          icon={AlertCircle}
          label="Errors"
          value={statsLoading ? '...' : stats?.errors || 0}
          color="red"
          to="/tracks?status=error"
        />
      </div>

      {/* Quick Actions */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h2 className="text-xl font-semibold mb-4">Quick Actions</h2>
        <div className="flex flex-wrap gap-4">
          <Link 
            to="/scan"
            className="px-4 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg transition-colors flex items-center gap-2"
          >
            <Search className="w-4 h-4" />
            Scan Library
          </Link>
          <button 
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors flex items-center gap-2"
            onClick={() => {/* TODO: batch match */}}
          >
            <Search className="w-4 h-4" />
            Match All Pending
          </button>
          <button 
            className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg transition-colors flex items-center gap-2"
            onClick={() => {/* TODO: batch tag */}}
          >
            <Tag className="w-4 h-4" />
            Tag All Matched
          </button>
        </div>
      </div>

      {/* Recent Tracks */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">Recent Tracks</h2>
          <Link 
            to="/tracks"
            className="text-primary-500 hover:text-primary-400 text-sm"
          >
            View All
          </Link>
        </div>
        
        {tracksLoading ? (
          <div className="text-center py-8 text-gray-400">Loading...</div>
        ) : recentTracks?.length > 0 ? (
          <div className="space-y-2">
            {recentTracks.map((track) => (
              <RecentTrackRow key={track.id} track={track} />
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-400">
            No tracks yet. Start by scanning your library!
          </div>
        )}
      </div>
    </div>
  )
}

export default Dashboard
