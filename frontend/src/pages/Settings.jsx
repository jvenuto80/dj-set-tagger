import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  Folder, 
  ChevronRight, 
  ChevronUp,
  Save,
  RotateCcw
} from 'lucide-react'
import { getSettings, updateSettings, listDirectories } from '../api'

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
  const [showDirBrowser, setShowDirBrowser] = useState(false)
  const [browsingPath, setBrowsingPath] = useState('/')

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const [formData, setFormData] = useState(null)

  // Initialize form when settings load
  if (settings && !formData) {
    setFormData({
      music_dir: settings.music_dir,
      scan_extensions: settings.scan_extensions.join(', '),
      fuzzy_threshold: settings.fuzzy_threshold,
      tracklists_delay: settings.tracklists_delay,
    })
  }

  const updateMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => {
      queryClient.invalidateQueries(['settings'])
    },
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    
    const updates = {
      music_dir: formData.music_dir,
      scan_extensions: formData.scan_extensions.split(',').map(s => s.trim().toLowerCase()),
      fuzzy_threshold: parseInt(formData.fuzzy_threshold),
      tracklists_delay: parseFloat(formData.tracklists_delay),
    }
    
    updateMutation.mutate(updates)
  }

  const selectDirectory = (path) => {
    setBrowsingPath(path)
  }

  const confirmDirectory = () => {
    setFormData({ ...formData, music_dir: browsingPath })
    setShowDirBrowser(false)
  }

  if (isLoading || !formData) {
    return <div className="text-center py-12 text-gray-400">Loading...</div>
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-gray-400 mt-1">Configure application settings</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Music Directory */}
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">Music Directory</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Directory to scan for audio files
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={formData.music_dir}
                  onChange={(e) => setFormData({ ...formData, music_dir: e.target.value })}
                  className="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                />
                <button
                  type="button"
                  onClick={() => {
                    setBrowsingPath(formData.music_dir || '/')
                    setShowDirBrowser(!showDirBrowser)
                  }}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg"
                >
                  <Folder className="w-5 h-5" />
                </button>
              </div>
            </div>
            
            {showDirBrowser && (
              <div className="space-y-2">
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
          <button
            type="submit"
            disabled={updateMutation.isPending}
            className="px-6 py-2 bg-primary-600 hover:bg-primary-700 rounded-lg flex items-center gap-2 disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {updateMutation.isPending ? 'Saving...' : 'Save Settings'}
          </button>
          
          <button
            type="button"
            onClick={() => setFormData({
              music_dir: settings.music_dir,
              scan_extensions: settings.scan_extensions.join(', '),
              fuzzy_threshold: settings.fuzzy_threshold,
              tracklists_delay: settings.tracklists_delay,
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
    </div>
  )
}

export default Settings
