import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react'

const AudioContext = createContext(null)

export function AudioProvider({ children }) {
  const [currentlyPlaying, setCurrentlyPlaying] = useState(null)
  const audioRefs = useRef(new Map())

  // Register an audio element
  const registerAudio = useCallback((trackId, audioRef) => {
    audioRefs.current.set(trackId, audioRef)
  }, [])

  // Unregister an audio element
  const unregisterAudio = useCallback((trackId) => {
    audioRefs.current.delete(trackId)
  }, [])

  // Play a track (stops any other playing track)
  const playTrack = useCallback((trackId) => {
    // Stop all other tracks
    audioRefs.current.forEach((ref, id) => {
      if (id !== trackId && ref?.current) {
        ref.current.pause()
        ref.current.currentTime = 0
      }
    })
    setCurrentlyPlaying(trackId)
  }, [])

  // Stop current track
  const stopTrack = useCallback((trackId) => {
    if (currentlyPlaying === trackId) {
      setCurrentlyPlaying(null)
    }
  }, [currentlyPlaying])

  // Check if a track is currently playing
  const isTrackPlaying = useCallback((trackId) => {
    return currentlyPlaying === trackId
  }, [currentlyPlaying])

  // Keyboard shortcuts: Space to toggle play/pause, Left/Right to seek
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Don't intercept if user is typing in an input
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return

      if (e.code === 'Space' && currentlyPlaying !== null) {
        e.preventDefault()
        const ref = audioRefs.current.get(currentlyPlaying)
        if (ref?.current) {
          if (ref.current.paused) {
            ref.current.play()
          } else {
            ref.current.pause()
          }
        }
      } else if (e.code === 'ArrowLeft' && currentlyPlaying !== null) {
        e.preventDefault()
        const ref = audioRefs.current.get(currentlyPlaying)
        if (ref?.current) ref.current.currentTime = Math.max(0, ref.current.currentTime - 5)
      } else if (e.code === 'ArrowRight' && currentlyPlaying !== null) {
        e.preventDefault()
        const ref = audioRefs.current.get(currentlyPlaying)
        if (ref?.current) ref.current.currentTime = Math.min(ref.current.duration, ref.current.currentTime + 5)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [currentlyPlaying])

  return (
    <AudioContext.Provider value={{
      currentlyPlaying,
      registerAudio,
      unregisterAudio,
      playTrack,
      stopTrack,
      isTrackPlaying
    }}>
      {children}
    </AudioContext.Provider>
  )
}

export function useAudio() {
  const context = useContext(AudioContext)
  if (!context) {
    throw new Error('useAudio must be used within an AudioProvider')
  }
  return context
}
