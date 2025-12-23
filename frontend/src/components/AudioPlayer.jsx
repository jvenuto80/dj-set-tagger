import { useState, useRef, useEffect, useCallback } from 'react'
import { Play, Pause, Volume2, VolumeX } from 'lucide-react'
import { useAudio } from '../contexts/AudioContext'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

// Cache for waveform data to avoid re-fetching
const waveformCache = new Map()

function AudioPlayer({ trackId, compact = false, className = '' }) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [isMuted, setIsMuted] = useState(false)
  const [waveformData, setWaveformData] = useState([])
  const [isLoadingWaveform, setIsLoadingWaveform] = useState(false)
  const [error, setError] = useState(null)
  
  const audioRef = useRef(null)
  const canvasRef = useRef(null)
  
  const { registerAudio, unregisterAudio, playTrack, stopTrack, currentlyPlaying } = useAudio()

  // Stop if another track starts playing
  useEffect(() => {
    if (currentlyPlaying !== null && currentlyPlaying !== trackId && isPlaying) {
      audioRef.current?.pause()
      setIsPlaying(false)
    }
  }, [currentlyPlaying, trackId, isPlaying])

  // Register audio on mount
  useEffect(() => {
    registerAudio(trackId, audioRef)
    return () => unregisterAudio(trackId)
  }, [trackId, registerAudio, unregisterAudio])

  // Generate waveform from audio data
  const generateWaveform = useCallback(async () => {
    // Check cache first
    if (waveformCache.has(trackId)) {
      setWaveformData(waveformCache.get(trackId))
      return
    }

    setIsLoadingWaveform(true)
    
    try {
      const audioUrl = `${API_BASE}/tracks/stream/${trackId}`
      const audioContext = new (window.AudioContext || window.webkitAudioContext)()
      const response = await fetch(audioUrl)
      const arrayBuffer = await response.arrayBuffer()
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer)
      
      // Get channel data
      const channelData = audioBuffer.getChannelData(0)
      const samples = 100 // Number of bars in waveform
      const blockSize = Math.floor(channelData.length / samples)
      const waveform = []
      
      for (let i = 0; i < samples; i++) {
        let sum = 0
        for (let j = 0; j < blockSize; j++) {
          sum += Math.abs(channelData[i * blockSize + j])
        }
        waveform.push(sum / blockSize)
      }
      
      // Normalize
      const max = Math.max(...waveform)
      const normalized = waveform.map(v => max > 0 ? v / max : 0.5)
      
      // Cache the result
      waveformCache.set(trackId, normalized)
      setWaveformData(normalized)
      audioContext.close()
    } catch (err) {
      console.error('Error generating waveform:', err)
      // Generate fallback waveform
      const seed = trackId * 12345
      const fallback = Array.from({ length: 100 }, (_, i) => {
        const x = (seed + i * 7919) % 1000 / 1000
        const base = 0.3 + Math.sin(i * 0.15) * 0.15
        return Math.min(0.95, Math.max(0.15, base + x * 0.4))
      })
      waveformCache.set(trackId, fallback)
      setWaveformData(fallback)
    } finally {
      setIsLoadingWaveform(false)
    }
  }, [trackId])

  // Load waveform on mount
  useEffect(() => {
    generateWaveform()
  }, [generateWaveform])

  // Draw waveform on canvas
  const drawWaveform = () => {
    const canvas = canvasRef.current
    if (!canvas || waveformData.length === 0) return
    
    const ctx = canvas.getContext('2d')
    const rect = canvas.getBoundingClientRect()
    
    // Skip if canvas has no size yet
    if (rect.width === 0 || rect.height === 0) return
    
    const dpr = window.devicePixelRatio || 1
    
    // Set canvas size accounting for device pixel ratio
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    ctx.scale(dpr, dpr)
    
    const width = rect.width
    const height = rect.height
    const barWidth = width / waveformData.length
    const progress = duration > 0 ? currentTime / duration : 0
    
    ctx.clearRect(0, 0, width, height)
    
    waveformData.forEach((value, index) => {
      const x = index * barWidth
      const barHeight = value * height * 0.85
      const y = (height - barHeight) / 2
      
      const barProgress = index / waveformData.length
      
      if (barProgress <= progress) {
        ctx.fillStyle = '#60a5fa' // blue-400
      } else {
        ctx.fillStyle = '#4b5563' // gray-600
      }
      
      const gap = Math.max(1, barWidth * 0.15)
      ctx.fillRect(x, y, barWidth - gap, barHeight)
    })
  }

  // Draw waveform when data or time changes
  useEffect(() => {
    drawWaveform()
  }, [waveformData, currentTime, duration])

  // Redraw on resize
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    
    const observer = new ResizeObserver(() => {
      drawWaveform()
    })
    
    observer.observe(canvas)
    
    // Initial draw after a short delay to ensure canvas is rendered
    const timer = setTimeout(drawWaveform, 50)
    
    return () => {
      observer.disconnect()
      clearTimeout(timer)
    }
  }, [waveformData])

  // Handle play/pause
  const togglePlay = async (e) => {
    e?.preventDefault()
    e?.stopPropagation()
    
    if (!audioRef.current) return
    
    if (isPlaying) {
      audioRef.current.pause()
      setIsPlaying(false)
      stopTrack(trackId)
    } else {
      try {
        setIsLoading(true)
        playTrack(trackId)
        await audioRef.current.play()
        setIsPlaying(true)
      } catch (err) {
        setError('Failed to play audio')
        console.error(err)
        stopTrack(trackId)
      } finally {
        setIsLoading(false)
      }
    }
  }

  // Handle time update
  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime)
    }
  }

  // Handle loaded metadata
  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration)
    }
  }

  // Handle seeking via waveform click
  const handleWaveformClick = (e) => {
    e.preventDefault()
    e.stopPropagation()
    
    if (!audioRef.current || !canvasRef.current || duration === 0) return
    
    const rect = canvasRef.current.getBoundingClientRect()
    const x = e.clientX - rect.left
    const progress = x / rect.width
    const newTime = progress * duration
    
    audioRef.current.currentTime = newTime
    setCurrentTime(newTime)
  }

  // Handle volume
  const toggleMute = (e) => {
    e?.preventDefault()
    e?.stopPropagation()
    
    if (audioRef.current) {
      audioRef.current.muted = !isMuted
      setIsMuted(!isMuted)
    }
  }

  // Handle audio ended
  const handleEnded = () => {
    setIsPlaying(false)
    setCurrentTime(0)
    stopTrack(trackId)
  }

  // Handle pause event (from external source)
  const handlePause = () => {
    setIsPlaying(false)
  }

  // Format time
  const formatTime = (seconds) => {
    if (!seconds || !isFinite(seconds)) return '0:00'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  if (compact) {
    return (
      <div className={`flex items-center gap-2 ${className}`} onClick={e => e.stopPropagation()}>
        <audio
          ref={audioRef}
          src={`${API_BASE}/tracks/stream/${trackId}`}
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={handleEnded}
          onPause={handlePause}
          preload="metadata"
        />
        
        <button
          onClick={togglePlay}
          disabled={isLoading}
          className="w-8 h-8 rounded-full bg-primary-500 hover:bg-primary-400 flex items-center justify-center transition-colors disabled:opacity-50 flex-shrink-0"
        >
          {isLoading ? (
            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : isPlaying ? (
            <Pause className="w-4 h-4 text-white" />
          ) : (
            <Play className="w-4 h-4 text-white ml-0.5" />
          )}
        </button>
        
        <div 
          className="flex-1 h-8 bg-gray-700/50 rounded cursor-pointer relative overflow-hidden min-w-[100px]"
          onClick={handleWaveformClick}
        >
          <canvas
            ref={canvasRef}
            className="w-full h-full"
            style={{ display: 'block' }}
          />
        </div>
        
        <span className="text-xs text-gray-400 w-10 text-right flex-shrink-0">
          {formatTime(currentTime)}
        </span>
      </div>
    )
  }

  return (
    <div className={`bg-gray-800 rounded-lg p-4 ${className}`} onClick={e => e.stopPropagation()}>
      <audio
        ref={audioRef}
        src={`${API_BASE}/tracks/stream/${trackId}`}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={handleEnded}
        onPause={handlePause}
        preload="metadata"
      />
      
      {error && (
        <div className="text-red-400 text-sm mb-2">{error}</div>
      )}
      
      <div className="flex items-center gap-4">
        {/* Play button */}
        <button
          onClick={togglePlay}
          disabled={isLoading}
          className="w-12 h-12 rounded-full bg-primary-500 hover:bg-primary-400 flex items-center justify-center transition-colors disabled:opacity-50 flex-shrink-0"
        >
          {isLoading ? (
            <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : isPlaying ? (
            <Pause className="w-5 h-5 text-white" />
          ) : (
            <Play className="w-5 h-5 text-white ml-0.5" />
          )}
        </button>
        
        {/* Waveform */}
        <div className="flex-1 flex flex-col gap-1">
          <div 
            className="h-12 bg-gray-700/50 rounded cursor-pointer relative overflow-hidden"
            onClick={handleWaveformClick}
          >
            <canvas
              ref={canvasRef}
              className="w-full h-full"
              style={{ display: 'block' }}
            />
          </div>
          
          {/* Time display */}
          <div className="flex justify-between text-xs text-gray-400">
            <span>{formatTime(currentTime)}</span>
            <span>{formatTime(duration)}</span>
          </div>
        </div>
        
        {/* Volume control */}
        <button
          onClick={toggleMute}
          className="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-white transition-colors flex-shrink-0"
        >
          {isMuted ? (
            <VolumeX className="w-5 h-5" />
          ) : (
            <Volume2 className="w-5 h-5" />
          )}
        </button>
      </div>
    </div>
  )
}

// Mini inline player for track lists
export function MiniPlayer({ trackId, className = '' }) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const audioRef = useRef(null)
  
  const { registerAudio, unregisterAudio, playTrack, stopTrack, currentlyPlaying } = useAudio()

  // Stop if another track starts playing
  useEffect(() => {
    if (currentlyPlaying !== null && currentlyPlaying !== trackId && isPlaying) {
      audioRef.current?.pause()
      setIsPlaying(false)
    }
  }, [currentlyPlaying, trackId, isPlaying])

  // Register audio on mount
  useEffect(() => {
    registerAudio(trackId, audioRef)
    return () => unregisterAudio(trackId)
  }, [trackId, registerAudio, unregisterAudio])

  const togglePlay = async (e) => {
    e.preventDefault()
    e.stopPropagation()
    
    if (!audioRef.current) return
    
    if (isPlaying) {
      audioRef.current.pause()
      setIsPlaying(false)
      stopTrack(trackId)
    } else {
      try {
        setIsLoading(true)
        playTrack(trackId)
        await audioRef.current.play()
        setIsPlaying(true)
      } catch (err) {
        console.error('Failed to play:', err)
        stopTrack(trackId)
      } finally {
        setIsLoading(false)
      }
    }
  }

  const handleEnded = () => {
    setIsPlaying(false)
    stopTrack(trackId)
  }

  const handlePause = () => {
    setIsPlaying(false)
  }

  return (
    <div className={`inline-flex items-center ${className}`} onClick={e => e.stopPropagation()}>
      <audio
        ref={audioRef}
        src={`${API_BASE}/tracks/stream/${trackId}`}
        onEnded={handleEnded}
        onPause={handlePause}
        preload="none"
      />
      <button
        onClick={togglePlay}
        disabled={isLoading}
        className="w-7 h-7 rounded-full bg-primary-500/80 hover:bg-primary-500 flex items-center justify-center transition-colors disabled:opacity-50"
      >
        {isLoading ? (
          <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
        ) : isPlaying ? (
          <Pause className="w-3.5 h-3.5 text-white" />
        ) : (
          <Play className="w-3.5 h-3.5 text-white ml-0.5" />
        )}
      </button>
    </div>
  )
}

export default AudioPlayer
