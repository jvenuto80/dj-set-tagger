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
  Filter
} from 'lucide-react'
import { getSettings, updateSettings, listDirectories, resyncDatabase, getLogs, clearLogs } from '../api'
import ProgressButton from '../components/ProgressButton'

function DirectoryBrowser({ currentPath, onSelect }) {
  const { data: dirs, isLoading } = useQuery({
    queryKey: ['directories', currentPath],
    queryFn: () => listDirectories(currentPath),
  })

  if (isLoading) {
    return <div className="p-4 text-gray-400">Loading...</div>
  }

  return (
    <div className="bg-gray-700 rounded-lg max-h-64 overflow-auto">
      {dirs?.parent && (
        <button
          onClick={() => onSelect(dirs.parent)}
          className="w-full flex items-center gap-2 px-4 py-2 hover:bg-gray-600 text-left"
        >
          <ChevronUp className="w-4 h-4" />
          <span>..</span>
        </button>
      )}
      {dirs?.directories?.map((dir) => (
        <button
          key={dir.path}
          onClick={() => onSelect(dir.path)}
          className="w-full flex items-center gap-2 px-4 py-2 hover:bg-gray-600 text-left"
        >
          <Folder className="w-4 h-4 text-primary-500" />
          <span className="truncate">{dir.name}</span>
          <ChevronRight className="w-4 h-4 ml-auto" />
        </button>
      ))}
      {dirs?.directories?.length === 0 && (
        <div className="p-4 text-gray-400 text-sm">No subdirectories</div>
      )}
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
  const [logLevel, setLogLevel] = useState('')
  const logContainerRef = useRef(null)

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const [formData, setFormData] = useState(null)

  // Initialize form when settings load
  if (settings && !formData) {
    setFormData({
      music_dirs: settings.music_dirs || [settings.music_dir],
      scan_extensions: settings.scan_extensions.join(', '),
      fuzzy_threshold: settings.fuzzy_threshold,
      tracklists_delay: settings.tracklists_delay,
      min_duration_minutes: settings.min_duration_minutes || 0,
    })
  }

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
    }
    
    updateMutation.mutate(updates)
  }

  const selectDirectory = (path) => {
    setBrowsingPath(path)
  }

  const confirmDirectory = () => {
    const newDirs = [...formData.music_dirs]
    newDirs[browsingIndex] = browsingPath
    setFormData({ ...formData, music_dirs: newDirs })
    setShowDirBrowser(false)
  }
  
  const addMountPoint = () => {
    setFormData({ ...formData, music_dirs: [...formData.music_dirs, ''] })
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
    a.download = `dj-set-tagger-logs-${new Date().toISOString().split('T')[0]}.log`
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
                <h2 className="text-lg font-semibold">Music Directories</h2>
                <button
                  type="button"
                  onClick={addMountPoint}
                  className="flex items-center gap-1 px-3 py-1.5 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm"
                >
                  <Plus className="w-4 h-4" />
                  Add Mount Point
                </button>
              </div>
          
          <div className="space-y-3">
            {formData.music_dirs.map((dir, index) => (
              <div key={index} className="space-y-2">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={dir}
                    onChange={(e) => updateMountPoint(index, e.target.value)}
                    placeholder="/path/to/music"
                    className="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setBrowsingPath(dir || '/')
                      setBrowsingIndex(index)
                      setShowDirBrowser(showDirBrowser && browsingIndex === index ? false : true)
                    }}
                    className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg"
                    title="Browse"
                  >
                    <Folder className="w-5 h-5" />
                  </button>
                  {formData.music_dirs.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeMountPoint(index)}
                      className="px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg"
                      title="Remove"
                    >
                      <Trash2 className="w-5 h-5" />
                    </button>
                  )}
                </div>
                
                {showDirBrowser && browsingIndex === index && (
                  <div className="space-y-2 ml-4 border-l-2 border-gray-600 pl-4">
                    <div className="text-sm text-gray-400">
                      Current: <span className="text-white">{browsingPath}</span>
                    </div>
                    <DirectoryBrowser
                      currentPath={browsingPath}
                      onSelect={selectDirectory}
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={confirmDirectory}
                        className="px-4 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg text-sm"
                      >
                        Select This Directory
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowDirBrowser(false)}
                        className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
          
          <p className="text-sm text-gray-500 mt-3">
            Add multiple mount points to scan music from different locations.
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
              scan_extensions: settings.scan_extensions.join(', '),
              fuzzy_threshold: settings.fuzzy_threshold,
              tracklists_delay: settings.tracklists_delay,
              min_duration_minutes: settings.min_duration_minutes || 0,
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
