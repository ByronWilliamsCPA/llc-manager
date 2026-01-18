import { useState, useEffect, useCallback } from 'react'
import { useApi } from '@/hooks/useApi'
import './ApiStatus.css'

interface HealthStatus {
  status: string
  timestamp?: string
  version?: string
}

type ConnectionState = 'loading' | 'connected' | 'error'

interface StatusDisplayProps {
  state: ConnectionState
  health: HealthStatus | null
  error: string | null
}

function StatusDisplay({ state, health, error }: StatusDisplayProps) {
  const config = {
    loading: {
      className: 'api-status--loading',
      content: <span>Checking API connection...</span>,
    },
    error: {
      className: 'api-status--error',
      content: (
        <div>
          <strong>API Offline</strong>
          <p>{error}</p>
          <small>Make sure the backend is running on port 8000</small>
        </div>
      ),
    },
    connected: {
      className: 'api-status--connected',
      content: (
        <div>
          <strong>API Connected</strong>
          <p>Status: {health?.status || 'healthy'}</p>
          {health?.version && <small>Version: {health.version}</small>}
        </div>
      ),
    },
  }

  const { className, content } = config[state]

  return (
    <div className={`api-status ${className}`}>
      <span className="api-status__indicator"></span>
      {content}
    </div>
  )
}

function useHealthCheck() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const api = useApi()

  const checkHealth = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await api.get<HealthStatus>('/health/live')
      setHealth(response.data)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to connect to API'
      setError(message)
      setHealth(null)
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    checkHealth()
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [checkHealth])

  return { health, error, loading }
}

export function ApiStatus() {
  const { health, error, loading } = useHealthCheck()

  const state: ConnectionState = loading ? 'loading' : error ? 'error' : 'connected'

  return <StatusDisplay state={state} health={health} error={error} />
}
