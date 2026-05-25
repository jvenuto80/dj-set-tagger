import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  CheckSquare,
  Square,
  Play,
  StopCircle,
  CheckCircle2,
  XCircle,
  Music,
  Disc3,
  ArrowRight,
  RefreshCw,
  FileAudio,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Image,
} from 'lucide-react'
import {
  startLibraryScan,
  getLibraryScanStatus,
  stopLibraryScan,
  getLibrarySuggestions,
  updateSuggestionSelection,
  selectAllSuggestions,
  applySuggestions,
  rejectSuggestions,
  getConvertStatus,
  convertToMp3,
  stopConversion,
} from '../api'

function LibraryScan() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState(null)
  const [classifyGenre, setClassifyGenre] = useState(true)
  const [checkCovers, setCheckCovers] = useState(true)
  const [forceReclassify, setForceReclassify] = useState(false)
  const [convertBitrate, setConvertBitrate] = useState(320)
  const [replaceOriginal, setReplaceOriginal] = useState(false)
  const [expandedRows, setExpandedRows] = useState(new Set())
  const [applyResult, setApplyResult] = useState(null)

  // Poll scan status
  const { data: scanStatus } = useQuery({
    queryKey: ['libraryScanStatus'],
    queryFn: getLibraryScanStatus,
    refetchInterval: (query) => query.state.data?.running ? 1000 : 5000,
  })

  // Get suggestions (only when scan complete and has suggestions)
  const { data: suggestionsData, refetch: refetchSuggestions } = useQuery({
    queryKey: ['librarySuggestions', statusFilter],
    queryFn: () => getLibrarySuggestions(statusFilter, 0, 200),
    enabled: scanStatus?.suggestion_count > 0,
    refetchInterval: scanStatus?.running ? 2000 : false,
  })

  // Conversion status
  const { data: convertStatus } = useQuery({
    queryKey: ['convertStatus'],
    queryFn: getConvertStatus,
    refetchInterval: (query) => query.state.data?.running ? 1000 : false,
  })

  const scanMutation = useMutation({
    mutationFn: () => startLibraryScan(null, classifyGenre, checkCovers, forceReclassify),
    onSuccess: () => queryClient.invalidateQueries(['libraryScanStatus']),
  })

  const stopScanMutation = useMutation({
    mutationFn: stopLibraryScan,
    onSuccess: () => queryClient.invalidateQueries(['libraryScanStatus']),
  })

  const toggleSelectionMutation = useMutation({
    mutationFn: ({ trackIds, selected }) => updateSuggestionSelection(trackIds, selected),
    onSuccess: () => refetchSuggestions(),
  })

  const selectAllMutation = useMutation({
    mutationFn: (selected) => selectAllSuggestions(selected),
    onSuccess: () => refetchSuggestions(),
  })

  const applyMutation = useMutation({
    mutationFn: applySuggestions,
    onSuccess: (data) => {
      setApplyResult(data)
      refetchSuggestions()
      queryClient.invalidateQueries(['tracks'])
      setTimeout(() => setApplyResult(null), 5000)
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (trackIds) => rejectSuggestions(trackIds),
    onSuccess: () => refetchSuggestions(),
  })

  const convertMutation = useMutation({
    mutationFn: (trackIds) => convertToMp3(trackIds, convertBitrate, replaceOriginal),
    onSuccess: () => {
      queryClient.invalidateQueries(['convertStatus'])
      queryClient.invalidateQueries(['tracks'])
      queryClient.invalidateQueries(['track-stats'])
      queryClient.invalidateQueries(['track-filters'])
    },
  })

  const stopConvertMutation = useMutation({
    mutationFn: stopConversion,
    onSuccess: () => queryClient.invalidateQueries(['convertStatus']),
  })

  const suggestions = suggestionsData?.suggestions || []
  const selectedCount = suggestions.filter(s => s.selected).length
  const pendingCount = suggestions.filter(s => s.status === 'pending').length

  const toggleRow = useCallback((trackId) => {
    setExpandedRows(prev => {
      const next = new Set(prev)
      next.has(trackId) ? next.delete(trackId) : next.add(trackId)
      return next
    })
  }, [])

  const isRunning = scanStatus?.running
  const phase = scanStatus?.phase || ''

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Search className="w-7 h-7" />
          Library Scan
        </h1>
      </div>

      {/* Scan Controls */}
      <div className="bg-gray-800 rounded-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold text-white">AI-Powered Library Scan</h2>
        <p className="text-gray-400 text-sm">
          Scan your library with AI to classify genres and check cover art quality.
          Review all suggestions before any changes are written to your files.
        </p>

        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-gray-300 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={classifyGenre}
              onChange={e => setClassifyGenre(e.target.checked)}
              className="rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500"
            />
            Genre Classification
          </label>
          <label className="flex items-center gap-2 text-gray-300 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={checkCovers}
              onChange={e => setCheckCovers(e.target.checked)}
              className="rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500"
            />
            Cover Art Check
          </label>
          <label
            className="flex items-center gap-2 text-gray-300 text-sm cursor-pointer"
            title="By default, tracks that already have a cached AI genre in the DB are skipped. Enable to re-run the classifier on every track."
          >
            <input
              type="checkbox"
              checked={forceReclassify}
              onChange={e => setForceReclassify(e.target.checked)}
              disabled={!classifyGenre}
              className="rounded border-gray-600 bg-gray-700 text-purple-500 focus:ring-purple-500 disabled:opacity-40"
            />
            Force Re-classify (ignore cache)
          </label>
        </div>

        <div className="flex items-center gap-3">
          {!isRunning ? (
            <button
              onClick={() => scanMutation.mutate()}
              disabled={scanMutation.isPending}
              className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 disabled:opacity-50"
            >
              <Play className="w-4 h-4" />
              Scan Library
            </button>
          ) : (
            <button
              onClick={() => stopScanMutation.mutate()}
              className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg flex items-center gap-2"
            >
              <StopCircle className="w-4 h-4" />
              Stop Scan
            </button>
          )}

          {isRunning && (
            <div className="flex items-center gap-3 text-gray-300">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span className="text-sm">
                {phase === 'scanning' && `Scanning tracks... ${scanStatus.progress}/${scanStatus.total}`}
                {phase === 'classifying' && `Classifying genres... ${scanStatus.progress}/${scanStatus.total}`}
              </span>
              <div className="w-48 bg-gray-700 rounded-full h-2">
                <div
                  className="bg-purple-500 rounded-full h-2 transition-all"
                  style={{ width: `${scanStatus.total ? (scanStatus.progress / scanStatus.total) * 100 : 0}%` }}
                />
              </div>
            </div>
          )}

          {phase === 'complete' && !isRunning && (
            <span className="text-green-400 text-sm flex items-center gap-1">
              <CheckCircle2 className="w-4 h-4" />
              Scan complete — {scanStatus.suggestion_count} suggestions
              {scanStatus.errors > 0 && `, ${scanStatus.errors} errors`}
            </span>
          )}
        </div>
      </div>

      {/* Apply Result Toast */}
      {applyResult && (
        <div className={`rounded-lg p-4 ${applyResult.errors > 0 ? 'bg-yellow-900/50 border border-yellow-700' : 'bg-green-900/50 border border-green-700'}`}>
          <p className={applyResult.errors > 0 ? 'text-yellow-300' : 'text-green-300'}>
            {applyResult.message}
          </p>
        </div>
      )}

      {/* Suggestions Table */}
      {suggestions.length > 0 && (
        <div className="bg-gray-800 rounded-lg overflow-hidden">
          {/* Toolbar */}
          <div className="p-4 border-b border-gray-700 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <button
                onClick={() => selectAllMutation.mutate(true)}
                className="text-sm text-purple-400 hover:text-purple-300 flex items-center gap-1"
              >
                <CheckSquare className="w-4 h-4" /> Select All
              </button>
              <button
                onClick={() => selectAllMutation.mutate(false)}
                className="text-sm text-gray-400 hover:text-gray-300 flex items-center gap-1"
              >
                <Square className="w-4 h-4" /> Deselect All
              </button>
              <span className="text-gray-500 text-sm">
                {selectedCount} selected / {pendingCount} pending
              </span>
            </div>

            <div className="flex items-center gap-3">
              {/* Status filter */}
              <select
                value={statusFilter || ''}
                onChange={e => setStatusFilter(e.target.value || null)}
                className="bg-gray-700 text-gray-300 text-sm rounded px-2 py-1 border border-gray-600"
              >
                <option value="">All</option>
                <option value="pending">Pending</option>
                <option value="applied">Applied</option>
                <option value="rejected">Rejected</option>
                <option value="error">Errors</option>
              </select>

              <button
                onClick={() => applyMutation.mutate()}
                disabled={selectedCount === 0 || applyMutation.isPending}
                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 text-sm disabled:opacity-50"
              >
                <CheckCircle2 className="w-4 h-4" />
                Apply Selected ({selectedCount})
              </button>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-750">
                <tr className="text-gray-400 text-left">
                  <th className="p-3 w-10"></th>
                  <th className="p-3">Track</th>
                  <th className="p-3">Changes</th>
                  <th className="p-3 w-24">Confidence</th>
                  <th className="p-3 w-24">Status</th>
                  <th className="p-3 w-16"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {suggestions.map(s => (
                  <SuggestionRow
                    key={s.track_id}
                    suggestion={s}
                    expanded={expandedRows.has(s.track_id)}
                    onToggleExpand={() => toggleRow(s.track_id)}
                    onToggleSelect={() =>
                      toggleSelectionMutation.mutate({ trackIds: [s.track_id], selected: !s.selected })
                    }
                    onReject={() => rejectMutation.mutate([s.track_id])}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* FLAC-to-MP3 Conversion */}
      <div className="bg-gray-800 rounded-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <FileAudio className="w-5 h-5" />
          FLAC → MP3 Conversion
        </h2>
        <p className="text-gray-400 text-sm">
          Convert lossless files to MP3. All tags, cover art, and Mixed In Key data are preserved.
          Requires ffmpeg ({convertStatus?.ffmpeg_available ? (
            <span className="text-green-400">installed</span>
          ) : (
            <span className="text-red-400">not found — brew install ffmpeg</span>
          )}).
        </p>

        <div className="flex flex-wrap items-center gap-4">
          <label className="text-gray-300 text-sm">
            Bitrate:
            <select
              value={convertBitrate}
              onChange={e => setConvertBitrate(Number(e.target.value))}
              className="ml-2 bg-gray-700 text-gray-300 rounded px-2 py-1 border border-gray-600"
            >
              <option value={128}>128 kbps</option>
              <option value={192}>192 kbps</option>
              <option value={256}>256 kbps</option>
              <option value={320}>320 kbps</option>
            </select>
          </label>

          <label className="flex items-center gap-2 text-gray-300 text-sm cursor-pointer" title="If checked, original FLAC/WAV files will be permanently deleted after a successful conversion.">
            <input
              type="checkbox"
              checked={replaceOriginal}
              onChange={e => setReplaceOriginal(e.target.checked)}
              className="rounded border-gray-600 bg-gray-700 text-red-500 focus:ring-red-500"
            />
            <span className={replaceOriginal ? 'text-red-400 font-medium' : ''}>
              Delete originals after conversion
              {replaceOriginal && <span className="ml-1">⚠</span>}
            </span>
          </label>
        </div>

        {convertStatus?.running && (
          <div className="flex items-center gap-3 text-gray-300">
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span className="text-sm">
              Converting... {convertStatus.progress}/{convertStatus.total}
              ({convertStatus.converted} done, {convertStatus.errors} errors)
            </span>
            <div className="w-48 bg-gray-700 rounded-full h-2">
              <div
                className="bg-blue-500 rounded-full h-2 transition-all"
                style={{ width: `${convertStatus.total ? (convertStatus.progress / convertStatus.total) * 100 : 0}%` }}
              />
            </div>
            <button
              onClick={() => stopConvertMutation.mutate()}
              className="text-red-400 hover:text-red-300 text-sm"
            >
              Stop
            </button>
          </div>
        )}

        <div className="flex items-center gap-3 pt-2 border-t border-gray-700">
          <button
            onClick={() => {
              if (replaceOriginal && !confirm('This will DELETE original FLAC/WAV files after conversion. Continue?')) return
              convertMutation.mutate(null) // null = all non-MP3 tracks
            }}
            disabled={!convertStatus?.ffmpeg_available || convertStatus?.running || convertMutation.isPending}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm flex items-center gap-2"
          >
            <FileAudio className="w-4 h-4" />
            Convert All Non-MP3 Tracks
          </button>
          <span className="text-gray-500 text-xs">
            Or select specific tracks on the Tracks page and use the bulk action menu.
          </span>
        </div>
      </div>
    </div>
  )
}

function SuggestionRow({ suggestion: s, expanded, onToggleExpand, onToggleSelect, onReject }) {
  const statusColors = {
    pending: 'text-yellow-400',
    applied: 'text-green-400',
    rejected: 'text-gray-500',
    error: 'text-red-400',
  }

  return (
    <>
      <tr className="hover:bg-gray-750/50">
        {/* Checkbox */}
        <td className="p-3">
          {s.status === 'pending' ? (
            <button onClick={onToggleSelect} className="text-gray-300 hover:text-white">
              {s.selected ? (
                <CheckSquare className="w-5 h-5 text-purple-400" />
              ) : (
                <Square className="w-5 h-5" />
              )}
            </button>
          ) : (
            <span className={statusColors[s.status]}>
              {s.status === 'applied' && <CheckCircle2 className="w-5 h-5" />}
              {s.status === 'rejected' && <XCircle className="w-5 h-5" />}
              {s.status === 'error' && <AlertTriangle className="w-5 h-5" />}
            </span>
          )}
        </td>

        {/* Track info */}
        <td className="p-3">
          <div className="text-white font-medium truncate max-w-xs">{s.filename}</div>
          <div className="text-gray-500 text-xs truncate max-w-xs">
            {s.current?.artist} — {s.current?.title}
          </div>
        </td>

        {/* Changes summary */}
        <td className="p-3">
          <div className="flex flex-wrap gap-1">
            {s.changes?.map((c, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-gray-700 text-gray-300"
              >
                {c.field === 'genre' && <Music className="w-3 h-3" />}
                {c.field === 'cover_art' && <Image className="w-3 h-3" />}
                {c.field}
              </span>
            ))}
          </div>
        </td>

        {/* Confidence */}
        <td className="p-3">
          {s.ai_confidence > 0 && (
            <span className={`text-sm ${s.ai_confidence >= 80 ? 'text-green-400' : s.ai_confidence >= 50 ? 'text-yellow-400' : 'text-red-400'}`}>
              {s.ai_confidence}%
            </span>
          )}
        </td>

        {/* Status */}
        <td className="p-3">
          <span className={`text-xs font-medium ${statusColors[s.status] || 'text-gray-400'}`}>
            {s.status}
          </span>
        </td>

        {/* Expand / Reject */}
        <td className="p-3">
          <div className="flex items-center gap-1">
            {s.status === 'pending' && (
              <button onClick={onReject} className="text-gray-500 hover:text-red-400 p-1" title="Reject">
                <XCircle className="w-4 h-4" />
              </button>
            )}
            <button onClick={onToggleExpand} className="text-gray-500 hover:text-white p-1">
              {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
          </div>
        </td>
      </tr>

      {/* Expanded detail row */}
      {expanded && (
        <tr className="bg-gray-900/50">
          <td colSpan={6} className="p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              {s.changes?.map((c, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-gray-500 font-medium min-w-[80px]">{c.field}:</span>
                  <span className="text-red-400 line-through">{c.old_value}</span>
                  <ArrowRight className="w-4 h-4 text-gray-600 flex-shrink-0 mt-0.5" />
                  <span className="text-green-400">{c.new_value}</span>
                </div>
              ))}
              {s.ai_reasoning && (
                <div className="col-span-full text-gray-500 text-xs italic">
                  AI reasoning: {s.ai_reasoning}
                </div>
              )}
              {s.cover_quality?.score < 100 && (
                <div className="col-span-full text-gray-500 text-xs">
                  Cover quality: {s.cover_quality.score}/100
                  {s.cover_quality.issues?.length > 0 && ` — ${s.cover_quality.issues.join(', ')}`}
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default LibraryScan
