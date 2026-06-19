import axios from 'axios'

// In Tauri, the frontend is served via a custom protocol so /api won't reach
// the Python backend. Use the full backend URL when running inside Tauri.
const isTauri = Boolean(window.__TAURI_INTERNALS__)
const baseURL = isTauri ? 'http://127.0.0.1:5050/api' : '/api'

// Backend URL for media (cover images, audio streams) — bare <img>/<audio>
// tags can't use the axios client, so they need an absolute URL in Tauri.
export const API_BASE = baseURL
export const embeddedCoverUrl = (trackId) => `${baseURL}/covers/embedded/${trackId}/image`

const api = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Native mode detection — retained as `async () => true` for backwards
// compatibility with any consumers; the app no longer supports Docker mode.
let _isNative = null
export const isNativeMode = async () => {
  if (_isNative === null) {
    try {
      const { data } = await api.get('/health')
      _isNative = data.native !== false
    } catch {
      _isNative = true
    }
  }
  return _isNative
}

// Tracks
export const getTracks = async (params = {}) => {
  const { data } = await api.get('/tracks', { params })
  return data
}

export const getTrackFilters = async () => {
  const { data } = await api.get('/tracks/filters')
  return data
}

export const getTrack = async (id) => {
  const { data } = await api.get(`/tracks/${id}`)
  return data
}

export const updateTrack = async (id, updates) => {
  const { data } = await api.patch(`/tracks/${id}`, updates)
  return data
}

export const deleteTrack = async (id) => {
  const { data } = await api.delete(`/tracks/${id}`)
  return data
}

export const autoMatchFromMetadata = async () => {
  const { data } = await api.post('/tracks/auto-match')
  return data
}

export const batchCoverArt = async () => {
  const { data } = await api.post('/tracks/batch-cover-art')
  return data
}

export const deleteTrackFile = async (id) => {
  const { data } = await api.delete(`/tracks/${id}/file`)
  return data
}

export const getTrackStats = async () => {
  const { data } = await api.get('/tracks/stats')
  return data
}

// Scan
export const startScan = async (directory = null) => {
  const params = directory ? { directory } : {}
  const { data } = await api.post('/scan/start', null, { params })
  return data
}

export const getScanStatus = async () => {
  const { data } = await api.get('/scan/status')
  return data
}

export const stopScan = async () => {
  const { data } = await api.post('/scan/stop')
  return data
}

export const clearDatabase = async () => {
  const { data } = await api.post('/scan/clear')
  return data
}

// Match
export const matchTrack = async (id) => {
  const { data } = await api.post(`/match/${id}`)
  return data
}

export const batchMatch = async (trackIds = null, statusFilter = null) => {
  const params = {}
  if (statusFilter) params.status_filter = statusFilter
  const { data } = await api.post('/match/batch', trackIds || undefined, { params })
  return data
}

export const getMatchResults = async (trackId) => {
  const { data } = await api.get(`/match/${trackId}/results`)
  return data
}

export const selectMatch = async (trackId, matchId) => {
  const { data } = await api.post(`/match/${trackId}/select/${matchId}`)
  return data
}

export const searchTracklists = async (query) => {
  const { data } = await api.post('/match/search', null, { params: { query } })
  return data
}

export const getYouTubeCandidates = async (trackId, query = null, limit = 6) => {
  const params = { limit }
  if (query) params.query = query
  const { data } = await api.get(`/youtube/${trackId}/candidates`, { params })
  return data
}

// Tags
export const applyTags = async (trackId) => {
  const { data } = await api.post(`/tags/${trackId}/apply`)
  return data
}

export const batchApplyTags = async (trackIds = null, applyAllMatched = false) => {
  const params = {}
  if (applyAllMatched) params.apply_all_matched = true
  const { data } = await api.post('/tags/batch/apply', trackIds || undefined, { params })
  return data
}

export const previewTags = async (trackId) => {
  const { data } = await api.get(`/tags/${trackId}/preview`)
  return data
}

export const renameTrack = async (trackId, newFilename) => {
  const { data } = await api.post(`/tags/${trackId}/rename`, null, {
    params: { new_filename: newFilename }
  })
  return data
}

export const batchRename = async (trackIds = null, pattern = '{artist} - {title}') => {
  const { data } = await api.post('/tags/batch/rename', trackIds, {
    params: { pattern }
  })
  return data
}

// Settings
export const getSettings = async () => {
  const { data } = await api.get('/settings')
  return data
}

export const updateSettings = async (settings) => {
  const { data } = await api.patch('/settings', settings)
  return data
}

// AI / Ollama
export const getAIStatus = async () => {
  const { data } = await api.get('/ai/status')
  return data
}

export const getAIModels = async () => {
  const { data } = await api.get('/ai/models')
  return data
}

export const updateAISettings = async (settings) => {
  const { data } = await api.post('/ai/settings', settings)
  return data
}

// AI enrichment (MusicBrainz / Last.fm / AcoustID / SearXNG)
export const getEnrichmentSettings = async () => {
  const { data } = await api.get('/ai/enrichment/settings')
  return data
}

export const updateEnrichmentSettings = async (settings) => {
  const { data } = await api.post('/ai/enrichment/settings', settings)
  return data
}

export const clearEnrichmentCache = async () => {
  const { data } = await api.post('/ai/enrichment/cache/clear')
  return data
}

export const testEnrichment = async (artist, title) => {
  const { data } = await api.post('/ai/enrichment/test', null, {
    params: { artist, title }
  })
  return data
}

// Phase 4 — Review queue + consistency pass
export const getReviewQueue = async (params = {}) => {
  const { data } = await api.get('/ai/review-queue', { params })
  return data
}

export const getReviewQueueStats = async () => {
  const { data } = await api.get('/ai/review-queue/stats')
  return data
}

export const approveReview = async (trackId, genres = null) => {
  const body = genres ? { genres } : {}
  const { data } = await api.post(`/ai/review/${trackId}/approve`, body)
  return data
}

export const rejectReview = async (trackId) => {
  const { data } = await api.post(`/ai/review/${trackId}/reject`)
  return data
}

export const runConsistencyPass = async () => {
  const { data } = await api.post('/ai/consistency-pass')
  return data
}

export const listDirectories = async (path = '/') => {
  const { data } = await api.get('/settings/directories', { params: { path } })
  return data
}

export const getAvailableMounts = async () => {
  const { data } = await api.get('/settings/mounts')
  return data
}

export const getVolumeInfo = async () => {
  const { data } = await api.get('/settings/volume-info')
  return data
}

// Cover Art
export const searchCoverArt = async (trackId, query) => {
  const { data } = await api.get(`/tracks/${trackId}/cover-options`, { params: { query } })
  return data
}

export const searchCoverArtByQuery = async (query) => {
  const { data } = await api.get('/tracks/cover-search', { params: { query } })
  return data
}

export const updateTrackCover = async (trackId, coverUrl) => {
  const { data } = await api.patch(`/tracks/${trackId}`, { matched_cover_url: coverUrl })
  return data
}

// Series Detection
export const detectSeries = async (includeTagged = false) => {
  const { data } = await api.get('/tracks/series/detect', {
    params: { include_tagged: includeTagged }
  })
  return data
}

export const getTaggedSeries = async () => {
  const { data } = await api.get('/tracks/series/tagged')
  return data
}

export const applySeriesAlbum = async (trackIds, album, artist = null, genre = null, albumArtist = null, coverUrl = null) => {
  const { data } = await api.post('/tracks/series/apply-album', trackIds, { 
    params: { album, artist, genre, album_artist: albumArtist, cover_url: coverUrl } 
  })
  return data
}

export const getTaggingJobStatus = async (jobId) => {
  const { data } = await api.get(`/tracks/series/apply-album/status/${jobId}`)
  return data
}

// Database maintenance
export const resyncDatabase = async () => {
  const { data } = await api.post('/tracks/resync')
  return data
}

export const backfillSeriesMarkers = async () => {
  const { data } = await api.post('/tracks/series/backfill-markers')
  return data
}

export const removeFromSeries = async (trackIds) => {
  const { data } = await api.post('/tracks/series/remove-from-series', trackIds)
  return data
}

// MusicBrainz search
export const searchMusicBrainz = async (query, artist = null) => {
  const params = { query }
  if (artist) params.artist = artist
  const { data } = await api.get('/tracks/musicbrainz/search', { params })
  return data
}

export const getMusicBrainzRelease = async (releaseId) => {
  const { data } = await api.get(`/tracks/musicbrainz/release/${releaseId}`)
  return data
}

export const searchMusicBrainzByTracks = async (trackNames) => {
  const { data } = await api.post('/tracks/musicbrainz/search-by-tracks', trackNames)
  return data
}

// Logs
export const getLogs = async (lines = 200, level = null) => {
  const params = { lines }
  if (level) params.level = level
  const { data } = await api.get('/settings/logs', { params })
  return data
}

export const clearLogs = async () => {
  const { data } = await api.delete('/settings/logs')
  return data
}

// Fingerprinting
export const getFingerprintStatus = async () => {
  const { data } = await api.get('/fingerprint/status')
  return data
}

export const identifyTrack = async (trackId) => {
  const { data } = await api.post('/fingerprint/identify', { track_id: trackId })
  return data
}

export const applyIdentification = async (trackId, metadata) => {
  const { data } = await api.post(`/fingerprint/identify/${trackId}/apply`, metadata)
  return data
}

export const generateFingerprints = async (overwrite = false, workers = 4) => {
  const { data } = await api.post('/fingerprint/generate', null, { params: { overwrite, workers } })
  return data
}

export const stopFingerprints = async () => {
  const { data } = await api.post('/fingerprint/stop')
  return data
}

export const generateSingleFingerprint = async (trackId) => {
  const { data } = await api.post(`/fingerprint/generate/${trackId}`)
  return data
}

export const getDuplicates = async () => {
  const { data } = await api.get('/fingerprint/duplicates')
  return data
}

// ---------------------------------------------------------------------------
// Library Scan Review
// ---------------------------------------------------------------------------

export const startLibraryScan = async (trackIds = null, classifyGenre = true, checkCovers = true, forceReclassify = false) => {
  const { data } = await api.post('/library/scan', { track_ids: trackIds, classify_genre: classifyGenre, check_covers: checkCovers, force_reclassify: forceReclassify })
  return data
}

export const getLibraryScanStatus = async () => {
  const { data } = await api.get('/library/scan/status')
  return data
}

export const stopLibraryScan = async () => {
  const { data } = await api.post('/library/scan/stop')
  return data
}

export const getLibrarySuggestions = async (status = null, offset = 0, limit = 50) => {
  const params = { offset, limit }
  if (status) params.status = status
  const { data } = await api.get('/library/suggestions', { params })
  return data
}

export const updateSuggestionSelection = async (trackIds, selected) => {
  const { data } = await api.post('/library/suggestions/select', { track_ids: trackIds, selected })
  return data
}

export const selectAllSuggestions = async (selected) => {
  const { data } = await api.post('/library/suggestions/select-all', { selected })
  return data
}

export const rejectSuggestions = async (trackIds) => {
  const { data } = await api.post('/library/suggestions/reject', { track_ids: trackIds })
  return data
}

export const applySuggestions = async () => {
  const { data } = await api.post('/library/suggestions/apply')
  return data
}

// ---------------------------------------------------------------------------
// FLAC-to-MP3 Conversion
// ---------------------------------------------------------------------------

export const getConvertStatus = async () => {
  const { data } = await api.get('/library/convert/status')
  return data
}

export const convertToMp3 = async (trackIds, bitrate = 320, replaceOriginal = false) => {
  const { data } = await api.post('/library/convert/to-mp3', { track_ids: trackIds, bitrate, replace_original: replaceOriginal })
  return data
}

export const stopConversion = async () => {
  const { data } = await api.post('/library/convert/stop')
  return data
}

export default api
