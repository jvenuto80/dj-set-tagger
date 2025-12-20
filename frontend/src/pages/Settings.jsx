import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  Folder, 
  ChevronRight, 
  ChevronUp,
  Save,
  RotateCcw,
  Plus,
  Trash2
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
  const [browsingIndex, setBrowsingIndex] = useState(0)  // Which directory we're browsing for

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-gray-400 mt-1">Configure application settings</p>
      </div>

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
    </div>
  )
}

export default Settings
