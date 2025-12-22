import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  Music, 
  Disc3, 
  Check, 
  ChevronDown, 
  ChevronRight,
  Loader2,
  AlertCircle,
  Search,
  X,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Image,
  RefreshCw
} from 'lucide-react'
import { detectSeries, getTaggedSeries, applySeriesAlbum } from '../api'
import ProgressButton from '../components/ProgressButton'
import CoverArtModal from '../components/CoverArtModal'
import { useJob } from '../contexts/JobContext'

// Toast notification component for errors
function ErrorToast({ errors, onClose, message }) {
  if (!errors || errors.length === 0) return null
  
  return (
    <div className="fixed bottom-4 right-4 max-w-lg bg-red-900/95 border border-red-700 rounded-xl shadow-2xl p-4 z-50">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-6 h-6 text-red-400 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-semibold text-red-200">{message}</h4>
            <button onClick={onClose} className="text-red-400 hover:text-red-300">
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="max-h-48 overflow-y-auto space-y-1">
            {errors.slice(0, 10).map((err, i) => (
              <div key={i} className="text-sm text-red-300 truncate">
                <span className="text-red-400">{err.filename}:</span> {err.error}
              </div>
            ))}
            {errors.length > 10 && (
              <div className="text-sm text-red-400 italic">
                ...and {errors.length - 10} more errors
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// Success toast component
function SuccessToast({ message, onClose }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 5000)
    return () => clearTimeout(timer)
  }, [onClose])
  
  return (
    <div className="fixed bottom-4 right-4 max-w-lg bg-green-900/95 border border-green-700 rounded-xl shadow-2xl p-4 z-50">
      <div className="flex items-center gap-3">
        <CheckCircle2 className="w-6 h-6 text-green-400" />
        <span className="text-green-200">{message}</span>
        <button onClick={onClose} className="text-green-400 hover:text-green-300 ml-auto">
          <X className="w-5 h-5" />
        </button>
      </div>
    </div>
  )
}

function SeriesCard({ series, seriesIndex, onApply, applyingIndex }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [selectedTracks, setSelectedTracks] = useState(
    series.tracks.map(t => t.track_id)
  )
  const [albumName, setAlbumName] = useState(series.suggested_album)
  const [artistName, setArtistName] = useState(series.suggested_artist)
  const [genreName, setGenreName] = useState(series.suggested_genre || '')
  const [albumArtistName, setAlbumArtistName] = useState(series.suggested_album_artist || '')
  const [coverUrl, setCoverUrl] = useState('')
  const [showCoverModal, setShowCoverModal] = useState(false)
  
  // Track if user has manually edited the inputs
  const [userEditedAlbum, setUserEditedAlbum] = useState(false)
  const [userEditedArtist, setUserEditedArtist] = useState(false)
  const [userEditedGenre, setUserEditedGenre] = useState(false)
  const [userEditedAlbumArtist, setUserEditedAlbumArtist] = useState(false)
  
  const isApplying = applyingIndex === seriesIndex
  
  // Reset selection when tracks change, but preserve user-edited values
  useEffect(() => {
    setSelectedTracks(series.tracks.map(t => t.track_id))
    // Only reset album/artist/genre/albumArtist if user hasn't manually edited them
    if (!userEditedAlbum) {
      setAlbumName(series.suggested_album)
    }
    if (!userEditedArtist) {
      setArtistName(series.suggested_artist)
    }
    if (!userEditedGenre) {
      setGenreName(series.suggested_genre || '')
    }
    if (!userEditedAlbumArtist) {
      setAlbumArtistName(series.suggested_album_artist || '')
    }
  }, [series.tracks, series.suggested_album, series.suggested_artist, series.suggested_genre, series.suggested_album_artist])

  const toggleTrack = (trackId) => {
    setSelectedTracks(prev => 
      prev.includes(trackId) 
        ? prev.filter(id => id !== trackId)
        : [...prev, trackId]
    )
  }

  const selectAll = () => {
    setSelectedTracks(series.tracks.map(t => t.track_id))
  }

  const selectNone = () => {
    setSelectedTracks([])
  }

  const needsUpdate = series.tracks.filter(t => 
    t.current_album !== albumName && t.matched_album !== albumName
  ).length

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      {/* Header */}
      <div 
        className="p-4 cursor-pointer hover:bg-gray-750 flex items-center justify-between"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-4">
          <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${
            series.is_orphan 
              ? 'bg-gradient-to-br from-yellow-500 to-orange-600' 
              : 'bg-gradient-to-br from-primary-500 to-purple-600'
          }`}>
            <Disc3 className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-semibold text-lg">
              {series.series_name}
              {series.is_orphan && (
                <span className="ml-2 text-xs font-normal text-yellow-400">
                  → Add to existing series
                </span>
              )}
            </h3>
            <p className="text-sm text-gray-400">
              {series.track_count} {series.track_count === 1 ? 'episode' : 'episodes'} found
              {series.matched_series && ` • Matches "${series.matched_series}"`}
              {!series.is_orphan && ` • ${needsUpdate} need album update`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {series.is_orphan && (
            <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 text-xs rounded-full">
              New episode
            </span>
          )}
          {!series.is_orphan && needsUpdate > 0 && (
            <span className="px-2 py-1 bg-yellow-500/20 text-yellow-400 text-xs rounded-full">
              {needsUpdate} to update
            </span>
          )}
          {isExpanded ? (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronRight className="w-5 h-5 text-gray-400" />
          )}
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="border-t border-gray-700 p-4 space-y-4">
          {/* Album/Artist/Genre/Album Artist inputs */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="text-sm text-gray-400">Album Name</label>
              <input
                type="text"
                value={albumName}
                onChange={(e) => {
                  setAlbumName(e.target.value)
                  setUserEditedAlbum(true)
                }}
                className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
              />
            </div>
            <div>
              <label className="text-sm text-gray-400">Artist</label>
              <input
                type="text"
                value={artistName}
                onChange={(e) => {
                  setArtistName(e.target.value)
                  setUserEditedArtist(true)
                }}
                className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
              />
            </div>
            <div>
              <label className="text-sm text-gray-400">Album Artist</label>
              <input
                type="text"
                value={albumArtistName}
                onChange={(e) => {
                  setAlbumArtistName(e.target.value)
                  setUserEditedAlbumArtist(true)
                }}
                placeholder="e.g. Various Artists"
                className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
              />
            </div>
            <div>
              <label className="text-sm text-gray-400">Genre</label>
              <input
                type="text"
                value={genreName}
                onChange={(e) => {
                  setGenreName(e.target.value)
                  setUserEditedGenre(true)
                }}
                placeholder="e.g. Progressive House"
                className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
              />
            </div>
          </div>

          {/* Cover Art */}
          <div className="flex items-center gap-4">
            <button
              onClick={() => setShowCoverModal(true)}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg flex items-center gap-2"
            >
              <Image className="w-4 h-4" />
              {coverUrl ? 'Change Cover' : 'Add Cover Art'}
            </button>
            {coverUrl && (
              <div className="flex items-center gap-3">
                <img
                  src={coverUrl}
                  alt="Selected cover"
                  className="w-10 h-10 rounded object-cover"
                />
                <button
                  onClick={() => setCoverUrl('')}
                  className="text-sm text-red-400 hover:text-red-300"
                >
                  Remove
                </button>
              </div>
            )}
          </div>

          {/* Selection controls */}
          <div className="flex items-center justify-between">
            <div className="flex gap-2">
              <button
                onClick={selectAll}
                className="text-sm text-primary-400 hover:text-primary-300"
              >
                Select All
              </button>
              <span className="text-gray-600">|</span>
              <button
                onClick={selectNone}
                className="text-sm text-primary-400 hover:text-primary-300"
              >
                Select None
              </button>
            </div>
            <span className="text-sm text-gray-400">
              {selectedTracks.length} selected
            </span>
          </div>

          {/* Track list */}
          <div className="max-h-64 overflow-y-auto space-y-1">
            {series.tracks.map((track) => (
              <div
                key={track.track_id}
                onClick={() => toggleTrack(track.track_id)}
                className={`p-2 rounded-lg cursor-pointer flex items-center gap-3 ${
                  selectedTracks.includes(track.track_id)
                    ? 'bg-primary-500/20 border border-primary-500/50'
                    : 'hover:bg-gray-700'
                }`}
              >
                <div className={`w-5 h-5 rounded border flex items-center justify-center ${
                  selectedTracks.includes(track.track_id)
                    ? 'bg-primary-500 border-primary-500'
                    : 'border-gray-600'
                }`}>
                  {selectedTracks.includes(track.track_id) && (
                    <Check className="w-3 h-3" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{track.filename}</p>
                  <p className="text-xs text-gray-500">
                    Current album: {track.current_album || track.matched_album || 'None'}
                    {track.episode && ` • Episode ${track.episode}`}
                  </p>
                </div>
                {(track.current_album === albumName || track.matched_album === albumName) && (
                  <span className="text-xs text-green-400">✓ Already set</span>
                )}
              </div>
            ))}
          </div>

          {/* Apply button */}
          <ProgressButton
            onClick={(e) => {
              e.stopPropagation()
              onApply(seriesIndex, selectedTracks, albumName, artistName, genreName, albumArtistName, coverUrl)
            }}
            disabled={selectedTracks.length === 0}
            isLoading={isApplying}
            loadingText={`Applying to ${selectedTracks.length} tracks...`}
            icon={<Check className="w-4 h-4" />}
            variant="success"
            className="w-full"
          >
            Apply Album to {selectedTracks.length} Tracks{coverUrl ? ' + Cover' : ''}
          </ProgressButton>
        </div>
      )}

      {/* Cover Art Modal */}
      <CoverArtModal
        isOpen={showCoverModal}
        onClose={() => setShowCoverModal(false)}
        onSelect={(url) => setCoverUrl(url)}
        defaultQuery={`${artistName || ''} ${albumName || ''}`.trim()}
      />
    </div>
  )
}

function TaggedSeriesCard({ series, onApply, applyingIndex, seriesIndex }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [selectedTracks, setSelectedTracks] = useState(
    series.tracks.map(t => t.track_id)
  )
  const [albumName, setAlbumName] = useState(series.suggested_album)
  const [artistName, setArtistName] = useState(series.suggested_artist || '')
  const [genreName, setGenreName] = useState(series.suggested_genre || '')
  const [albumArtistName, setAlbumArtistName] = useState(series.suggested_album_artist || '')
  const [coverUrl, setCoverUrl] = useState('')
  const [showCoverModal, setShowCoverModal] = useState(false)
  
  const isApplying = applyingIndex === seriesIndex

  const toggleTrack = (trackId) => {
    setSelectedTracks(prev => 
      prev.includes(trackId) 
        ? prev.filter(id => id !== trackId)
        : [...prev, trackId]
    )
  }

  const selectAll = () => {
    setSelectedTracks(series.tracks.map(t => t.track_id))
  }

  const selectNone = () => {
    setSelectedTracks([])
  }

  return (
    <div className="bg-gray-800/50 rounded-xl border border-gray-700/50 overflow-hidden">
      {/* Header */}
      <div 
        className="p-4 cursor-pointer hover:bg-gray-750 flex items-center justify-between"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-4">
          {series.cover_url ? (
            <img 
              src={series.cover_url} 
              alt={series.series_name}
              className="w-12 h-12 rounded-lg object-cover"
              onError={(e) => {
                e.target.style.display = 'none'
                e.target.nextSibling.style.display = 'flex'
              }}
            />
          ) : null}
          <div 
            className={`w-12 h-12 bg-gradient-to-br from-green-500 to-emerald-600 rounded-lg items-center justify-center ${series.cover_url ? 'hidden' : 'flex'}`}
          >
            <CheckCircle2 className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-semibold text-lg">{series.series_name}</h3>
            <p className="text-sm text-gray-400">
              {series.track_count} episodes • {series.suggested_artist || 'Various'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-2 py-1 bg-green-500/20 text-green-400 text-xs rounded-full">
            Tagged
          </span>
          {isExpanded ? (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronRight className="w-5 h-5 text-gray-400" />
          )}
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="border-t border-gray-700 p-4 space-y-4">
          {/* Edit toggle */}
          <div className="flex items-center justify-between">
            <button
              onClick={(e) => {
                e.stopPropagation()
                setIsEditing(!isEditing)
              }}
              className="text-sm text-primary-400 hover:text-primary-300"
            >
              {isEditing ? 'Cancel Edit' : 'Edit & Re-tag'}
            </button>
            {isEditing && (
              <div className="flex gap-2">
                <button
                  onClick={selectAll}
                  className="text-sm text-primary-400 hover:text-primary-300"
                >
                  Select All
                </button>
                <span className="text-gray-600">|</span>
                <button
                  onClick={selectNone}
                  className="text-sm text-primary-400 hover:text-primary-300"
                >
                  Select None
                </button>
                <span className="text-sm text-gray-400 ml-2">
                  {selectedTracks.length} selected
                </span>
              </div>
            )}
          </div>

          {/* Album/Artist/Album Artist/Genre inputs (only when editing) */}
          {isEditing && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="text-sm text-gray-400">Album Name</label>
                <input
                  type="text"
                  value={albumName}
                  onChange={(e) => setAlbumName(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                />
              </div>
              <div>
                <label className="text-sm text-gray-400">Artist</label>
                <input
                  type="text"
                  value={artistName}
                  onChange={(e) => setArtistName(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                />
              </div>
              <div>
                <label className="text-sm text-gray-400">Album Artist</label>
                <input
                  type="text"
                  value={albumArtistName}
                  onChange={(e) => setAlbumArtistName(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  placeholder="e.g. Various Artists"
                  className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                />
              </div>
              <div>
                <label className="text-sm text-gray-400">Genre</label>
                <input
                  type="text"
                  value={genreName}
                  onChange={(e) => setGenreName(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  placeholder="e.g. Progressive House"
                  className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                />
              </div>
            </div>
          )}

          {/* Cover Art (only when editing) */}
          {isEditing && (
            <div className="flex items-center gap-4">
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setShowCoverModal(true)
                }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg flex items-center gap-2"
              >
                <Image className="w-4 h-4" />
                {coverUrl ? 'Change Cover' : 'Add Cover Art'}
              </button>
              {coverUrl && (
                <div className="flex items-center gap-3">
                  <img
                    src={coverUrl}
                    alt="Selected cover"
                    className="w-10 h-10 rounded object-cover"
                  />
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setCoverUrl('')
                    }}
                    className="text-sm text-red-400 hover:text-red-300"
                  >
                    Remove
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Track list */}
          <div className="max-h-48 overflow-y-auto space-y-1">
            {series.tracks.map((track) => (
              <div
                key={track.track_id}
                onClick={(e) => {
                  if (isEditing) {
                    e.stopPropagation()
                    toggleTrack(track.track_id)
                  }
                }}
                className={`p-2 rounded-lg flex items-center gap-3 ${
                  isEditing 
                    ? selectedTracks.includes(track.track_id)
                      ? 'bg-primary-500/20 border border-primary-500/50 cursor-pointer'
                      : 'bg-gray-700/30 cursor-pointer hover:bg-gray-700/50'
                    : 'bg-gray-700/30'
                }`}
              >
                {isEditing ? (
                  <div className={`w-5 h-5 rounded border flex items-center justify-center ${
                    selectedTracks.includes(track.track_id)
                      ? 'bg-primary-500 border-primary-500'
                      : 'border-gray-600'
                  }`}>
                    {selectedTracks.includes(track.track_id) && (
                      <Check className="w-3 h-3" />
                    )}
                  </div>
                ) : (
                  <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{track.filename}</p>
                  <p className="text-xs text-gray-500">
                    Album: {track.matched_album || track.current_album || 'None'}
                    {track.episode && ` • Episode ${track.episode}`}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Apply button (only when editing) */}
          {isEditing && (
            <ProgressButton
              onClick={(e) => {
                e.stopPropagation()
                onApply(seriesIndex, selectedTracks, albumName, artistName, genreName, albumArtistName, coverUrl)
              }}
              disabled={selectedTracks.length === 0}
              isLoading={isApplying}
              loadingText={`Re-tagging ${selectedTracks.length} tracks...`}
              icon={<Check className="w-4 h-4" />}
              variant="primary"
              className="w-full"
            >
              Re-tag {selectedTracks.length} Tracks{coverUrl ? ' + Cover' : ''}
            </ProgressButton>
          )}
        </div>
      )}

      {/* Cover Art Modal */}
      <CoverArtModal
        isOpen={showCoverModal}
        onClose={() => setShowCoverModal(false)}
        onSelect={(url) => setCoverUrl(url)}
        defaultQuery={`${artistName || ''} ${albumName || ''}`.trim()}
      />
    </div>
  )
}

function Series() {
  const queryClient = useQueryClient()
  const { backgroundJob, toast: jobToast, clearToast: clearJobToast, startPolling } = useJob()
  const [applyingIndex, setApplyingIndex] = useState(null)
  const [includeTagged, setIncludeTagged] = useState(false)
  const [isReEvaluating, setIsReEvaluating] = useState(false)
  const [applyingTaggedIndex, setApplyingTaggedIndex] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [activeTab, setActiveTab] = useState('untagged') // 'untagged' or 'tagged'
  const [localToast, setLocalToast] = useState(null)

  // Combine job toast with local toast
  const toast = jobToast || localToast
  const clearToast = jobToast ? clearJobToast : () => setLocalToast(null)

  // Clear applying state when job completes
  useEffect(() => {
    if (backgroundJob?.status === 'completed' || backgroundJob?.status === 'not_found' || !backgroundJob) {
      setApplyingIndex(null)
      setApplyingTaggedIndex(null)
    }
  }, [backgroundJob])

  const { data: series, isLoading, error } = useQuery({
    queryKey: ['series'],
    queryFn: () => detectSeries(false),
  })

  const { data: taggedSeries, isLoading: isLoadingTagged } = useQuery({
    queryKey: ['taggedSeries'],
    queryFn: getTaggedSeries,
  })

  const applyMutation = useMutation({
    mutationFn: ({ trackIds, album, artist, genre, albumArtist, coverUrl }) => applySeriesAlbum(trackIds, album, artist, genre, albumArtist, coverUrl),
    onSuccess: (data) => {
      // Check if this is a background job
      if (data.background && data.job_id) {
        // Start polling via context (handles localStorage)
        startPolling(data.job_id)
        return // Don't clear applying state yet
      }
      
      // Synchronous completion
      setApplyingIndex(null)
      setApplyingTaggedIndex(null)
      queryClient.invalidateQueries(['series'])
      queryClient.invalidateQueries(['taggedSeries'])
      queryClient.invalidateQueries(['tracks'])
      
      // Check if there were errors writing to files
      if (data.errors && data.errors.length > 0) {
        setLocalToast({
          type: 'error',
          message: `${data.written}/${data.total_files} files written. ${data.errors.length} errors:`,
          errors: data.errors
        })
      } else {
        setLocalToast({
          type: 'success',
          message: data.message || `Successfully updated ${data.updated} tracks`
        })
      }
    },
    onError: (error) => {
      setApplyingIndex(null)
      setApplyingTaggedIndex(null)
      setLocalToast({
        type: 'error',
        message: 'Failed to apply changes',
        errors: [{ filename: 'API Error', error: error.message || 'Unknown error' }]
      })
    },
  })

  const handleApply = (index, trackIds, album, artist, genre, albumArtist, coverUrl) => {
    setApplyingIndex(index)
    applyMutation.mutate({ trackIds, album, artist, genre, albumArtist, coverUrl })
  }

  const handleApplyTagged = (index, trackIds, album, artist, genre, albumArtist, coverUrl) => {
    setApplyingTaggedIndex(index)
    applyMutation.mutate({ trackIds, album, artist, genre, albumArtist, coverUrl })
  }

  // Filter series based on search query
  const filteredSeries = useMemo(() => {
    if (!series) return []
    if (!searchQuery.trim()) return series
    
    const query = searchQuery.toLowerCase()
    return series.filter(s => {
      if (s.series_name?.toLowerCase().includes(query)) return true
      if (s.suggested_album?.toLowerCase().includes(query)) return true
      if (s.suggested_artist?.toLowerCase().includes(query)) return true
      if (s.tracks?.some(t => t.filename?.toLowerCase().includes(query))) return true
      return false
    })
  }, [series, searchQuery])

  // Filter tagged series based on search query
  const filteredTaggedSeries = useMemo(() => {
    if (!taggedSeries) return []
    if (!searchQuery.trim()) return taggedSeries
    
    const query = searchQuery.toLowerCase()
    return taggedSeries.filter(s => {
      if (s.series_name?.toLowerCase().includes(query)) return true
      if (s.suggested_artist?.toLowerCase().includes(query)) return true
      if (s.tracks?.some(t => t.filename?.toLowerCase().includes(query))) return true
      return false
    })
  }, [taggedSeries, searchQuery])

  // Calculate totals
  const totalTracks = series?.reduce((sum, s) => sum + s.track_count, 0) || 0
  const totalTaggedTracks = taggedSeries?.reduce((sum, s) => sum + s.track_count, 0) || 0

  if (isLoading && isLoadingTagged) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400">
        <AlertCircle className="w-6 h-6 mr-2" />
        Error loading series: {error.message}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Series Detection</h1>
          <p className="text-gray-400 mt-1">
            Automatically detected podcast and radio show series in your library. 
            Apply consistent album names to group episodes together.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={includeTagged}
              onChange={(e) => setIncludeTagged(e.target.checked)}
              className="rounded border-gray-600 bg-gray-700 text-primary-500 focus:ring-primary-500"
            />
            Include tagged
          </label>
          <button
            onClick={async () => {
              setIsReEvaluating(true)
              try {
                // Fetch fresh data with the include_tagged param
                const freshData = await detectSeries(includeTagged)
                queryClient.setQueryData(['series'], freshData)
                queryClient.invalidateQueries(['taggedSeries'])
              } finally {
                setIsReEvaluating(false)
              }
            }}
            disabled={isLoading || isLoadingTagged || isReEvaluating}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-500 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg transition-colors"
            title="Re-evaluate series detection"
          >
            <RefreshCw className={`w-4 h-4 ${(isLoading || isLoadingTagged || isReEvaluating) ? 'animate-spin' : ''}`} />
            <span>Re-evaluate</span>
          </button>
        </div>
      </div>

      {/* Background Job Progress */}
      {backgroundJob && (
        <div className="bg-primary-900/30 border border-primary-700/50 rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-3">
              <Loader2 className="w-5 h-5 animate-spin text-primary-400" />
              <span className="font-medium">
                {backgroundJob.status === 'starting' && 'Starting...'}
                {backgroundJob.status === 'resuming' && 'Resuming...'}
                {backgroundJob.status === 'downloading_cover' && 'Downloading cover art...'}
                {backgroundJob.status === 'loading_tracks' && 'Loading tracks...'}
                {backgroundJob.status === 'tagging' && 'Tagging files...'}
                {backgroundJob.status === 'updating_database' && 'Updating database...'}
                {backgroundJob.status === 'completed' && 'Complete!'}
                {!['starting', 'resuming', 'downloading_cover', 'loading_tracks', 'tagging', 'updating_database', 'completed'].includes(backgroundJob.status) && 
                  `Processing... (${backgroundJob.status || 'unknown'})`}
              </span>
            </div>
            <span className="text-sm text-gray-400">
              {backgroundJob.processed || 0}/{backgroundJob.total || 0} files
            </span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
            <div 
              className="bg-primary-500 h-2 transition-all duration-300 ease-out"
              style={{ width: `${backgroundJob.total > 0 ? (backgroundJob.processed / backgroundJob.total) * 100 : 0}%` }}
            />
          </div>
          {backgroundJob.written > 0 && (
            <div className="mt-2 text-sm text-gray-400">
              {backgroundJob.written} files written successfully
              {backgroundJob.errors?.length > 0 && `, ${backgroundJob.errors.length} errors`}
            </div>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-gray-700">
        <button
          onClick={() => setActiveTab('untagged')}
          className={`px-4 py-3 font-medium text-sm border-b-2 transition-colors ${
            activeTab === 'untagged'
              ? 'border-primary-500 text-primary-400'
              : 'border-transparent text-gray-400 hover:text-gray-300'
          }`}
        >
          <div className="flex items-center gap-2">
            <Disc3 className="w-4 h-4" />
            <span>To Tag</span>
            {series && series.length > 0 && (
              <span className={`px-2 py-0.5 rounded-full text-xs ${
                activeTab === 'untagged' 
                  ? 'bg-primary-500/20 text-primary-400' 
                  : 'bg-gray-700 text-gray-400'
              }`}>
                {series.length}
              </span>
            )}
          </div>
        </button>
        <button
          onClick={() => setActiveTab('tagged')}
          className={`px-4 py-3 font-medium text-sm border-b-2 transition-colors ${
            activeTab === 'tagged'
              ? 'border-green-500 text-green-400'
              : 'border-transparent text-gray-400 hover:text-gray-300'
          }`}
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            <span>Already Tagged</span>
            {taggedSeries && taggedSeries.length > 0 && (
              <span className={`px-2 py-0.5 rounded-full text-xs ${
                activeTab === 'tagged' 
                  ? 'bg-green-500/20 text-green-400' 
                  : 'bg-gray-700 text-gray-400'
              }`}>
                {taggedSeries.length}
              </span>
            )}
          </div>
        </button>
      </div>

      {/* Search Bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
        <input
          type="text"
          placeholder={`Search ${activeTab === 'untagged' ? 'untagged' : 'tagged'} series by name, artist, or track filename...`}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full pl-10 pr-10 py-3 bg-gray-800 border border-gray-700 rounded-xl focus:outline-none focus:border-primary-500 placeholder-gray-500"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="absolute right-3 top-1/2 transform -translate-y-1/2 p-1 hover:bg-gray-700 rounded-full"
          >
            <X className="w-4 h-4 text-gray-400" />
          </button>
        )}
      </div>

      {/* Tab Content */}
      {activeTab === 'untagged' ? (
        <>
          {/* Info box */}
          <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
            <div className="flex gap-3">
              <Disc3 className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-blue-200">
                  <strong>Tip:</strong> Setting the album tag to the series name (e.g., "A State of Trance") 
                  helps music players group all episodes together.
                </p>
              </div>
            </div>
          </div>

          {/* Stats */}
          {series && series.length > 0 && (
            <div className="text-sm text-gray-400">
              {searchQuery 
                ? `Found ${filteredSeries.length} series matching "${searchQuery}"`
                : `${series.length} series detected • ${totalTracks} tracks`
              }
            </div>
          )}

          {/* Untagged Series list */}
          {filteredSeries.length > 0 ? (
            <div className="space-y-4">
              {filteredSeries.map((s, index) => (
                <SeriesCard
                  key={`${s.series_name}-${index}`}
                  seriesIndex={index}
                  series={s}
                  onApply={handleApply}
                  applyingIndex={applyingIndex}
                />
              ))}
            </div>
          ) : searchQuery ? (
            <div className="text-center py-12 text-gray-400">
              <Search className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No untagged series found matching "{searchQuery}"</p>
              <button
                onClick={() => setSearchQuery('')}
                className="mt-2 text-primary-400 hover:text-primary-300 text-sm"
              >
                Clear search
              </button>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-400">
              <CheckCircle2 className="w-12 h-12 mx-auto mb-4 opacity-50 text-green-500" />
              <p>All series have been tagged!</p>
              <p className="text-sm mt-2">
                Check the "Already Tagged" tab to see your tagged series.
              </p>
            </div>
          )}
        </>
      ) : (
        <>
          {/* Stats */}
          {taggedSeries && taggedSeries.length > 0 && (
            <div className="text-sm text-gray-400">
              {searchQuery 
                ? `Found ${filteredTaggedSeries.length} series matching "${searchQuery}"`
                : `${taggedSeries.length} series tagged • ${totalTaggedTracks} tracks`
              }
            </div>
          )}

          {/* Tagged Series list */}
          {isLoadingTagged ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : filteredTaggedSeries.length > 0 ? (
            <div className="space-y-3">
              {filteredTaggedSeries.map((s, index) => (
                <TaggedSeriesCard
                  key={`tagged-${s.series_name}-${index}`}
                  series={s}
                  seriesIndex={index}
                  onApply={handleApplyTagged}
                  applyingIndex={applyingTaggedIndex}
                />
              ))}
            </div>
          ) : searchQuery ? (
            <div className="text-center py-12 text-gray-400">
              <Search className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No tagged series found matching "{searchQuery}"</p>
              <button
                onClick={() => setSearchQuery('')}
                className="mt-2 text-primary-400 hover:text-primary-300 text-sm"
              >
                Clear search
              </button>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-400">
              <Music className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No tagged series yet.</p>
              <p className="text-sm mt-2">
                Tag series from the "To Tag" tab to see them here.
              </p>
            </div>
          )}
        </>
      )}
      
      {/* Toast notifications */}
      {toast?.type === 'error' && (
        <ErrorToast 
          errors={toast.errors} 
          message={toast.message}
          onClose={() => setToast(null)} 
        />
      )}
      {toast?.type === 'success' && (
        <SuccessToast 
          message={toast.message} 
          onClose={() => setToast(null)} 
        />
      )}
    </div>
  )
}

export default Series
