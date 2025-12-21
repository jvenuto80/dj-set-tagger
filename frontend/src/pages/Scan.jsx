import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { 
  FolderSearch, 
  Play, 
  Square, 
  CheckCircle,
  AlertCircle,
  Loader2
} from 'lucide-react'
import { startScan, getScanStatus, stopScan, getSettings } from '../api'
import ProgressButton from '../components/ProgressButton'

function Scan() {
  const queryClient = useQueryClient()
  const [isScanning, setIsScanning] = useState(false)

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['scan-status'],
    queryFn: getScanStatus,
    refetchInterval: isScanning ? 500 : false,
  })

  // Sync local state with server state
  useEffect(() => {
    if (status?.running === false && isScanning) {
      // Scan just finished
      setIsScanning(false)
      queryClient.invalidateQueries(['tracks'])
    } else if (status?.running === true && !isScanning) {
      // Scan started externally
      setIsScanning(true)
    }
  }, [status?.running, isScanning, queryClient])

  const startMutation = useMutation({
    mutationFn: startScan,
    onSuccess: () => {
      setIsScanning(true)
      refetchStatus()
    },
  })

  const stopMutation = useMutation({
    mutationFn: stopScan,
    onSuccess: () => {
      setIsScanning(false)
      refetchStatus()
    },
  })

  const progress = status?.total > 0 
    ? Math.round((status.progress / status.total) * 100) 
    : 0

  // Determine if we should show running state (use server status as source of truth)
  const showRunning = status?.running === true

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Scan Library</h1>
        <p className="text-gray-400 mt-1">
          Scan your music directory for audio files
        </p>
      </div>

      {/* Current Directories */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Scan Directories</h2>
        <div className="space-y-3">
          {(settings?.music_dirs || [settings?.music_dir || '/music']).map((dir, index) => (
            <div key={index} className="flex items-center gap-4">
              <FolderSearch className="w-6 h-6 text-gray-400" />
              <div className="flex-1">
                <p className="font-medium">{dir}</p>
                {index === 0 && (
                  <p className="text-sm text-gray-400">
                    Scanning for: {settings?.scan_extensions?.join(', ') || 'mp3, flac, wav, m4a, aac, ogg'}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 pt-4 border-t border-gray-700">
          <Link 
            to="/settings"
            className="text-primary-500 hover:text-primary-400 text-sm"
          >
            Manage Directories
          </Link>
        </div>
      </div>

      {/* Scan Status */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <h2 className="text-lg font-semibold mb-4">Scan Status</h2>
        
        {showRunning ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <Loader2 className="w-5 h-5 text-primary-500 animate-spin" />
              <span>Scanning in progress...</span>
            </div>
            
            {/* Progress Bar */}
            <div className="relative h-4 bg-gray-700 rounded-full overflow-hidden">
              <div 
                className="absolute inset-y-0 left-0 bg-primary-500 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
              <div className="absolute inset-0 flex items-center justify-center text-xs font-medium">
                {progress}%
              </div>
            </div>
            
            {/* Current File */}
            {status.current_file && (
              <p className="text-sm text-gray-400 truncate">
                Current: {status.current_file}
              </p>
            )}
            
            {/* Stats */}
            <div className="grid grid-cols-3 gap-4 text-center">
              <div className="bg-gray-700/50 rounded-lg p-3">
                <p className="text-2xl font-bold">{status.files_found || 0}</p>
                <p className="text-sm text-gray-400">Found</p>
              </div>
              <div className="bg-gray-700/50 rounded-lg p-3">
                <p className="text-2xl font-bold text-green-500">{status.files_added || 0}</p>
                <p className="text-sm text-gray-400">Added</p>
              </div>
              <div className="bg-gray-700/50 rounded-lg p-3">
                <p className="text-2xl font-bold text-gray-400">{status.files_skipped || 0}</p>
                <p className="text-sm text-gray-400">Skipped</p>
              </div>
            </div>
            
            <ProgressButton
              onClick={() => stopMutation.mutate()}
              isLoading={stopMutation.isPending}
              loadingText="Stopping..."
              icon={<Square className="w-4 h-4" />}
              variant="danger"
              className="w-full"
            >
              Stop Scan
            </ProgressButton>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Show last scan results if we have any data */}
            {(status?.files_found > 0 || status?.files_added > 0 || status?.files_skipped > 0) ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3 text-green-500">
                  <CheckCircle className="w-5 h-5" />
                  <span>Scan completed</span>
                </div>
                
                {/* Results Stats */}
                <div className="grid grid-cols-4 gap-3 text-center">
                  <div className="bg-gray-700/50 rounded-lg p-3">
                    <p className="text-xl font-bold">{status.files_found || 0}</p>
                    <p className="text-xs text-gray-400">Found</p>
                  </div>
                  <div className="bg-gray-700/50 rounded-lg p-3">
                    <p className="text-xl font-bold text-green-500">{status.files_added || 0}</p>
                    <p className="text-xs text-gray-400">Added</p>
                  </div>
                  <div className="bg-gray-700/50 rounded-lg p-3">
                    <p className="text-xl font-bold text-gray-400">{status.files_skipped || 0}</p>
                    <p className="text-xs text-gray-400">Skipped</p>
                  </div>
                  <div className="bg-gray-700/50 rounded-lg p-3">
                    <p className="text-xl font-bold text-yellow-500">{status.files_filtered || 0}</p>
                    <p className="text-xs text-gray-400">Filtered</p>
                  </div>
                </div>
                
                {status.files_skipped > 0 && status.files_added === 0 && (
                  <p className="text-sm text-gray-400">
                    All files were already in the database. Scan a different directory or clear database to re-scan.
                  </p>
                )}
                
                {status.files_filtered > 0 && (
                  <p className="text-sm text-gray-400">
                    {status.files_filtered} files were filtered due to minimum duration setting.
                  </p>
                )}
              </div>
            ) : status?.errors?.length > 0 ? (
              <div className="flex items-center gap-3 text-red-500">
                <AlertCircle className="w-5 h-5" />
                <span>Scan completed with errors</span>
              </div>
            ) : (
              <div className="flex items-center gap-3 text-gray-400">
                <FolderSearch className="w-5 h-5" />
                <span>Ready to scan</span>
              </div>
            )}
            
            <ProgressButton
              onClick={() => startMutation.mutate(settings?.music_dir)}
              isLoading={startMutation.isPending}
              loadingText="Starting..."
              icon={<Play className="w-4 h-4" />}
              variant="primary"
              className="w-full"
            >
              Start Scan
            </ProgressButton>
          </div>
        )}
        
        {/* Errors */}
        {status?.errors?.length > 0 && (
          <div className="mt-4 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
            <h3 className="font-medium text-red-400 mb-2">Errors ({status.errors.length})</h3>
            <ul className="text-sm text-gray-400 space-y-1 max-h-32 overflow-auto">
              {status.errors.map((error, i) => (
                <li key={i} className="truncate">{error}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Next Steps */}
      {!showRunning && (status?.files_added > 0 || status?.files_skipped > 0) && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">Next Steps</h2>
          <div className="flex gap-4">
            <Link
              to="/tracks"
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg"
            >
              View Tracks
            </Link>
            <Link
              to="/tracks?status=pending"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg"
            >
              Start Matching
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

export default Scan
