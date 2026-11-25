import { useState, useEffect, useCallback } from 'react'
import {
  TrendingUp, DollarSign, Target, BarChart3,
  ArrowUpRight, AlertCircle, RefreshCw
} from 'lucide-react'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, PieChart,
  Pie, Cell
} from 'recharts'
import api from '../api'

const timeframes = ['1W', '1M', '3M', '6M', '1Y', 'ALL']
const PIE_COLORS = ['#10b981', '#f43f5e']

export default function Analytics({ session }) {
  const [timeframe, setTimeframe] = useState('ALL')
  const [stats, setStats] = useState(null)
  const [equityCurve, setEquityCurve] = useState([])
  const [byStrategy, setByStrategy] = useState([])
  const [byPair, setByPair] = useState([])
  const [monthly, setMonthly] = useState([])
  const [trades, setTrades] = useState([])
  const [livePositions, setLivePositions] = useState([])
  const [floatingPnl, setFloatingPnl] = useState(0)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [apiError, setApiError] = useState(null)

  const getDateRange = useCallback((tf) => {
    if (tf === 'ALL') return {}
    const now = new Date()
    const from = new Date()
    if (tf === '1W') from.setDate(now.getDate() - 7)
    else if (tf === '1M') from.setMonth(now.getMonth() - 1)
    else if (tf === '3M') from.setMonth(now.getMonth() - 3)
    else if (tf === '6M') from.setMonth(now.getMonth() - 6)
    else if (tf === '1Y') from.setFullYear(now.getFullYear() - 1)
    return {
      from_date: from.toISOString(),
      to_date: now.toISOString()
    }
  }, [])

  const loadSummary = useCallback((cancelledRef = { current: false }, silent = false) => {
    if (!session?.access_token) {
      setLoading(false)
      return Promise.resolve()
    }
    if (!silent) setLoading(true)
    const headers = { 'Authorization': `Bearer ${session.access_token}` }
    const range = getDateRange(timeframe)
    const params = new URLSearchParams()
    if (range.from_date) params.set('from_date', range.from_date)
    if (range.to_date) params.set('to_date', range.to_date)
    params.set('limit', '100')
    const qStr = `?${params.toString()}`

    return api.get(`/api/analytics/summary${qStr}`, { headers })
      .then((summary) => {
        if (cancelledRef.current) return
        setApiError(null)
        const s = summary?.overview || {}
        setStats({
          total_trades: s.total_trades || 0,
          winning_trades: s.winning_trades || 0,
          losing_trades: s.losing_trades || 0,
          win_rate: s.win_rate || 0,
          total_profit: s.total_profit || 0,
          gross_profit: s.gross_profit || 0,
          gross_loss: s.gross_loss || 0,
          profit_factor: s.profit_factor || 0,
          avg_profit: s.avg_profit || 0,
          avg_pips: s.avg_pips || 0,
        })
        setEquityCurve(Array.isArray(summary?.equity_curve) ? summary.equity_curve : [])
        setByStrategy(Array.isArray(summary?.by_strategy) ? summary.by_strategy : [])
        setByPair(Array.isArray(summary?.by_pair) ? summary.by_pair : [])
        setMonthly(Array.isArray(summary?.monthly) ? summary.monthly : [])
        setTrades(Array.isArray(summary?.trades) ? summary.trades : [])
        setLivePositions(Array.isArray(summary?.live_positions) ? summary.live_positions : [])
        setFloatingPnl(Number(summary?.floating_pnl || 0))
      })
      .catch(() => {
        if (cancelledRef.current || silent) return
        setApiError('Backend offline')
        setStats({
          total_trades: 0,
          winning_trades: 0,
          losing_trades: 0,
          win_rate: 0,
          total_profit: 0,
          gross_profit: 0,
          gross_loss: 0,
          profit_factor: 0,
          avg_profit: 0,
          avg_pips: 0
        })
        setEquityCurve([])
        setByStrategy([])
        setByPair([])
        setMonthly([])
        setTrades([])
        setLivePositions([])
      })
      .finally(() => {
        if (!cancelledRef.current) setLoading(false)
      })
  }, [session, timeframe, getDateRange])

  useEffect(() => {
    const ref = { current: false }
    loadSummary(ref, false)
    const timer = setInterval(() => loadSummary(ref, true), 5000)
    return () => {
      ref.current = true
      clearInterval(timer)
    }
  }, [loadSummary])

  const handleSyncMt5 = async () => {
    if (!session?.access_token) return
    setSyncing(true)
    try {
      await api.post('/api/trades/sync-mt5', {}, { headers: { Authorization: `Bearer ${session.access_token}` } })
      await loadSummary()
    } catch {
      // ignore if MT5 offline
    } finally {
      setSyncing(false)
    }
  }

  const winCount = stats?.winning_trades || 0
  const lossCount = stats?.losing_trades || 0
  const winLossData = [
    { name: 'Wins', value: winCount },
    { name: 'Losses', value: lossCount },
  ]

  const statCards = [
    {
      label: 'Win Rate',
      value: `${stats?.win_rate || 0}%`,
      change: `${winCount} wins`,
      up: (stats?.win_rate || 0) >= 50,
      icon: Target,
      color: '#8b5cf6'
    },
    {
      label: 'Total Trades',
      value: String(stats?.total_trades || 0),
      change: `${winCount} wins · ${lossCount} losses`,
      up: true,
      icon: BarChart3,
      color: '#3b5bf5'
    },
    {
      label: 'Profit Factor',
      value: stats?.profit_factor ? stats.profit_factor.toFixed(2) : '0.00',
      change: 'Superior Performance',
      up: true,
      icon: TrendingUp,
      color: '#10b981'
    },
    {
      label: 'Net Profit',
      value: `$${(stats?.total_profit || 0).toLocaleString()}`,
      change: '',
      up: (stats?.total_profit || 0) >= 0,
      icon: DollarSign,
      color: '#f59e0b'
    },
    {
      label: 'Avg. Profit',
      value: `$${(stats?.avg_profit || 0).toLocaleString()}`,
      change: 'per trade',
      up: (stats?.avg_profit || 0) >= 0,
      icon: ArrowUpRight,
      color: '#06b6d4'
    },
  ]

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
        alignItems: 'flex-start',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: '800', color: '#ffffff', letterSpacing: '-0.3px', margin: 0 }}>
            Analytics & Performance
          </h1>
          <p style={{ color: '#94a3b8', fontSize: '13px', marginTop: '4px' }}>
            Comprehensive risk metrics, trade breakdown, and statistical equity analysis
          </p>
        </div>

        {/* Right controls: Sync MT5 + Timeframe pill selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <button
            onClick={handleSyncMt5}
            disabled={syncing}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 14px',
              background: '#131722',
              border: '1px solid #1c2233',
              borderRadius: '10px',
              color: '#94a3b8',
              fontSize: '12px',
              fontWeight: 600,
              cursor: syncing ? 'not-allowed' : 'pointer'
            }}
            title="Reconcile closed MT5 trades into Analytics"
          >
            <RefreshCw size={13} style={{ animation: syncing ? 'spin 1s linear infinite' : 'none' }} />
            <span>{syncing ? 'Syncing...' : 'Sync MT5 Deals'}</span>
          </button>

          <div style={{
            display: 'flex',
            background: '#131722',
            border: '1px solid #1c2233',
            borderRadius: '12px',
            padding: '4px',
            gap: '4px'
          }}>
            {timeframes.map(t => (
              <button
                key={t}
                onClick={() => setTimeframe(t)}
                style={{
                  padding: '6px 14px',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '12px',
                  background: timeframe === t ? '#3b5bf5' : 'transparent',
                  color: timeframe === t ? '#ffffff' : '#64748b',
                  transition: 'all 0.15s ease'
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </div>

      {apiError && (
        <div style={{
          background: 'rgba(59, 91, 245, 0.08)',
          border: '1px solid rgba(59, 91, 245, 0.25)',
          borderRadius: '12px',
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          fontSize: '13px',
          color: '#93c5fd'
        }}>
          <AlertCircle size={16} color="#60a5fa" />
          <span>{apiError}</span>
        </div>
      )}

      {/* Responsive Stat Cards Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '16px'
      }}>
        {statCards.map((st) => {
          const Icon = st.icon
          return (
            <div
              key={st.label}
              style={{
                background: '#131722',
                border: '1px solid #1c2233',
                borderRadius: '16px',
                padding: '18px 20px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                <span style={{ color: '#94a3b8', fontSize: '12px', fontWeight: '500' }}>{st.label}</span>
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  background: `${st.color}1a`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}>
                  <Icon size={16} color={st.color} />
                </div>
              </div>
              <div style={{ fontSize: '24px', fontWeight: '800', color: '#ffffff', letterSpacing: '-0.3px', marginBottom: '4px' }}>
                {st.value}
              </div>
              <div style={{ fontSize: '12px', color: st.up ? '#10b981' : '#f43f5e', fontWeight: '500' }}>
                {st.change}
              </div>
            </div>
          )
        })}
      </div>

      {/* Grid 2: Equity Curve & Win/Loss Distribution */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: '16px'
      }}>
        {/* Equity Curve */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px'
        }}>
          <h2 style={{ fontSize: '15px', fontWeight: '700', color: '#ffffff', marginBottom: '16px' }}>
            Account Equity Growth
          </h2>
          <div style={{ width: '100%', height: '240px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={equityCurve.length > 0 ? equityCurve : []}>
                <defs>
                  <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b5bf5" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#3b5bf5" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1c2233" vertical={false} />
                <XAxis dataKey="date" stroke="#334155" tick={{ fill: '#64748b', fontSize: 11 }} />
                <YAxis
                  stroke="#334155"
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  tickFormatter={v => Math.abs(v) >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${Number(v).toFixed(0)}`}
                />
                <Tooltip
                  contentStyle={{ background: '#0d1017', border: '1px solid #252d43', borderRadius: '8px', color: '#fff' }}
                  formatter={(val) => [`$${Number(val).toLocaleString()}`, 'Equity']}
                />
                <Area type="monotone" dataKey="equity" stroke="#3b5bf5" strokeWidth={2.5} fill="url(#eqGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Win / Loss Distribution */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <h2 style={{ fontSize: '15px', fontWeight: '700', color: '#ffffff', marginBottom: '16px' }}>
            Win / Loss Distribution
          </h2>
          <div style={{ width: '100%', height: '200px', position: 'relative' }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={winLossData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={75}
                  paddingAngle={4}
                  dataKey="value"
                >
                  {winLossData.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} stroke="none" />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#0d1017', border: '1px solid #252d43', borderRadius: '8px', color: '#fff' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '24px', marginTop: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10b981' }} />
              <span style={{ color: '#94a3b8' }}>Winning: <strong>{winLossData[0].value}</strong> ({(winLossData[0].value + winLossData[1].value) > 0 ? Math.round(winLossData[0].value / (winLossData[0].value + winLossData[1].value) * 100) : 0}%)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#f43f5e' }} />
              <span style={{ color: '#94a3b8' }}>Losing: <strong>{winLossData[1].value}</strong> ({(winLossData[0].value + winLossData[1].value) > 0 ? Math.round(winLossData[1].value / (winLossData[0].value + winLossData[1].value) * 100) : 0}%)</span>
            </div>
          </div>
        </div>
      </div>

      {/* Grid 3: Strategy & Monthly Returns */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: '16px'
      }}>
        {/* By Strategy */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px'
        }}>
          <h2 style={{ fontSize: '15px', fontWeight: '700', color: '#ffffff', marginBottom: '16px' }}>
            Performance by Strategy
          </h2>
          <div style={{ width: '100%', height: '220px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={byStrategy}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1c2233" vertical={false} />
                <XAxis dataKey="strategy" stroke="#334155" tick={{ fill: '#64748b', fontSize: 11 }} />
                <YAxis stroke="#334155" tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={v => Math.abs(v) >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${Number(v).toFixed(0)}`} />
                <Tooltip contentStyle={{ background: '#0d1017', border: '1px solid #252d43', borderRadius: '8px', color: '#fff' }} />
                <Bar dataKey="profit" fill="#8b5cf6" radius={[6, 6, 0, 0]} maxBarSize={36} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Monthly Returns */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px'
        }}>
          <h2 style={{ fontSize: '15px', fontWeight: '700', color: '#ffffff', marginBottom: '16px' }}>
            Monthly Returns
          </h2>
          <div style={{ width: '100%', height: '220px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthly}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1c2233" vertical={false} />
                <XAxis dataKey="month" stroke="#334155" tick={{ fill: '#64748b', fontSize: 11 }} />
                <YAxis stroke="#334155" tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={v => Math.abs(v) >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${Number(v).toFixed(0)}`} />
                <Tooltip contentStyle={{ background: '#0d1017', border: '1px solid #252d43', borderRadius: '8px', color: '#fff' }} />
                <Bar dataKey="profit" radius={[6, 6, 0, 0]} maxBarSize={32}>
                  {monthly.map((entry, index) => (
                    <Cell key={index} fill={entry.profit >= 0 ? '#10b981' : '#f43f5e'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Live Open MT5 Positions Banner */}
      {livePositions.length > 0 && (
        <div style={{
          background: 'rgba(16, 185, 129, 0.06)',
          border: '1px solid rgba(16, 185, 129, 0.25)',
          borderRadius: '18px',
          padding: '20px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
            <h2 style={{ fontSize: '15px', fontWeight: '700', color: '#10b981', margin: 0 }}>
              Live Open MT5 Positions ({livePositions.length})
            </h2>
            <span style={{ fontSize: '14px', fontWeight: 800, color: floatingPnl >= 0 ? '#10b981' : '#f43f5e' }}>
              Floating P&amp;L: {floatingPnl >= 0 ? '+' : ''}${floatingPnl.toFixed(2)}
            </span>
          </div>
          <div className="responsive-table-wrapper">
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ color: '#64748b', borderBottom: '1px solid #1c2233' }}>
                  {['Ticket', 'Symbol', 'Direction', 'Lots', 'Entry', 'Current', 'SL / TP', 'Floating P&L'].map(h => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: '600' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {livePositions.map(p => (
                  <tr key={p.ticket} style={{ borderBottom: '1px solid #161b2a' }}>
                    <td style={{ padding: '10px 12px', color: '#94a3b8', fontFamily: 'monospace' }}>#{p.ticket}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 700, color: '#fff' }}>{p.symbol}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 700, color: p.type === 'BUY' ? '#10b981' : '#f43f5e' }}>{p.type}</td>
                    <td style={{ padding: '10px 12px', color: '#cbd5e1' }}>{p.volume}</td>
                    <td style={{ padding: '10px 12px', color: '#cbd5e1' }}>{p.open_price}</td>
                    <td style={{ padding: '10px 12px', color: '#fff', fontWeight: 600 }}>{p.current_price}</td>
                    <td style={{ padding: '10px 12px', color: '#94a3b8', fontSize: '11px' }}>{p.stop_loss || '—'} / {p.take_profit || '—'}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 800, color: Number(p.profit) >= 0 ? '#10b981' : '#f43f5e' }}>
                      {Number(p.profit) >= 0 ? '+' : ''}${Number(p.profit || 0).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Trade History Table with Responsive Horizontal Scroll */}
      <div style={{
        background: '#131722',
        border: '1px solid #1c2233',
        borderRadius: '18px',
        padding: '20px'
      }}>
        <h2 style={{ fontSize: '15px', fontWeight: '700', color: '#ffffff', marginBottom: '16px' }}>
          Live &amp; Historical Trade Log
        </h2>

        <div className="responsive-table-wrapper">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ color: '#64748b', borderBottom: '1px solid #1c2233' }}>
                {['Date', 'Pair', 'Direction', 'Volume', 'Strategy', 'Profit', 'Status'].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: '600' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                    No trades available
                  </td>
                </tr>
              ) : (
                trades.map((t, i) => {
                  const isBuy = (t.direction || '').toUpperCase() === 'BUY'
                  const profitNum = Number(t.profit || 0)
                  return (
                  <tr key={t.id || t.ticket || i} style={{ borderBottom: '1px solid #161b2a' }}>
                    <td style={{ padding: '12px 14px', color: '#94a3b8' }}>{t.opened_at ? new Date(t.opened_at).toLocaleDateString() : '--'}</td>
                    <td style={{ padding: '12px 14px', fontWeight: '600', color: '#ffffff' }}>{t.symbol || t.pair}</td>
                    <td style={{ padding: '12px 14px' }}>
                      <span style={{
                        padding: '3px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: '600',
                        background: isBuy ? 'rgba(16, 185, 129, 0.12)' : 'rgba(244, 63, 94, 0.12)',
                        color: isBuy ? '#10b981' : '#f43f5e'
                      }}>
                        {(t.direction || 'BUY').toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: '12px 14px', color: '#cbd5e1' }}>{t.volume || t.lot_size || '--'}</td>
                    <td style={{ padding: '12px 14px', color: '#94a3b8' }}>{t.strategy || '--'}</td>
                    <td style={{ padding: '12px 14px', fontWeight: '700', color: profitNum >= 0 ? '#10b981' : '#f43f5e' }}>
                      {profitNum !== 0 ? `${profitNum >= 0 ? '+' : ''}$${profitNum.toFixed(2)}` : '$0.00'}
                    </td>
                    <td style={{ padding: '12px 14px' }}>
                      <span style={{
                        padding: '3px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: '600',
                        background: t.is_live ? 'rgba(16, 185, 129, 0.15)' : 'rgba(59, 91, 245, 0.12)',
                        color: t.is_live ? '#10b981' : '#818cf8'
                      }}>
                        {t.is_live ? 'LIVE OPEN' : (t.status || 'open')}
                      </span>
                    </td>
                  </tr>
                )})
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
