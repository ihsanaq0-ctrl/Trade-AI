import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  User, Mail, Shield, Key, Calendar, Clock,
  CheckCircle2, Copy, Check, Sparkles, ArrowUpRight,
  Settings as SettingsIcon, LogOut, ArrowLeft, Save
} from 'lucide-react'
import { supabase } from '../supabase'
import { useToast } from '../components/Toast'
import api from '../api'

export default function Profile({ session, userPlan: propPlan = 'free' }) {
  const toast = useToast()
  const navigate = useNavigate()

  const user = session?.user
  const userMetadata = user?.user_metadata || {}

  const [displayName, setDisplayName] = useState(
    userMetadata.full_name || (user?.email ? user.email.split('@')[0] : 'Trader')
  )
  const [bio, setBio] = useState(userMetadata.bio || 'Algorithmic Forex & Crypto Trader')
  const [tradingStyle, setTradingStyle] = useState(userMetadata.trading_style || 'Algorithmic / Quantitative')
  const [timezone, setTimezone] = useState(userMetadata.timezone || 'UTC (GMT+0)')
  const [copiedUid, setCopiedUid] = useState(false)
  const [saving, setSaving] = useState(false)
  const [accountsCount, setAccountsCount] = useState(0)
  const [activeAccount, setActiveAccount] = useState(null)
  const [currentPlan, setCurrentPlan] = useState((propPlan || 'free').toLowerCase())

  useEffect(() => {
    setCurrentPlan((propPlan || 'free').toLowerCase())
  }, [propPlan])

  useEffect(() => {
    if (!session?.user) return
    const meta = session.user.user_metadata || {}
    const emailFallback = session.user.email ? session.user.email.split('@')[0] : 'Trader'

    setDisplayName(meta.full_name || emailFallback)
    setBio(meta.bio || 'Algorithmic Forex & Crypto Trader')
    setTradingStyle(meta.trading_style || 'Algorithmic / Quantitative')
    setTimezone(meta.timezone || 'UTC (GMT+0)')

    // Also inspect public.profiles row for canonical name/plan (never stale cache)
    supabase.from('profiles')
      .select('name, plan')
      .eq('id', session.user.id)
      .maybeSingle()
      .then(({ data: prof }) => {
        if (prof?.name && !meta.full_name) {
          setDisplayName(prof.name)
        }
        if (prof?.plan) {
          setCurrentPlan(prof.plan.toLowerCase())
        }
      })
      .catch(() => {})

    if (!session?.access_token) return
    const headers = { 'Authorization': `Bearer ${session.access_token}` }

    api.get('/api/payments/license', { headers })
      .then(d => {
        if (d && d.plan) setCurrentPlan(d.plan.toLowerCase())
      })
      .catch(() => setCurrentPlan('free'))

    api.get('/api/accounts', { headers })
      .then(d => {
        if (Array.isArray(d)) setAccountsCount(d.length)
      })
      .catch(() => setAccountsCount(0))

    api.get('/api/markets/active-account', { headers })
      .then(d => {
        if (d && d.connected && d.login) setActiveAccount(d)
        else setActiveAccount(null)
      })
      .catch(() => setActiveAccount(null))
  }, [session])

  const handleCopyUid = () => {
    if (!user?.id) return
    navigator.clipboard.writeText(user.id)
    setCopiedUid(true)
    toast.success('User ID copied to clipboard')
    setTimeout(() => setCopiedUid(false), 2000)
  }

  const handleSaveProfile = async () => {
    setSaving(true)
    try {
      const cleanName = displayName.trim() || (user?.email ? user.email.split('@')[0] : 'Trader')
      const { error } = await supabase.auth.updateUser({
        data: {
          full_name: cleanName,
          bio,
          trading_style: tradingStyle,
          timezone
        }
      })
      if (error) throw error

      if (user?.id) {
        await supabase.from('profiles').upsert([{
          id: user.id,
          name: cleanName,
          email: user.email
        }], { onConflict: 'id' })
      }
      await supabase.auth.refreshSession().catch(() => {})
      toast.success('Profile updated successfully')
    } catch (err) {
      toast.error(`Failed to update profile: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handlePasswordReset = async () => {
    if (!user?.email) return
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(user.email)
      if (error) throw error
      toast.success(`Password reset email sent to ${user.email}`)
    } catch (err) {
      toast.error(`Reset email failed: ${err.message}`)
    }
  }

  const handleLogout = async () => {
    try {
      const uid = user?.id
      if (uid) {
        localStorage.removeItem(`trade_profile_name_${uid}`)
        localStorage.removeItem(`trade_bot_risk_defaults_${uid}`)
      }
      localStorage.removeItem('trade_profile_name')
      localStorage.removeItem('favPairs')
      localStorage.removeItem('tradeai_active_uid')
    } catch {}
    await supabase.auth.signOut()
    navigate('/login')
  }

  const userInitial = displayName.charAt(0).toUpperCase() || 'T'
  const planBadge = currentPlan === 'elite'
    ? { label: 'ELITE VIP', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)', border: 'rgba(245, 158, 11, 0.35)' }
    : currentPlan === 'pro'
    ? { label: 'PRO TRADER', color: '#00d4ff', bg: 'rgba(0, 212, 255, 0.15)', border: 'rgba(0, 212, 255, 0.35)' }
    : { label: 'FREE PLAN', color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', border: 'rgba(16, 185, 129, 0.35)' }

  const createdAtFormatted = user?.created_at
    ? new Date(user.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
    : 'Recent member'
  const lastSignInFormatted = user?.last_sign_in_at
    ? new Date(user.last_sign_in_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : 'Recent session'

  const cardStyle = {
    background: '#131722',
    border: '1px solid #1c2233',
    borderRadius: '16px',
    padding: '24px'
  }

  const inputStyle = {
    width: '100%',
    padding: '11px 14px',
    background: '#0c0e15',
    border: '1px solid #1c2233',
    borderRadius: '10px',
    color: '#ffffff',
    fontSize: '13px',
    outline: 'none',
    boxSizing: 'border-box',
    transition: 'border-color 0.2s'
  }

  return (
    <div style={{
      padding: '24px',
      background: '#0c0e15',
      minHeight: '100vh',
      color: '#f8fafc',
      display: 'flex',
      flexDirection: 'column',
      gap: '24px',
      maxWidth: '1000px',
      margin: '0 auto',
      width: '100%'
    }}>
      {/* Breadcrumb / Top Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: '#64748b' }}>
          <Link to="/dashboard" style={{ color: '#94a3b8', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <ArrowLeft size={14} /> Dashboard
          </Link>
          <span>/</span>
          <span style={{ color: '#f8fafc', fontWeight: 600 }}>Trader Profile</span>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <Link
            to="/settings"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 14px',
              background: '#131722',
              border: '1px solid #1c2233',
              borderRadius: '8px',
              color: '#94a3b8',
              textDecoration: 'none',
              fontSize: '12px',
              fontWeight: 500
            }}
          >
            <SettingsIcon size={14} /> Settings
          </Link>
          <button
            onClick={handleLogout}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 14px',
              background: 'rgba(244, 63, 94, 0.08)',
              border: '1px solid rgba(244, 63, 94, 0.2)',
              borderRadius: '8px',
              color: '#f43f5e',
              fontSize: '12px',
              fontWeight: 500,
              cursor: 'pointer'
            }}
          >
            <LogOut size={14} /> Sign Out
          </button>
        </div>
      </div>

      {/* Hero Profile Card */}
      <div style={{
        ...cardStyle,
        position: 'relative',
        overflow: 'hidden',
        background: 'linear-gradient(135deg, #131722 0%, #171c2b 100%)'
      }}>
        <div style={{
          position: 'absolute',
          top: '-60px',
          right: '-40px',
          width: '200px',
          height: '200px',
          background: 'radial-gradient(circle, rgba(59, 91, 245, 0.2) 0%, transparent 70%)',
          pointerEvents: 'none'
        }} />

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '24px',
          flexWrap: 'wrap'
        }}>
          {/* Avatar */}
          <div style={{ position: 'relative' }}>
            <div style={{
              width: '84px',
              height: '84px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #f59e0b, #ec4899)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 800,
              fontSize: '32px',
              color: '#ffffff',
              boxShadow: '0 8px 24px rgba(245, 158, 11, 0.35)',
              border: '3px solid #1e2538'
            }}>
              {userInitial}
            </div>
            <div style={{
              position: 'absolute',
              bottom: '2px',
              right: '2px',
              width: '20px',
              height: '20px',
              borderRadius: '50%',
              background: '#10b981',
              border: '2px solid #131722',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Check size={11} color="#ffffff" strokeWidth={3} />
            </div>
          </div>

          {/* Core Info */}
          <div style={{ flex: 1, minWidth: '220px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '6px' }}>
              <h1 style={{ fontSize: '22px', fontWeight: '800', color: '#ffffff', margin: 0, letterSpacing: '-0.3px' }}>
                {displayName}
              </h1>

              {/* Single accurate, clickable Plan Badge */}
              <Link
                to="/pricing?plan=pro"
                style={{
                  background: planBadge.bg,
                  border: `1px solid ${planBadge.border}`,
                  color: planBadge.color,
                  padding: '3px 10px',
                  borderRadius: '20px',
                  fontSize: '11px',
                  fontWeight: 700,
                  letterSpacing: '0.04em',
                  textDecoration: 'none',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px'
                }}
              >
                <Sparkles size={11} />
                {planBadge.label}
                {currentPlan === 'free' && <span style={{ color: '#fff', marginLeft: '2px' }}>· Upgrade →</span>}
              </Link>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap', fontSize: '13px', color: '#94a3b8' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Mail size={14} color="#64748b" />
                <span>{user?.email || ''}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Calendar size={14} color="#64748b" />
                <span>Joined {createdAtFormatted}</span>
              </div>
            </div>

            {/* UID Copy row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '12px' }}>
              <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>User ID:</span>
              <code style={{
                background: '#0c0e15',
                border: '1px solid #1c2233',
                padding: '3px 8px',
                borderRadius: '6px',
                fontSize: '11px',
                color: '#94a3b8'
              }}>
                {user?.id ? `${user.id.slice(0, 8)}...${user.id.slice(-6)}` : '—'}
              </code>
              <button
                onClick={handleCopyUid}
                style={{
                  background: 'none',
                  border: 'none',
                  color: copiedUid ? '#10b981' : '#64748b',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  padding: '2px',
                  transition: 'color 0.2s'
                }}
                title="Copy full UID"
              >
                {copiedUid ? <Check size={13} /> : <Copy size={13} />}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Grid: Profile Details & Trading Context */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: '20px'
      }}>
        {/* Personal & Trading Identity (Editable) */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
            <div style={{
              width: '34px',
              height: '34px',
              borderRadius: '8px',
              background: 'rgba(59, 91, 245, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <User size={17} color="#3b5bf5" />
            </div>
            <div>
              <h2 style={{ fontSize: '15px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
                Edit Profile Information
              </h2>
              <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                Manage your public display credentials and preferences
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
                Display Name
              </label>
              <input
                style={inputStyle}
                type="text"
                value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                placeholder="Your trader name"
              />
            </div>

            <div>
              <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
                Email Address
              </label>
              <input
                style={{ ...inputStyle, opacity: 0.65, cursor: 'not-allowed' }}
                type="text"
                value={user?.email || ''}
                disabled
              />
              <span style={{ fontSize: '11px', color: '#64748b', marginTop: '4px', display: 'block' }}>
                Managed via Supabase Auth authentication provider
              </span>
            </div>

            <div>
              <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
                Trading Bio / Strategy Style
              </label>
              <input
                style={inputStyle}
                type="text"
                value={bio}
                onChange={e => setBio(e.target.value)}
                placeholder="e.g. Algorithmic Scalper / Smart Money Trader"
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
                  Execution Style
                </label>
                <select
                  style={inputStyle}
                  value={tradingStyle}
                  onChange={e => setTradingStyle(e.target.value)}
                >
                  <option value="Algorithmic / Quantitative">Algorithmic / Quantitative</option>
                  <option value="Scalping (M1 / M5)">Scalping (M1 / M5)</option>
                  <option value="Intraday Trend Following">Intraday Trend</option>
                  <option value="Smart Money Concepts (SMC)">Smart Money Concepts</option>
                  <option value="Swing Portfolio">Swing Portfolio</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
                  Timezone
                </label>
                <input
                  style={inputStyle}
                  type="text"
                  value={timezone}
                  onChange={e => setTimezone(e.target.value)}
                  placeholder="UTC (GMT+0)"
                />
              </div>
            </div>

            <button
              onClick={handleSaveProfile}
              disabled={saving}
              style={{
                marginTop: '6px',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                background: '#3b5bf5',
                color: '#ffffff',
                border: 'none',
                borderRadius: '8px',
                padding: '11px 18px',
                fontSize: '13px',
                fontWeight: '600',
                cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving ? 0.7 : 1,
                transition: 'background 0.2s'
              }}
            >
              <Save size={15} />
              {saving ? 'Saving...' : 'Save Profile Details'}
            </button>
          </div>
        </div>

        {/* Security & Authentication Status */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
            <div style={{
              width: '34px',
              height: '34px',
              borderRadius: '8px',
              background: 'rgba(16, 185, 129, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Shield size={17} color="#10b981" />
            </div>
            <div>
              <h2 style={{ fontSize: '15px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
                Security &amp; Account Status
              </h2>
              <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                Active session safeguards and cryptographic credentials
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{
              background: '#0c0e15',
              border: '1px solid #1c2233',
              borderRadius: '10px',
              padding: '12px 14px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <div>
                <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Auth Method</div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc', marginTop: '2px' }}>
                  Supabase Cloud Authentication
                </div>
              </div>
              <span style={{
                background: 'rgba(16, 185, 129, 0.12)',
                color: '#10b981',
                padding: '3px 8px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: 600
              }}>
                SECURE
              </span>
            </div>

            <div style={{
              background: '#0c0e15',
              border: '1px solid #1c2233',
              borderRadius: '10px',
              padding: '12px 14px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <div>
                <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Last Sign In</div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc', marginTop: '2px' }}>
                  {lastSignInFormatted}
                </div>
              </div>
              <Clock size={16} color="#64748b" />
            </div>

            <div style={{
              background: '#0c0e15',
              border: '1px solid #1c2233',
              borderRadius: '10px',
              padding: '12px 14px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <div>
                <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Connected MetaTrader 5</div>
                <div style={{
                  fontSize: '13px',
                  fontWeight: 600,
                  color: activeAccount ? (activeAccount.terminal_synced ? '#10b981' : '#f59e0b') : '#94a3b8',
                  marginTop: '2px'
                }}>
                  {activeAccount
                    ? activeAccount.terminal_synced
                      ? `Synced: #${activeAccount.login} (${activeAccount.server})`
                      : `Linked #${activeAccount.login} (MT5 Desktop not synced)`
                    : (accountsCount > 0 ? `${accountsCount} saved account(s) (disconnected)` : 'No MT5 account linked')}
                </div>
              </div>
              <Link to="/accounts" style={{ color: '#3b5bf5', fontSize: '12px', textDecoration: 'none', fontWeight: 600 }}>
                Manage &rarr;
              </Link>
            </div>

            <div style={{ marginTop: '6px' }}>
              <button
                onClick={handlePasswordReset}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  background: '#1a1f30',
                  border: '1px solid #252d43',
                  borderRadius: '8px',
                  padding: '10px 16px',
                  color: '#cbd5e1',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'background 0.2s'
                }}
                onMouseEnter={e => e.currentTarget.style.background = '#222940'}
                onMouseLeave={e => e.currentTarget.style.background = '#1a1f30'}
              >
                <Key size={14} color="#818cf8" />
                Request Password Reset Link
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Membership & Subscription Plans (All Cards Clickable -> /pricing) */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
              Trading Platform Membership Tiers
            </h3>
            <p style={{ fontSize: '12px', color: '#94a3b8', margin: '3px 0 0 0' }}>
              Click any plan card to compare tiers, purchase Pro, or activate your license key
            </p>
          </div>
          <Link
            to="/pricing"
            style={{
              background: planBadge.bg,
              border: `1px solid ${planBadge.border}`,
              color: planBadge.color,
              padding: '5px 12px',
              borderRadius: '20px',
              fontSize: '11px',
              fontWeight: 700,
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px'
            }}
          >
            CURRENT PLAN: {currentPlan.toUpperCase()} <ArrowUpRight size={12} />
          </Link>
        </div>

        {/* 3 Clickable Tier Cards */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          gap: '16px'
        }}>
          {/* FREE PLAN */}
          <div
            onClick={() => navigate('/pricing?plan=free')}
            style={{
              background: '#0c0e15',
              border: `1px solid ${currentPlan === 'free' ? 'rgba(16, 185, 129, 0.45)' : '#1c2233'}`,
              borderRadius: '12px',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
              position: 'relative',
              cursor: 'pointer'
            }}
          >
            {currentPlan === 'free' && (
              <span style={{
                position: 'absolute', top: '-10px', right: '14px',
                background: '#10b981', color: '#0c0e15', fontSize: '10px', fontWeight: 800,
                padding: '2px 8px', borderRadius: '10px'
              }}>ACTIVE</span>
            )}
            <div>
              <div style={{ fontSize: '15px', fontWeight: '700', color: '#ffffff' }}>Free Starter</div>
              <div style={{ fontSize: '22px', fontWeight: '800', color: '#10b981', margin: '6px 0 2px 0' }}>$0 <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 500 }}>/ forever</span></div>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0 }}>Basic algorithmic trading &amp; manual station</p>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px', color: '#94a3b8', flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#10b981" />
                <span><strong>1 Active Bot</strong> running at a time</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#10b981" />
                <span>Classic Mode &amp; Smart Money access</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#10b981" />
                <span>Full Manual Trading Station</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#10b981" />
                <span>Live MetaTrader 5 broker sync</span>
              </div>
            </div>
            <button
              type="button"
              onClick={e => { e.stopPropagation(); navigate('/pricing?plan=free') }}
              style={{
                width: '100%', padding: '9px 12px', borderRadius: '8px',
                background: '#131722', border: '1px solid #1c2233',
                color: currentPlan === 'free' ? '#10b981' : '#94a3b8',
                fontSize: '12px', fontWeight: 700, cursor: 'pointer'
              }}
            >
              {currentPlan === 'free' ? 'Current Active Plan' : 'Included'}
            </button>
          </div>

          {/* PRO PLAN */}
          <div
            onClick={() => navigate('/pricing?plan=pro')}
            style={{
              background: 'linear-gradient(180deg, rgba(0, 212, 255, 0.06) 0%, #0c0e15 100%)',
              border: `1px solid ${currentPlan === 'pro' ? '#00d4ff' : 'rgba(0, 212, 255, 0.4)'}`,
              borderRadius: '12px',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
              position: 'relative',
              boxShadow: '0 0 25px rgba(0, 212, 255, 0.08)',
              cursor: 'pointer'
            }}
          >
            <span style={{
              position: 'absolute', top: '-10px', right: '14px',
              background: '#00d4ff', color: '#0c0e15', fontSize: '10px', fontWeight: 800,
              padding: '2px 8px', borderRadius: '10px'
            }}>{currentPlan === 'pro' ? 'ACTIVE' : 'POPULAR'}</span>
            <div>
              <div style={{ fontSize: '15px', fontWeight: '700', color: '#00d4ff' }}>Pro Trader</div>
              <div style={{ fontSize: '22px', fontWeight: '800', color: '#ffffff', margin: '6px 0 2px 0' }}>$29 <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 500 }}>/ month</span></div>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0 }}>Unlocks PipStep Reversal EA &amp; multi-bot execution</p>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px', color: '#cbd5e1', flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#00d4ff" />
                <span><strong style={{ color: '#00d4ff' }}>PipStep Reversal EA</strong> (Full Access)</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#00d4ff" />
                <span>Symmetrical BuyStop / SellStop Straddle</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#00d4ff" />
                <span>Dynamic Step Trailing SL &amp; Reversal</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#00d4ff" />
                <span>Up to <strong>3 Active Bots</strong> simultaneously</span>
              </div>
            </div>
            <button
              type="button"
              onClick={e => { e.stopPropagation(); navigate('/pricing?plan=pro') }}
              style={{
                width: '100%', padding: '10px 12px', borderRadius: '8px',
                background: currentPlan === 'pro' ? 'rgba(0, 212, 255, 0.14)' : 'linear-gradient(135deg, #00d4ff, #3b5bf5)',
                border: currentPlan === 'pro' ? '1px solid rgba(0, 212, 255, 0.4)' : 'none',
                color: currentPlan === 'pro' ? '#00d4ff' : '#ffffff',
                fontSize: '12px', fontWeight: 700, cursor: 'pointer'
              }}
            >
              {currentPlan === 'pro' ? 'Manage Pro Plan →' : 'Buy / Activate Pro →'}
            </button>
          </div>

          {/* ELITE PLAN */}
          <div
            onClick={() => navigate('/pricing?plan=elite')}
            style={{
              background: '#0c0e15',
              border: '1px solid rgba(245, 158, 11, 0.3)',
              borderRadius: '12px',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
              opacity: 0.9,
              cursor: 'pointer'
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontSize: '15px', fontWeight: '700', color: '#f59e0b' }}>Elite VIP</div>
                <span style={{ fontSize: '10px', color: '#f59e0b', background: 'rgba(245, 158, 11, 0.15)', padding: '2px 6px', borderRadius: '4px', fontWeight: 700 }}>COMING SOON</span>
              </div>
              <div style={{ fontSize: '22px', fontWeight: '800', color: '#ffffff', margin: '6px 0 2px 0' }}>$79 <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 500 }}>/ month</span></div>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0 }}>Advanced AI consensus &amp; multi-pair hedging</p>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px', color: '#94a3b8', flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#f59e0b" />
                <span><strong>Other Advanced Bots</strong> (In development)</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#f59e0b" />
                <span>TradingAgents 6-Agent Committee</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#f59e0b" />
                <span>Signal Strength Delta Hedging</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={14} color="#f59e0b" />
                <span>Unlimited concurrent bot instances</span>
              </div>
            </div>
            <button
              type="button"
              onClick={e => { e.stopPropagation(); navigate('/pricing?plan=elite') }}
              style={{
                width: '100%', padding: '9px 12px', borderRadius: '8px',
                background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)',
                color: '#f59e0b', fontSize: '12px', fontWeight: 700, cursor: 'pointer'
              }}
            >
              View Elite Details →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
