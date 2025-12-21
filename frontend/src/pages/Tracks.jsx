import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { 
  Music, 
  Search, 
  Tag, 
  Trash2, 
  CheckSquare, 
  Square,
  ChevronDown,
  Filter,
  X,
  ChevronLeft,
  ChevronRight
} from 'lucide-react'
import { getTracks, deleteTrack, batchMatch, batchApplyTags, getTrackFilters, getTrackStats } from '../api'

const statusFilters = [
  { value: '', label: 'All Tracks' },
  { value: 'pending', label: 'Pending' },
  { value: 'matched', label: 'Matched' },
  { value: 'tagged', label: 'Tagged' },
  { value: 'error', label: 'Errors' },
]

const statusColors = {
  pending: 'bg-yellow-500/20 text-yellow-400',
  matched: 'bg-blue-500/20 text-blue-400',
  tagged: 'bg-green-500/20 text-green-400',
  error: 'bg-red-500/20 text-red-400',
}

const pageSizeOptions = [
  { value: 20, label: '20' },
  { value: 50, label: '50' },
  { value: 100, label: '100' },
  { value: 300, label: '300' },
  { value: 10000, label: 'All' },
]

function TrackRow({ track, selected, onSelect }) {
  return (
    <div className={`flex items-center gap-4 p-4 rounded-lg border transition-colors ${
      selected ? 'border-primary-500 bg-primary-500/10' : 'border-gray-700 hover:border-gray-600'
    }`}>
      <button
        onClick={() => onSelect(track.id)}
        className="text-gray-400 hover:text-white"
      >
        {selected ? (
          <CheckSquare className="w-5 h-5 text-primary-500" />
        ) : (
          <Square className="w-5 h-5" />
        )}
      </button>
      
      <div className="w-12 h-12 bg-gray-700 rounded flex items-center justify-center flex-shrink-0">
        {track.matched_cover_url ? (
          <img 
            src={track.matched_cover_url} 
            alt="" 
            className="w-full h-full object-cover rounded"
          />
        ) : (
          <Music className="w-6 h-6 text-gray-400" />
        )}
      </div>
      
      <Link to={`/tracks/${track.id}`} className="flex-1 min-w-0">
        <p className="font-medium truncate">
          {track.matched_title || track.title || track.filename}
        </p>
        <p className="text-sm text-gray-400 truncate">
          {track.matched_artist || track.artist || 'Unknown Artist'}
          {track.matched_genre && ` • ${track.matched_genre}`}
        </p>
      </Link>
      
      <div className="flex items-center gap-3">
        {track.match_confidence && (
          <span className="text-sm text-gray-400">
            {Math.round(track.match_confidence)}%
          </span>
        )}
        
        <span className={`px-2 py-1 rounded text-xs font-medium ${statusColors[track.status]}`}>
          {track.status}
        </span>
      </div>
    </div>
  )
}

function Tracks() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedTracks, setSelectedTracks] = useState(new Set())
  const [genreFilter, setGenreFilter] = useState('')
  const [artistFilter, setArtistFilter] = useState('')
  const [albumFilter, setAlbumFilter] = useState('')
  const [pageSize, setPageSize] = useState(50)
  const [currentPage, setCurrentPage] = useState(0)
  const queryClient = useQueryClient()

  const status = searchParams.get('status') || ''

  // Fetch filter options
  const { data: filterOptions } = useQuery({
    queryKey: ['track-filters'],
    queryFn: getTrackFilters,
    staleTime: 60000, // Cache for 1 minute
  })

  // Fetch stats for total count
  const { data: stats } = useQuery({
    queryKey: ['track-stats'],
    queryFn: getTrackStats,
    staleTime: 30000,
  })

  const { data: tracks, isLoading } = useQuery({
    queryKey: ['tracks', status, searchQuery, genreFilter, artistFilter, albumFilter, pageSize, currentPage],
    queryFn: () => getTracks({ 
      status: status || undefined, 
      search: searchQuery || undefined,
      genre: genreFilter || undefined,
      artist: artistFilter || undefined,
      album: albumFilter || undefined,
      limit: pageSize,
      skip: currentPage * pageSize
    }),
    refetchInterval: 10000,
  })

  // Reset to first page when filters change
  const handleFilterChange = (setter) => (value) => {
    setter(value)
    setCurrentPage(0)
  }

  const deleteMutation = useMutation({
    mutationFn: deleteTrack,
    onSuccess: () => {
      queryClient.invalidateQueries(['tracks'])
      queryClient.invalidateQueries(['track-stats'])
    },
  })

  const batchMatchMutation = useMutation({
    mutationFn: (ids) => batchMatch(ids.length > 0 ? Array.from(ids) : null, status || 'pending'),
    onSuccess: () => {
      setSelectedTracks(new Set())
      queryClient.invalidateQueries(['tracks'])
    },
  })

  const batchTagMutation = useMutation({
    mutationFn: (ids) => batchApplyTags(ids.length > 0 ? Array.from(ids) : null, ids.size === 0),
    onSuccess: () => {
      setSelectedTracks(new Set())
      queryClient.invalidateQueries(['tracks'])
    },
  })

  const toggleSelect = (id) => {
    setSelectedTracks((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const selectAll = () => {
    if (selectedTracks.size === tracks?.length) {
      setSelectedTracks(new Set())
    } else {
      setSelectedTracks(new Set(tracks?.map((t) => t.id) || []))
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Tracks</h1>
          <p className="text-gray-400 mt-1">
            {stats?.total || 0} total tracks
          </p>
        </div>
      </div>

      {/* Filters and Search */}
      <div className="flex flex-wrap gap-4 items-center">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search tracks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-primary-500"
          />
        </div>

        <div className="relative">
          <select
            value={status}
            onChange={(e) => setSearchParams(e.target.value ? { status: e.target.value } : {})}
            className="pl-4 pr-10 py-2 bg-gray-800 border border-gray-700 rounded-lg appearance-none focus:outline-none focus:border-primary-500"
          >
            {statusFilters.map((filter) => (
              <option key={filter.value} value={filter.value}>
                {filter.label}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>

        {/* Genre Filter */}
        <div className="relative">
          <select
            value={genreFilter}
            onChange={(e) => handleFilterChange(setGenreFilter)(e.target.value)}
            className="pl-4 pr-10 py-2 bg-gray-800 border border-gray-700 rounded-lg appearance-none focus:outline-none focus:border-primary-500 min-w-[140px]"
          >
            <option value="">All Genres</option>
            {filterOptions?.genres?.map((genre) => (
              <option key={genre} value={genre}>{genre}</option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>

        {/* Artist Filter */}
        <div className="relative">
          <select
            value={artistFilter}
            onChange={(e) => handleFilterChange(setArtistFilter)(e.target.value)}
            className="pl-4 pr-10 py-2 bg-gray-800 border border-gray-700 rounded-lg appearance-none focus:outline-none focus:border-primary-500 min-w-[160px]"
          >
            <option value="">All Artists</option>
            {filterOptions?.artists?.map((artist) => (
              <option key={artist} value={artist}>{artist}</option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>

        {/* Album Filter */}
        <div className="relative">
          <select
            value={albumFilter}
            onChange={(e) => handleFilterChange(setAlbumFilter)(e.target.value)}
            className="pl-4 pr-10 py-2 bg-gray-800 border border-gray-700 rounded-lg appearance-none focus:outline-none focus:border-primary-500 min-w-[160px]"
          >
            <option value="">All Albums</option>
            {filterOptions?.albums?.map((album) => (
              <option key={album} value={album}>{album}</option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>

        {/* Clear Filters */}
        {(genreFilter || artistFilter || albumFilter) && (
          <button
            onClick={() => {
              setGenreFilter('')
              setArtistFilter('')
              setAlbumFilter('')
              setCurrentPage(0)
            }}
            className="px-3 py-2 text-sm text-gray-400 hover:text-white flex items-center gap-1"
          >
            <X className="w-4 h-4" />
            Clear Filters
          </button>
        )}

        {/* Page Size */}
        <div className="relative ml-auto">
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value))
              setCurrentPage(0)
            }}
            className="pl-4 pr-10 py-2 bg-gray-800 border border-gray-700 rounded-lg appearance-none focus:outline-none focus:border-primary-500"
          >
            {pageSizeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label} per page
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>
      </div>

      {/* Batch Actions */}
      {selectedTracks.size > 0 && (
        <div className="bg-gray-800 rounded-lg p-4 flex items-center gap-4 border border-gray-700">
          <span className="text-sm text-gray-400">
            {selectedTracks.size} selected
          </span>
          <button
            onClick={() => batchMatchMutation.mutate(selectedTracks)}
            disabled={batchMatchMutation.isPending}
            className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm flex items-center gap-2 disabled:opacity-50"
          >
            <Search className="w-4 h-4" />
            Match Selected
          </button>
          <button
            onClick={() => batchTagMutation.mutate(selectedTracks)}
            disabled={batchTagMutation.isPending}
            className="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm flex items-center gap-2 disabled:opacity-50"
          >
            <Tag className="w-4 h-4" />
            Tag Selected
          </button>
          <button
            onClick={() => {
              if (confirm(`Delete ${selectedTracks.size} tracks?`)) {
                selectedTracks.forEach((id) => deleteMutation.mutate(id))
                setSelectedTracks(new Set())
              }
            }}
            className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm flex items-center gap-2"
          >
            <Trash2 className="w-4 h-4" />
            Delete
          </button>
        </div>
      )}

      {/* Track List */}
      <div className="space-y-2">
        {/* Header */}
        <div className="flex items-center gap-4 px-4 py-2 text-sm text-gray-400">
          <button onClick={selectAll} className="hover:text-white">
            {selectedTracks.size === tracks?.length ? (
              <CheckSquare className="w-5 h-5 text-primary-500" />
            ) : (
              <Square className="w-5 h-5" />
            )}
          </button>
          <span className="flex-1">Track</span>
          <span>Status</span>
        </div>

        {isLoading ? (
          <div className="text-center py-12 text-gray-400">Loading tracks...</div>
        ) : tracks?.length > 0 ? (
          tracks.map((track) => (
            <TrackRow
              key={track.id}
              track={track}
              selected={selectedTracks.has(track.id)}
              onSelect={toggleSelect}
            />
          ))
        ) : (
          <div className="text-center py-12 text-gray-400">
            No tracks found. Try adjusting your filters or scan your library.
          </div>
        )}
      </div>

      {/* Pagination Controls */}
      {tracks?.length > 0 && pageSize < 10000 && (
        <div className="flex items-center justify-between border-t border-gray-700 pt-4">
          <div className="text-sm text-gray-400">
            Showing {currentPage * pageSize + 1} - {Math.min((currentPage + 1) * pageSize, stats?.total || 0)} of {stats?.total || 0}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage(0)}
              disabled={currentPage === 0}
              className="px-3 py-1 bg-gray-800 border border-gray-700 rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:border-gray-600"
            >
              First
            </button>
            <button
              onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
              disabled={currentPage === 0}
              className="p-2 bg-gray-800 border border-gray-700 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:border-gray-600"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-4 py-1 text-sm">
              Page {currentPage + 1} of {Math.ceil((stats?.total || 0) / pageSize)}
            </span>
            <button
              onClick={() => setCurrentPage(p => p + 1)}
              disabled={(currentPage + 1) * pageSize >= (stats?.total || 0)}
              className="p-2 bg-gray-800 border border-gray-700 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:border-gray-600"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            <button
              onClick={() => setCurrentPage(Math.ceil((stats?.total || 0) / pageSize) - 1)}
              disabled={(currentPage + 1) * pageSize >= (stats?.total || 0)}
              className="px-3 py-1 bg-gray-800 border border-gray-700 rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:border-gray-600"
            >
              Last
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default Tracks
