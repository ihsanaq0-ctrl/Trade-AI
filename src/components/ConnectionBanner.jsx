import { useState, useEffect, useRef } from 'react'
import { Wifi, WifiOff, CheckCircle2 } from 'lucide-react'
import api from '../api'

export default function ConnectionBanner() {
  const [status, setStatus] = useState({ ok: true, checking: true })
  const intervalRef = useRef(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    const check = async () => {
      const result = await api.checkHealth()
      setStatus({ ...result, checking: false })
    }
    check()
    intervalRef.current = setInterval(check, 20000)
    return () => clearInterval(intervalRef.current)
  }, [])

  // Don't show anything while checking or if dismissed
  if (status.checking) return null
  if (status.ok) return null
  if (dismissed) return null

  return (
    <div style={{
      background: 'rgba(245, 158, 11, 0.06)',
      borderBottom: '1px solid rgba(245, 158, 11, 0.15)',
      padding: '8px 24px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '12px'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <WifiOff size={15} color="#f59e0b" />
        <span style={{ color: '#fbbf24', fontSize: '12px', fontWeight: '500' }}>
          Backend API not reachable
        </span>
        <span style={{ color: '#64748b', fontSize: '12px' }}>
          — Start with: <code style={{
            background: '#131722',
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '11px',
            color: '#94a3b8'
          }}>cd backend && uvicorn main:app --port 8002 --reload</code>
        </span>
      </div>
      <button
        onClick={() => setDismissed(true)}
        style={{
          background: 'none',
          border: 'none',
          color: '#64748b',
          cursor: 'pointer',
          fontSize: '12px',
          padding: '2px 6px'
        }}
      >
        Dismiss
      </button>
    </div>
  )
}
