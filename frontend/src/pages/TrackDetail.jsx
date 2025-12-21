import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  Music, 
  ArrowLeft, 
  Search, 
  Tag, 
  Edit3, 
  Check, 
  X,
  ExternalLink,
  Clock,
  HardDrive,
  FileAudio,
  Loader2,
  Image,
  RefreshCw
} from 'lucide-react'
import { 
  getTrack, 
  updateTrack, 
  matchTrack, 
  getMatchResults, 
  selectMatch,
  applyTags,
  renameTrack,
  searchCoverArt,
  updateTrackCover
} from '../api'
import ProgressButton from '../components/ProgressButton'

function formatDuration(seconds) {
  if (!seconds) return '--:--'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function formatFileSize(bytes) {
  if (!bytes) return '--'
  const mb = bytes / (1024 * 1024)
  return `${mb.toFixed(1)} MB`
}

function MatchCard({ match, isSelected, onSelect }) {
  return (
    <div 
      onClick={onSelect}
      className={`p-4 rounded-lg border cursor-pointer transition-colors ${
        isSelected 
          ? 'border-primary-500 bg-primary-500/10' 
          : 'border-gray-700 hover:border-gray-600'
      }`}
    >
      <div className="flex items-start gap-4">
        <div className="w-16 h-16 bg-gray-700 rounded flex-shrink-0 overflow-hidden">
          {match.cover_url ? (
            <img src={match.cover_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <Music className="w-8 h-8 text-gray-500" />
            </div>
          )}
        </div>
        
        <div className="flex-1 min-w-0">
          <p className="font-medium truncate">{match.title}</p>
          <p className="text-sm text-gray-400 truncate">
            {match.artist || match.dj || 'Unknown Artist'}
          </p>
          {match.genre && (
            <p className="text-sm text-gray-500">{match.genre}</p>
          )}
          {match.event && (
            <p className="text-sm text-gray-500">{match.event}</p>
          )}
        </div>
        
        <div className="text-right">
          <div className={`text-lg font-bold ${
            match.confidence >= 85 ? 'text-green-500' :
            match.confidence >= 70 ? 'text-yellow-500' : 'text-gray-400'
          }`}>
            {Math.round(match.confidence)}%
          </div>
          <span className="text-xs text-gray-500">{match.match_type}</span>
        </div>
      </div>
      
      {match.tracklist_url && (
        <a 
          href={match.tracklist_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="mt-2 text-xs text-primary-400 hover:text-primary-300 flex items-center gap-1"
        >
          View on 1001Tracklists <ExternalLink className="w-3 h-3" />
        </a>
      )}
    </div>
  )
}

function TrackDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [isEditing, setIsEditing] = useState(false)
  const [editForm, setEditForm] = useState({})
  const [showCoverOptions, setShowCoverOptions] = useState(false)
  const [coverOptions, setCoverOptions] = useState([])
  const [isLoadingCovers, setIsLoadingCovers] = useState(false)
  const [isSearching, setIsSearching] = useState(false)

  const { data: track, isLoading } = useQuery({
    queryKey: ['track', id],
    queryFn: () => getTrack(id),
  })

  const { data: matches } = useQuery({
    queryKey: ['matches', id],
    queryFn: () => getMatchResults(id),
    enabled: !!track,
    // Poll more frequently while searching
    refetchInterval: isSearching ? 1000 : false,
  })

  const updateMutation = useMutation({
    mutationFn: (updates) => updateTrack(id, updates),
    onSuccess: () => {
      queryClient.invalidateQueries(['track', id])
      setIsEditing(false)
    },
  })

  const matchMutation = useMutation({
    mutationFn: () => matchTrack(id),
    onMutate: () => {
      setIsSearching(true)
      // Auto-stop searching after 30 seconds as fallback
      setTimeout(() => setIsSearching(false), 30000)
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['track', id])
      queryClient.invalidateQueries(['matches', id])
      // Keep searching state for a bit to catch the results
      setTimeout(() => setIsSearching(false), 3000)
    },
    onError: () => {
      setIsSearching(false)
    },
  })

  const selectMatchMutation = useMutation({
    mutationFn: (matchId) => selectMatch(id, matchId),
    onSuccess: () => {
      queryClient.invalidateQueries(['track', id])
    },
  })

  const tagMutation = useMutation({
    mutationFn: () => applyTags(id),
    onSuccess: () => {
      queryClient.invalidateQueries(['track', id])
      queryClient.invalidateQueries(['track-stats'])
    },
  })

  const coverMutation = useMutation({
    mutationFn: (coverUrl) => updateTrackCover(id, coverUrl),
    onSuccess: () => {
      queryClient.invalidateQueries(['track', id])
      setShowCoverOptions(false)
    },
  })

  const loadCoverOptions = async () => {
    setIsLoadingCovers(true)
    setShowCoverOptions(true)
    try {
      // Collect cover URLs from matches
      const matchCovers = (matches || [])
        .filter(m => m.cover_url)
        .map(m => ({
          url: m.cover_url,
          source: m.source || 'Match Result',
          title: m.title
        }))
      
      // Search for additional cover art
      const searchQuery = `${track.artist || ''} ${track.title || track.filename}`.trim()
      const searchResults = await searchCoverArt(id, searchQuery)
      
      // Combine and dedupe by URL
      const allCovers = [...matchCovers, ...(searchResults || [])]
      const uniqueCovers = allCovers.filter((cover, index, self) => 
        index === self.findIndex(c => c.url === cover.url)
      )
      
      setCoverOptions(uniqueCovers)
    } catch (error) {
      console.error('Error loading cover options:', error)
      // Still show match covers even if search fails
      const matchCovers = (matches || [])
        .filter(m => m.cover_url)
        .map(m => ({
          url: m.cover_url,
          source: m.source || 'Match Result',
          title: m.title
        }))
      setCoverOptions(matchCovers)
    } finally {
      setIsLoadingCovers(false)
    }
  }

  const startEditing = () => {
    setEditForm({
      title: track.matched_title || track.title || '',
      artist: track.matched_artist || track.artist || '',
      album: track.matched_album || track.album || '',
      albumArtist: track.matched_album_artist || track.album_artist || '',
      genre: track.matched_genre || track.genre || '',
      year: track.matched_year || track.year || '',
    })
    setIsEditing(true)
  }

  const saveEdits = () => {
    updateMutation.mutate({
      matched_title: editForm.title,
      matched_artist: editForm.artist,
      matched_album: editForm.album,
      matched_album_artist: editForm.albumArtist,
      matched_genre: editForm.genre,
      matched_year: editForm.year,
      status: 'matched',
    })
  }

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">Loading...</div>
  }

  if (!track) {
    return <div className="text-center py-12 text-gray-400">Track not found</div>
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button 
          onClick={() => navigate(-1)}
          className="p-2 hover:bg-gray-800 rounded-lg"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold">{track.title || track.filename}</h1>
          <p className="text-gray-400">{track.artist || 'Unknown Artist'}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Info */}
        <div className="lg:col-span-2 space-y-6">
          {/* Current / Matched Metadata */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Metadata</h2>
              {!isEditing ? (
                <button
                  onClick={startEditing}
                  className="p-2 hover:bg-gray-700 rounded-lg"
                >
                  <Edit3 className="w-4 h-4" />
                </button>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={saveEdits}
                    disabled={updateMutation.isPending}
                    className="p-2 hover:bg-green-600/20 text-green-500 rounded-lg"
                  >
                    <Check className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setIsEditing(false)}
                    className="p-2 hover:bg-red-600/20 text-red-500 rounded-lg"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm text-gray-400">Title</label>
                {isEditing ? (
                  <input
                    type="text"
                    value={editForm.title}
                    onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                    className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                  />
                ) : (
                  <p className="mt-1 font-medium">
                    {track.matched_title || track.title || '-'}
                  </p>
                )}
              </div>
              
              <div>
                <label className="text-sm text-gray-400">Artist</label>
                {isEditing ? (
                  <input
                    type="text"
                    value={editForm.artist}
                    onChange={(e) => setEditForm({ ...editForm, artist: e.target.value })}
                    className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                  />
                ) : (
                  <p className="mt-1 font-medium">
                    {track.matched_artist || track.artist || '-'}
                  </p>
                )}
              </div>
              
              <div>
                <label className="text-sm text-gray-400">Album</label>
                {isEditing ? (
                  <input
                    type="text"
                    value={editForm.album}
                    onChange={(e) => setEditForm({ ...editForm, album: e.target.value })}
                    className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                  />
                ) : (
                  <p className="mt-1 font-medium">
                    {track.matched_album || track.album || '-'}
                  </p>
                )}
              </div>
              
              <div>
                <label className="text-sm text-gray-400">Album Artist</label>
                {isEditing ? (
                  <input
                    type="text"
                    value={editForm.albumArtist}
                    onChange={(e) => setEditForm({ ...editForm, albumArtist: e.target.value })}
                    className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                  />
                ) : (
                  <p className="mt-1 font-medium">
                    {track.matched_album_artist || track.album_artist || '-'}
                  </p>
                )}
              </div>
              
              <div>
                <label className="text-sm text-gray-400">Genre</label>
                {isEditing ? (
                  <input
                    type="text"
                    value={editForm.genre}
                    onChange={(e) => setEditForm({ ...editForm, genre: e.target.value })}
                    className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                  />
                ) : (
                  <p className="mt-1 font-medium">
                    {track.matched_genre || track.genre || '-'}
                  </p>
                )}
              </div>
              
              <div>
                <label className="text-sm text-gray-400">Year</label>
                {isEditing ? (
                  <input
                    type="text"
                    value={editForm.year}
                    onChange={(e) => setEditForm({ ...editForm, year: e.target.value })}
                    className="w-full mt-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                  />
                ) : (
                  <p className="mt-1 font-medium">
                    {track.matched_year || track.year || '-'}
                  </p>
                )}
              </div>
              
              <div>
                <label className="text-sm text-gray-400">Match Confidence</label>
                <p className="mt-1 font-medium">
                  {track.match_confidence ? `${Math.round(track.match_confidence)}%` : '-'}
                </p>
              </div>
            </div>
          </div>

          {/* Match Results */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Match Results</h2>
              <ProgressButton
                onClick={() => matchMutation.mutate()}
                isLoading={isSearching}
                loadingText="Searching..."
                icon={<Search className="w-4 h-4" />}
                variant="primary"
              >
                Search Again
              </ProgressButton>
            </div>

            {matches?.length > 0 ? (
              <div className="space-y-3">
                {matches.map((match) => (
                  <MatchCard
                    key={match.id}
                    match={match}
                    isSelected={track.matched_tracklist_url === match.tracklist_url}
                    onSelect={() => selectMatchMutation.mutate(match.id)}
                  />
                ))}
              </div>
            ) : (
              <p className="text-gray-400 text-center py-8">
                No matches found. Try searching again or edit the metadata manually.
              </p>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Cover Art */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Cover Art</h2>
              <button
                onClick={loadCoverOptions}
                disabled={isLoadingCovers}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm flex items-center gap-2 disabled:opacity-50"
                title="Browse cover options"
              >
                {isLoadingCovers ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Image className="w-4 h-4" />
                )}
                Browse
              </button>
            </div>
            <div className="aspect-square bg-gray-700 rounded-lg overflow-hidden">
              {track.matched_cover_url ? (
                <img 
                  src={track.matched_cover_url} 
                  alt="Cover" 
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <Music className="w-16 h-16 text-gray-500" />
                </div>
              )}
            </div>
            {track.matched_cover_url && (
              <p className="text-xs text-gray-500 mt-2 truncate" title={track.matched_cover_url}>
                Source: {new URL(track.matched_cover_url).hostname}
              </p>
            )}
          </div>

          {/* Cover Art Options Modal */}
          {showCoverOptions && (
            <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">Choose Cover Art</h2>
                <button
                  onClick={() => setShowCoverOptions(false)}
                  className="p-1 hover:bg-gray-700 rounded"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              
              {isLoadingCovers ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
                </div>
              ) : coverOptions.length > 0 ? (
                <div className="grid grid-cols-2 gap-3 max-h-80 overflow-y-auto">
                  {coverOptions.map((cover, index) => (
                    <button
                      key={index}
                      onClick={() => coverMutation.mutate(cover.url)}
                      disabled={coverMutation.isPending}
                      className={`relative aspect-square bg-gray-700 rounded-lg overflow-hidden hover:ring-2 hover:ring-primary-500 transition-all ${
                        track.matched_cover_url === cover.url ? 'ring-2 ring-green-500' : ''
                      }`}
                    >
                      <img 
                        src={cover.url} 
                        alt={cover.title || 'Cover option'}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          e.target.parentElement.style.display = 'none'
                        }}
                      />
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
                        <p className="text-xs text-white truncate">{cover.source}</p>
                      </div>
                      {track.matched_cover_url === cover.url && (
                        <div className="absolute top-2 right-2 bg-green-500 rounded-full p-1">
                          <Check className="w-3 h-3" />
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-gray-400 text-center py-4">
                  No cover art options found. Try searching for matches first.
                </p>
              )}
              
              {/* Custom URL input */}
              <div className="mt-4 pt-4 border-t border-gray-700">
                <label className="text-sm text-gray-400">Custom URL</label>
                <div className="flex gap-2 mt-1">
                  <input
                    type="text"
                    placeholder="Paste image URL..."
                    id="custom-cover-url"
                    className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-primary-500"
                  />
                  <button
                    onClick={() => {
                      const input = document.getElementById('custom-cover-url')
                      if (input.value) {
                        coverMutation.mutate(input.value)
                      }
                    }}
                    disabled={coverMutation.isPending}
                    className="px-3 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm"
                  >
                    Apply
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* File Info */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h2 className="text-lg font-semibold mb-4">File Info</h2>
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-sm">
                <FileAudio className="w-4 h-4 text-gray-400" />
                <span className="text-gray-400">Format:</span>
                <span>{track.file_format?.toUpperCase() || '-'}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <Clock className="w-4 h-4 text-gray-400" />
                <span className="text-gray-400">Duration:</span>
                <span>{formatDuration(track.duration)}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <HardDrive className="w-4 h-4 text-gray-400" />
                <span className="text-gray-400">Size:</span>
                <span>{formatFileSize(track.file_size)}</span>
              </div>
              {track.bitrate && (
                <div className="flex items-center gap-3 text-sm">
                  <span className="w-4 h-4 text-gray-400 text-xs font-bold">kb</span>
                  <span className="text-gray-400">Bitrate:</span>
                  <span>{track.bitrate} kbps</span>
                </div>
              )}
            </div>
            <div className="mt-4 pt-4 border-t border-gray-700">
              <p className="text-sm text-gray-400 break-all">{track.filepath}</p>
            </div>
          </div>

          {/* Actions */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h2 className="text-lg font-semibold mb-4">Actions</h2>
            <div className="space-y-2">
              <button
                onClick={() => tagMutation.mutate()}
                disabled={track.status !== 'matched' || tagMutation.isPending}
                className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg flex items-center justify-center gap-2"
              >
                <Tag className="w-4 h-4" />
                Apply Tags to File
              </button>
              
              {track.matched_tracklist_url && (
                <a
                  href={track.matched_tracklist_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg flex items-center justify-center gap-2"
                >
                  <ExternalLink className="w-4 h-4" />
                  View Tracklist
                </a>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default TrackDetail
