import { useState, useEffect } from 'react'
import {
  User, Shield, Key, CreditCard, Bell,
  AlertTriangle, CheckCircle2, Copy, Radio,
  Sparkles, Save, Database
} from 'lucide-react'
import { useToast } from '../components/Toast'
import { supabase } from '../supabase'

export default function Settings({ session }) {
  const toast = useToast()

  const [profile, setProfile] = useState(() => ({
    name: localStorage.getItem('trade_profile_name') || session?.user?.user_metadata?.full_name || (session?.user?.email ? session.user.email.split('@')[0] : 'Trader'),
    email: session?.user?.email || ''
  }))

  useEffect(() => {
    if (session?.user) {
      setProfile(prev => ({
        ...prev,
        email: session.user.email || '',
        name: localStorage.getItem('trade_profile_name') || prev.name || session.user.user_metadata?.full_name || (session.user.email ? session.user.email.split('@')[0] : 'Trader')
      }))
    }
  }, [session])

  const [defaults, setDefaults] = useState(() => {
    try {
      const saved = localStorage.getItem('trade_bot_risk_defaults')
      return saved ? JSON.parse(saved) : {
        riskPercent: 2,
        lotSize: 0.01,
        maxPositions: 3,
        tpPips: 50,
        slPips: 25
      }
    } catch {
      return { riskPercent: 2, lotSize: 0.01, maxPositions: 3, tpPips: 50, slPips: 25 }
    }
  })

  const [marketApiKey, setMarketApiKey] = useState(() => {
    return localStorage.getItem('finance_market_api_key') || ''
  })
  const [marketProvider, setMarketProvider] = useState(() => {
    return localStorage.getItem('finance_market_provider') || 'binance_public'
  })

  const handleSaveProfile = async () => {
    try {
      localStorage.setItem('trade_profile_name', profile.name)
      if (session?.user) {
        await supabase.auth.updateUser({
          data: { full_name: profile.name }
        })
      }
      toast.success('Profile preferences updated')
    } catch {
      localStorage.setItem('trade_profile_name', profile.name)
      toast.success('Profile preferences saved')
    }
  }

  const handleSaveDefaults = () => {
    localStorage.setItem('trade_bot_risk_defaults', JSON.stringify(defaults))
    toast.success('Default bot risk parameters saved')
  }

  const handleSaveApiKeys = () => {
    localStorage.setItem('finance_market_api_key', marketApiKey)
    localStorage.setItem('finance_market_provider', marketProvider)
    toast.success('Market Data API settings updated')
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
    boxSizing: 'border-box'
  }

  const cardStyle = {
    background: '#131722',
    border: '1px solid #1c2233',
    borderRadius: '16px',
    padding: '24px'
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
      {/* Header */}
      <div>
        <h1 style={{ fontSize: '24px', fontWeight: '800', color: '#ffffff', letterSpacing: '-0.3px', margin: 0 }}>
          Platform Settings
        </h1>
        <p style={{ color: '#94a3b8', fontSize: '13px', marginTop: '4px' }}>
          Configure your profile, trading bots, risk limits, and real-time market API feeds
        </p>
      </div>

      {/* 1. Market Data & API Keys Configuration */}
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
            <Database size={17} color="#3b5bf5" />
          </div>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
              Live Market Data & API Providers
            </h2>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Connect real-time pricing feeds for top pairs, forex, commodities, and crypto
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px', marginBottom: '16px' }}>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
              Data Provider
            </label>
            <select
              style={inputStyle}
              value={marketProvider}
              onChange={e => setMarketProvider(e.target.value)}
            >
              <option value="binance_public">Real-Time Public Feed (Binance + MT5 Active)</option>
              <option value="alphavantage">Alpha Vantage (Forex, Equities, Crypto)</option>
              <option value="finnhub">Finnhub Stock & Forex API</option>
              <option value="twelvedata">TwelveData Real-Time API</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
              API Key (Optional / User Provided)
            </label>
            <input
              style={inputStyle}
              type="password"
              placeholder={marketProvider === 'binance_public' ? 'No key required (Live Public Active)' : 'Enter your provider API Key'}
              value={marketApiKey}
              onChange={e => setMarketApiKey(e.target.value)}
            />
          </div>
        </div>

        <div style={{
          background: 'rgba(16, 185, 129, 0.08)',
          border: '1px solid rgba(16, 185, 129, 0.25)',
          borderRadius: '10px',
          padding: '10px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '16px'
        }}>
          <CheckCircle2 size={16} color="#10b981" />
          <span style={{ fontSize: '12px', color: '#6ee7b7' }}>
            Real-time top pair market feeds (Bitcoin, Gold, S&P 500, NASDAQ, Solana) are currently active and live.
          </span>
        </div>

        <button
          onClick={handleSaveApiKeys}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            background: '#3b5bf5',
            color: '#ffffff',
            border: 'none',
            borderRadius: '8px',
            padding: '10px 18px',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer'
          }}
        >
          <Save size={15} /> Save API Settings
        </button>
      </div>

      {/* 2. Profile Information */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
          <div style={{
            width: '34px',
            height: '34px',
            borderRadius: '8px',
            background: 'rgba(6, 182, 212, 0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <User size={17} color="#06b6d4" />
          </div>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
              Profile Information
            </h2>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Your account details and display name
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px', marginBottom: '16px' }}>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
              Display Name
            </label>
            <input
              style={inputStyle}
              value={profile.name}
              onChange={e => setProfile({ ...profile, name: e.target.value })}
            />
          </div>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
              Email Address
            </label>
            <input
              style={{ ...inputStyle, opacity: 0.7 }}
              value={profile.email}
              disabled
            />
          </div>
        </div>

        <button
          onClick={handleSaveProfile}
          style={{
            background: '#1e2538',
            color: '#ffffff',
            border: '1px solid #28324f',
            borderRadius: '8px',
            padding: '9px 18px',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer'
          }}
        >
          Save Changes
        </button>
      </div>

      {/* 3. Bot Risk Parameters */}
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
            <h2 style={{ fontSize: '16px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
              Default Bot Risk Configuration
            </h2>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Global safeguards applied to automated execution strategies
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '16px' }}>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
              Risk Per Trade (%)
            </label>
            <input
              style={inputStyle}
              type="number"
              step="0.5"
              value={defaults.riskPercent}
              onChange={e => setDefaults({ ...defaults, riskPercent: e.target.value })}
            />
          </div>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
              Default Lot Size
            </label>
            <input
              style={inputStyle}
              type="number"
              step="0.01"
              value={defaults.lotSize}
              onChange={e => setDefaults({ ...defaults, lotSize: e.target.value })}
            />
          </div>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
              Max Open Positions
            </label>
            <input
              style={inputStyle}
              type="number"
              value={defaults.maxPositions}
              onChange={e => setDefaults({ ...defaults, maxPositions: e.target.value })}
            />
          </div>
          <div>
            <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
              Default Take Profit (pips)
            </label>
            <input
              style={inputStyle}
              type="number"
              value={defaults.tpPips}
              onChange={e => setDefaults({ ...defaults, tpPips: e.target.value })}
            />
          </div>
        </div>

        <button
          onClick={handleSaveDefaults}
          style={{
            background: '#1e2538',
            color: '#ffffff',
            border: '1px solid #28324f',
            borderRadius: '8px',
            padding: '9px 18px',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer'
          }}
        >
          Save Risk Parameters
        </button>
      </div>

      {/* 4. Plan & Engine Status */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
          <div style={{
            width: '34px',
            height: '34px',
            borderRadius: '8px',
            background: 'rgba(245, 158, 11, 0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <CreditCard size={17} color="#f59e0b" />
          </div>
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
              Engine & License Status
            </h2>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              MetaTrader 5 quantitative automation license & runtime bridge
            </div>
          </div>
        </div>

        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          background: '#0c0e15',
          border: '1px solid #1c2233',
          borderRadius: '12px',
          padding: '16px'
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <span style={{ fontSize: '15px', fontWeight: '700', color: '#ffffff' }}>Full Automation Suite</span>
              <span style={{
                background: 'rgba(16, 185, 129, 0.15)',
                color: '#10b981',
                padding: '2px 8px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: '600'
              }}>
                ACTIVE
              </span>
            </div>
            <div style={{ fontSize: '12px', color: '#64748b' }}>
              Node ID: <code style={{ color: '#cbd5e1' }}>{session?.user?.id ? `${session.user.id.slice(0, 18)}...` : 'MT5-CORE-LOCAL-INSTANCE'}</code>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => {
                const id = session?.user?.id || 'MT5-CORE-LOCAL-INSTANCE'
                navigator.clipboard?.writeText(id)
                toast.success('Engine ID copied to clipboard')
              }}
              style={{
                background: 'rgba(59, 91, 245, 0.15)',
                border: '1px solid rgba(59, 91, 245, 0.3)',
                color: '#818cf8',
                borderRadius: '8px',
                padding: '8px 14px',
                fontSize: '12px',
                fontWeight: '600',
                cursor: 'pointer'
              }}
            >
              Copy Node ID
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
