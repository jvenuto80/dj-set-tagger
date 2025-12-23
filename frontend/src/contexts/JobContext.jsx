import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getTaggingJobStatus } from '../api'

const JobContext = createContext(null)

const STORAGE_KEY = 'setlist_activeJob'

export function JobProvider({ children }) {
  const queryClient = useQueryClient()
  const [backgroundJob, setBackgroundJob] = useState(null)
  const [toast, setToast] = useState(null)
  const pollIntervalRef = useRef(null)

  // Core polling function
  const doPoll = useCallback(async (jobId) => {
    try {
      const status = await getTaggingJobStatus(jobId)
      
      setBackgroundJob({
        jobId,
        status: status.status,
        processed: status.processed || 0,
        total: status.total || 0,
        written: status.written || 0,
        errors: status.errors || []
      })
      
      if (status.status === 'completed') {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current)
          pollIntervalRef.current = null
        }
        localStorage.removeItem(STORAGE_KEY)
        
        queryClient.invalidateQueries(['series'])
        queryClient.invalidateQueries(['taggedSeries'])
        queryClient.invalidateQueries(['tracks'])
        
        if (status.errors?.length > 0) {
          setToast({
            type: 'error',
            message: `${status.written}/${status.total} files written. ${status.errors.length} errors:`,
            errors: status.errors
          })
        } else {
          setToast({
            type: 'success',
            message: `Successfully tagged ${status.written} tracks`
          })
        }
        
        setTimeout(() => setBackgroundJob(null), 2000)
      } else if (status.status === 'not_found') {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current)
          pollIntervalRef.current = null
        }
        localStorage.removeItem(STORAGE_KEY)
        setBackgroundJob(null)
      }
    } catch (error) {
      console.error('Error polling job status:', error)
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
      localStorage.removeItem(STORAGE_KEY)
      setBackgroundJob(null)
    }
  }, [queryClient])

  // Start polling for a job
  const startPolling = useCallback((jobId) => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
    }
    
    // Save to localStorage
    localStorage.setItem(STORAGE_KEY, jobId)
    
    setBackgroundJob({
      jobId,
      status: 'starting',
      processed: 0,
      total: 0,
      written: 0,
      errors: []
    })
    
    doPoll(jobId)
    pollIntervalRef.current = setInterval(() => doPoll(jobId), 500)
  }, [doPoll])

  // On mount, check localStorage and resume polling if needed
  useEffect(() => {
    const savedJobId = localStorage.getItem(STORAGE_KEY)
    if (savedJobId && !pollIntervalRef.current) {
      console.log('JobContext: Resuming polling for:', savedJobId)
      setBackgroundJob({
        jobId: savedJobId,
        status: 'resuming',
        processed: 0,
        total: 0,
        written: 0,
        errors: []
      })
      doPoll(savedJobId)
      pollIntervalRef.current = setInterval(() => doPoll(savedJobId), 500)
    }
    
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
    }
  }, [doPoll])

  const clearToast = useCallback(() => setToast(null), [])

  return (
    <JobContext.Provider value={{ 
      backgroundJob, 
      toast, 
      clearToast,
      startPolling 
    }}>
      {children}
    </JobContext.Provider>
  )
}

export function useJob() {
  const context = useContext(JobContext)
  if (!context) {
    throw new Error('useJob must be used within a JobProvider')
  }
  return context
}
