import { useState, useEffect } from 'react'
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
  ChevronRight,
  Loader2,
  CheckCircle2
} from 'lucide-react'
import { getTracks, deleteTrack, batchMatch, batchApplyTags, getTrackFilters, getTrackStats, convertToMp3, updateTrack } from '../api'
import { MiniPlayer } from '../components/AudioPlayer'
import TrackCover from '../components/TrackCover'

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

const bulkTagFields = [
  { key: 'matched_title', base: 'title', label: 'Title' },
  { key: 'matched_artist', base: 'artist', label: 'Artist' },
  { key: 'matched_album', base: 'album', label: 'Album' },
  { key: 'matched_album_artist', base: 'album_artist', label: 'Album Artist' },
  { key: 'matched_genre', base: 'genre', label: 'Genre' },
  { key: 'matched_year', base: 'year', label: 'Year' },
]

const emptyBulkTagForm = bulkTagFields.reduce((acc, field) => {
  acc[field.key] = ''
  return acc
}, {})

const emptyClearFields = bulkTagFields.reduce((acc, field) => {
  acc[field.key] = false
  return acc
}, {})

function SuccessToast({ message, onClose }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 4000)
    return () => clearTimeout(timer)
  }, [onClose])

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-md rounded-xl border border-green-700 bg-green-900/95 p-4 shadow-2xl">
      <div className="flex items-center gap-3">
        <CheckCircle2 className="h-6 w-6 flex-shrink-0 text-green-400" />
        <span className="text-green-100">{message}</span>
        <button onClick={onClose} className="ml-auto text-green-400 hover:text-green-200" aria-label="Dismiss notification">
          <X className="h-5 w-5" />
        </button>
      </div>
    </div>
  )
}

function BulkTagModal({
  isOpen,
  selectedCount,
  form,
  clearFields,
  applyMatchedOnly,
  onChange,
  onToggleClear,
  onToggleApplyMatchedOnly,
  onClose,
  onSubmit,
  isSubmitting,
}) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-gray-700 bg-gray-800 shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-700 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold">Bulk Tag Selected Tracks</h2>
            <p className="mt-1 text-sm text-gray-400">Apply these tag values to {selectedCount} selected tracks.</p>
          </div>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="rounded p-1 text-gray-400 hover:text-white disabled:opacity-50"
            aria-label="Close bulk tag modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSubmit()
          }}
          className="space-y-4 px-5 py-4"
        >
          <label className="flex items-start gap-3 rounded-lg border border-gray-700 bg-gray-900/60 px-3 py-2">
            <input
              type="checkbox"
              checked={applyMatchedOnly}
              onChange={(e) => onToggleApplyMatchedOnly(e.target.checked)}
              className="mt-1 h-4 w-4 rounded border-gray-600 bg-gray-900 text-primary-500 focus:ring-primary-500"
            />
            <span className="text-sm text-gray-300">
              Apply existing matched tags only
              <span className="block text-xs text-gray-500">
                Write current matched metadata to files without changing any fields below.
              </span>
            </span>
          </label>

          <p className="text-xs text-gray-500">
            Leave a field blank to keep existing values. Check <span className="font-medium text-gray-400">Clear</span> to
            remove that field on all selected tracks.
          </p>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {bulkTagFields.map((field) => {
              const isCleared = clearFields[field.key]
              return (
                <div key={field.key} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-300">{field.label}</span>
                    <label className="flex items-center gap-1.5 text-xs text-gray-400">
                      <input
                        type="checkbox"
                        checked={isCleared}
                        onChange={(e) => onToggleClear(field.key, e.target.checked)}
                        disabled={applyMatchedOnly}
                        className="h-3.5 w-3.5 rounded border-gray-600 bg-gray-900 text-red-500 focus:ring-red-500 disabled:opacity-50"
                      />
                      Clear
                    </label>
                  </div>
                  <input
                    type="text"
                    value={isCleared ? '' : form[field.key]}
                    onChange={(e) => onChange(field.key, e.target.value)}
                    placeholder={isCleared ? 'Will be cleared' : `Set ${field.label.toLowerCase()}`}
                    disabled={applyMatchedOnly || isCleared}
                    className="w-full rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none disabled:opacity-50"
                  />
                </div>
              )
            })}
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-gray-700 pt-4">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="rounded-lg border border-gray-600 px-4 py-2 text-sm text-gray-300 hover:border-gray-500 hover:text-white disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="inline-flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium hover:bg-green-700 disabled:opacity-50"
            >
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Tag className="h-4 w-4" />}
              Apply Tags
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function TrackRow({ track, selected, onSelect }) {
  return (
    <div className={`flex items-center gap-2 sm:gap-4 p-3 sm:p-4 rounded-lg border transition-colors ${
      selected ? 'border-primary-500 bg-primary-500/10' : 'border-gray-700 hover:border-gray-600'
    }`}>
      <button
        onClick={() => onSelect(track.id)}
        className="text-gray-400 hover:text-white flex-shrink-0"
      >
        {selected ? (
          <CheckSquare className="w-5 h-5 text-primary-500" />
        ) : (
          <Square className="w-5 h-5" />
        )}
      </button>
      
      {/* Mini Player - hidden on small screens */}
      <div className="hidden sm:block">
        <MiniPlayer trackId={track.id} />
      </div>
      
      <div className="w-10 h-10 sm:w-12 sm:h-12 bg-gray-700 rounded flex items-center justify-center flex-shrink-0 overflow-hidden">
        <TrackCover trackId={track.id} matchedUrl={track.matched_cover_url} alt="" />
      </div>
      
      <Link to={`/tracks/${track.id}`} className="flex-1 min-w-0">
        <p className="font-medium truncate text-sm sm:text-base">
          {track.matched_title || track.title || track.filename}
        </p>
        <p className="text-xs sm:text-sm text-gray-400 truncate">
          {track.matched_artist || track.artist || 'Unknown Artist'}
          {track.matched_genre && ` • ${track.matched_genre}`}
        </p>
      </Link>
      
      <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
        {track.match_confidence && (
          <span className="text-xs sm:text-sm text-gray-400 hidden md:inline">
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
  const [formatFilter, setFormatFilter] = useState('')
  const [pageSize, setPageSize] = useState(50)
  const [currentPage, setCurrentPage] = useState(0)
  const [isBulkTagModalOpen, setIsBulkTagModalOpen] = useState(false)
  const [bulkTagForm, setBulkTagForm] = useState(emptyBulkTagForm)
  const [bulkClearFields, setBulkClearFields] = useState(emptyClearFields)
  const [applyMatchedOnly, setApplyMatchedOnly] = useState(false)
  const [toastMessage, setToastMessage] = useState('')
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

  const { data: tracksRaw, isLoading } = useQuery({
    queryKey: ['tracks', status, searchQuery, genreFilter, artistFilter, albumFilter, formatFilter, pageSize, currentPage],
    queryFn: () => getTracks({ 
      status: status || undefined, 
      search: searchQuery || undefined,
      genre: genreFilter || undefined,
      artist: artistFilter || undefined,
      album: albumFilter || undefined,
      file_format: formatFilter || undefined,
      limit: pageSize,
      skip: currentPage * pageSize
    }),
    refetchInterval: 10000,
  })

  const tracks = Array.isArray(tracksRaw) ? tracksRaw : Array.isArray(tracksRaw?.tracks) ? tracksRaw.tracks : []

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
    mutationFn: (ids) => batchMatch(ids.size > 0 ? Array.from(ids) : null, status || 'pending'),
    onSuccess: () => {
      setSelectedTracks(new Set())
      queryClient.invalidateQueries(['tracks'])
      queryClient.invalidateQueries(['track-stats'])
    },
  })

  const bulkTagMutation = useMutation({
    mutationFn: async ({ ids, form, clearFields, matchedOnly }) => {
      const selectedIds = ids.size > 0 ? Array.from(ids) : []
      const payload = {}

      if (!matchedOnly) {
        for (const field of bulkTagFields) {
          if (clearFields[field.key]) {
            // Clear both the matched and base value so the field is removed everywhere.
            payload[field.key] = ''
            payload[field.base] = ''
          } else {
            const trimmed = form[field.key].trim()
            if (trimmed) {
              payload[field.key] = trimmed
            }
          }
        }
      }

      if (Object.keys(payload).length > 0) {
        payload.status = 'matched'
        const chunkSize = 25
        for (let i = 0; i < selectedIds.length; i += chunkSize) {
          const chunk = selectedIds.slice(i, i + chunkSize)
          await Promise.all(chunk.map((id) => updateTrack(id, payload)))
        }
      }

      await batchApplyTags(selectedIds, false)
      return selectedIds.length
    },
    onSuccess: (count) => {
      setIsBulkTagModalOpen(false)
      setBulkTagForm(emptyBulkTagForm)
      setBulkClearFields(emptyClearFields)
      setApplyMatchedOnly(false)
      setSelectedTracks(new Set())
      setToastMessage(`Tagging started for ${count} track${count === 1 ? '' : 's'}.`)
      queryClient.invalidateQueries(['tracks'])
      queryClient.invalidateQueries(['track-stats'])
      queryClient.invalidateQueries(['track-filters'])
    },
  })

  const convertMutation = useMutation({
    mutationFn: (ids) => convertToMp3(Array.from(ids), 320, false),
    onSuccess: (data) => {
      setSelectedTracks(new Set())
      queryClient.invalidateQueries(['tracks'])
      queryClient.invalidateQueries(['track-stats'])
      queryClient.invalidateQueries(['track-filters'])
      if (data?.converting === 0 || data?.started === false) {
        alert(data?.message || 'No non-MP3 tracks in selection')
      } else {
        alert(`Converting ${data.converting} track(s) in the background. Check Library Scan page for progress.`)
      }
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

  const handleOpenBulkTagModal = () => {
    if (selectedTracks.size === 0) return

    // Prefill a field when every selected track (that we have loaded) shares
    // the same value for it; otherwise leave it blank.
    const selected = tracks.filter((t) => selectedTracks.has(t.id))
    const prefill = { ...emptyBulkTagForm }
    if (selected.length > 0) {
      for (const field of bulkTagFields) {
        const values = selected.map((t) => {
          const raw = t[field.key] ?? t[field.base]
          return raw == null ? '' : String(raw)
        })
        const first = values[0]
        if (first && values.every((v) => v === first)) {
          prefill[field.key] = first
        }
      }
    }

    setBulkTagForm(prefill)
    setBulkClearFields(emptyClearFields)
    setApplyMatchedOnly(false)
    setIsBulkTagModalOpen(true)
  }

  const handleBulkTagFieldChange = (field, value) => {
    setBulkTagForm((prev) => ({ ...prev, [field]: value }))
  }

  const handleToggleClearField = (field, checked) => {
    setBulkClearFields((prev) => ({ ...prev, [field]: checked }))
  }

  const handleToggleApplyMatchedOnly = (checked) => {
    setApplyMatchedOnly(checked)
  }

  const handleSubmitBulkTag = () => {
    if (!applyMatchedOnly) {
      const hasUpdates = bulkTagFields.some(
        (field) => bulkClearFields[field.key] || bulkTagForm[field.key].trim().length > 0
      )
      if (!hasUpdates) {
        alert('Enter or clear at least one tag field, or enable "Apply existing matched tags only".')
        return
      }
    }
    bulkTagMutation.mutate({
      ids: selectedTracks,
      form: bulkTagForm,
      clearFields: bulkClearFields,
      matchedOnly: applyMatchedOnly,
    })
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

        {/* Format Filter */}
        <div className="relative">
          <select
            value={formatFilter}
            onChange={(e) => handleFilterChange(setFormatFilter)(e.target.value)}
            className="pl-4 pr-10 py-2 bg-gray-800 border border-gray-700 rounded-lg appearance-none focus:outline-none focus:border-primary-500 min-w-[120px]"
            title="Filter by file extension"
          >
            <option value="">All Formats</option>
            {filterOptions?.formats?.map((fmt) => (
              <option key={fmt} value={fmt}>{fmt.toUpperCase()}</option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>

        {/* Clear Filters */}
        {(genreFilter || artistFilter || albumFilter || formatFilter) && (
          <button
            onClick={() => {
              setGenreFilter('')
              setArtistFilter('')
              setAlbumFilter('')
              setFormatFilter('')
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
            onClick={handleOpenBulkTagModal}
            disabled={bulkTagMutation.isPending}
            className="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm flex items-center gap-2 disabled:opacity-50"
          >
            <Tag className="w-4 h-4" />
            Tag Selected
          </button>
          <button
            onClick={() => convertMutation.mutate(selectedTracks)}
            disabled={convertMutation.isPending}
            className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm flex items-center gap-2 disabled:opacity-50"
            title="Convert non-MP3 tracks in selection to MP3 (320 kbps, keeps originals)"
          >
            <Music className="w-4 h-4" />
            Convert to MP3
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

      <BulkTagModal
        isOpen={isBulkTagModalOpen}
        selectedCount={selectedTracks.size}
        form={bulkTagForm}
        clearFields={bulkClearFields}
        applyMatchedOnly={applyMatchedOnly}
        onChange={handleBulkTagFieldChange}
        onToggleClear={handleToggleClearField}
        onToggleApplyMatchedOnly={handleToggleApplyMatchedOnly}
        onClose={() => {
          if (!bulkTagMutation.isPending) {
            setIsBulkTagModalOpen(false)
          }
        }}
        onSubmit={handleSubmitBulkTag}
        isSubmitting={bulkTagMutation.isPending}
      />

      {toastMessage && (
        <SuccessToast message={toastMessage} onClose={() => setToastMessage('')} />
      )}
    </div>
  )
}

export default Tracks
