import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  Music, 
  Disc3, 
  Check, 
  ChevronDown, 
  ChevronRight,
  Loader2,
  AlertCircle
} from 'lucide-react'
import { detectSeries, applySeriesAlbum } from '../api'

function SeriesCard({ series, seriesIndex, onApply, applyingIndex }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [selectedTracks, setSelectedTracks] = useState(
    series.tracks.map(t => t.track_id)
  )
  const [albumName, setAlbumName] = useState(series.suggested_album)
  const [artistName, setArtistName] = useState(series.suggested_artist)
  
  // Track if user has manually edited the inputs
  const [userEditedAlbum, setUserEditedAlbum] = useState(false)
  const [userEditedArtist, setUserEditedArtist] = useState(false)
  
  const isApplying = applyingIndex === seriesIndex
  
  // Reset selection when tracks change, but preserve user-edited values
  useEffect(() => {
    setSelectedTracks(series.tracks.map(t => t.track_id))
    // Only reset album/artist if user hasn't manually edited them
    if (!userEditedAlbum) {
      setAlbumName(series.suggested_album)
    }
    if (!userEditedArtist) {
      setArtistName(series.suggested_artist)
    }
  }, [series.tracks, series.suggested_album, series.suggested_artist])

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
          <div className="w-12 h-12 bg-gradient-to-br from-primary-500 to-purple-600 rounded-lg flex items-center justify-center">
            <Disc3 className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-semibold text-lg">{series.series_name}</h3>
            <p className="text-sm text-gray-400">
              {series.track_count} episodes found • {needsUpdate} need album update
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {needsUpdate > 0 && (
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
          {/* Album/Artist inputs */}
          <div className="grid grid-cols-2 gap-4">
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
              <label className="text-sm text-gray-400">Artist (optional)</label>
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
          <button
            onClick={(e) => {
              e.stopPropagation()
              onApply(seriesIndex, selectedTracks, albumName, artistName)
            }}
            disabled={selectedTracks.length === 0 || isApplying}
            className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg flex items-center justify-center gap-2"
          >
            {isApplying ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Check className="w-4 h-4" />
            )}
            Apply Album to {selectedTracks.length} Tracks
          </button>
        </div>
      )}
    </div>
  )
}

function Series() {
  const queryClient = useQueryClient()
  const [applyingIndex, setApplyingIndex] = useState(null)

  const { data: series, isLoading, error } = useQuery({
    queryKey: ['series'],
    queryFn: detectSeries,
  })

  const applyMutation = useMutation({
    mutationFn: ({ trackIds, album, artist }) => applySeriesAlbum(trackIds, album, artist),
    onSuccess: () => {
      setApplyingIndex(null)
      queryClient.invalidateQueries(['series'])
      queryClient.invalidateQueries(['tracks'])
    },
    onError: () => {
      setApplyingIndex(null)
    },
  })

  const handleApply = (index, trackIds, album, artist) => {
    setApplyingIndex(index)
    applyMutation.mutate({ trackIds, album, artist })
  }

  // Calculate total tracks needing attention
  const totalTracks = series?.reduce((sum, s) => sum + s.track_count, 0) || 0

  if (isLoading) {
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Series Detection</h1>
          <p className="text-gray-400 mt-1">
            Automatically detected podcast and radio show series in your library. 
            Apply consistent album names to group episodes together.
          </p>
        </div>
        {series && series.length > 0 && (
          <div className="text-right">
            <div className="text-2xl font-bold text-primary-400">{series.length}</div>
            <div className="text-sm text-gray-400">series • {totalTracks} tracks</div>
          </div>
        )}
      </div>

      {/* Info box */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
        <div className="flex gap-3">
          <Disc3 className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-blue-200">
              <strong>Tip:</strong> Setting the album tag to the series name (e.g., "A State of Trance") 
              helps music players group all episodes together. Tracks you've already tagged won't appear here again.
            </p>
          </div>
        </div>
      </div>

      {/* Series list */}
      {series && series.length > 0 ? (
        <div className="space-y-4">
          {series.map((s, index) => (
            <SeriesCard
              key={`${s.series_name}-${index}`}
              seriesIndex={index}
              series={s}
              onApply={handleApply}
              applyingIndex={applyingIndex}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-gray-400">
          <Music className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No podcast or radio show series detected in your library.</p>
          <p className="text-sm mt-2">
            Try scanning a directory with DJ sets like "A State of Trance" episodes.
          </p>
        </div>
      )}
    </div>
  )
}

export default Series
