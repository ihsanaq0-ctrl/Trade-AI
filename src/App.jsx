import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
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
import Login from './pages/Login'
import ConnectionBanner from './components/ConnectionBanner'
import { ToastProvider } from './components/Toast'
import './index.css'

function ProtectedRoute({ session, children }) {
  if (!session) {
    return <Navigate to="/login" replace />
  }
  return children
}

function Layout() {
  const location = useLocation()
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const isLoginPage = location.pathname === '/login'

  useEffect(() => {
    // 1. Check active Supabase session
    supabase.auth.getSession().then(({ data: { session: activeSession } }) => {
      setSession(activeSession || null)
      setLoading(false)
    }).catch((err) => {
      console.error('Session retrieval error:', err)
      setSession(null)
      setLoading(false)
    })

    // 2. Listen to real auth state changes (login, token refresh, logout)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession || null)
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

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#0c0e15', overflow: 'hidden' }}>
      {!isLoginPage && session && (
        <Sidebar
          session={session}
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
              session={session}
              onToggleMobileSidebar={() => setMobileOpen(!mobileOpen)}
            />
            <ConnectionBanner />
          </>
        )}
        
        <Routes>
          <Route path="/" element={<Navigate to={session ? '/dashboard' : '/login'} replace />} />
          <Route path="/login" element={!session ? <Login /> : <Navigate to="/dashboard" replace />} />
          
          <Route path="/dashboard" element={<ProtectedRoute session={session}><Dashboard session={session} /></ProtectedRoute>} />
          <Route path="/markets" element={<ProtectedRoute session={session}><Markets session={session} /></ProtectedRoute>} />
          <Route path="/bot" element={<ProtectedRoute session={session}><Bot session={session} /></ProtectedRoute>} />
          <Route path="/analytics" element={<ProtectedRoute session={session}><Analytics session={session} /></ProtectedRoute>} />
          <Route path="/accounts" element={<ProtectedRoute session={session}><Accounts session={session} /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute session={session}><Settings session={session} /></ProtectedRoute>} />
          <Route path="/profile" element={<ProtectedRoute session={session}><Profile session={session} /></ProtectedRoute>} />
          <Route path="/admin" element={<ProtectedRoute session={session}><Admin session={session} /></ProtectedRoute>} />
          
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
