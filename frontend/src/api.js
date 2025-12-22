import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

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

// Match
export const matchTrack = async (id) => {
  const { data } = await api.post(`/match/${id}`)
  return data
}

export const batchMatch = async (trackIds = null, statusFilter = null) => {
  const params = {}
  if (statusFilter) params.status_filter = statusFilter
  const { data } = await api.post('/match/batch', trackIds, { params })
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

// Tags
export const applyTags = async (trackId) => {
  const { data } = await api.post(`/tags/${trackId}/apply`)
  return data
}

export const batchApplyTags = async (trackIds = null, applyAllMatched = false) => {
  const params = {}
  if (applyAllMatched) params.apply_all_matched = true
  const { data } = await api.post('/tags/batch/apply', trackIds, { params })
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

export const listDirectories = async (path = '/') => {
  const { data } = await api.get('/settings/directories', { params: { path } })
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

export default api
