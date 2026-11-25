import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useEffect, useState, useCallback } from 'react'
import { supabase } from './supabase'
import Sidebar from './components/Sidebar'
import Navbar from './components/Navbar'
import Dashboard from './pages/Dashboard'
import Markets from './pages/Markets'
import Bot from './pages/Bot'
import Analytics from './pages/Analytics'
import Accounts from './pages/Accounts'
import Admin from './pages/Admin'
import Settings from './pages/Settings'
import Profile from './pages/Profile'
import Pricing from './pages/Pricing'
import Login from './pages/Login'
import ConnectionBanner from './components/ConnectionBanner'
import { ToastProvider } from './components/Toast'
import api from './api'
import './index.css'

function ProtectedRoute({ session, children }) {
  if (!session) {
    return <Navigate to="/login" replace />
  }
  return children
}

// Clear stale unscoped or cross-user browser localStorage whenever user ID switches
function syncUserLocalStorage(userId) {
  try {
    const prevUid = localStorage.getItem('tradeai_active_uid')
    if (prevUid && userId && prevUid !== userId) {
      localStorage.removeItem('trade_profile_name')
      localStorage.removeItem('favPairs')
      localStorage.removeItem('trade_bot_risk_defaults')
    }
    if (userId) {
      localStorage.setItem('tradeai_active_uid', userId)
    } else {
      localStorage.removeItem('tradeai_active_uid')
      localStorage.removeItem('trade_profile_name')
      localStorage.removeItem('favPairs')
    }
  } catch {
    // ignore storage errors
  }
}

function Layout() {
  const location = useLocation()
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [userPlan, setUserPlan] = useState('free')
  const [isOwner, setIsOwner] = useState(false)
  const isLoginPage = location.pathname === '/login'

  const fetchUserPlan = useCallback(async (activeSession) => {
    const s = activeSession ?? session
    if (!s?.access_token) {
      setUserPlan('free')
      setIsOwner(false)
      return
    }
    try {
      const res = await api.get('/api/payments/license', {
        headers: { Authorization: `Bearer ${s.access_token}` }
      })
      setUserPlan((res?.plan || 'free').toLowerCase())
      setIsOwner(Boolean(res?.is_owner))
    } catch {
      setUserPlan('free')
      setIsOwner(false)
    }
  }, [session])

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session: activeSession } }) => {
      syncUserLocalStorage(activeSession?.user?.id || null)
      setSession(activeSession || null)
      setLoading(false)
      if (activeSession) fetchUserPlan(activeSession)
    }).catch((err) => {
      console.error('Session retrieval error:', err)
      setSession(null)
      setLoading(false)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, newSession) => {
      syncUserLocalStorage(newSession?.user?.id || null)
      setSession(newSession || null)
      if (newSession) {
        fetchUserPlan(newSession)
      } else {
        setUserPlan('free')
        setIsOwner(false)
      }
    })

    return () => subscription.unsubscribe()
  }, [])

  if (loading) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center',
        justifyContent: 'center', height: '100vh',
        background: '#0c0e15', flexDirection: 'column', gap: '16px'
      }}>
        <div style={{
          width: '44px', height: '44px',
          background: 'linear-gradient(135deg, #3b5bf5, #8b5cf6)',
          borderRadius: '12px', animation: 'pulseGlow 1.5s infinite'
        }} />
        <p style={{ color: '#94a3b8', fontSize: '13px', fontWeight: 500 }}>Loading Trading Platform...</p>
      </div>
    )
  }

  const uidKey = session?.user?.id || 'guest'

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#0c0e15', overflow: 'hidden' }}>
      {!isLoginPage && session && (
        <Sidebar
          key={`sidebar-${uidKey}`}
          session={session}
          userPlan={userPlan}
          mobileOpen={mobileOpen}
          onCloseMobile={() => setMobileOpen(false)}
        />
      )}

      <div style={{
        flex: 1,
        overflow: 'auto',
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0
      }}>
        {!isLoginPage && session && (
          <>
            <Navbar
              key={`navbar-${uidKey}`}
              session={session}
              userPlan={userPlan}
              onToggleMobileSidebar={() => setMobileOpen(!mobileOpen)}
            />
            <ConnectionBanner key={`conn-${uidKey}`} />
          </>
        )}

        <Routes>
          <Route path="/" element={<Navigate to={session ? '/dashboard' : '/login'} replace />} />
          <Route path="/login" element={!session ? <Login /> : <Navigate to="/dashboard" replace />} />

          <Route path="/dashboard" element={<ProtectedRoute session={session}><Dashboard key={uidKey} session={session} /></ProtectedRoute>} />
          <Route path="/markets" element={<ProtectedRoute session={session}><Markets key={uidKey} session={session} /></ProtectedRoute>} />
          <Route path="/bot" element={<ProtectedRoute session={session}><Bot key={uidKey} session={session} userPlan={userPlan} /></ProtectedRoute>} />
          <Route path="/analytics" element={<ProtectedRoute session={session}><Analytics key={uidKey} session={session} /></ProtectedRoute>} />
          <Route path="/accounts" element={<ProtectedRoute session={session}><Accounts key={uidKey} session={session} /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute session={session}><Settings key={uidKey} session={session} /></ProtectedRoute>} />
          <Route path="/profile" element={<ProtectedRoute session={session}><Profile key={uidKey} session={session} userPlan={userPlan} /></ProtectedRoute>} />
          <Route path="/pricing" element={<ProtectedRoute session={session}><Pricing key={uidKey} session={session} userPlan={userPlan} isOwner={isOwner} onPlanUpdated={() => fetchUserPlan(session)} /></ProtectedRoute>} />
          <Route path="/admin" element={<ProtectedRoute session={session}><Admin key={uidKey} session={session} /></ProtectedRoute>} />

          <Route path="*" element={<Navigate to={session ? '/dashboard' : '/login'} replace />} />
        </Routes>
      </div>
    </div>
  )
}

function App() {
  return (
    <ToastProvider>
      <Router>
        <Layout />
      </Router>
    </ToastProvider>
  )
}

export default App
