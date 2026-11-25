import React, { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot as BotIcon, TrendingUp, DollarSign, Activity, AlertCircle, Brain, Crown } from 'lucide-react'
import BotCard from '../components/BotCard'
import StrategyConfigModal from '../components/StrategyConfigModal'
import MMCDashboard from '../components/MMCDashboard'
import AIAgentsModal from '../components/AIAgentsModal'
import api from '../api'
import { useToast } from '../components/Toast'

export const BUILTIN_STRATEGIES = [
  { name: 'smart_money', title: 'Smart Money Mode', risk: 'Medium', description: 'Order blocks, fair value gaps & liquidity sweeps' },
  { name: 'mmc_mirror', title: 'MMC Mirror', risk: 'Medium', description: '50% equilibrium continuation strategy, XAUUSD M5' },
  { name: 'classic', title: 'Classic Mode', risk: 'Low', description: 'Trend-following EMA 20/50 cross with MACD confirmation' },
  { name: 'full_confluence', title: 'Full Confluence', risk: 'Low', description: 'Multi-timeframe confirmation across H4/H1/M15' },
  { name: 'scalp_pyramid', title: 'Scalp Pyramid', risk: 'High', description: 'Aggressive momentum pyramid scaling on micro timeframes' },
  { name: 'scalp_fvg', title: 'Scalp (FVG)', risk: 'High', description: 'Rapid M1-M5 imbalance filling and mean reversion' },
  { name: 'signal_strength_hedge', title: 'Signal Strength Hedge', risk: 'High', description: 'Dynamic directional delta hedging across correlated pairs' },
  { name: 'nyao_scalper', title: 'Nyao Scalper (Trade Mgmt)', risk: 'Medium', description: 'Dynamic trailing stop, breakeven protection & partial take profit' },
  { name: 'trading_agents', title: 'TradingAgents AI', risk: 'Adaptive', description: 'Multi-agent LLM consensus: Technical, Macro, Sentiment & Risk' },
  { name: 'pipstep_reversal', title: 'PipStep Reversal EA', risk: 'Medium', description: 'BuyStop/SellStop straddle pair, step trailing SL & instant reversal on SL hit' }
]

export default function Bot({ session, userPlan: propPlan = 'free' }) {
  const navigate = useNavigate()
  const [activeBots, setActiveBots] = useState([])
  const [loading, setLoading] = useState(true)
  const [backendOnline, setBackendOnline] = useState(null)
  const [strategies, setStrategies] = useState(BUILTIN_STRATEGIES)
  const [selectedStrategy, setSelectedStrategy] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [showAIAgentsModal, setShowAIAgentsModal] = useState(false)
  const [modalInitialConfig, setModalInitialConfig] = useState(null)
  const [accountInfo, setAccountInfo] = useState(null)
  const [apiError, setApiError] = useState(null)
  const [winRate, setWinRate] = useState(null)
  const [userPlan, setUserPlan] = useState((propPlan || 'free').toLowerCase())
  const toast = useToast()
  const pollRef = useRef(null)

  useEffect(() => {
    setUserPlan((propPlan || 'free').toLowerCase())
  }, [propPlan])

  useEffect(() => {
    if (!session?.access_token) {
      setLoading(false)
      return
    }
    const headers = { 'Authorization': `Bearer ${session.access_token}` }

    // Check user subscription tier
    api.get('/api/payments/license', { headers })
      .then(d => {
        if (d && d.plan) setUserPlan(d.plan.toLowerCase())
      })
      .catch(() => setUserPlan('free'))

    // Check backend health
    api.checkHealth().then(h => setBackendOnline(h.ok)).catch(() => setBackendOnline(false))

    // Strategy list for cards: merges backend list (including custom admin additions)
    api.get('/api/strategies', { timeout: 5000 })
      .then(list => {
        if (Array.isArray(list) && list.length > 0) {
          // Merge custom strategies with builtin ones
          const existingNames = new Set(BUILTIN_STRATEGIES.map(s => s.name))
          const customs = list.filter(s => !existingNames.has(s.name))
          setStrategies([...BUILTIN_STRATEGIES, ...customs])
        }
      })
      .catch(() => {})

    // Fetch win rate from analytics
    api.get('/api/analytics/overview', { headers })
      .then(d => { if (d && d.win_rate !== undefined) setWinRate(Number(d.win_rate)) })
      .catch(() => {})

    // Fetch bots & live terminal status
    const fetchData = async () => {
      try {
        const [data, accData] = await Promise.all([
          api.get('/api/bots', { headers }),
          api.get('/api/markets/active-account', { headers }).catch(() => null),
        ])
        setActiveBots(Array.isArray(data) ? data : [])
        if (accData !== null) {
          setAccountInfo(accData?.connected && accData?.login ? accData : null)
        }
        setApiError(null)
      } catch (e) {
        setApiError(e.message)
        setActiveBots([])
      } finally {
        setLoading(false)
      }
    }
    fetchData()

    // Poll every 5s for active bots status & live MT5 Algo Trading state
    pollRef.current = setInterval(fetchData, 5000)
    return () => clearInterval(pollRef.current)
  }, [session])

  const handleUpgrade = (tier = 'pro') => {
    navigate(`/pricing?plan=${tier}`)
  }

  const handleStart = (strategy) => {
    if (backendOnline === false) {
      toast.error('Backend API is offline. Run start.bat or cd backend && uvicorn main:app --port 8002')
      return
    }

    // Elite lock rule: allow when userPlan === 'elite' (or owner)
    if (['trading_agents', 'signal_strength_hedge', 'ai_committee'].includes(strategy) && userPlan !== 'elite') {
      toast.info('This strategy is exclusive to the Elite Plan (Coming Soon). Opening plan details...')
      navigate('/pricing?plan=elite')
      return
    }

    // Pro lock rule: PipStep Reversal EA requires Pro or Elite
    if (strategy === 'pipstep_reversal' && userPlan === 'free') {
      toast.warn('PipStep Reversal EA requires the PRO Plan. Redirecting to upgrade page...')
      navigate('/pricing?plan=pro')
      return
    }

    // Free limit rule: only 1 bot can run
    const runningCount = activeBots.filter(b => b.status === 'running').length
    if (userPlan === 'free' && runningCount >= 1) {
      toast.warn('Free Plan allows 1 active bot at a time. Upgrade to Pro for multi-bot execution.')
      navigate('/pricing?plan=pro')
      return
    }

    setSelectedStrategy(strategy)
    setModalInitialConfig(null)
    setShowModal(true)
  }

  const handleStop = async (botId) => {
    if (!session?.access_token) return
    try {
      await api.post(`/api/bots/${botId}/stop`, {}, {
        headers: { 'Authorization': `Bearer ${session.access_token}` }
      })
      setActiveBots(prev => prev.map(b => b.id === botId ? { ...b, status: 'stopped' } : b))
      toast.success('Bot stopped')
    } catch (e) {
      toast.error(`Failed to stop bot: ${e.message}`)
    }
  }

  const handleConfigure = (strategy) => {
    const sameStrategy = activeBots.filter(b => b.strategy === strategy)
    const existing = sameStrategy.find(b => b.status === 'running') ||
                     sameStrategy[sameStrategy.length - 1] || null
    setSelectedStrategy(strategy)
    setModalInitialConfig(existing)
    setShowModal(true)
  }

  const handleSave = async (config) => {
    if (!session?.access_token) return
    if (!backendOnline) {
      toast.error('Backend API is offline — cannot start bot. Start backend first.')
      return
    }
    try {
      const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${session.access_token}`
      }

      const sameStrategy = activeBots.filter(b => b.strategy === selectedStrategy)
      const existing = modalInitialConfig ||
                       sameStrategy.find(b => b.status === 'running') ||
                       sameStrategy[sameStrategy.length - 1] || null
      let bot
      if (existing) {
        await api.post(`/api/bots/${existing.id}/stop`, {}, { headers: { 'Authorization': `Bearer ${session.access_token}` } })
        const updPayload = {
          pair: config.pair,
          timeframe: config.timeframe,
          lot_size: config.lot_size,
          max_trades: config.max_trades,
          max_daily_loss: config.max_daily_loss,
        }
        // Only send config when the modal actually provides one - never wipe the stored dict
        if (config.config && typeof config.config === 'object') updPayload.config = config.config
        const updRes = await api.put(`/api/bots/${existing.id}`, updPayload, { headers })
        bot = updRes
        bot.id = existing.id
      } else {
        bot = await api.post('/api/bots', {
          ...config,
          strategy: selectedStrategy,
          account_id: config.account_id || '',
        }, { headers })
      }

      const startRes = await api.post(`/api/bots/${bot.id}/start`, {}, {
        headers: { 'Authorization': `Bearer ${session.access_token}` }
      })

      if (startRes?.warning) {
        toast.warn(startRes.warning)
      } else {
        toast.success(`${config.pair} bot started! Watching for trades...`)
      }

      const bots = await api.get('/api/bots', {
        headers: { 'Authorization': `Bearer ${session.access_token}` }
      })
      setActiveBots(Array.isArray(bots) ? bots : [])
      setShowModal(false)
      setModalInitialConfig(null)
    } catch (e) {
      toast.error(`Failed to start bot: ${e.message}`)
    }
  }

  const runningBots = activeBots.filter(b => b.status === 'running')
  const totalProfit = runningBots.reduce((sum, b) => sum + (b.profit || 0), 0)
  const totalTrades = runningBots.reduce((sum, b) => sum + (b.trades || 0), 0)

  const styles = {
    container: { padding: 'clamp(16px, 3vw, 24px)', maxWidth: 1200, margin: '0 auto', width: '100%', boxSizing: 'border-box' },
    header: { marginBottom: 28 },
    title: { fontSize: 24, fontWeight: 700, color: '#e1e4e8', margin: '0 0 4px 0' },
    subtitle: { fontSize: 14, color: '#6b7a8d', margin: 0 },
    statsRow: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 16, marginBottom: 28 },
    statCard: { background: '#0d1117', border: '1px solid #1e2d3d', borderRadius: 16, padding: 18 },
    statHeader: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 },
    statIconBox: { width: 32, height: 32, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' },
    statLabel: { fontSize: 12, color: '#6b7a8d' },
    statValue: { fontSize: 20, fontWeight: 700, color: '#e1e4e8' },
    cardsRow: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16, marginBottom: 28 },
    sectionHeader: { fontSize: 18, fontWeight: 600, color: '#e1e4e8', marginBottom: 16, marginTop: 8 },
    emptyState: { background: '#0d1117', border: '1px solid #1e2d3d', borderRadius: 16, padding: 40, textAlign: 'center', color: '#6b7a8d' },
    errorBanner: { background: '#ff475711', border: '1px solid #ff475733', borderRadius: 12, padding: '14px 18px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 10 }
  }

  return (
    <div style={styles.container}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '16px',
        marginBottom: '28px'
      }}>
        <div>
          <h1 style={styles.title}>AI Bots</h1>
          <p style={styles.subtitle}>Deploy and manage your AI trading bots</p>
          {accountInfo?.login && (
            <p style={{ color: accountInfo.terminal_synced ? '#10b981' : '#f59e0b', fontSize: 12, marginTop: 4 }}>
              {accountInfo.terminal_synced
                ? `MT5 Synced: #${accountInfo.login} on ${accountInfo.server} ($${accountInfo.balance?.toLocaleString()})`
                : `MT5 Linked: #${accountInfo.login} (Open MT5 Desktop to sync live terminal)`}
            </p>
          )}
          {backendOnline === false && (
            <div style={{ marginTop: 8 }}>
              <span style={{ color: '#ff4757', fontSize: 12 }}>⚠ Backend API offline — bots cannot run</span>
            </div>
          )}
          {backendOnline === true && (
            <div style={{ marginTop: 8 }}>
              <span style={{ color: '#00ff88', fontSize: 12 }}>✓ Backend connected</span>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <button
            onClick={() => navigate('/pricing?plan=pro')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '7px',
              background: userPlan === 'free' ? 'linear-gradient(135deg, #00d4ff, #3b5bf5)' : 'rgba(0, 212, 255, 0.12)',
              border: userPlan === 'free' ? 'none' : '1px solid rgba(0, 212, 255, 0.35)',
              color: userPlan === 'free' ? '#ffffff' : '#00d4ff',
              padding: '10px 16px',
              borderRadius: '12px',
              fontWeight: '700',
              fontSize: '12.5px',
              cursor: 'pointer'
            }}
          >
            <Crown size={15} />
            <span>{userPlan === 'free' ? 'Upgrade to Pro ($29/mo)' : `${userPlan.toUpperCase()} Plan Active`}</span>
          </button>

          <button
            onClick={() => setShowAIAgentsModal(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: 'linear-gradient(135deg, #38bdf8, #6366f1)',
              border: 'none',
              color: '#ffffff',
              padding: '11px 20px',
              borderRadius: '12px',
              fontWeight: '700',
              fontSize: '13px',
              cursor: 'pointer',
              boxShadow: '0 4px 16px rgba(56, 189, 248, 0.35)',
              transition: 'transform 0.15s ease'
            }}
          >
            <Brain size={18} />
            <span>TradingAgents Committee</span>
          </button>
        </div>
      </div>

      {accountInfo?.terminal_synced && (accountInfo?.trade_allowed === false || accountInfo?.tradeapi_disabled) && (
        <div style={{
          background: 'rgba(245, 158, 11, 0.12)',
          border: '1px solid rgba(245, 158, 11, 0.4)',
          borderRadius: 12,
          padding: '14px 18px',
          marginBottom: 20,
          display: 'flex',
          alignItems: 'center',
          gap: 12
        }}>
          <AlertCircle size={20} color="#f59e0b" style={{ flexShrink: 0 }} />
          <div>
            <div style={{ color: '#fbbf24', fontSize: 13.5, fontWeight: 700 }}>
              MetaTrader 5 Algo Trading is Disabled (Retcode 10027)
            </div>
            <div style={{ color: '#cbd5e1', fontSize: 12.5, marginTop: 2 }}>
              Your MT5 terminal is connected, but order execution is blocked until you click the <strong>Algo Trading</strong> button in the MetaTrader 5 toolbar (or press <strong>Ctrl+E</strong> in MT5 Desktop).
            </div>
          </div>
        </div>
      )}

      {apiError && (
        <div style={styles.errorBanner}>
          <AlertCircle size={18} color="#ff4757" />
          <div>
            <div style={{ color: '#ff4757', fontSize: 13, fontWeight: 600 }}>Cannot reach backend</div>
            <div style={{ color: '#6b7a8d', fontSize: 12, marginTop: 2 }}>{apiError}</div>
          </div>
        </div>
      )}

      <div style={styles.statsRow}>
        <div style={styles.statCard}>
          <div style={styles.statHeader}>
            <div style={{ ...styles.statIconBox, background: '#00ff8822' }}><BotIcon size={16} color="#00ff88" /></div>
            <span style={styles.statLabel}>Running</span>
          </div>
          <div style={styles.statValue}>{runningBots.length}</div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statHeader}>
            <div style={{ ...styles.statIconBox, background: '#00d4ff22' }}><Activity size={16} color="#00d4ff" /></div>
            <span style={styles.statLabel}>Total P&L</span>
          </div>
          <div style={{ ...styles.statValue, color: totalProfit >= 0 ? '#00ff88' : '#ff4757' }}>
            {totalProfit >= 0 ? '+' : ''}${totalProfit.toFixed(2)}
          </div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statHeader}>
            <div style={{ ...styles.statIconBox, background: '#7c3aed22' }}><TrendingUp size={16} color="#7c3aed" /></div>
            <span style={styles.statLabel}>Total Trades</span>
          </div>
          <div style={styles.statValue}>{totalTrades}</div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statHeader}>
            <div style={{ ...styles.statIconBox, background: '#f59e0b22' }}><DollarSign size={16} color="#f59e0b" /></div>
            <span style={styles.statLabel}>Win Rate</span>
          </div>
          <div style={{ ...styles.statValue, color: (winRate || 0) >= 50 ? '#00ff88' : '#e1e4e8' }}>
            {winRate !== null ? `${winRate.toFixed(1)}%` : (totalTrades > 0 ? '0.0%' : '—')}
          </div>
        </div>
      </div>

      <h2 style={styles.sectionHeader}>Choose a Strategy</h2>
      <div style={styles.cardsRow}>
        {strategies.map(s => {
          const stratName = s.name || s
          const runningBot = runningBots.find(b => b.strategy === stratName && b.status === 'running')
          return (
            <BotCard
              key={stratName}
              strategy={stratName}
              title={s.title}
              description={s.description}
              risk={s.risk}
              userPlan={userPlan}
              isRunning={Boolean(runningBot)}
              runtime={runningBot?.runtime}
              onStart={() => handleStart(stratName)}
              onStop={() => {
                if (runningBot) handleStop(runningBot.id)
              }}
              onConfigure={() => handleConfigure(stratName)}
              onUpgrade={handleUpgrade}
            />
          )
        })}
      </div>

      <MMCDashboard session={session} />

      <h2 style={styles.sectionHeader}>Running Bots</h2>
      {loading ? (
        <div style={styles.emptyState}><p>Loading...</p></div>
      ) : activeBots.length === 0 ? (
        <div style={styles.emptyState}>
          <AlertCircle size={40} style={{ marginBottom: 12, opacity: 0.5 }} />
          <p>No bots configured. Select a strategy above to start trading.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {activeBots.map(bot => (
            <div key={bot.id} style={{
              background: '#0d1117', border: '1px solid #1e2d3d', borderRadius: 12, padding: '14px 18px',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12
            }}>
              <div>
                <div style={{ color: '#e1e4e8', fontWeight: 600, fontSize: 14 }}>
                  {bot.strategy.replace(/_/g, ' ')} <span style={{ color: '#6b7a8d', fontWeight: 400 }}>— {bot.pair} ({bot.timeframe})</span>
                </div>
                <div style={{ color: '#6b7a8d', fontSize: 12, marginTop: 2 }}>
                  Status: <span style={{ color: bot.status === 'running' ? '#00ff88' : bot.status === 'error' ? '#ff4757' : '#6b7a8d' }}>{bot.status}</span>
                  {bot.runtime?.state ? ` (${bot.runtime.state})` : ''}
                  {bot.lot_size && ` · ${bot.lot_size} lots`}
                  {bot.runtime?.reversals > 0 ? ` · ${bot.runtime.reversals} reversals` : ''}
                </div>
                {bot.runtime?.last_message && (
                  <div style={{ color: bot.runtime.error_code ? '#fbbf24' : '#94a3b8', fontSize: 11.5, marginTop: 4 }}>
                    {bot.runtime.last_message}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <span style={{
                  padding: '4px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600,
                  background: bot.status === 'running' ? '#00ff8822' : '#1e2d3d',
                  color: bot.status === 'running' ? '#00ff88' : '#6b7a8d'
                }}>
                  {bot.status === 'running' ? 'Running' : bot.status === 'stopped' ? 'Stopped' : bot.status}
                </span>
                {bot.status === 'running' && (
                  <button onClick={() => handleStop(bot.id)}
                    style={{ padding: '4px 12px', background: '#ff475722', border: 'none', borderRadius: 6, color: '#ff4757', fontSize: 12, cursor: 'pointer', fontWeight: 500 }}>
                    Stop
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal && selectedStrategy && (
        <StrategyConfigModal
          strategy={selectedStrategy}
          initialConfig={modalInitialConfig}
          onSave={handleSave}
          onClose={() => setShowModal(false)}
        />
      )}

      <AIAgentsModal
        isOpen={showAIAgentsModal}
        onClose={() => setShowAIAgentsModal(false)}
        onDeployBot={(config) => {
          setSelectedStrategy('trading_agents')
          setModalInitialConfig(config)
          setShowAIAgentsModal(false)
          setShowModal(true)
        }}
      />
    </div>
  )
}
