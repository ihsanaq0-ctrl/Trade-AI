import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Search, Sparkles, Bell, Mail, Moon,
  Menu, X, Crown
} from 'lucide-react'
import api from '../api'

export default function Navbar({ session, userPlan = 'free', onToggleMobileSidebar }) {
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [showAiModal, setShowAiModal] = useState(false)
  const [copilotData, setCopilotData] = useState({ account: null, positions: [], loading: false })

  const userName = session?.user?.user_metadata?.full_name
    || (session?.user?.email ? session.user.email.split('@')[0] : 'Trader')
  const plan = (userPlan || 'free').toLowerCase()
  const planLabel = plan === 'elite' ? 'Elite VIP' : plan === 'pro' ? 'Pro Trader' : 'Free Starter'
  const planColor = plan === 'elite' ? '#f59e0b' : plan === 'pro' ? '#00d4ff' : '#10b981'
  const userInitial = userName.charAt(0).toUpperCase() || 'T'

  useEffect(() => {
    if (showAiModal) {
      setCopilotData(prev => ({ ...prev, loading: true }))
      Promise.all([
        api.get('/api/markets/active-account').catch(() => null),
        api.get('/api/trades/positions').catch(() => null)
      ]).then(([acc, pos]) => {
        setCopilotData({
          account: acc && acc.connected && acc.terminal_synced && acc.login ? acc : null,
          positions: pos && Array.isArray(pos.positions) ? pos.positions : [],
          loading: false
        })
      })
    }
  }, [showAiModal])

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    if (searchQuery.trim()) {
      navigate(`/markets?search=${encodeURIComponent(searchQuery.trim())}`)
    }
  }

  return (
    <header style={{
      height: '70px',
      background: '#0c0e15',
      borderBottom: '1px solid #1c2233',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 24px',
      gap: '16px',
      position: 'sticky',
      top: 0,
      zIndex: 40
    }}>
      {/* Mobile Hamburger & Search Bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flex: 1, maxWidth: '520px' }}>
        <button
          onClick={onToggleMobileSidebar}
          style={{
            display: 'none',
            background: '#131722',
            border: '1px solid #1c2233',
            color: '#94a3b8',
            borderRadius: '8px',
            padding: '8px',
            cursor: 'pointer',
            alignItems: 'center',
            justifyContent: 'center'
          }}
          className="mobile-hamburger-btn"
          aria-label="Toggle navigation"
        >
          <Menu size={18} />
        </button>

        <form onSubmit={handleSearchSubmit} style={{
          position: 'relative',
          width: '100%',
          display: 'flex',
          alignItems: 'center'
        }}>
          <Search
            size={16}
            style={{
              position: 'absolute',
              left: '14px',
              color: '#64748b',
              pointerEvents: 'none'
            }}
          />
          <input
            type="text"
            placeholder="Search markets (e.g. EURUSD, XAUUSD)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              height: '42px',
              background: '#131722',
              border: '1px solid #1c2233',
              borderRadius: '22px',
              padding: '0 44px 0 40px',
              color: '#f8fafc',
              fontSize: '13px',
              outline: 'none',
              transition: 'border-color 0.2s',
            }}
            onFocus={(e) => e.target.style.borderColor = '#3b5bf5'}
            onBlur={(e) => e.target.style.borderColor = '#1c2233'}
          />
          <button
            type="submit"
            style={{
              position: 'absolute',
              right: '8px',
              background: '#1a1f30',
              border: '1px solid #252d43',
              borderRadius: '6px',
              padding: '3px 8px',
              fontSize: '11px',
              fontWeight: 600,
              color: '#818cf8',
              cursor: 'pointer'
            }}
          >
            Go
          </button>
        </form>
      </div>

      {/* Right Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        {/* AI Assistant Button */}
        <button
          onClick={() => setShowAiModal(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: 'linear-gradient(135deg, rgba(59, 91, 245, 0.15), rgba(139, 92, 246, 0.15))',
            border: '1px solid rgba(59, 91, 245, 0.4)',
            color: '#818cf8',
            padding: '8px 16px',
            borderRadius: '20px',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.2s'
          }}
          onMouseEnter={(e) => e.currentTarget.style.background = 'linear-gradient(135deg, rgba(59, 91, 245, 0.3), rgba(139, 92, 246, 0.3))'}
          onMouseLeave={(e) => e.currentTarget.style.background = 'linear-gradient(135deg, rgba(59, 91, 245, 0.15), rgba(139, 92, 246, 0.15))'}
        >
          <Sparkles size={14} color="#a5b4fc" />
          <span>AI Assistant</span>
        </button>

        {/* Action Icon Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <button style={{
            background: '#131722',
            border: '1px solid #1c2233',
            width: '38px',
            height: '38px',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#94a3b8',
            cursor: 'pointer',
            position: 'relative'
          }}>
            <Bell size={16} />
            <span style={{
              position: 'absolute',
              top: '9px',
              right: '9px',
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: '#3b5bf5'
            }} />
          </button>

          <button style={{
            background: '#131722',
            border: '1px solid #1c2233',
            width: '38px',
            height: '38px',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#94a3b8',
            cursor: 'pointer'
          }}>
            <Mail size={16} />
          </button>

          <button style={{
            background: '#131722',
            border: '1px solid #1c2233',
            width: '38px',
            height: '38px',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#94a3b8',
            cursor: 'pointer'
          }}>
            <Moon size={16} />
          </button>
        </div>

        {/* Plan Upgrade / Status Pill (Clickable to /pricing) */}
        <Link
          to="/pricing"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '7px 12px',
            borderRadius: '20px',
            background: `${planColor}18`,
            border: `1px solid ${planColor}44`,
            color: planColor,
            fontSize: '12px',
            fontWeight: 700,
            textDecoration: 'none',
            whiteSpace: 'nowrap',
            transition: 'all 0.15s ease'
          }}
          title="View or upgrade membership plan"
        >
          <Crown size={13} />
          <span>{plan === 'free' ? 'Upgrade Pro' : planLabel}</span>
        </Link>

        {/* User Profile (Clickable to /profile) */}
        <Link
          to="/profile"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            paddingLeft: '10px',
            borderLeft: '1px solid #1c2233',
            textDecoration: 'none',
            padding: '5px 10px',
            borderRadius: '12px',
            transition: 'all 0.2s ease',
            cursor: 'pointer'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = '#131722'
            e.currentTarget.style.transform = 'translateY(-1px)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent'
            e.currentTarget.style.transform = 'translateY(0)'
          }}
          title="View your Trader Profile"
        >
          <div style={{
            width: '38px',
            height: '38px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #f59e0b, #ec4899)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
            fontSize: '15px',
            color: '#ffffff',
            boxShadow: '0 2px 8px rgba(245, 158, 11, 0.3)'
          }}>
            {userInitial}
          </div>
          <div className="user-profile-meta" style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc', lineHeight: 1.2 }}>
              {userName}
            </span>
            <span style={{ fontSize: '11px', color: planColor, fontWeight: 600 }}>
              {planLabel}
            </span>
          </div>
        </Link>
      </div>

      {/* AI Assistant Quick Modal */}
      {showAiModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999
        }} onClick={() => setShowAiModal(false)}>
          <div style={{
            width: '460px',
            maxWidth: '92vw',
            background: '#131722',
            border: '1px solid #252d43',
            borderRadius: '16px',
            padding: '24px',
            boxShadow: '0 20px 40px rgba(0,0,0,0.5)'
          }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={18} color="#818cf8" />
                <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#fff', margin: 0 }}>Trade-AI Copilot</h3>
              </div>
              <button onClick={() => setShowAiModal(false)} style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>
            {copilotData.loading ? (
              <div style={{ padding: '24px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
                Querying live terminal telemetries...
              </div>
            ) : copilotData.account ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ background: '#0c0e15', border: '1px solid #1c2233', borderRadius: '12px', padding: '14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '12px', color: '#94a3b8' }}>MT5 Login #{copilotData.account.login}</span>
                    <span style={{ fontSize: '11px', background: 'rgba(16, 185, 129, 0.15)', color: '#10b981', padding: '2px 8px', borderRadius: '6px', fontWeight: 600 }}>
                      Live Connected
                    </span>
                  </div>
                  <div style={{ fontSize: '24px', fontWeight: 800, color: '#ffffff', letterSpacing: '-0.5px' }}>
                    ${Number(copilotData.account.balance || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <div style={{ display: 'flex', gap: '16px', marginTop: '8px', fontSize: '11px', color: '#64748b' }}>
                    <span>Equity: <strong style={{ color: '#cbd5e1' }}>${Number(copilotData.account.equity || 0).toLocaleString()}</strong></span>
                    <span>Leverage: <strong style={{ color: '#cbd5e1' }}>1:{copilotData.account.leverage || 100}</strong></span>
                    <span>Free Margin: <strong style={{ color: '#cbd5e1' }}>${Number(copilotData.account.margin_free || 0).toLocaleString()}</strong></span>
                  </div>
                </div>

                <div style={{ background: '#171b28', padding: '12px 14px', borderRadius: '10px', border: '1px solid #1c2233', fontSize: '12px', color: '#cbd5e1' }}>
                  <div style={{ fontWeight: 600, color: '#ffffff', marginBottom: '4px' }}>Active Positions</div>
                  {copilotData.positions.length > 0 ? (
                    <span>Currently holding <strong>{copilotData.positions.length}</strong> open MT5 positions with active exposure.</span>
                  ) : (
                    <span>No open positions. Zero margin exposure at current market tick.</span>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '10px', marginTop: '4px' }}>
                  <button
                    onClick={() => { setShowAiModal(false); navigate('/markets') }}
                    style={{
                      flex: 1,
                      padding: '10px',
                      background: '#3b5bf5',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '8px',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                  >
                    Open Terminal Chart
                  </button>
                  <button
                    onClick={() => { setShowAiModal(false); navigate('/bot') }}
                    style={{
                      flex: 1,
                      padding: '10px',
                      background: 'rgba(255,255,255,0.06)',
                      color: '#cbd5e1',
                      border: '1px solid #252d43',
                      borderRadius: '8px',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                  >
                    Deploy AI Bot
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ padding: '16px 0', textAlign: 'center' }}>
                <p style={{ color: '#94a3b8', fontSize: '13px', margin: '0 0 16px 0' }}>
                  No MT5 terminal connected yet. Connect your broker account to view live copilot diagnostics.
                </p>
                <button
                  onClick={() => { setShowAiModal(false); navigate('/accounts') }}
                  style={{
                    padding: '10px 18px',
                    background: '#3b5bf5',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '8px',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                >
                  Connect MT5 Account
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  )
}
