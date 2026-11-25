import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  CheckCircle2, Sparkles, Key, ArrowLeft, ExternalLink,
  ShieldCheck, Zap, Crown, Lock, RefreshCw, Copy
} from 'lucide-react'
import api from '../api'
import { useToast } from '../components/Toast'

export default function Pricing({ session, userPlan = 'free', isOwner = false, onPlanUpdated }) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const toast = useToast()

  const highlightedPlan = searchParams.get('plan') || 'pro'
  const [plansMeta, setPlansMeta] = useState({ checkout_url: '', gumroad_configured: false })
  const [licenseKey, setLicenseKey] = useState('')
  const [activating, setActivating] = useState(false)
  const [showCheckoutInfo, setShowCheckoutInfo] = useState(false)

  // Owner license key generator state
  const [genPlan, setGenPlan] = useState('pro')
  const [genEmail, setGenEmail] = useState('')
  const [generatedKey, setGeneratedKey] = useState('')
  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    api.get('/api/payments/plans')
      .then(d => {
        if (d) setPlansMeta(d)
      })
      .catch(() => {})
  }, [])

  const envCheckoutUrl = import.meta.env.VITE_GUMROAD_PRO_URL || ''
  const checkoutUrl = plansMeta.checkout_url || envCheckoutUrl
  const hasProAccess = userPlan === 'pro' || userPlan === 'elite'
  const hasEliteAccess = userPlan === 'elite'

  const handleBuyPro = () => {
    if (checkoutUrl) {
      const emailParam = session?.user?.email ? `?email=${encodeURIComponent(session.user.email)}` : ''
      window.open(`${checkoutUrl}${checkoutUrl.includes('?') ? '&' : ''}${emailParam.replace(/^\?/, '')}`, '_blank', 'noopener,noreferrer')
      toast.info('Complete checkout in the opened tab, then paste your license key below to activate Pro instantly.')
    } else {
      setShowCheckoutInfo(true)
    }
  }

  const handleActivateLicense = async (e) => {
    e.preventDefault()
    const cleanKey = licenseKey.trim()
    if (!cleanKey) {
      toast.error('Please enter your license key first')
      return
    }
    if (session?.user?.id && cleanKey.toLowerCase() === session.user.id.toLowerCase()) {
      toast.warn('That is your User ID (UID), not a billing license key. Refresh the page if your owner email already grants full access, or generate/enter a TAI-PRO license key.')
      return
    }
    setActivating(true)
    try {
      const res = await api.post('/api/payments/activate-license', { license_key: cleanKey })
      if (res?.success) {
        toast.success(res.message || 'Pro Trader plan activated!')
        setLicenseKey('')
        if (onPlanUpdated) await onPlanUpdated()
      } else {
        toast.error(res?.detail || 'License activation failed')
      }
    } catch (err) {
      toast.error(err.detail || err.message || 'Invalid or expired license key')
    } finally {
      setActivating(false)
    }
  }

  const handleGenerateKey = async (e) => {
    e.preventDefault()
    setGenerating(true)
    try {
      const res = await api.post('/api/payments/admin/issue-license', {
        plan: genPlan,
        target_email: genEmail.trim()
      })
      if (res?.success && res.license_key) {
        setGeneratedKey(res.license_key)
        toast.success(`Issued ${res.plan.toUpperCase()} key: ${res.license_key}`)
      }
    } catch (err) {
      toast.error(err.detail || err.message || 'Failed to issue license key')
    } finally {
      setGenerating(false)
    }
  }

  const cardBase = {
    background: '#131722',
    borderRadius: '16px',
    padding: '26px',
    display: 'flex',
    flexDirection: 'column',
    gap: '18px',
    position: 'relative',
  }

  return (
    <div style={{
      padding: '24px',
      background: '#0c0e15',
      minHeight: '100vh',
      color: '#f8fafc',
      maxWidth: '1120px',
      margin: '0 auto',
      width: '100%',
      boxSizing: 'border-box',
      display: 'flex',
      flexDirection: 'column',
      gap: '24px'
    }}>
      {/* Top Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <button
          onClick={() => navigate(-1)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            background: '#131722',
            border: '1px solid #1c2233',
            borderRadius: '8px',
            color: '#94a3b8',
            padding: '8px 14px',
            fontSize: '12px',
            fontWeight: 600,
            cursor: 'pointer'
          }}
        >
          <ArrowLeft size={14} /> Back
        </button>

        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 14px',
          borderRadius: '20px',
          background: userPlan === 'elite' ? 'rgba(245, 158, 11, 0.14)' : userPlan === 'pro' ? 'rgba(0, 212, 255, 0.14)' : 'rgba(16, 185, 129, 0.14)',
          border: `1px solid ${userPlan === 'elite' ? 'rgba(245, 158, 11, 0.35)' : userPlan === 'pro' ? 'rgba(0, 212, 255, 0.35)' : 'rgba(16, 185, 129, 0.35)'}`,
          color: userPlan === 'elite' ? '#f59e0b' : userPlan === 'pro' ? '#00d4ff' : '#10b981',
          fontSize: '12px',
          fontWeight: 700
        }}>
          <Crown size={14} />
          {isOwner ? 'OWNER FULL ACCESS (ALL PLANS UNLOCKED)' : `ACTIVE MEMBERSHIP: ${userPlan.toUpperCase()} PLAN`}
        </div>
      </div>

      {/* Hero Header */}
      <div style={{ textAlign: 'center', padding: '8px 12px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: '800', color: '#ffffff', margin: '0 0 8px 0', letterSpacing: '-0.4px' }}>
          {hasEliteAccess ? 'All Trade-AI Plans & Bots Unlocked' : 'Upgrade Your Trade-AI Membership'}
        </h1>
        <p style={{ fontSize: '14px', color: '#94a3b8', maxWidth: '640px', margin: '0 auto', lineHeight: 1.5 }}>
          {isOwner
            ? 'You are signed in as the platform Owner. Free, Pro (PipStep Reversal EA), and Elite AI strategies are all enabled on your account.'
            : (
              <>
                Start free with 1 active bot &amp; full manual chart trading, or unlock the high-frequency{' '}
                <strong style={{ color: '#00d4ff' }}>PipStep Reversal EA</strong> and multi-bot automation with Pro.
              </>
            )}
        </p>
      </div>

      {/* 3 Plan Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))',
        gap: '20px',
        alignItems: 'stretch'
      }}>
        {/* 1. FREE STARTER */}
        <div style={{
          ...cardBase,
          border: `1px solid ${userPlan === 'free' ? 'rgba(16, 185, 129, 0.5)' : '#1c2233'}`
        }}>
          {userPlan === 'free' && (
            <span style={{
              position: 'absolute', top: '-11px', right: '18px',
              background: '#10b981', color: '#0c0e15', fontSize: '10px', fontWeight: 800,
              padding: '3px 10px', borderRadius: '10px'
            }}>CURRENT PLAN</span>
          )}
          <div>
            <div style={{ fontSize: '16px', fontWeight: 700, color: '#ffffff' }}>Free Starter</div>
            <div style={{ fontSize: '30px', fontWeight: 800, color: '#10b981', margin: '8px 0 4px 0' }}>
              $0 <span style={{ fontSize: '13px', color: '#64748b', fontWeight: 500 }}>/ forever</span>
            </div>
            <p style={{ fontSize: '13px', color: '#94a3b8', margin: 0 }}>
              Essential algorithmic trading &amp; live MT5 chart execution
            </p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px', color: '#cbd5e1', flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={15} color="#10b981" />
              <span><strong>1 Active Bot</strong> running simultaneously</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={15} color="#10b981" />
              <span>Classic Mode, Smart Money &amp; Scalp bots</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={15} color="#10b981" />
              <span>Full Manual Buy/Sell Chart Station</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={15} color="#10b981" />
              <span>Real-Time MetaTrader 5 Desktop sync</span>
            </div>
          </div>

          <button
            onClick={() => navigate('/bot')}
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: '10px',
              border: '1px solid #252d43',
              background: '#0c0e15',
              color: '#10b981',
              fontSize: '13px',
              fontWeight: 700,
              cursor: 'pointer'
            }}
          >
            {userPlan === 'free' ? 'Active on Your Account' : '✓ Included'}
          </button>
        </div>

        {/* 2. PRO TRADER */}
        <div style={{
          ...cardBase,
          background: 'linear-gradient(180deg, rgba(0, 212, 255, 0.08) 0%, #131722 100%)',
          border: `1.5px solid ${highlightedPlan === 'pro' || hasProAccess ? '#00d4ff' : 'rgba(0, 212, 255, 0.4)'}`,
          boxShadow: '0 0 32px rgba(0, 212, 255, 0.12)'
        }}>
          <span style={{
            position: 'absolute', top: '-11px', right: '18px',
            background: '#00d4ff', color: '#0c0e15', fontSize: '10px', fontWeight: 800,
            padding: '3px 10px', borderRadius: '10px'
          }}>
            {hasProAccess ? 'UNLOCKED' : 'POPULAR · UNLOCKS PIPSTEP EA'}
          </span>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={18} color="#00d4ff" />
              <div style={{ fontSize: '16px', fontWeight: 700, color: '#00d4ff' }}>Pro Trader</div>
            </div>
            <div style={{ fontSize: '30px', fontWeight: 800, color: '#ffffff', margin: '8px 0 4px 0' }}>
              $29 <span style={{ fontSize: '13px', color: '#64748b', fontWeight: 500 }}>/ month</span>
            </div>
            <p style={{ fontSize: '13px', color: '#cbd5e1', margin: 0 }}>
              Full access to PipStep Reversal EA (Python + MQL5) &amp; multi-bot trading
            </p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px', color: '#e2e8f0', flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={15} color="#00d4ff" />
              <span><strong style={{ color: '#00d4ff' }}>PipStep Reversal EA</strong> (Instant Unlock)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={15} color="#00d4ff" />
              <span>Symmetrical BuyStop / SellStop Straddle</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={15} color="#00d4ff" />
              <span>Dynamic Step Trailing SL &amp; Instant Reversal</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={15} color="#00d4ff" />
              <span>Run up to <strong>3 Active Bots</strong> simultaneously</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={15} color="#00d4ff" />
              <span>Includes native MT5 <code>PipStep_Reversal_EA.mq5</code></span>
            </div>
          </div>

          {hasProAccess ? (
            <button
              onClick={() => navigate('/bot')}
              style={{
                width: '100%',
                padding: '13px',
                borderRadius: '10px',
                border: '1px solid rgba(0, 212, 255, 0.4)',
                background: 'rgba(0, 212, 255, 0.14)',
                color: '#00d4ff',
                fontSize: '13px',
                fontWeight: 700,
                cursor: 'pointer'
              }}
            >
              ✓ Pro Unlocked — Open AI Bots
            </button>
          ) : (
            <button
              onClick={handleBuyPro}
              style={{
                width: '100%',
                padding: '13px',
                borderRadius: '10px',
                border: 'none',
                background: 'linear-gradient(135deg, #00d4ff, #3b5bf5)',
                color: '#ffffff',
                fontSize: '14px',
                fontWeight: 800,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                boxShadow: '0 6px 20px rgba(0, 212, 255, 0.3)'
              }}
            >
              <Sparkles size={16} />
              <span>Buy Pro Plan — $29/mo</span>
              <ExternalLink size={14} />
            </button>
          )}
        </div>

        {/* 3. ELITE VIP */}
        <div style={{
          ...cardBase,
          border: `1.5px solid ${hasEliteAccess || highlightedPlan === 'elite' ? '#f59e0b' : 'rgba(245, 158, 11, 0.3)'}`,
          opacity: hasEliteAccess ? 1 : 0.92
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ fontSize: '16px', fontWeight: 700, color: '#f59e0b' }}>Elite VIP</div>
            <span style={{
              fontSize: '10px',
              color: hasEliteAccess ? '#0c0e15' : '#f59e0b',
              background: hasEliteAccess ? '#f59e0b' : 'rgba(245, 158, 11, 0.15)',
              padding: '3px 8px',
              borderRadius: '6px',
              fontWeight: 800
            }}>{hasEliteAccess ? 'UNLOCKED' : 'COMING SOON'}</span>
          </div>

          <div>
            <div style={{ fontSize: '30px', fontWeight: 800, color: '#ffffff', margin: '4px 0' }}>
              $79 <span style={{ fontSize: '13px', color: '#64748b', fontWeight: 500 }}>/ month</span>
            </div>
            <p style={{ fontSize: '13px', color: '#94a3b8', margin: 0 }}>
              Institutional AI agent committee &amp; delta-neutral hedging desks
            </p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px', color: '#cbd5e1', flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {hasEliteAccess ? <CheckCircle2 size={15} color="#f59e0b" /> : <Lock size={14} color="#f59e0b" />}
              <span>TradingAgents 6-Agent LLM Consensus</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {hasEliteAccess ? <CheckCircle2 size={15} color="#f59e0b" /> : <Lock size={14} color="#f59e0b" />}
              <span>Signal Strength Delta Hedging Engine</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {hasEliteAccess ? <CheckCircle2 size={15} color="#f59e0b" /> : <Lock size={14} color="#f59e0b" />}
              <span>Unlimited concurrent bots &amp; VIP alerts</span>
            </div>
          </div>

          <button
            onClick={() => hasEliteAccess ? navigate('/bot') : toast.info('Elite VIP is currently under development for external customers!')}
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: '10px',
              border: '1px solid rgba(245, 158, 11, 0.4)',
              background: hasEliteAccess ? 'rgba(245, 158, 11, 0.16)' : 'rgba(245, 158, 11, 0.08)',
              color: '#f59e0b',
              fontSize: '13px',
              fontWeight: 700,
              cursor: 'pointer'
            }}
          >
            {hasEliteAccess ? '✓ Elite Unlocked — Open AI Bots' : 'In Development — Coming Soon'}
          </button>
        </div>
      </div>

      {/* Owner License Key Issuer Tool (visible ONLY to Owner / Admin) */}
      {isOwner && (
        <div style={{
          background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.08), #131722)',
          border: '1px solid rgba(245, 158, 11, 0.35)',
          borderRadius: '16px',
          padding: '22px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
            <Crown size={18} color="#f59e0b" />
            <h2 style={{ fontSize: '15px', fontWeight: 700, color: '#ffffff', margin: 0 }}>
              Owner Panel: Issue Customer License Key (100% Free)
            </h2>
          </div>
          <p style={{ margin: '0 0 14px 0', fontSize: '12.5px', color: '#94a3b8' }}>
            Generate an active license key for yourself or any buyer before enabling Gumroad. Leave email empty to bind to your account or enter a user email.
          </p>
          <form onSubmit={handleGenerateKey} style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <select
              value={genPlan}
              onChange={e => setGenPlan(e.target.value)}
              style={{
                padding: '10px 14px', background: '#0c0e15', border: '1px solid #1c2233',
                borderRadius: '10px', color: '#ffffff', fontSize: '13px', outline: 'none'
              }}
            >
              <option value="pro">Pro Trader ($29/mo)</option>
              <option value="elite">Elite VIP ($79/mo)</option>
            </select>
            <input
              type="email"
              value={genEmail}
              onChange={e => setGenEmail(e.target.value)}
              placeholder="Customer email (optional — leave blank for self)"
              style={{
                flex: '1 1 240px', padding: '10px 14px', background: '#0c0e15',
                border: '1px solid #1c2233', borderRadius: '10px', color: '#ffffff', fontSize: '13px', outline: 'none'
              }}
            />
            <button
              type="submit"
              disabled={generating}
              style={{
                padding: '10px 18px', borderRadius: '10px', border: 'none',
                background: '#f59e0b', color: '#0c0e15', fontSize: '13px', fontWeight: 800, cursor: 'pointer'
              }}
            >
              {generating ? 'Issuing...' : 'Generate License Key'}
            </button>
          </form>
          {generatedKey && (
            <div style={{
              marginTop: '12px', padding: '10px 14px', background: '#0c0e15', border: '1px solid #1c2233',
              borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px'
            }}>
              <code style={{ color: '#00d4ff', fontSize: '13px', fontWeight: 700 }}>{generatedKey}</code>
              <button
                type="button"
                onClick={() => { navigator.clipboard.writeText(generatedKey); toast.success('License key copied!') }}
                style={{
                  background: 'rgba(0, 212, 255, 0.14)', border: '1px solid rgba(0, 212, 255, 0.35)',
                  color: '#00d4ff', padding: '5px 10px', borderRadius: '6px', fontSize: '12px', cursor: 'pointer',
                  display: 'inline-flex', alignItems: 'center', gap: '5px'
                }}
              >
                <Copy size={12} /> Copy Key
              </button>
            </div>
          )}
        </div>
      )}

      {/* Checkout Instructions notice when Gumroad URL is not yet linked */}
      {showCheckoutInfo && !checkoutUrl && (
        <div style={{
          background: 'rgba(59, 91, 245, 0.08)',
          border: '1px solid rgba(59, 91, 245, 0.3)',
          borderRadius: '14px',
          padding: '18px 22px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px'
        }}>
          <div style={{ fontSize: '14px', fontWeight: 700, color: '#ffffff', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShieldCheck size={17} color="#3b5bf5" />
            Pro Plan Checkout &amp; License Delivery
          </div>
          <p style={{ margin: 0, fontSize: '13px', color: '#cbd5e1', lineHeight: 1.6 }}>
            Online checkout works cleanly with <strong>Gumroad (Free to set up — $0 monthly cost)</strong>.
            Once your Gumroad product URL is set in <code>VITE_GUMROAD_PRO_URL</code> (and{' '}
            <code>GUMROAD_PRODUCT_ID</code> / <code>GUMROAD_SECRET</code> in backend <code>.env</code>), clicking{' '}
            <strong>Buy Pro Plan</strong> opens your checkout page directly and issues instant license keys.
          </p>
        </div>
      )}

      {/* License Key Activation Card */}
      <div style={{
        background: '#131722',
        border: '1px solid #1c2233',
        borderRadius: '16px',
        padding: '24px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
          <div style={{
            width: '34px', height: '34px', borderRadius: '8px',
            background: 'rgba(0, 212, 255, 0.15)', display: 'flex',
            alignItems: 'center', justifyContent: 'center'
          }}>
            <Key size={17} color="#00d4ff" />
          </div>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#ffffff', margin: 0 }}>
              Already have a Pro License Key?
            </h2>
            <p style={{ fontSize: '12px', color: '#94a3b8', margin: '2px 0 0 0' }}>
              Paste your Gumroad or Trade-AI license key below to unlock Pro Trader immediately
            </p>
          </div>
        </div>

        <form onSubmit={handleActivateLicense} style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '14px' }}>
          <input
            type="text"
            value={licenseKey}
            onChange={e => setLicenseKey(e.target.value)}
            placeholder="e.g. TAI-PRO-XXXXXXXX or Gumroad license key"
            style={{
              flex: '1 1 280px',
              padding: '12px 16px',
              background: '#0c0e15',
              border: '1px solid #1c2233',
              borderRadius: '10px',
              color: '#ffffff',
              fontSize: '13px',
              outline: 'none',
              fontFamily: 'monospace'
            }}
          />
          <button
            type="submit"
            disabled={activating}
            style={{
              padding: '12px 22px',
              borderRadius: '10px',
              border: 'none',
              background: '#00d4ff',
              color: '#0c0e15',
              fontSize: '13px',
              fontWeight: 800,
              cursor: activating ? 'not-allowed' : 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              opacity: activating ? 0.7 : 1
            }}
          >
            {activating ? <RefreshCw size={15} style={{ animation: 'spin 1s linear infinite' }} /> : <CheckCircle2 size={15} />}
            {activating ? 'Verifying...' : 'Activate License'}
          </button>
        </form>
      </div>
    </div>
  )
}
