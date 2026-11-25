import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Eye, EyeOff, TrendingUp, TrendingDown, ArrowUpRight,
  ArrowDownLeft, DollarSign, Sparkles, X, Info,
  ChevronDown, Cpu, Shield, Clock, CheckCircle2, ArrowRight,
  Target, Activity, Zap, Layers, AlertTriangle
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, BarChart, Bar
} from 'recharts'
import api from '../api'
import { fetchLiveMarketData, DEFAULT_TOP_PAIRS } from '../services/marketData'

export default function Dashboard({ session }) {
  const navigate = useNavigate()
  const [showBalance, setShowBalance] = useState(true)
  const [showAssistantBanner, setShowAssistantBanner] = useState(true)
  const [marketData, setMarketData] = useState(DEFAULT_TOP_PAIRS)
  const [account, setAccount] = useState(null)
  const [liveTrades, setLiveTrades] = useState([])
  const [userBots, setUserBots] = useState([])
  const [equityCurve, setEquityCurve] = useState([])
  const [drawdown, setDrawdown] = useState({ current_drawdown: 0, max_drawdown_pct: 0, max_drawdown_amount: 0 })
  const [loadingMarkets, setLoadingMarkets] = useState(true)
  const [analytics, setAnalytics] = useState({
    grossProfit: 0,
    grossLoss: 0,
    netProfit: 0,
    totalTrades: 0,
    winRate: 0,
    profitFactor: 0
  })

  const uid = session?.user?.id || 'guest'
  const userName = session?.user?.user_metadata?.full_name?.split(' ')[0] 
    || (session?.user?.email ? session.user.email.split('@')[0] : 'Trader')

  // Fetch real-time live market pairs + fast single-shot backend telemetry
  useEffect(() => {
    let isMounted = true

    const loadMarkets = async () => {
      try {
        const data = await fetchLiveMarketData()
        if (isMounted) {
          setMarketData(data.overview)
          setLoadingMarkets(false)
        }
      } catch {
        if (isMounted) setLoadingMarkets(false)
      }
    }

    loadMarkets()
    const timer = setInterval(loadMarkets, 8000)

    if (session?.access_token) {
      const headers = { Authorization: `Bearer ${session.access_token}` }

      // Fetch active account, combined analytics summary, and real user bots in parallel (3 fast requests total!)
      Promise.all([
        api.get('/api/markets/active-account', { headers }).catch(() => null),
        api.get('/api/analytics/summary?limit=10', { headers }).catch(() => null),
        api.get('/api/bots', { headers }).catch(() => []),
      ]).then(([accData, summaryData, botsData]) => {
        if (!isMounted) return

        if (accData && accData.connected && accData.login) {
          setAccount(accData)
        } else {
          setAccount(null)
        }

        if (summaryData) {
          const ov = summaryData.overview || {}
          setAnalytics({
            grossProfit: Number(ov.gross_profit) || 0,
            grossLoss: Number(ov.gross_loss) || 0,
            netProfit: Number(ov.total_profit) || 0,
            totalTrades: Number(ov.total_trades) || 0,
            winRate: Number(ov.win_rate) || 0,
            profitFactor: Number(ov.profit_factor) || 0
          })
          if (Array.isArray(summaryData.equity_curve)) {
            setEquityCurve(summaryData.equity_curve)
          }
          if (summaryData.drawdown) {
            setDrawdown(summaryData.drawdown)
          }
          if (Array.isArray(summaryData.trades)) {
            setLiveTrades(summaryData.trades)
          }
        }

        if (Array.isArray(botsData)) {
          setUserBots(botsData)
        }
      })
    }

    return () => {
      isMounted = false
      clearInterval(timer)
    }
  }, [session])

  // Real Account Equity Curve Data
  const chartData = (equityCurve && equityCurve.length > 0)
    ? equityCurve
    : [
        { date: 'Initial', equity: account?.balance || 0 },
        { date: 'Live', equity: account?.equity || account?.balance || 0 }
      ]

  const equityValues = chartData.map(d => Number(d.equity) || 0)
  const minEquity = Math.min(...equityValues, (account?.balance || 0) * 0.98)
  const maxEquity = Math.max(...equityValues, (account?.equity || account?.balance || 0) * 1.02)

  // Real Margin & Capital Allocation
  const freeMargin = account?.margin_free ?? (account?.balance || 0)
  const usedMargin = account?.margin ?? 0
  const marginData = (freeMargin > 0 || usedMargin > 0) ? [
    { name: 'Free Margin', value: Math.max(0, Number(freeMargin.toFixed(2))), color: '#10b981' },
    { name: 'Used Margin', value: Math.max(0, Number(usedMargin.toFixed(2))), color: '#3b5bf5' }
  ] : [
    { name: 'Available Capital', value: 100, color: '#10b981' }
  ]

  // Quantitative Drawdown & Risk Calculation
  const currentDd = Number(drawdown?.current_drawdown || 0)
  const maxDd = Number(drawdown?.max_drawdown_pct || 0)
  const gaugePercent = Math.min(Math.max(currentDd / 20, 0), 1) // 20% max gauge scale
  const strokeOffset = 125.6 * (1 - gaugePercent)
  const riskColor = currentDd < 5 ? '#10b981' : (currentDd < 10 ? '#f59e0b' : '#f43f5e')
  const riskTitle = currentDd < 5 ? 'Capital Protected' : (currentDd < 10 ? 'Moderate Exposure' : 'High Drawdown Alert')
  const riskDesc = currentDd < 5 ? 'Drawdown is under 5.0%. Margin exposure is optimal.' : 'Drawdown elevated. Monitor active bot positions.'

  // Real User Algorithmic Bots (instead of hardcoded fake statuses)
  const strategyPalette = {
    smart_money: '#10b981',
    pipstep_reversal: '#00d4ff',
    classic: '#3b5bf5',
    scalp_fvg: '#a855f7',
    scalp_pyramid: '#ff6b35',
    nyao_scalper: '#38ef7d',
    full_confluence: '#f59e0b'
  }
  const strategies = userBots.slice(0, 3).map(b => ({
    id: b.id,
    name: (b.strategy || 'bot').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    pair: `${b.pair || 'EURUSD'} · ${b.timeframe || 'H1'}`,
    status: (b.status || 'stopped').toUpperCase(),
    color: strategyPalette[b.strategy] || '#3b5bf5'
  }))

  // Quant Risk Limits & Safeguards (reads user-scoped preferences when set)
  let riskPrefs = {}
  try {
    riskPrefs = JSON.parse(localStorage.getItem(`trade_bot_risk_defaults_${uid}`) || '{}')
  } catch {}
  const dailyTarget = 100
  const dailyProfit = Math.max(0, analytics.netProfit)
  const dailyTargetPct = Math.min(100, Math.round((dailyProfit / dailyTarget) * 100))

  const maxPositionsLimit = Number(riskPrefs.maxPositions) || 3
  const currentOpenPositions = liveTrades.filter(t => (t.status || '').toLowerCase() === 'open').length
  const positionOccupancyPct = Math.min(100, Math.round((currentOpenPositions / maxPositionsLimit) * 100))

  const maxLossLimitPct = Number(riskPrefs.riskPercent) || 3.0
  const lossGuardPct = Math.min(100, Math.round((currentDd / maxLossLimitPct) * 100))

  const pnlDistributionData = [
    { name: 'P&L', Profit: analytics.grossProfit, Loss: analytics.grossLoss }
  ]

  return (
    <div style={{
      padding: '24px',
      background: '#0c0e15',
      minHeight: '100vh',
      color: '#f8fafc',
      display: 'flex',
      flexDirection: 'column',
      gap: '20px'
    }}>

      {/* ================= ROW 1 ================= */}
      <div className="dashboard-grid-row1">
        {/* 1.1 Account Capital & Equity Card */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '22px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          position: 'relative'
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', color: '#94a3b8', fontWeight: '500' }}>Account Equity</span>
                <button
                  onClick={() => setShowBalance(!showBalance)}
                  style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                  title="Toggle balance visibility"
                >
                  {showBalance ? <Eye size={15} /> : <EyeOff size={15} />}
                </button>
              </div>
              <span style={{
                fontSize: '11px',
                color: account?.terminal_synced ? '#10b981' : (account?.connected ? '#f59e0b' : '#64748b'),
                background: '#171b28',
                padding: '2px 8px',
                borderRadius: '4px',
                border: '1px solid #252d43'
              }}>
                {account?.server || 'No Broker Connected'}
              </span>
            </div>

            <div style={{
              fontSize: '32px',
              fontWeight: '800',
              color: '#ffffff',
              letterSpacing: '-0.5px',
              lineHeight: 1.1,
              marginBottom: '8px'
            }}>
              {showBalance ? (account?.equity ? `$${account.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : (account?.balance ? `$${account.balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '$0.00')) : '••••••••'}
            </div>

            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', marginBottom: '20px' }}>
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                background: (account?.profit >= 0) ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                color: (account?.profit >= 0) ? '#10b981' : '#f43f5e',
                padding: '3px 8px',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: '600'
              }}>
                {(account?.profit >= 0) ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                {(account?.profit >= 0 ? '+' : '')}${(account?.profit || 0).toFixed(2)} Floating P&L
              </span>
              <span style={{ fontSize: '12px', color: '#64748b' }}>
                Balance: ${account?.balance ? account.balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00'}
              </span>
            </div>
          </div>

          {/* Sub-metrics: Gross Profit, Gross Loss, Net P&L */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr',
            gap: '10px',
            borderTop: '1px solid #1c2233',
            paddingTop: '16px'
          }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#10b981', fontSize: '11px', fontWeight: '600', marginBottom: '3px' }}>
                <ArrowDownLeft size={13} />
                <span>Gross Profit</span>
              </div>
              <div style={{ fontSize: '14px', fontWeight: '700', color: '#ffffff' }}>
                ${analytics.grossProfit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#f43f5e', fontSize: '11px', fontWeight: '600', marginBottom: '3px' }}>
                <ArrowUpRight size={13} />
                <span>Gross Loss</span>
              </div>
              <div style={{ fontSize: '14px', fontWeight: '700', color: '#ffffff' }}>
                ${analytics.grossLoss.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#38bdf8', fontSize: '11px', fontWeight: '600', marginBottom: '3px' }}>
                <TrendingUp size={13} />
                <span>Net P&amp;L</span>
              </div>
              <div style={{ fontSize: '14px', fontWeight: '700', color: analytics.netProfit >= 0 ? '#10b981' : '#f43f5e' }}>
                {analytics.netProfit >= 0 ? '+' : ''}${analytics.netProfit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
          </div>
        </div>

        {/* 1.2 Account Equity Curve */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px 22px',
          position: 'relative'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <div>
              <h2 style={{ fontSize: '15px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
                Account Equity Curve
              </h2>
              <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                Historical mark-to-market performance
              </div>
            </div>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: '#171b28',
              border: '1px solid #252d43',
              borderRadius: '8px',
              padding: '5px 10px',
              fontSize: '12px',
              color: '#94a3b8'
            }}>
              <span>Live Feed</span>
            </div>
          </div>

          <div style={{ width: '100%', height: '175px', position: 'relative' }}>
            {/* Peak Equity Marker */}
            <div style={{
              position: 'absolute',
              top: '10px',
              right: '20px',
              background: '#0f172a',
              border: '1px solid #283354',
              color: '#10b981',
              padding: '4px 10px',
              borderRadius: '6px',
              fontSize: '11px',
              fontWeight: '700',
              zIndex: 10
            }}>
              Live: ${account?.equity ? account.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00'}
            </div>

            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="growthGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b5bf5" stopOpacity={0.6} />
                    <stop offset="95%" stopColor="#141829" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  stroke="#334155"
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  stroke="#334155"
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  domain={[Math.floor(minEquity), Math.ceil(maxEquity)]}
                  tickFormatter={(val) => `$${Number(val).toLocaleString()}`}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div style={{
                          background: '#0f172a',
                          border: '1px solid #334155',
                          borderRadius: '8px',
                          padding: '6px 10px',
                          color: '#fff',
                          fontSize: '12px'
                        }}>
                          <div style={{ color: '#94a3b8', fontSize: '11px' }}>{payload[0].payload.date}</div>
                          <div style={{ fontWeight: '700', color: '#818cf8' }}>
                            ${Number(payload[0].value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </div>
                        </div>
                      )
                    }
                    return null
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="equity"
                  stroke="#3b5bf5"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#growthGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 1.3 Quant Engine & Risk Telemetry */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Top 2 Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            {/* Win Rate */}
            <div style={{
              background: '#131722',
              border: '1px solid #1c2233',
              borderRadius: '16px',
              padding: '14px 16px',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: '500' }}>Win Rate</span>
                <Target size={15} color="#8b5cf6" />
              </div>
              <div style={{ fontSize: '20px', fontWeight: '800', color: analytics.winRate >= 50 ? '#10b981' : '#cbd5e1' }}>
                {analytics.winRate}%
              </div>
            </div>

            {/* Total Closed Trades */}
            <div style={{
              background: '#131722',
              border: '1px solid #1c2233',
              borderRadius: '16px',
              padding: '14px 16px',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: '500' }}>Total Trades</span>
                <Activity size={15} color="#3b5bf5" />
              </div>
              <div style={{ fontSize: '20px', fontWeight: '800', color: '#ffffff' }}>
                {analytics.totalTrades}
              </div>
            </div>
          </div>

          {/* Quant Engine Runtime Card */}
          {showAssistantBanner && (
            <div style={{
              background: 'linear-gradient(135deg, #181d33 0%, #15192b 100%)',
              border: '1px solid #283354',
              borderRadius: '16px',
              padding: '16px 18px',
              position: 'relative',
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center'
            }}>
              <button
                onClick={() => setShowAssistantBanner(false)}
                style={{
                  position: 'absolute',
                  top: '12px',
                  right: '12px',
                  background: 'none',
                  border: 'none',
                  color: '#64748b',
                  cursor: 'pointer'
                }}
              >
                <X size={15} />
              </button>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <span style={{
                  width: '8px', height: '8px', borderRadius: '50%',
                  background: account?.terminal_synced ? '#10b981' : (account?.connected ? '#f59e0b' : '#64748b'),
                  boxShadow: account?.terminal_synced ? '0 0 8px #10b981' : (account?.connected ? '0 0 8px #f59e0b' : 'none')
                }} />
                <span style={{ fontSize: '12px', fontWeight: '700', color: '#cbd5e1' }}>
                  MT5 Execution Bridge
                </span>
              </div>

              <div style={{ fontSize: '13px', fontWeight: '700', color: '#ffffff', marginBottom: '6px' }}>
                {account?.terminal_synced
                  ? `Synced: #${account.login}`
                  : account?.connected
                  ? `Linked: #${account.login} (Not Synced)`
                  : 'No MT5 Account Connected'}
              </div>

              {account?.connected ? (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '11px', color: '#94a3b8' }}>
                  <div>Leverage: <strong style={{ color: '#ffffff' }}>1:{account?.leverage || 100}</strong></div>
                  <div>Free Margin: <strong style={{ color: '#10b981' }}>${account?.margin_free ? Math.round(account.margin_free).toLocaleString() : '0'}</strong></div>
                </div>
              ) : (
                <button
                  onClick={() => navigate('/accounts')}
                  style={{
                    marginTop: '4px',
                    padding: '6px 12px',
                    borderRadius: '8px',
                    background: 'rgba(59, 91, 245, 0.2)',
                    border: '1px solid rgba(59, 91, 245, 0.4)',
                    color: '#818cf8',
                    fontSize: '11px',
                    fontWeight: '700',
                    cursor: 'pointer',
                    alignSelf: 'flex-start'
                  }}
                >
                  Connect MT5 Account →
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ================= ROW 2 ================= */}
      <div className="dashboard-grid-row2">
        {/* 2.1 Margin & Capital Allocation */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <h2 style={{ fontSize: '14px', fontWeight: '700', color: '#ffffff', marginBottom: '14px' }}>
            Capital &amp; Margin Allocation
          </h2>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
            {/* Donut Chart with Center Text */}
            <div style={{ width: '130px', height: '130px', position: 'relative' }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={marginData}
                    cx="50%"
                    cy="50%"
                    innerRadius={42}
                    outerRadius={58}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {marginData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} stroke="none" />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '10px', color: '#64748b', fontWeight: '500' }}>Available</div>
                <div style={{ fontSize: '13px', color: '#ffffff', fontWeight: '700' }}>
                  ${account?.margin_free ? Math.round(account.margin_free).toLocaleString() : (account?.balance ? Math.round(account.balance).toLocaleString() : '0')}
                </div>
              </div>
            </div>

            {/* Custom Legend */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#10b981' }} />
                  <span style={{ color: '#94a3b8' }}>Free Margin</span>
                </div>
                <span style={{ fontWeight: '600', color: '#f8fafc' }}>
                  ${account?.margin_free ? account.margin_free.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '0.0'}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#3b5bf5' }} />
                  <span style={{ color: '#94a3b8' }}>Used Margin</span>
                </div>
                <span style={{ fontWeight: '600', color: '#f8fafc' }}>
                  ${account?.margin ? account.margin.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : '0.0'}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#f59e0b' }} />
                  <span style={{ color: '#94a3b8' }}>Leverage</span>
                </div>
                <span style={{ fontWeight: '600', color: '#f8fafc' }}>
                  1:{account?.leverage || 100}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* 2.2 Drawdown & Margin Safety Gauge */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'space-between',
          textAlign: 'center'
        }}>
          <div style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '14px', fontWeight: '700', color: '#ffffff' }}>Drawdown Safeguard</span>
            <Shield size={14} color="#64748b" />
          </div>

          {/* Gauge SVG */}
          <div style={{ position: 'relative', width: '150px', height: '85px', marginTop: '10px' }}>
            <svg viewBox="0 0 100 55" width="100%" height="100%">
              {/* Background Arc */}
              <path
                d="M 10 50 A 40 40 0 0 1 90 50"
                fill="none"
                stroke="#1e293b"
                strokeWidth="8"
                strokeLinecap="round"
              />
              {/* Active Drawdown Arc */}
              <path
                d="M 10 50 A 40 40 0 0 1 90 50"
                fill="none"
                stroke={riskColor}
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray="125.6"
                strokeDashoffset={strokeOffset}
              />
            </svg>
            <div style={{
              position: 'absolute',
              bottom: '0px',
              left: '50%',
              transform: 'translateX(-50%)',
              textAlign: 'center'
            }}>
              <span style={{ fontSize: '24px', fontWeight: '800', color: '#ffffff' }}>
                {currentDd.toFixed(1)}%
              </span>
            </div>
          </div>

          <div>
            <div style={{ fontSize: '13px', fontWeight: '700', color: riskColor, marginBottom: '2px' }}>
              {riskTitle}
            </div>
            <div style={{ fontSize: '11px', color: '#64748b', maxWidth: '190px' }}>
              Max Historical DD: <strong style={{ color: '#cbd5e1' }}>{maxDd.toFixed(1)}%</strong>
            </div>
          </div>
        </div>

        {/* 2.3 Market Overview (Real Live Data!) */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h2 style={{ fontSize: '14px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
                Live Markets
              </h2>
              <span style={{
                width: '6px', height: '6px', borderRadius: '50%', background: '#10b981',
                boxShadow: '0 0 8px #10b981'
              }} title="Live Real Feed" />
            </div>
            <button
              onClick={() => navigate('/markets')}
              style={{ background: 'none', border: 'none', color: '#64748b', fontSize: '12px', cursor: 'pointer', fontWeight: '500' }}
            >
              Trade Now →
            </button>
          </div>

          {/* 2x2 Grid for Top Market Pairs */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', flex: 1 }}>
            {marketData.slice(0, 4).map((item) => (
              <div
                key={item.symbol}
                onClick={() => navigate(`/markets?symbol=${item.symbol}`)}
                style={{
                  background: '#0d1017',
                  border: '1px solid #1c2233',
                  borderRadius: '12px',
                  padding: '10px 12px',
                  cursor: 'pointer',
                  transition: 'border-color 0.2s',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between'
                }}
                onMouseEnter={(e) => e.currentTarget.style.borderColor = '#3b5bf5'}
                onMouseLeave={(e) => e.currentTarget.style.borderColor = '#1c2233'}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <span style={{ fontSize: '12px', fontWeight: '600', color: '#94a3b8' }}>
                    {item.name}
                  </span>
                  <TrendingUp size={13} color={item.direction === 'up' ? '#10b981' : '#f43f5e'} />
                </div>
                <div>
                  <div style={{ fontSize: '14px', fontWeight: '700', color: '#ffffff' }}>
                    {item.price > 1000 ? item.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : item.price}
                  </div>
                  <div style={{
                    fontSize: '11px',
                    fontWeight: '600',
                    color: item.changePct >= 0 ? '#10b981' : '#f43f5e'
                  }}>
                    {item.changePct >= 0 ? `+${item.changePct.toFixed(2)}%` : `${item.changePct.toFixed(2)}%`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 2.4 Active Algorithmic Strategies */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h2 style={{ fontSize: '14px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
              Algorithmic Strategies
            </h2>
            <button
              onClick={() => navigate('/bot')}
              style={{ background: 'none', border: 'none', color: '#64748b', fontSize: '12px', cursor: 'pointer', fontWeight: '500' }}
            >
              Configure →
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1, justifyContent: strategies.length > 0 ? 'space-between' : 'center' }}>
            {strategies.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '16px 8px', color: '#64748b', fontSize: '12px' }}>
                No bots configured on this account yet.
                <div style={{ marginTop: '10px' }}>
                  <button
                    onClick={() => navigate('/bot')}
                    style={{
                      background: 'rgba(59, 91, 245, 0.15)',
                      border: '1px solid rgba(59, 91, 245, 0.35)',
                      color: '#818cf8',
                      padding: '6px 12px',
                      borderRadius: '8px',
                      fontSize: '11px',
                      fontWeight: 700,
                      cursor: 'pointer'
                    }}
                  >
                    Configure AI Bot →
                  </button>
                </div>
              </div>
            ) : strategies.map((strat) => (
              <div
                key={strat.id}
                onClick={() => navigate('/bot')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '9px 12px',
                  borderRadius: '10px',
                  background: '#0d1017',
                  border: '1px solid #1c2233',
                  cursor: 'pointer'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div style={{
                    width: '30px', height: '30px', borderRadius: '8px',
                    background: `${strat.color}22`, display: 'flex',
                    alignItems: 'center', justifyContent: 'center'
                  }}>
                    <Zap size={15} color={strat.color} />
                  </div>
                  <div>
                    <div style={{ fontSize: '12px', fontWeight: '600', color: '#ffffff' }}>
                      {strat.name}
                    </div>
                    <div style={{ fontSize: '10px', color: '#64748b' }}>
                      {strat.pair}
                    </div>
                  </div>
                </div>

                <div style={{ textAlign: 'right' }}>
                  <span style={{
                    background: strat.status === 'RUNNING' ? 'rgba(16, 185, 129, 0.15)' : strat.status === 'ERROR' ? 'rgba(244, 63, 94, 0.15)' : 'rgba(100, 116, 139, 0.15)',
                    color: strat.status === 'RUNNING' ? '#10b981' : strat.status === 'ERROR' ? '#f43f5e' : '#94a3b8',
                    padding: '2px 8px',
                    borderRadius: '6px',
                    fontSize: '10px',
                    fontWeight: '700'
                  }}>
                    {strat.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ================= ROW 3 ================= */}
      <div className="dashboard-grid-row3">
        {/* 3.1 Recent Trade Executions */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h2 style={{ fontSize: '14px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
              Recent Trade Executions
            </h2>
            <button
              onClick={() => navigate('/analytics')}
              style={{ background: 'none', border: 'none', color: '#64748b', fontSize: '12px', cursor: 'pointer', fontWeight: '500' }}
            >
              Full Journal →
            </button>
          </div>

          <div className="responsive-table-wrapper" style={{ flex: 1 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr style={{ color: '#64748b', borderBottom: '1px solid #1c2233' }}>
                  <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '500' }}>Symbol</th>
                  <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '500' }}>Type</th>
                  <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '500' }}>Lots</th>
                  <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '500' }}>Status</th>
                  <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: '500' }}>Profit</th>
                </tr>
              </thead>
              <tbody>
                {liveTrades && liveTrades.length > 0 ? (
                  liveTrades.slice(0, 5).map((t, idx) => {
                    const profitNum = Number(t.profit || 0)
                    const isWin = profitNum >= 0
                    return (
                      <tr key={t.id || t.ticket || idx} style={{ borderBottom: '1px solid #161b2a' }}>
                        <td style={{ padding: '10px 10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontWeight: '600', color: '#f8fafc' }}>{t.symbol || t.pair || 'TRADE'}</span>
                        </td>
                        <td style={{ padding: '10px 10px', color: (t.direction || t.type || '').toUpperCase() === 'BUY' ? '#10b981' : '#f43f5e', fontWeight: '600' }}>
                          {(t.direction || t.type || 'BUY').toUpperCase()}
                        </td>
                        <td style={{ padding: '10px 10px', color: '#94a3b8' }}>
                          {t.volume || '0.01'}
                        </td>
                        <td style={{ padding: '10px 10px' }}>
                          <span style={{
                            background: (t.status || 'open').toLowerCase() === 'open' ? 'rgba(59, 130, 246, 0.12)' : 'rgba(16, 185, 129, 0.12)',
                            color: (t.status || 'open').toLowerCase() === 'open' ? '#3b82f6' : '#10b981',
                            padding: '3px 8px',
                            borderRadius: '6px',
                            fontSize: '11px',
                            fontWeight: '600'
                          }}>
                            {(t.status || 'OPEN').toUpperCase()}
                          </span>
                        </td>
                        <td style={{ padding: '10px 10px', textAlign: 'right', fontWeight: '700', color: isWin ? '#10b981' : '#f43f5e' }}>
                          {isWin ? '+' : ''}${profitNum.toFixed(2)}
                        </td>
                      </tr>
                    )
                  })
                ) : (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: '#64748b' }}>
                      No active trades in journal. Activate a bot or execute a manual trade.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* 3.2 Risk Safeguards & Execution Limits */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h2 style={{ fontSize: '14px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
              Risk Safeguards
            </h2>
            <button
              onClick={() => navigate('/settings')}
              style={{ background: 'none', border: 'none', color: '#64748b', fontSize: '12px', cursor: 'pointer', fontWeight: '500' }}
            >
              Risk Settings →
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1, justifyContent: 'space-around' }}>
            {/* Limit 1: Daily Target */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Target size={14} color="#10b981" />
                  <span style={{ fontSize: '13px', fontWeight: '600', color: '#ffffff' }}>
                    Daily Target (+${dailyTarget})
                  </span>
                </div>
                <span style={{ fontSize: '12px', fontWeight: '700', color: '#10b981' }}>
                  ${dailyProfit.toFixed(2)} ({dailyTargetPct}%)
                </span>
              </div>
              <div style={{ width: '100%', height: '6px', background: '#1c2233', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ width: `${dailyTargetPct}%`, height: '100%', background: '#10b981', borderRadius: '4px' }} />
              </div>
            </div>

            {/* Limit 2: Position Concurrency */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Layers size={14} color="#3b5bf5" />
                  <span style={{ fontSize: '13px', fontWeight: '600', color: '#ffffff' }}>
                    Open Position Cap ({maxPositionsLimit} max)
                  </span>
                </div>
                <span style={{ fontSize: '12px', fontWeight: '700', color: '#3b5bf5' }}>
                  {currentOpenPositions} / {maxPositionsLimit} Active
                </span>
              </div>
              <div style={{ width: '100%', height: '6px', background: '#1c2233', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ width: `${positionOccupancyPct}%`, height: '100%', background: '#3b5bf5', borderRadius: '4px' }} />
              </div>
            </div>

            {/* Limit 3: Max Drawdown Ceiling */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <AlertTriangle size={14} color="#f59e0b" />
                  <span style={{ fontSize: '13px', fontWeight: '600', color: '#ffffff' }}>
                    Daily Max Loss Guard ({maxLossLimitPct}%)
                  </span>
                </div>
                <span style={{ fontSize: '12px', fontWeight: '700', color: currentDd < maxLossLimitPct ? '#10b981' : '#f43f5e' }}>
                  {currentDd.toFixed(1)}% Used
                </span>
              </div>
              <div style={{ width: '100%', height: '6px', background: '#1c2233', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ width: `${lossGuardPct}%`, height: '100%', background: currentDd < maxLossLimitPct ? '#10b981' : '#f43f5e', borderRadius: '4px' }} />
              </div>
            </div>
          </div>
        </div>

        {/* 3.3 Trade Profit vs Loss Distribution */}
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '18px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <h2 style={{ fontSize: '14px', fontWeight: '700', color: '#ffffff', margin: 0 }}>
              P&amp;L Performance Breakdown
            </h2>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              background: '#171b28',
              border: '1px solid #252d43',
              borderRadius: '6px',
              padding: '4px 8px',
              fontSize: '11px',
              color: '#94a3b8'
            }}>
              <span>Factor: {analytics.profitFactor > 0 ? analytics.profitFactor : '—'}</span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <div style={{ display: 'flex', gap: '16px' }}>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b' }}>Gross Profit</span>
                <div style={{ fontSize: '13px', fontWeight: '700', color: '#10b981' }}>
                  ${analytics.grossProfit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
              </div>
              <div>
                <span style={{ fontSize: '11px', color: '#64748b' }}>Gross Loss</span>
                <div style={{ fontSize: '13px', fontWeight: '700', color: '#f43f5e' }}>
                  ${analytics.grossLoss.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '10px', color: '#94a3b8' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#10b981' }} />
                <span>Profit</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#f43f5e' }} />
                <span>Loss</span>
              </div>
            </div>
          </div>

          <div style={{ width: '100%', height: '145px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={pnlDistributionData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                <XAxis
                  dataKey="name"
                  stroke="#334155"
                  tick={{ fill: '#64748b', fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  stroke="#334155"
                  tick={{ fill: '#64748b', fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(val) => `$${val}`}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div style={{
                          background: '#0f172a',
                          border: '1px solid #334155',
                          borderRadius: '6px',
                          padding: '6px 10px',
                          color: '#fff',
                          fontSize: '11px'
                        }}>
                          <div style={{ color: '#10b981' }}>Profit: ${payload[0]?.value}</div>
                          <div style={{ color: '#f43f5e' }}>Loss: ${payload[1]?.value}</div>
                        </div>
                      )
                    }
                    return null
                  }}
                />
                <Bar dataKey="Profit" fill="#10b981" radius={[4, 4, 0, 0]} maxBarSize={28} />
                <Bar dataKey="Loss" fill="#f43f5e" radius={[4, 4, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

    </div>
  )
}
