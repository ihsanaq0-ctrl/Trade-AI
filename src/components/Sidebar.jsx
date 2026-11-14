import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Briefcase, TrendingUp,
  BarChart2, Sparkles, HelpCircle,
  Settings, ShieldCheck, LogOut, X
} from 'lucide-react'
import { supabase } from '../supabase'

const primaryNav = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/accounts', icon: Briefcase, label: 'Portfolio' },
  { path: '/markets', icon: TrendingUp, label: 'Markets' },
  { path: '/analytics', icon: BarChart2, label: 'Analytics' },
  { path: '/bot', icon: Sparkles, label: 'AI Bots' },

]

export default function Sidebar({ session, mobileOpen, onCloseMobile }) {
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = async () => {
    try {
      localStorage.removeItem('trade_profile_name')
      localStorage.removeItem('favPairs')
    } catch {}
    await supabase.auth.signOut()
    navigate('/login')
  }

  return (
    <>
      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          onClick={onCloseMobile}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            backdropFilter: 'blur(3px)',
            zIndex: 90
          }}
        />
      )}

      <aside
        className={`sidebar-container ${mobileOpen ? 'mobile-open' : ''}`}
        style={{
          width: '240px',
          height: '100vh',
          background: '#0c0e15',
          borderRight: '1px solid #1c2233',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
          position: 'sticky',
          top: 0,
          zIndex: 100,
          overflowY: 'auto'
        }}
      >
        {/* Brand Header */}
        <div style={{
          padding: '24px 20px 20px 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {/* Triangular Geometry Logo */}
            <div style={{
              width: '32px',
              height: '32px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              position: 'relative'
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                <path d="M12 3L2 21H22L12 3Z" fill="#f8fafc" />
                <path d="M12 8L5.5 19.5H18.5L12 8Z" fill="#3b5bf5" />
              </svg>
            </div>
            <div>
              <div style={{
                fontWeight: '800',
                fontSize: '17px',
                color: '#ffffff',
                letterSpacing: '-0.3px',
                lineHeight: 1.1
              }}>
                Trade-AI
              </div>
              <div style={{
                fontSize: '9px',
                fontWeight: '700',
                color: '#3b5bf5',
                letterSpacing: '1.2px',
                marginTop: '1px'
              }}>
                TRADING PLATFORM
              </div>
            </div>
          </div>

          {/* Mobile close button */}
          <button
            onClick={onCloseMobile}
            className="mobile-close-btn"
            style={{
              display: 'none',
              background: 'none',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer'
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Navigation Menu */}
        <nav style={{ flex: 1, padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: '3px' }}>
          {primaryNav.map(({ path, icon: Icon, label }) => {
            const isCurrent = location.pathname === path.split('?')[0] && (
              !path.includes('?') || location.search === path.substring(path.indexOf('?'))
            )

            return (
              <NavLink
                key={path}
                to={path}
                onClick={onCloseMobile}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '9px 14px',
                  borderRadius: '12px',
                  textDecoration: 'none',
                  color: isCurrent ? '#ffffff' : '#8590a6',
                  background: isCurrent
                    ? 'linear-gradient(135deg, #3b5bf5, #4f46e5)'
                    : 'transparent',
                  fontWeight: isCurrent ? '600' : '500',
                  fontSize: '13px',
                  boxShadow: isCurrent ? '0 4px 14px rgba(59, 91, 245, 0.35)' : 'none',
                  transition: 'all 0.15s ease'
                }}
                onMouseEnter={(e) => {
                  if (!isCurrent) {
                    e.currentTarget.style.color = '#ffffff'
                    e.currentTarget.style.background = 'rgba(255, 255, 255, 0.04)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isCurrent) {
                    e.currentTarget.style.color = '#8590a6'
                    e.currentTarget.style.background = 'transparent'
                  }
                }}
              >
                <Icon size={17} strokeWidth={isCurrent ? 2.3 : 1.8} />
                <span>{label}</span>
              </NavLink>
            )
          })}
        </nav>

        {/* PRO Plan Badge */}
        <div style={{ padding: '0 14px', marginBottom: '14px' }}>
          <div style={{
            background: 'linear-gradient(135deg, rgba(59, 91, 245, 0.08), rgba(139, 92, 246, 0.08))',
            border: '1px solid rgba(59, 91, 245, 0.2)',
            borderRadius: '12px',
            padding: '14px 16px'
          }}>
            <div style={{
              fontSize: '11px',
              color: '#818cf8',
              fontWeight: '700',
              letterSpacing: '0.5px',
              marginBottom: '3px'
            }}>
              PRO PLAN
            </div>
            <div style={{
              fontSize: '12px',
              color: '#64748b',
              lineHeight: 1.4
            }}>
              All AI strategies & analytics unlocked
            </div>
          </div>
        </div>

        {/* Bottom Auxiliary Links */}
        <div style={{
          padding: '12px 14px 20px 14px',
          borderTop: '1px solid #1c2233',
          display: 'flex',
          flexDirection: 'column',
          gap: '2px'
        }}>
          <button
            onClick={() => window.open('https://t.me/tradeaipro', '_blank')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '8px 14px',
              borderRadius: '10px',
              border: 'none',
              background: 'transparent',
              color: '#8590a6',
              fontSize: '13px',
              fontWeight: '500',
              cursor: 'pointer',
              textAlign: 'left'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = '#ffffff'
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.04)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = '#8590a6'
              e.currentTarget.style.background = 'transparent'
            }}
          >
            <HelpCircle size={16} />
            <span>Help & Support</span>
          </button>

          <NavLink
            to="/settings"
            onClick={onCloseMobile}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '8px 14px',
              borderRadius: '10px',
              textDecoration: 'none',
              color: isActive ? '#ffffff' : '#8590a6',
              background: isActive ? 'rgba(59, 91, 245, 0.15)' : 'transparent',
              fontSize: '13px',
              fontWeight: '500'
            })}
          >
            <Settings size={16} />
            <span>Settings</span>
          </NavLink>

          <button
            onClick={handleLogout}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '8px 14px',
              borderRadius: '10px',
              border: 'none',
              background: 'transparent',
              color: '#f43f5e',
              fontSize: '13px',
              fontWeight: '500',
              cursor: 'pointer',
              textAlign: 'left',
              marginTop: '4px'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(244, 63, 94, 0.08)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent'
            }}
          >
            <LogOut size={16} />
            <span>Logout</span>
          </button>
        </div>
      </aside>
    </>
  )
}