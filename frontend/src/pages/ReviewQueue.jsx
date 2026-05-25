import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, X, Edit3, AlertTriangle, Sparkles, RefreshCw } from 'lucide-react'
import {
  getReviewQueue,
  getReviewQueueStats,
  approveReview,
  rejectReview,
  runConsistencyPass,
} from '../api'

const STATUS_TABS = [
  { key: 'needs_review', label: 'Needs Review', desc: '60-84% confidence' },
  { key: 'manual_review', label: 'Manual Review', desc: '<60% confidence' },
  { key: 'approved', label: 'Approved', desc: 'Human-confirmed' },
  { key: 'rejected', label: 'Rejected', desc: 'Dismissed' },
  { key: 'auto_applied', label: 'Auto-Applied', desc: '≥85% confidence' },
]

function ReviewQueue() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('needs_review')
  const [editingId, setEditingId] = useState(null)
  const [editValue, setEditValue] = useState('')

  const { data: stats } = useQuery({
    queryKey: ['reviewQueueStats'],
    queryFn: getReviewQueueStats,
    refetchInterval: 5000,
  })

  const { data: tracks = [], isLoading } = useQuery({
    queryKey: ['reviewQueue', activeTab],
    queryFn: () => getReviewQueue({ status: activeTab, limit: 500 }),
    refetchInterval: 5000,
  })

  const approveMutation = useMutation({
    mutationFn: ({ trackId, genres }) => approveReview(trackId, genres),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reviewQueue'] })
      queryClient.invalidateQueries({ queryKey: ['reviewQueueStats'] })
      setEditingId(null)
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (trackId) => rejectReview(trackId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reviewQueue'] })
      queryClient.invalidateQueries({ queryKey: ['reviewQueueStats'] })
    },
  })

  const consistencyMutation = useMutation({
    mutationFn: runConsistencyPass,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reviewQueue'] })
      queryClient.invalidateQueries({ queryKey: ['reviewQueueStats'] })
    },
  })

  const startEdit = (track) => {
    setEditingId(track.id)
    setEditValue(track.ai_genre || '')
  }

  const saveEdit = (trackId) => {
    const genres = editValue.split(';').map((g) => g.trim()).filter(Boolean)
    if (genres.length === 0) return
    approveMutation.mutate({ trackId, genres })
  }

  const confidenceColor = (c) => {
    if (c == null) return 'text-gray-400 bg-gray-700'
    if (c >= 85) return 'text-green-300 bg-green-900/50'
    if (c >= 60) return 'text-yellow-300 bg-yellow-900/50'
    return 'text-red-300 bg-red-900/50'
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Sparkles className="text-primary-400" size={28} />
            Review Queue
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Confidence-gated AI genre classifications awaiting human decision.
          </p>
        </div>
        <button
          onClick={() => consistencyMutation.mutate()}
          disabled={consistencyMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 rounded-lg text-sm font-medium"
        >
          <RefreshCw size={16} className={consistencyMutation.isPending ? 'animate-spin' : ''} />
          Run Consistency Pass
        </button>
      </div>

      {consistencyMutation.data && (
        <div className="mb-4 p-3 bg-gray-800 border border-gray-700 rounded-lg text-sm">
          Cross-track pass complete: <strong>{consistencyMutation.data.artists_checked}</strong> artists checked,{' '}
          <strong className="text-yellow-300">{consistencyMutation.data.tracks_flagged}</strong> flagged,{' '}
          <strong>{consistencyMutation.data.tracks_cleared}</strong> cleared.
        </div>
      )}

      {/* Status tabs */}
      <div className="flex flex-wrap gap-2 mb-6 border-b border-gray-700 pb-2">
        {STATUS_TABS.map((tab) => {
          const count = stats?.[tab.key] ?? 0
          const active = activeTab === tab.key
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                active
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
              }`}
              title={tab.desc}
            >
              {tab.label}
              <span className="ml-2 px-2 py-0.5 bg-gray-900/50 rounded text-xs">{count}</span>
            </button>
          )
        })}
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-gray-400">Loading…</div>
      ) : tracks.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          No tracks in this bucket.
        </div>
      ) : (
        <div className="space-y-2">
          {tracks.map((t) => (
            <div
              key={t.id}
              className="bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-gray-600 transition"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium truncate">{t.title || t.filename}</span>
                    {t.consistency_flag && (
                      <span
                        className="flex items-center gap-1 text-xs text-yellow-300 bg-yellow-900/30 px-2 py-0.5 rounded"
                        title={t.consistency_flag}
                      >
                        <AlertTriangle size={12} />
                        Consistency
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-400 truncate">
                    {t.artist || '—'} {t.album && <span className="text-gray-500">• {t.album}</span>}
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                    <span className="text-gray-500">AI genre:</span>
                    {editingId === t.id ? (
                      <input
                        type="text"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        placeholder="Genre1; Genre2"
                        className="flex-1 max-w-md px-2 py-1 bg-gray-900 border border-gray-600 rounded text-sm"
                        autoFocus
                      />
                    ) : (
                      <span className="font-medium">{t.ai_genre || '—'}</span>
                    )}
                    {t.ai_genre_confidence != null && (
                      <span className={`text-xs px-2 py-0.5 rounded font-mono ${confidenceColor(t.ai_genre_confidence)}`}>
                        {t.ai_genre_confidence}%
                      </span>
                    )}
                    {t.current_genre && t.current_genre !== t.ai_genre && (
                      <span className="text-xs text-gray-500">
                        (current: {t.current_genre})
                      </span>
                    )}
                  </div>

                  {t.consistency_flag && (
                    <div className="mt-1 text-xs text-yellow-300/80 italic">
                      {t.consistency_flag}
                    </div>
                  )}

                  {t.ai_reasoning && (
                    <details className="mt-2">
                      <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300">
                        Reasoning
                      </summary>
                      <p className="mt-1 text-xs text-gray-400 whitespace-pre-wrap pl-2 border-l-2 border-gray-700">
                        {t.ai_reasoning}
                      </p>
                    </details>
                  )}
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  {editingId === t.id ? (
                    <>
                      <button
                        onClick={() => saveEdit(t.id)}
                        disabled={approveMutation.isPending}
                        className="p-2 bg-green-700 hover:bg-green-600 rounded"
                        title="Save & approve"
                      >
                        <Check size={16} />
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="p-2 bg-gray-700 hover:bg-gray-600 rounded"
                        title="Cancel"
                      >
                        <X size={16} />
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => approveMutation.mutate({ trackId: t.id })}
                        disabled={!t.ai_genre || approveMutation.isPending}
                        className="p-2 bg-green-700 hover:bg-green-600 disabled:opacity-40 rounded"
                        title="Approve AI genre"
                      >
                        <Check size={16} />
                      </button>
                      <button
                        onClick={() => startEdit(t)}
                        className="p-2 bg-blue-700 hover:bg-blue-600 rounded"
                        title="Edit & approve"
                      >
                        <Edit3 size={16} />
                      </button>
                      <button
                        onClick={() => rejectMutation.mutate(t.id)}
                        disabled={rejectMutation.isPending}
                        className="p-2 bg-red-700 hover:bg-red-600 rounded"
                        title="Reject"
                      >
                        <X size={16} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default ReviewQueue
