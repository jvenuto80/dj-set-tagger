import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  Folder, 
  ChevronRight, 
  ChevronUp,
  Save,
  RotateCcw,
  Plus,
  Trash2,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Database,
  FileText,
  Settings as SettingsIcon,
  Download,
  Filter,
  Fingerprint,
  Eye,
  EyeOff,
  Info
} from 'lucide-react'
import { getSettings, updateSettings, listDirectories, resyncDatabase, backfillSeriesMarkers, getLogs, clearLogs, getFingerprintStatus, clearDatabase, getAIModels, updateAISettings, getEnrichmentSettings, updateEnrichmentSettings, clearEnrichmentCache, testEnrichment } from '../api'
import { isTauri, pickFolder } from '../tauri'
import ProgressButton from '../components/ProgressButton'

// Native-only: paths are shown as-is
const displayPath = (path) => path || ''

function DirectoryBrowser({ currentPath, onSelect, onConfirm, onCancel }) {
  const [manualPath, setManualPath] = useState('')
  const rootPath = '/'

  const { data: dirs, isLoading, isError, error } = useQuery({
    queryKey: ['directories', currentPath],
    queryFn: () => listDirectories(currentPath),
    retry: false,
  })

  if (isLoading) {
    return (
      <div className="bg-gray-700 rounded-lg border border-gray-600 p-6 text-center">
        <div className="w-5 h-5 border-2 border-primary-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
        <p className="text-sm text-gray-400">Loading folders...</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="bg-gray-700 rounded-lg border border-gray-600 overflow-hidden">
        <div className="p-4 text-center">
          <p className="text-yellow-400 text-sm mb-2">
            {error?.response?.status === 408 
              ? 'This folder is on a slow or network mount and couldn\'t be browsed.'
              : 'Unable to browse this folder.'}
          </p>
          <p className="text-gray-400 text-xs mb-3">You can type the path directly instead.</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              placeholder={displayPath(currentPath) + '/...'}
              className="flex-1 px-3 py-2 bg-gray-600 border border-gray-500 rounded text-sm focus:outline-none focus:border-primary-500"
            />
            <button
              type="button"
              onClick={() => onConfirm(manualPath)}
              disabled={!manualPath}
              className="px-3 py-2 bg-primary-600 hover:bg-primary-700 rounded text-sm disabled:opacity-50"
            >
              Use Path
            </button>
          </div>
        </div>
        <div className="px-4 py-3 bg-gray-600/30 border-t border-gray-600 flex justify-between">
          <button type="button" onClick={() => onSelect(dirs?.parent || rootPath)} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm">
            Back
          </button>
          <button type="button" onClick={onCancel} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm">
            Cancel
          </button>
        </div>
      </div>
    )
  }

  // Don't let user navigate above root
  const canGoUp = dirs?.parent && currentPath !== rootPath

  return (
    <div className="bg-gray-700 rounded-lg border border-gray-600 overflow-hidden">
      {/* Current location bar */}
      <div className="px-4 py-2 bg-gray-600/50 border-b border-gray-600 flex items-center gap-2">
        <Folder className="w-4 h-4 text-primary-400 flex-shrink-0" />
        <span className="text-sm text-white truncate">{displayPath(currentPath)}</span>
      </div>
      
      {/* Directory list */}
      <div className="max-h-56 overflow-auto">
        {canGoUp && (
          <button
            onClick={() => onSelect(dirs.parent)}
            className="w-full flex items-center gap-2 px-4 py-2 hover:bg-gray-600 text-left text-gray-300"
          >
            <ChevronUp className="w-4 h-4" />
            <span>Back</span>
          </button>
        )}
        {dirs?.directories?.map((dir) => (
          <button
            key={dir.path}
            onClick={() => onSelect(dir.path)}
            className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-gray-600 text-left"
          >
            <Folder className="w-4 h-4 text-primary-500 flex-shrink-0" />
            <span className="truncate flex-1">{dir.name}</span>
            <ChevronRight className="w-4 h-4 text-gray-500" />
          </button>
        ))}
        {dirs?.directories?.length === 0 && (
          <div className="p-4 text-gray-400 text-sm text-center">No subfolders</div>
        )}
      </div>
      
      {/* Action bar */}
      <div className="px-4 py-3 bg-gray-600/30 border-t border-gray-600 flex items-center justify-between gap-2">
        <span className="text-xs text-gray-400 truncate hidden sm:block">
          {displayPath(currentPath)}
        </span>
        <div className="flex gap-2 ml-auto">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(currentPath)}
            className="px-3 py-1.5 bg-primary-600 hover:bg-primary-700 rounded text-sm"
          >
            Select Folder
          </button>
        </div>
      </div>
    </div>
  )
}

function Settings() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('settings') // 'settings' or 'logs'
  const [showDirBrowser, setShowDirBrowser] = useState(false)
  const [browsingPath, setBrowsingPath] = useState('/')
  const [browsingIndex, setBrowsingIndex] = useState(0)  // Which directory we're browsing for
  const [resyncResult, setResyncResult] = useState(null)
  const [backfillResult, setBackfillResult] = useState(null)
  const [clearDbResult, setClearDbResult] = useState(null)
  const [clearDbConfirm, setClearDbConfirm] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [logLevel, setLogLevel] = useState('')
  const logContainerRef = useRef(null)

  const { data: settings, isLoading, isError, error } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
    retry: 5,
    retryDelay: 1000,
  })

  const { data: fpStatus } = useQuery({
    queryKey: ['fingerprintStatus'],
    queryFn: getFingerprintStatus,
    refetchInterval: 10000, // Refresh every 10s
  })

  const [formData, setFormData] = useState(null)

  // Initialize form when settings load
  useEffect(() => {
    if (settings && !formData) {
      setFormData({
        music_dirs: settings.music_dirs || [settings.music_dir],
        scan_extensions: (settings.scan_extensions || []).join(', '),
        fuzzy_threshold: settings.fuzzy_threshold,
        tracklists_delay: settings.tracklists_delay,
        min_duration_minutes: settings.min_duration_minutes || 0,
        acoustid_api_key: settings.acoustid_api_key || '',
      })
    }
  }, [settings])

  const updateMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => {
      queryClient.invalidateQueries(['settings'])
    },
  })

  const resyncMutation = useMutation({
    mutationFn: resyncDatabase,
    onSuccess: (data) => {
      setResyncResult(data)
      queryClient.invalidateQueries(['tracks'])
      queryClient.invalidateQueries(['series'])
      queryClient.invalidateQueries(['taggedSeries'])
    },
    onError: (error) => {
      setResyncResult({ error: error.message || 'Resync failed' })
    }
  })

  const backfillMutation = useMutation({
    mutationFn: backfillSeriesMarkers,
    onSuccess: (data) => {
      setBackfillResult(data)
    },
    onError: (error) => {
      setBackfillResult({ error: error.message || 'Backfill failed' })
    }
  })

  const clearDbMutation = useMutation({
    mutationFn: clearDatabase,
    onSuccess: (data) => {
      setClearDbResult(data)
      setClearDbConfirm(false)
      queryClient.invalidateQueries(['tracks'])
      queryClient.invalidateQueries(['series'])
      queryClient.invalidateQueries(['taggedSeries'])
      queryClient.invalidateQueries(['recentTracks'])
      queryClient.invalidateQueries(['duplicates'])
    },
    onError: (error) => {
      setClearDbResult({ error: error.message || 'Clear failed' })
      setClearDbConfirm(false)
    }
  })

  // AI Model
  const { data: aiModels, refetch: refetchAIModels, isLoading: isLoadingAIModels } = useQuery({
    queryKey: ['aiModels'],
    queryFn: getAIModels,
    retry: 1,
  })

  const aiSettingsMutation = useMutation({
    mutationFn: updateAISettings,
    onSuccess: () => {
      queryClient.invalidateQueries(['aiModels'])
    },
  })

  // Enrichment (MusicBrainz / Last.fm / AcoustID / SearXNG)
  const { data: enrichmentCfg, refetch: refetchEnrichment } = useQuery({
    queryKey: ['enrichmentSettings'],
    queryFn: getEnrichmentSettings,
    retry: 1,
  })

  const [enrichmentForm, setEnrichmentForm] = useState({
    enabled: true,
    use_web_search: true,
    lastfm_api_key: '',
    searxng_url: '',
    discogs_token: '',
    spotify_client_id: '',
    spotify_client_secret: '',
  })
  const [enrichmentTestResult, setEnrichmentTestResult] = useState(null)
  const [enrichmentTestQuery, setEnrichmentTestQuery] = useState({ artist: '', title: '' })

  useEffect(() => {
    if (enrichmentCfg) {
      setEnrichmentForm((prev) => ({
        ...prev,
        enabled: enrichmentCfg.enabled,
        use_web_search: enrichmentCfg.use_web_search,
        searxng_url: enrichmentCfg.searxng_url || '',
        // Keep whatever was typed; only sync key fields when blank
        lastfm_api_key: prev.lastfm_api_key,
        discogs_token: prev.discogs_token,
        spotify_client_id: prev.spotify_client_id,
        spotify_client_secret: prev.spotify_client_secret,
      }))
    }
  }, [enrichmentCfg])

  const enrichmentSaveMutation = useMutation({
    mutationFn: updateEnrichmentSettings,
    onSuccess: () => {
      refetchEnrichment()
    },
  })

  const enrichmentClearMutation = useMutation({
    mutationFn: clearEnrichmentCache,
  })

  const enrichmentTestMutation = useMutation({
    mutationFn: ({ artist, title }) => testEnrichment(artist, title),
    onSuccess: (data) => setEnrichmentTestResult(data),
    onError: (err) => setEnrichmentTestResult({ error: err?.message || 'test failed' }),
  })

  // Logs query
  const { data: logsData, isLoading: isLoadingLogs, refetch: refetchLogs } = useQuery({
    queryKey: ['logs', logLevel],
    queryFn: () => getLogs(500, logLevel || null),
    enabled: activeTab === 'logs',
    refetchInterval: activeTab === 'logs' ? 5000 : false, // Auto-refresh every 5s when viewing logs
  })

  const clearLogsMutation = useMutation({
    mutationFn: clearLogs,
    onSuccess: () => {
      queryClient.invalidateQueries(['logs'])
    },
  })

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (logContainerRef.current && logsData?.logs) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logsData?.logs])

  const handleSubmit = (e) => {
    e.preventDefault()
    
    // Filter out empty directories
    const validDirs = formData.music_dirs.filter(d => d && d.trim())
    
    const updates = {
      music_dirs: validDirs,
      music_dir: validDirs[0] || '',  // Keep legacy field in sync
      scan_extensions: formData.scan_extensions.split(',').map(s => s.trim().toLowerCase()),
      fuzzy_threshold: parseInt(formData.fuzzy_threshold),
      tracklists_delay: parseFloat(formData.tracklists_delay),
      min_duration_minutes: parseInt(formData.min_duration_minutes) || 0,
      acoustid_api_key: formData.acoustid_api_key || '',
    }
    
    updateMutation.mutate(updates)
  }

  const selectDirectory = (path) => {
    setBrowsingPath(path)
  }
  
  const addMountPoint = async () => {
    if (isTauri()) {
      const selected = await pickFolder()
      if (selected) {
        setFormData({ ...formData, music_dirs: [...formData.music_dirs, selected] })
      }
    } else {
      setFormData({ ...formData, music_dirs: [...formData.music_dirs, ''] })
    }
  }
  
  const removeMountPoint = (index) => {
    if (formData.music_dirs.length <= 1) return  // Keep at least one
    const newDirs = formData.music_dirs.filter((_, i) => i !== index)
    setFormData({ ...formData, music_dirs: newDirs })
  }
  
  const updateMountPoint = (index, value) => {
    const newDirs = [...formData.music_dirs]
    newDirs[index] = value
    setFormData({ ...formData, music_dirs: newDirs })
  }

  if (isError) {
    return (
      <div className="text-center py-12">
        <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-3" />
        <p className="text-red-400 mb-2">Failed to load settings</p>
        <p className="text-gray-500 text-sm">{error?.message || 'Backend not reachable'}</p>
      </div>
    )
  }

  if (isLoading || !formData) {
    return <div className="text-center py-12 text-gray-400">Loading...</div>
  }

  // Helper to get log level color
  const getLogLevelColor = (line) => {
    if (line.includes('| ERROR')) return 'text-red-400'
    if (line.includes('| WARNING')) return 'text-yellow-400'
    if (line.includes('| INFO')) return 'text-blue-400'
    if (line.includes('| DEBUG')) return 'text-gray-500'
    return 'text-gray-300'
  }

  // Download logs
  const downloadLogs = () => {
    if (!logsData?.logs) return
    const blob = new Blob([logsData.logs.join('\n')], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `setlist-logs-${new Date().toISOString().split('T')[0]}.log`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-gray-400 mt-1">Configure application settings</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-gray-700">
        <button
          onClick={() => setActiveTab('settings')}
          className={`px-4 py-2 flex items-center gap-2 border-b-2 transition-colors ${
            activeTab === 'settings'
              ? 'border-primary-500 text-white'
              : 'border-transparent text-gray-400 hover:text-white'
          }`}
        >
          <SettingsIcon className="w-4 h-4" />
          Settings
        </button>
        <button
          onClick={() => setActiveTab('logs')}
          className={`px-4 py-2 flex items-center gap-2 border-b-2 transition-colors ${
            activeTab === 'logs'
              ? 'border-primary-500 text-white'
              : 'border-transparent text-gray-400 hover:text-white'
          }`}
        >
          <FileText className="w-4 h-4" />
          Logs
        </button>
      </div>

      {/* Settings Tab */}
      {activeTab === 'settings' && (
        <>
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Music Directories */}
            <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">Music Folders</h2>
                <button
                  type="button"
                  onClick={addMountPoint}
                  className="flex items-center gap-1 px-3 py-1.5 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm"
                >
                  <Plus className="w-4 h-4" />
                  Add Folder
                </button>
              </div>
          
          <div className="space-y-3">
            {formData.music_dirs.map((dir, index) => (
              <div key={index} className="space-y-2">
                <div className="flex gap-2 items-center">
                  <input
                    type="text"
                    value={displayPath(dir)}
                    onChange={(e) => {
                      updateMountPoint(index, e.target.value)
                    }}
                    placeholder="Click Browse or type a path (e.g. /Users/you/Music)"
                    className="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm focus:outline-none focus:border-primary-500"
                  />
                  <button
                    type="button"
                    onClick={async () => {
                      if (isTauri()) {
                        const selected = await pickFolder()
                        if (selected) {
                          const newDirs = [...formData.music_dirs]
                          newDirs[index] = selected
                          setFormData({ ...formData, music_dirs: newDirs })
                        }
                      } else {
                        const startPath = dir || '/'
                        setBrowsingPath(startPath)
                        setBrowsingIndex(index)
                        setShowDirBrowser(showDirBrowser && browsingIndex === index ? false : true)
                      }
                    }}
                    className="px-4 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm flex items-center gap-2"
                  >
                    <Folder className="w-4 h-4" />
                    <span className="hidden sm:inline">Browse</span>
                  </button>
                  {formData.music_dirs.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeMountPoint(index)}
                      className="px-3 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg"
                      title="Remove"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
                
                {showDirBrowser && browsingIndex === index && (
                  <DirectoryBrowser
                    currentPath={browsingPath}
                    onSelect={selectDirectory}
                    onConfirm={(path) => {
                      const newDirs = [...formData.music_dirs]
                      newDirs[index] = path
                      setFormData({ ...formData, music_dirs: newDirs })
                      setShowDirBrowser(false)
                    }}
                    onCancel={() => setShowDirBrowser(false)}
                  />
                )}
              </div>
            ))}
          </div>
          
          <p className="text-sm text-gray-500 mt-3">
            Choose the folders on your computer that contain music to scan and tag.
          </p>
        </div>

        {/* Scan Settings */}
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">Scan Settings</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                File Extensions (comma-separated)
              </label>
              <input
                type="text"
                value={formData.scan_extensions}
                onChange={(e) => setFormData({ ...formData, scan_extensions: e.target.value })}
                className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                placeholder="mp3, flac, wav, m4a"
              />
            </div>
            
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Minimum Track Duration (minutes)
              </label>
              <input
                type="number"
                min="0"
                max="999"
                value={formData.min_duration_minutes}
                onChange={(e) => setFormData({ ...formData, min_duration_minutes: e.target.value })}
                className="w-32 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
              />
              <p className="text-sm text-gray-500 mt-1">
                Filter out tracks shorter than this. Use 30-60 to exclude singles. Set to 0 to disable.
              </p>
            </div>
          </div>
        </div>

        {/* Matching Settings */}
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">Matching Settings</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Fuzzy Match Threshold (0-100)
              </label>
              <input
                type="number"
                min="0"
                max="100"
                value={formData.fuzzy_threshold}
                onChange={(e) => setFormData({ ...formData, fuzzy_threshold: e.target.value })}
                className="w-32 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
              />
              <p className="text-sm text-gray-500 mt-1">
                Higher values require closer matches. Recommended: 70-85
              </p>
            </div>
            
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Request Delay (seconds)
              </label>
              <input
                type="number"
                min="0.5"
                max="10"
                step="0.5"
                value={formData.tracklists_delay}
                onChange={(e) => setFormData({ ...formData, tracklists_delay: e.target.value })}
                className="w-32 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
              />
              <p className="text-sm text-gray-500 mt-1">
                Delay between requests to 1001Tracklists to avoid rate limiting
              </p>
            </div>
          </div>
        </div>

        {/* Audio Fingerprinting / AcoustID */}
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <div className="flex items-center gap-3 mb-4">
            <Fingerprint className="w-5 h-5 text-purple-500" />
            <h2 className="text-lg font-semibold">Audio Fingerprinting</h2>
          </div>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                AcoustID API Key
              </label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={formData.acoustid_api_key}
                    onChange={(e) => setFormData({ ...formData, acoustid_api_key: e.target.value })}
                    placeholder="Enter your AcoustID API key"
                    className="w-full px-4 py-2 pr-10 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-300"
                  >
                    {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <p className="text-sm text-gray-500 mt-1">
                Get a free <strong className="text-gray-400">Developer API key</strong> from{' '}
                <a 
                  href="https://acoustid.org/new-application" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-primary-400 hover:underline"
                >
                  acoustid.org/new-application
                </a>
                {' '}to enable track identification. Sign in and register a new application to get your key.
              </p>
            </div>

            {/* Fingerprint Status */}
            {fpStatus && (
              <div className="bg-gray-700/50 rounded-lg p-4">
                <h3 className="text-sm font-medium mb-2">Status</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-400">Chromaprint:</span>{' '}
                    <span className={fpStatus.fpcalc_available ? 'text-green-400' : 'text-red-400'}>
                      {fpStatus.fpcalc_available ? '✓ Available' : '✗ Not found'}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-400">AcoustID API:</span>{' '}
                    <span className={fpStatus.acoustid_configured ? 'text-green-400' : 'text-yellow-400'}>
                      {fpStatus.acoustid_configured ? '✓ Configured' : '○ Not configured'}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-400">Fingerprinted:</span>{' '}
                    <span className="text-gray-200">
                      {fpStatus.fingerprinted_tracks} / {fpStatus.total_tracks} tracks
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Save Button */}
        <div className="flex gap-4">
          <ProgressButton
            type="submit"
            isLoading={updateMutation.isPending}
            loadingText="Saving..."
            icon={<Save className="w-4 h-4" />}
            variant="primary"
          >
            Save Settings
          </ProgressButton>
          
          <button
            type="button"
            onClick={() => setFormData({
              music_dirs: settings.music_dirs || [settings.music_dir],
              scan_extensions: (settings.scan_extensions || []).join(', '),
              fuzzy_threshold: settings.fuzzy_threshold,
              tracklists_delay: settings.tracklists_delay,
              min_duration_minutes: settings.min_duration_minutes || 0,
              acoustid_api_key: settings.acoustid_api_key || '',
            })}
            className="px-6 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg flex items-center gap-2"
          >
            <RotateCcw className="w-4 h-4" />
            Reset
          </button>
        </div>
        
        {updateMutation.isSuccess && (
          <div className="text-green-500 text-sm">Settings saved successfully!</div>
        )}
        
        {updateMutation.isError && (
          <div className="text-red-500 text-sm">
            Error: {updateMutation.error?.response?.data?.detail || 'Failed to save settings'}
          </div>
        )}
      </form>

      {/* Database Maintenance */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex items-center gap-3 mb-4">
          <Database className="w-5 h-5 text-primary-500" />
          <h2 className="text-lg font-semibold">Database Maintenance</h2>
        </div>
        
        <div className="space-y-4">
          <div>
            <p className="text-gray-400 text-sm mb-3">
              Resync the database with actual file tags. This reads the tags from your music files 
              and updates the database to match. Use this if files were tagged externally or if the 
              database is out of sync with your files.
            </p>
            
            <ProgressButton
              onClick={() => {
                setResyncResult(null)
                resyncMutation.mutate()
              }}
              isLoading={resyncMutation.isPending}
              loadingText="Resyncing database..."
              icon={<RefreshCw className="w-4 h-4" />}
              variant="warning"
            >
              Resync Database
            </ProgressButton>
          </div>
          
          {resyncResult && (
            <div className={`p-4 rounded-lg ${resyncResult.error ? 'bg-red-900/50 border border-red-700' : 'bg-gray-700'}`}>
              {resyncResult.error ? (
                <div className="flex items-center gap-2 text-red-400">
                  <AlertTriangle className="w-5 h-5" />
                  <span>{resyncResult.error}</span>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-green-400">
                    <CheckCircle2 className="w-5 h-5" />
                    <span>{resyncResult.message}</span>
                  </div>
                  <div className="text-sm text-gray-400">
                    <div>Tracks checked: {resyncResult.checked}</div>
                    <div>Tracks updated: {resyncResult.updated}</div>
                    {resyncResult.errors?.length > 0 && (
                      <div className="mt-2">
                        <div className="text-amber-400">Errors ({resyncResult.errors.length}):</div>
                        <div className="max-h-32 overflow-auto mt-1">
                          {resyncResult.errors.slice(0, 10).map((err, i) => (
                            <div key={i} className="text-red-400 text-xs truncate">
                              {err.filename}: {err.error}
                            </div>
                          ))}
                          {resyncResult.errors.length > 10 && (
                            <div className="text-gray-500 text-xs">
                              ...and {resyncResult.errors.length - 10} more
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
          
          {/* Backfill Series Markers */}
          <div className="border-t border-gray-700 pt-4 mt-4">
            <p className="text-gray-400 text-sm mb-3">
              Write series markers to file metadata for all tagged tracks. This ensures series 
              tagging is preserved if you reinstall or move files to a new system.
            </p>
            
            <ProgressButton
              onClick={() => {
                setBackfillResult(null)
                backfillMutation.mutate()
              }}
              isLoading={backfillMutation.isPending}
              loadingText="Writing series markers..."
              icon={<Save className="w-4 h-4" />}
              variant="primary"
            >
              Backfill Series Markers
            </ProgressButton>
          </div>
          
          {backfillResult && (
            <div className={`p-4 rounded-lg ${backfillResult.error ? 'bg-red-900/50 border border-red-700' : 'bg-gray-700'}`}>
              {backfillResult.error ? (
                <div className="flex items-center gap-2 text-red-400">
                  <AlertTriangle className="w-5 h-5" />
                  <span>{backfillResult.error}</span>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-green-400">
                    <CheckCircle2 className="w-5 h-5" />
                    <span>{backfillResult.message}</span>
                  </div>
                  <div className="text-sm text-gray-400">
                    <div>Tracks updated: {backfillResult.updated}</div>
                    <div>Tracks skipped: {backfillResult.skipped}</div>
                    {backfillResult.errors?.length > 0 && (
                      <div className="mt-2">
                        <div className="text-amber-400">Errors ({backfillResult.errors.length}):</div>
                        <div className="max-h-32 overflow-auto mt-1">
                          {backfillResult.errors.slice(0, 10).map((err, i) => (
                            <div key={i} className="text-red-400 text-xs truncate">
                              {err.filename}: {err.error}
                            </div>
                          ))}
                          {backfillResult.errors.length > 10 && (
                            <div className="text-gray-500 text-xs">
                              ...and {backfillResult.errors.length - 10} more
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* AI Model (Ollama) */}
          <div className="border-t border-gray-700 pt-4 mt-4">
            <h3 className="text-lg font-semibold text-white mb-2 flex items-center gap-2">
              <SettingsIcon className="w-5 h-5" />
              AI Genre Classification (Ollama)
            </h3>
            <p className="text-gray-400 text-sm mb-3">
              Choose which locally-installed Ollama model to use for genre classification during scans.
              The selected model must be pulled in Ollama (<code className="bg-gray-700 px-1 rounded">ollama pull &lt;model&gt;</code>).
            </p>

            {isLoadingAIModels ? (
              <div className="text-sm text-gray-400">Loading models...</div>
            ) : aiModels?.available_models?.length > 0 ? (
              <div className="flex items-center gap-3">
                <select
                  value={aiModels.current_model || ''}
                  onChange={(e) => aiSettingsMutation.mutate({ model: e.target.value })}
                  disabled={aiSettingsMutation.isPending}
                  className="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm flex-1 max-w-md"
                >
                  {!aiModels.available_models.includes(aiModels.current_model) && (
                    <option value={aiModels.current_model}>
                      {aiModels.current_model} (not installed)
                    </option>
                  )}
                  {aiModels.available_models.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
                <button
                  onClick={() => refetchAIModels()}
                  className="p-2 text-gray-400 hover:text-white"
                  title="Refresh model list"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
                {aiSettingsMutation.isPending && (
                  <span className="text-xs text-gray-400">Saving...</span>
                )}
                {aiSettingsMutation.isSuccess && !aiSettingsMutation.isPending && (
                  <span className="text-xs text-green-400 flex items-center gap-1">
                    <CheckCircle2 className="w-4 h-4" /> Saved
                  </span>
                )}
              </div>
            ) : (
              <div className="bg-yellow-900/30 border border-yellow-700 rounded p-3 text-sm text-yellow-200">
                <div className="flex items-center gap-2 mb-1">
                  <AlertTriangle className="w-4 h-4" />
                  <strong>No Ollama models detected</strong>
                </div>
                <p className="text-xs">
                  Make sure Ollama is running (<code className="bg-gray-800 px-1 rounded">ollama serve</code>)
                  and you have at least one model installed
                  (e.g., <code className="bg-gray-800 px-1 rounded">ollama pull qwen2.5:7b</code>).
                  Current model: <code className="bg-gray-800 px-1 rounded">{aiModels?.current_model || 'unknown'}</code>
                </p>
                <button
                  onClick={() => refetchAIModels()}
                  className="mt-2 text-xs underline hover:text-yellow-100"
                >
                  Retry
                </button>
              </div>
            )}

            {/* Two-pass classification (reasoning + classifier) */}
            <div className="mt-4 pt-4 border-t border-gray-700/60">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <h4 className="text-sm font-semibold text-white">Two-Pass Classification</h4>
                  <p className="text-xs text-gray-400">
                    Pass 1: reasoning model analyzes all signals (think mode). Pass 2: classifier picks final genres from taxonomy.
                    Slower but significantly more accurate for ambiguous tracks.
                  </p>
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm text-gray-200 mb-2">
                <input
                  type="checkbox"
                  checked={!!aiModels?.two_pass_enabled}
                  onChange={(e) => aiSettingsMutation.mutate({ two_pass_enabled: e.target.checked })}
                  disabled={aiSettingsMutation.isPending}
                />
                Enable two-pass (reasoning → classifier)
              </label>
              <div className="flex items-center gap-3">
                <label className="text-xs text-gray-400 w-32">Reasoning model:</label>
                <select
                  value={aiModels?.reasoning_model || ''}
                  onChange={(e) => aiSettingsMutation.mutate({ reasoning_model: e.target.value })}
                  disabled={aiSettingsMutation.isPending || !aiModels?.available_models?.length}
                  className="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm flex-1 max-w-md"
                >
                  {aiModels?.reasoning_model && !aiModels?.available_models?.includes(aiModels.reasoning_model) && (
                    <option value={aiModels.reasoning_model}>
                      {aiModels.reasoning_model} (not installed)
                    </option>
                  )}
                  {aiModels?.available_models?.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-gray-500 mt-2">
                Tip: <code className="bg-gray-800 px-1 rounded">deepseek-r1:latest</code> or any qwen3 model with reasoning works well as the investigator.
              </p>
            </div>
          </div>

          {/* AI Enrichment (MusicBrainz / Last.fm / AcoustID / SearXNG) */}
          <div className="border-t border-gray-700 pt-4 mt-4">
            <h3 className="text-lg font-semibold text-white mb-2 flex items-center gap-2">
              <SettingsIcon className="w-5 h-5" />
              AI Enrichment Sources
            </h3>
            <p className="text-gray-400 text-sm mb-3">
              Before classifying, fetch authoritative tags from external sources and feed them to the model.
              This dramatically improves accuracy for obscure artists. Results are cached per artist for 90 days.
            </p>

            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={enrichmentForm.enabled}
                  onChange={(e) => setEnrichmentForm({ ...enrichmentForm, enabled: e.target.checked })}
                  className="accent-primary-500"
                />
                <span>Enable enrichment (MusicBrainz + AcoustID always on when keys present)</span>
              </label>

              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={enrichmentForm.use_web_search}
                  onChange={(e) => setEnrichmentForm({ ...enrichmentForm, use_web_search: e.target.checked })}
                  className="accent-primary-500"
                />
                <span>Use SearXNG web search as fallback grounding</span>
              </label>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Last.fm API Key</label>
                <input
                  type="password"
                  value={enrichmentForm.lastfm_api_key}
                  onChange={(e) => setEnrichmentForm({ ...enrichmentForm, lastfm_api_key: e.target.value })}
                  placeholder={enrichmentCfg?.lastfm_api_key_set ? '••••••• (saved) — type to replace' : 'Get one at last.fm/api/account/create'}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Free at{' '}
                  <a href="https://www.last.fm/api/account/create" target="_blank" rel="noopener noreferrer"
                     className="text-primary-400 hover:underline">last.fm/api/account/create</a>.
                  Provides user-voted artist + track tags.
                </p>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">SearXNG URL</label>
                <input
                  type="text"
                  value={enrichmentForm.searxng_url}
                  onChange={(e) => setEnrichmentForm({ ...enrichmentForm, searxng_url: e.target.value })}
                  placeholder="http://10.0.30.159:8093"
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Base URL of a SearXNG instance with the <code className="bg-gray-800 px-1 rounded">json</code> format enabled.
                </p>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">AcoustID</label>
                <p className="text-xs text-gray-500">
                  Uses the AcoustID API key configured in the <strong>Audio Fingerprinting</strong> section above.
                  Pulls canonical artist/title and release-group tags from audio fingerprints.
                </p>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Discogs Token</label>
                <input
                  type="password"
                  value={enrichmentForm.discogs_token}
                  onChange={(e) => setEnrichmentForm({ ...enrichmentForm, discogs_token: e.target.value })}
                  placeholder={enrichmentCfg?.discogs_token_set ? '••••••• (saved) — type to replace' : 'Personal access token'}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Free at{' '}
                  <a href="https://www.discogs.com/settings/developers" target="_blank" rel="noopener noreferrer"
                     className="text-primary-400 hover:underline">discogs.com/settings/developers</a>.
                  Provides curated <code className="bg-gray-800 px-1 rounded">genre[]</code> + <code className="bg-gray-800 px-1 rounded">style[]</code> per release.
                </p>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Spotify Client ID</label>
                <input
                  type="text"
                  value={enrichmentForm.spotify_client_id}
                  onChange={(e) => setEnrichmentForm({ ...enrichmentForm, spotify_client_id: e.target.value })}
                  placeholder={enrichmentCfg?.spotify_client_id_set ? '••••••• (saved) — type to replace' : 'From developer.spotify.com app'}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Spotify Client Secret</label>
                <input
                  type="password"
                  value={enrichmentForm.spotify_client_secret}
                  onChange={(e) => setEnrichmentForm({ ...enrichmentForm, spotify_client_secret: e.target.value })}
                  placeholder={enrichmentCfg?.spotify_client_secret_set ? '••••••• (saved) — type to replace' : 'From developer.spotify.com app'}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Create a free app at{' '}
                  <a href="https://developer.spotify.com/dashboard" target="_blank" rel="noopener noreferrer"
                     className="text-primary-400 hover:underline">developer.spotify.com/dashboard</a>.
                  Uses client-credentials flow (no user login). Gives curated <code className="bg-gray-800 px-1 rounded">genres[]</code> per artist.
                </p>
              </div>

              <div className="flex flex-wrap gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => enrichmentSaveMutation.mutate(enrichmentForm)}
                  disabled={enrichmentSaveMutation.isPending}
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm disabled:opacity-50"
                >
                  {enrichmentSaveMutation.isPending ? 'Saving...' : 'Save Enrichment Settings'}
                </button>
                <button
                  type="button"
                  onClick={() => enrichmentClearMutation.mutate()}
                  disabled={enrichmentClearMutation.isPending}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm disabled:opacity-50"
                >
                  {enrichmentClearMutation.isPending ? 'Clearing...' : 'Clear Enrichment Cache'}
                </button>
                {enrichmentSaveMutation.isSuccess && !enrichmentSaveMutation.isPending && (
                  <span className="text-xs text-green-400 flex items-center gap-1">
                    <CheckCircle2 className="w-4 h-4" /> Saved
                  </span>
                )}
                {enrichmentClearMutation.isSuccess && (
                  <span className="text-xs text-green-400">
                    Cleared {enrichmentClearMutation.data?.rows_deleted ?? 0} cached entries
                  </span>
                )}
              </div>

              {/* Live test */}
              <div className="bg-gray-700/40 rounded-lg p-3 mt-3">
                <p className="text-sm text-gray-300 mb-2">Test enrichment for an artist/title:</p>
                <div className="flex flex-wrap gap-2">
                  <input
                    type="text"
                    placeholder="Artist"
                    value={enrichmentTestQuery.artist}
                    onChange={(e) => setEnrichmentTestQuery({ ...enrichmentTestQuery, artist: e.target.value })}
                    className="flex-1 min-w-[180px] px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm"
                  />
                  <input
                    type="text"
                    placeholder="Title (optional)"
                    value={enrichmentTestQuery.title}
                    onChange={(e) => setEnrichmentTestQuery({ ...enrichmentTestQuery, title: e.target.value })}
                    className="flex-1 min-w-[180px] px-3 py-1.5 bg-gray-800 border border-gray-600 rounded text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      if (enrichmentTestQuery.artist.trim()) {
                        enrichmentTestMutation.mutate(enrichmentTestQuery)
                      }
                    }}
                    disabled={enrichmentTestMutation.isPending || !enrichmentTestQuery.artist.trim()}
                    className="px-3 py-1.5 bg-primary-600 hover:bg-primary-700 rounded text-sm disabled:opacity-50"
                  >
                    {enrichmentTestMutation.isPending ? 'Testing...' : 'Test'}
                  </button>
                </div>
                {enrichmentTestResult && (
                  <pre className="mt-2 text-xs bg-gray-900 border border-gray-700 rounded p-2 max-h-64 overflow-auto whitespace-pre-wrap text-gray-300">
                    {enrichmentTestResult.error
                      ? `Error: ${enrichmentTestResult.error}`
                      : enrichmentTestResult.prompt_block || JSON.stringify(enrichmentTestResult, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          </div>

          {/* Clear Database */}
          <div className="border-t border-gray-700 pt-4 mt-4">
            <p className="text-gray-400 text-sm mb-3">
              Remove all tracks, matches, and scan data from the database. Your settings will be preserved.
              Use this to start fresh if the database has stale or incorrect data.
            </p>
            
            {!clearDbConfirm ? (
              <ProgressButton
                onClick={() => setClearDbConfirm(true)}
                isLoading={false}
                icon={<Trash2 className="w-4 h-4" />}
                variant="danger"
              >
                Clear Database
              </ProgressButton>
            ) : (
              <div className="flex items-center gap-3">
                <span className="text-red-400 text-sm font-medium">Are you sure? This cannot be undone.</span>
                <ProgressButton
                  onClick={() => {
                    setClearDbResult(null)
                    clearDbMutation.mutate()
                  }}
                  isLoading={clearDbMutation.isPending}
                  loadingText="Clearing..."
                  icon={<Trash2 className="w-4 h-4" />}
                  variant="danger"
                >
                  Yes, Clear Everything
                </ProgressButton>
                <button
                  onClick={() => setClearDbConfirm(false)}
                  className="px-3 py-2 text-sm text-gray-400 hover:text-white"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
          
          {clearDbResult && (
            <div className={`p-4 rounded-lg ${clearDbResult.error ? 'bg-red-900/50 border border-red-700' : 'bg-gray-700'}`}>
              {clearDbResult.error ? (
                <div className="flex items-center gap-2 text-red-400">
                  <AlertTriangle className="w-5 h-5" />
                  <span>{clearDbResult.error}</span>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-green-400">
                  <CheckCircle2 className="w-5 h-5" />
                  <span>{clearDbResult.message}</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
        </>
      )}

      {/* Logs Tab */}
      {activeTab === 'logs' && (
        <div className="space-y-4">
          {/* Log Controls */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="relative">
                <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <select
                  value={logLevel}
                  onChange={(e) => setLogLevel(e.target.value)}
                  className="pl-10 pr-8 py-2 bg-gray-800 border border-gray-700 rounded-lg appearance-none focus:outline-none focus:border-primary-500"
                >
                  <option value="">All Levels</option>
                  <option value="DEBUG">Debug</option>
                  <option value="INFO">Info</option>
                  <option value="WARNING">Warning</option>
                  <option value="ERROR">Error</option>
                </select>
              </div>
              
              <button
                onClick={() => refetchLogs()}
                className="px-3 py-2 bg-gray-800 border border-gray-700 hover:border-gray-600 rounded-lg flex items-center gap-2"
              >
                <RefreshCw className={`w-4 h-4 ${isLoadingLogs ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
            
            <div className="flex items-center gap-2">
              <button
                onClick={downloadLogs}
                disabled={!logsData?.logs?.length}
                className="px-3 py-2 bg-gray-800 border border-gray-700 hover:border-gray-600 rounded-lg flex items-center gap-2 disabled:opacity-50"
              >
                <Download className="w-4 h-4" />
                Download
              </button>
              
              <button
                onClick={() => {
                  if (confirm('Clear all logs?')) {
                    clearLogsMutation.mutate()
                  }
                }}
                disabled={clearLogsMutation.isPending}
                className="px-3 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-900 rounded-lg flex items-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Clear
              </button>
            </div>
          </div>
          
          {/* Log Info */}
          {logsData && (
            <div className="text-sm text-gray-400">
              Showing {logsData.showing} of {logsData.total_lines} log entries
              {logLevel && ` (filtered by ${logLevel})`}
            </div>
          )}
          
          {/* Log Output */}
          <div 
            ref={logContainerRef}
            className="bg-gray-900 rounded-xl border border-gray-700 p-4 h-[600px] overflow-auto font-mono text-sm"
          >
            {isLoadingLogs ? (
              <div className="text-gray-400 text-center py-8">Loading logs...</div>
            ) : logsData?.logs?.length > 0 ? (
              <div className="space-y-1">
                {logsData.logs.map((line, i) => (
                  <div key={i} className={`${getLogLevelColor(line)} whitespace-pre-wrap break-all`}>
                    {line}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-gray-400 text-center py-8">
                {logsData?.message || 'No logs available'}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default Settings
