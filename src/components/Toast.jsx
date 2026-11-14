import { createContext, useContext, useState, useCallback } from 'react'

const ToastContext = createContext(null)

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const addToast = useCallback((message, type = 'error', duration = 6000) => {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { id, message, type }])
    if (duration > 0) {
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id))
      }, duration)
    }
  }, [])

  const error = useCallback((msg) => addToast(msg, 'error'), [addToast])
  const warn = useCallback((msg) => addToast(msg, 'warn'), [addToast])
  const success = useCallback((msg) => addToast(msg, 'success'), [addToast])
  const info = useCallback((msg) => addToast(msg, 'info', 4000), [addToast])

  return (
    <ToastContext.Provider value={{ toasts, addToast, error, warn, success, info }}>
      {children}
      <div style={{
        position: 'fixed', bottom: 20, right: 20, zIndex: 9999,
        display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 400
      }}>
        {toasts.map(t => {
          const colors = {
            error: { bg: '#ff475722', border: '#ff4757', icon: 'X' },
            warn: { bg: '#f59e0b22', border: '#f59e0b', icon: '!' },
            success: { bg: '#00ff8822', border: '#00ff88', icon: 'OK' },
            info: { bg: '#00d4ff22', border: '#00d4ff', icon: 'i' },
          }
          const c = colors[t.type] || colors.error
          return (
            <div key={t.id} onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))} style={{
              background: '#0d1117', border: `1px solid ${c.border}`,
              borderLeft: `3px solid ${c.border}`, borderRadius: 10, padding: '12px 16px',
              color: '#e1e4e8', fontSize: 13, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 10,
              animation: 'slideIn 0.3s ease', boxShadow: '0 4px 20px rgba(0,0,0,0.4)'
            }}>
              <span style={{ width: 20, height: 20, borderRadius: '50%', background: c.bg, color: c.border, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0 }}>{c.icon}</span>
              <span style={{ flex: 1 }}>{t.message}</span>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be inside ToastProvider')
  return ctx
}
