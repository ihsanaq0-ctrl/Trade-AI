import { useState, useEffect } from 'react'
import {
  Plus, PlugZap, Unplug, Database, Trash2,
  AlertCircle, ShieldCheck, CheckCircle2, X, RefreshCw
} from 'lucide-react'
import api from '../api'
import { useToast } from '../components/Toast'

export default function Accounts({ session }) {
  const [accounts, setAccounts] = useState([])
  const [mt5Info, setMt5Info] = useState(null)
  const [showAdd, setShowAdd] = useState(false)
  const [loading, setLoading] = useState(true)
  const [syncingId, setSyncingId] = useState(null)
  const [form, setForm] = useState({
    nickname: '',
    broker: 'Exness',
    login: '',
    password: '',
    server: '',
    type: 'demo'
  })
  const toast = useToast()

  useEffect(() => {
    if (!session?.access_token) {
      setLoading(false)
      return
    }

    const headers = { 'Authorization': `Bearer ${session.access_token}` }

    api.get('/api/accounts', { headers })
      .then(d => {
        if (Array.isArray(d) && d.length > 0) {
          setAccounts(d)
        } else {
          setAccounts([])
        }
      })
      .catch(() => {
        // Fallback default
        setAccounts([])
      })

    api.get('/api/markets/active-account')
      .then(d => setMt5Info(d?.balance !== undefined ? d : null))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [session])

  const handleAdd = async () => {
    if (!form.nickname || !form.login || !form.server) {
      toast.error('Please fill in all required fields')
      return
    }

    try {
      const payload = {
        nickname: form.nickname,
        broker: form.broker,
        login: form.login,
        password: form.password || '',
        server: form.server,
        account_type: form.type || 'demo'
      }

      // Save to backend database
      const saved = await api.post('/api/accounts', payload)
      let finalAcc = {
        ...saved,
        balance: saved.balance || 0,
        equity: saved.equity || 0,
        profit: saved.profit || 0,
        status: 'connected',
        color: (saved.account_type || form.type) === 'live' ? '#3b5bf5' : '#f59e0b'
      }

      // Automatically connect to register credentials and fetch balance
      try {
        const connRes = await api.post(`/api/accounts/${saved.id}/connect`)
        if (connRes?.success) {
          finalAcc.balance = connRes.balance ?? finalAcc.balance
          finalAcc.equity = connRes.equity ?? finalAcc.equity
        }
      } catch (connErr) {
        console.warn('Initial connect warning:', connErr)
      }

      setAccounts(prev => [finalAcc, ...prev.filter(a => a.id !== finalAcc.id)])
      setShowAdd(false)
      setForm({ nickname: '', broker: 'Exness', login: '', password: '', server: '', type: 'demo' })
      toast.success('Broker account connected successfully')
    } catch (e) {
      toast.error(`Connection failed: ${e?.response?.data?.detail || e.message}`)
    }
  }

  const toggleConnect = async (id, currentStatus) => {
    try {
      const isConnecting = currentStatus !== 'connected'
      const endpoint = isConnecting ? `/api/accounts/${id}/connect` : `/api/accounts/${id}/disconnect`
      const res = await api.post(endpoint)

      setAccounts(prev => prev.map(a => a.id === id ? {
        ...a,
        status: isConnecting ? 'connected' : 'disconnected',
        ...(res?.balance !== undefined ? { balance: res.balance, equity: res.equity } : {})
      } : a))
      toast.info(isConnecting ? 'Account connected' : 'Account disconnected')
    } catch (e) {
      toast.error(`Operation failed: ${e?.response?.data?.detail || e.message}`)
    }
  }

  const removeAccount = async (id) => {
    try {
      await api.delete(`/api/accounts/${id}`)
      setAccounts(prev => prev.filter(a => a.id !== id))
      toast.success('Account removed')
    } catch (e) {
      toast.error(`Failed to remove account: ${e?.response?.data?.detail || e.message}`)
    }
  }

  const syncAccount = async (id) => {
    try {
      setSyncingId(id)
      const res = await api.post(`/api/accounts/${id}/sync`)
      setAccounts(prev => prev.map(a => a.id === id ? {
        ...a,
        balance: res?.balance !== undefined ? res.balance : a.balance,
        equity: res?.equity !== undefined ? res.equity : a.equity,
        profit: res?.profit !== undefined ? res.profit : a.profit,
      } : a))
      toast.success('Account synced successfully')
    } catch (e) {
      toast.error(`Sync failed: ${e?.response?.data?.detail || e.message}`)
    } finally {
      setSyncingId(null)
    }
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

  return (
    <div style={{
      padding: '24px',
      background: '#0c0e15',
      minHeight: '100vh',
      color: '#f8fafc',
      display: 'flex',
      flexDirection: 'column',
      gap: '24px'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: '800', color: '#ffffff', letterSpacing: '-0.3px', margin: 0 }}>
            Broker Accounts & Portfolios
          </h1>
          <p style={{ color: '#94a3b8', fontSize: '13px', marginTop: '4px' }}>
            Manage MT4, MT5, and proprietary trading broker terminals
          </p>
        </div>

        <button
          onClick={() => setShowAdd(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: '#3b5bf5',
            border: 'none',
            color: '#ffffff',
            padding: '10px 18px',
            borderRadius: '10px',
            fontWeight: '600',
            fontSize: '13px',
            cursor: 'pointer',
            boxShadow: '0 4px 14px rgba(59, 91, 245, 0.3)'
          }}
        >
          <Plus size={16} />
          <span>Add Account</span>
        </button>
      </div>

      {/* Active MT5 Status Banner */}
      {mt5Info?.login && (
        <div style={{
          background: 'rgba(16, 185, 129, 0.08)',
          border: '1px solid rgba(16, 185, 129, 0.25)',
          borderRadius: '14px',
          padding: '14px 18px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <PlugZap size={18} color="#10b981" />
            <span style={{ fontSize: '13px', color: '#94a3b8' }}>
              <strong style={{ color: '#ffffff' }}>MT5 Terminal Connected</strong> — Login {mt5Info.login} on {mt5Info.server}
            </span>
          </div>
          <span style={{ fontSize: '14px', fontWeight: '700', color: '#10b981' }}>
            ${mt5Info.balance?.toLocaleString()} {mt5Info.currency || 'USD'}
          </span>
        </div>
      )}

      {/* Account List Grid */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {loading && accounts.length === 0 ? (
          <div style={{
            background: '#131722', border: '1px solid #1c2233', borderRadius: '16px',
            padding: '24px', display: 'flex', flexDirection: 'column', gap: '14px',
            animation: 'pulseGlow 1.5s infinite'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ width: '160px', height: '20px', borderRadius: '6px', background: '#1c2233' }} />
              <div style={{ width: '80px', height: '20px', borderRadius: '6px', background: '#1c2233' }} />
            </div>
            <div style={{ width: '220px', height: '14px', borderRadius: '6px', background: '#1c2233' }} />
            <div style={{ display: 'flex', gap: '24px', marginTop: '8px' }}>
              <div style={{ width: '90px', height: '24px', borderRadius: '6px', background: '#1c2233' }} />
              <div style={{ width: '90px', height: '24px', borderRadius: '6px', background: '#1c2233' }} />
            </div>
          </div>
        ) : !loading && accounts.length === 0 ? (
          <div style={{
            background: '#131722', border: '1px solid #1c2233', borderRadius: '16px',
            padding: '36px', textAlign: 'center', color: '#64748b'
          }}>
            <ShieldCheck size={36} style={{ marginBottom: '12px', opacity: 0.5 }} />
            <div style={{ fontSize: '15px', fontWeight: 600, color: '#94a3b8', marginBottom: '6px' }}>No broker accounts connected</div>
            <p style={{ fontSize: '13px', margin: 0 }}>Click "+ Add Account" to link your MetaTrader 5 or proprietary trading account credentials.</p>
          </div>
        ) : null}

        {accounts.map((a) => {
          const isPositive = (a.profit || 0) >= 0
          return (
            <div
              key={a.id}
              style={{
                background: '#131722',
                border: '1px solid #1c2233',
                borderRadius: '16px',
                padding: '20px 22px',
                position: 'relative'
              }}
            >
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                flexWrap: 'wrap',
                gap: '16px'
              }}>
                {/* Account Details */}
                <div style={{ minWidth: '220px', flex: '1 1 240px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                    <span style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      background: a.status === 'connected' ? '#10b981' : '#64748b',
                      boxShadow: a.status === 'connected' ? '0 0 8px #10b981' : 'none'
                    }} />
                    <span style={{ fontSize: '16px', fontWeight: '700', color: '#ffffff' }}>
                      {a.nickname}
                    </span>
                    <span style={{
                      fontSize: '11px',
                      fontWeight: '600',
                      padding: '2px 8px',
                      borderRadius: '6px',
                      background: (a.account_type || a.type) === 'live' ? 'rgba(59, 91, 245, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                      color: (a.account_type || a.type) === 'live' ? '#818cf8' : '#f59e0b'
                    }}>
                      {(a.account_type || a.type || 'demo').toUpperCase()}
                    </span>
                  </div>
                  <div style={{ fontSize: '13px', color: '#94a3b8' }}>
                    {a.broker} · {a.server} · Account ID: <code style={{ color: '#cbd5e1' }}>{a.login}</code>
                  </div>
                </div>

                {/* Account Metrics: Responsive Wrap */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '24px',
                  flexWrap: 'wrap',
                  justifyContent: 'flex-end',
                  flex: '2 1 300px'
                }}>
                  <div>
                    <div style={{ fontSize: '11px', color: '#64748b', fontWeight: '500', marginBottom: '2px' }}>Balance</div>
                    <div style={{ fontSize: '15px', fontWeight: '700', color: '#ffffff' }}>
                      ${(a.balance || 0).toLocaleString()}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: '11px', color: '#64748b', fontWeight: '500', marginBottom: '2px' }}>Equity</div>
                    <div style={{ fontSize: '15px', fontWeight: '700', color: '#cbd5e1' }}>
                      ${(a.equity || 0).toLocaleString()}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: '11px', color: '#64748b', fontWeight: '500', marginBottom: '2px' }}>Total P&L</div>
                    <div style={{ fontSize: '15px', fontWeight: '700', color: isPositive ? '#10b981' : '#f43f5e' }}>
                      {isPositive ? '+' : ''}${(a.profit || 0).toLocaleString()}
                    </div>
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <button
                      onClick={() => toggleConnect(a.id, a.status)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '8px 14px',
                        borderRadius: '8px',
                        border: 'none',
                        fontSize: '12px',
                        fontWeight: '600',
                        cursor: 'pointer',
                        background: a.status === 'connected' ? 'rgba(244, 63, 94, 0.12)' : 'rgba(16, 185, 129, 0.12)',
                        color: a.status === 'connected' ? '#f43f5e' : '#10b981',
                        transition: 'all 0.15s ease'
                      }}
                    >
                      {a.status === 'connected' ? <Unplug size={14} /> : <PlugZap size={14} />}
                      <span>{a.status === 'connected' ? 'Disconnect' : 'Connect'}</span>
                    </button>

                    {a.status === 'connected' && (
                      <button
                        onClick={() => syncAccount(a.id)}
                        disabled={syncingId === a.id}
                        style={{
                          padding: '8px',
                          borderRadius: '8px',
                          border: '1px solid #1c2233',
                          background: '#0c0e15',
                          color: '#3b82f6',
                          cursor: syncingId === a.id ? 'not-allowed' : 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center'
                        }}
                        title="Sync Account Balance"
                      >
                        <RefreshCw size={14} style={{ animation: syncingId === a.id ? 'spin 1s linear infinite' : 'none' }} />
                      </button>
                    )}

                    <button
                      onClick={() => removeAccount(a.id)}
                      style={{
                        padding: '8px',
                        borderRadius: '8px',
                        border: '1px solid #1c2233',
                        background: '#0c0e15',
                        color: '#64748b',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}
                      title="Remove Account"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Add Account Responsive Modal */}
      {showAdd && (
        <div
          onClick={() => setShowAdd(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.7)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '16px',
            zIndex: 1000
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: '#131722',
              border: '1px solid #252d43',
              borderRadius: '20px',
              padding: '28px',
              width: '100%',
              maxWidth: '480px',
              boxShadow: '0 20px 50px rgba(0,0,0,0.6)'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '18px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
                Connect Broker Account
              </h2>
              <button
                onClick={() => setShowAdd(false)}
                style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
                  Account Nickname
                </label>
                <input
                  style={inputStyle}
                  placeholder="e.g. Exness Live Main"
                  value={form.nickname}
                  onChange={e => setForm({ ...form, nickname: e.target.value })}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
                    Broker
                  </label>
                  <select
                    style={inputStyle}
                    value={form.broker}
                    onChange={e => setForm({ ...form, broker: e.target.value })}
                  >
                    <option value="Exness">Exness</option>
                    <option value="FTMO">FTMO</option>
                    <option value="IC Markets">IC Markets</option>
                    <option value="Funding Pips">Funding Pips</option>
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
                    Account Type
                  </label>
                  <select
                    style={inputStyle}
                    value={form.type}
                    onChange={e => setForm({ ...form, type: e.target.value })}
                  >
                    <option value="demo">Demo</option>
                    <option value="live">Live</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
                    MT5 Login ID
                  </label>
                  <input
                    style={inputStyle}
                    placeholder="12345678"
                    value={form.login}
                    onChange={e => setForm({ ...form, login: e.target.value })}
                  />
                </div>

                <div>
                  <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
                    Server
                  </label>
                  <input
                    style={inputStyle}
                    placeholder="Exness-MT5Real9"
                    value={form.server}
                    onChange={e => setForm({ ...form, server: e.target.value })}
                  />
                </div>
              </div>

              <div>
                <label style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '500', marginBottom: '6px', display: 'block' }}>
                  Master / Investor Password
                </label>
                <input
                  style={inputStyle}
                  type="password"
                  placeholder="••••••••••••"
                  value={form.password}
                  onChange={e => setForm({ ...form, password: e.target.value })}
                />
              </div>

              <div style={{ display: 'flex', gap: '12px', marginTop: '10px' }}>
                <button
                  onClick={() => setShowAdd(false)}
                  style={{
                    flex: 1,
                    padding: '11px',
                    background: '#171b28',
                    border: '1px solid #1c2233',
                    borderRadius: '10px',
                    color: '#94a3b8',
                    fontWeight: '600',
                    fontSize: '13px',
                    cursor: 'pointer'
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleAdd}
                  style={{
                    flex: 1,
                    padding: '11px',
                    background: '#3b5bf5',
                    border: 'none',
                    borderRadius: '10px',
                    color: '#ffffff',
                    fontWeight: '600',
                    fontSize: '13px',
                    cursor: 'pointer'
                  }}
                >
                  Save & Connect
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
