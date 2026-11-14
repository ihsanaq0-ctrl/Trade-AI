import { useState, useEffect, useCallback } from 'react'
import {
  TrendingUp, TrendingDown, Search, Star, AlertCircle,
  Zap, Layers, RefreshCw, X, Shield, Wallet
} from 'lucide-react'
import ChartModal from '../components/ChartModal'
import api from '../api'
import { useToast } from '../components/Toast'

const categories = ['All', 'Forex', 'Crypto', 'Commodities']

export default function Markets() {
  const toast = useToast()
  const [prices, setPrices] = useState([])
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const [favorites, setFavorites] = useState(() => {
    try { return JSON.parse(localStorage.getItem('favPairs') || '[]') } catch { return [] }
  })
  const [showFavorites, setShowFavorites] = useState(false)
  const [selectedPair, setSelectedPair] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [viewTab, setViewTab] = useState('markets') // 'markets' | 'positions'
  const [openPositions, setOpenPositions] = useState([])
  const [loadingPositions, setLoadingPositions] = useState(false)
  const [closingTicket, setClosingTicket] = useState(null)
  const [accountInfo, setAccountInfo] = useState(null)

  // 1. Fetch prices from backend
  const fetchPrices = useCallback(async () => {
    try {
      const data = await api.get('/api/markets/prices')
      setPrices(data.prices || [])
      setError(null)
    } catch (e) {
      setError(e.message)
      setPrices([])
    } finally {
      setLoading(false)
    }
  }, [])

  // 2. Fetch live positions from MT5
  const fetchPositions = useCallback(async () => {
    setLoadingPositions(true)
    try {
      const data = await api.get('/api/trades/positions')
      setOpenPositions(data?.positions || [])
    } catch {
      setOpenPositions([])
    } finally {
      setLoadingPositions(false)
    }
  }, [])

  // 3. Fetch account info
  useEffect(() => {
    fetchPrices()
    fetchPositions()
    api.get('/api/markets/active-account')
      .then(d => { if (d && d.connected && d.login) setAccountInfo(d); else setAccountInfo(null); })
      .catch(() => setAccountInfo(null))

    const priceInterval = setInterval(fetchPrices, 6000)
    const posInterval = setInterval(fetchPositions, 6000)
    return () => {
      clearInterval(priceInterval)
      clearInterval(posInterval)
    }
  }, [fetchPrices, fetchPositions])

  // Close position handler
  const handleClosePosition = async (ticket) => {
    setClosingTicket(ticket)
    try {
      const res = await api.post('/api/trades/close', { ticket: String(ticket) })
      if (res && res.success) {
        toast.success(`Position #${ticket} successfully closed! P&L: $${Number(res.profit || 0).toFixed(2)}`)
        fetchPositions()
      } else {
        toast.error(res?.error || 'Failed to close position')
      }
    } catch (err) {
      toast.error(`Close failed: ${err.message}`)
    } finally {
      setClosingTicket(null)
    }
  }

  const categorized = prices.map(p => ({
    ...p,
    displaySymbol: p.symbol.replace(/(.{3})/, '$1/'),
    category: ['BTC', 'ETH', 'SOL', 'XRP', 'LTC', 'BNB', 'DOGE', 'ADA'].some(c => p.symbol.startsWith(c))
      ? 'Crypto'
      : p.symbol.startsWith('X')
      ? 'Commodities'
      : 'Forex',
  }))

  const toggleFavorite = (e, symbol) => {
    e.stopPropagation()
    const next = favorites.includes(symbol) ? favorites.filter(f => f !== symbol) : [...favorites, symbol]
    setFavorites(next)
    localStorage.setItem('favPairs', JSON.stringify(next))
  }

  const filtered = categorized.filter(p => {
    const matchSearch = p.displaySymbol.toLowerCase().includes(search.toLowerCase())
    const matchCategory = category === 'All' || p.category === category
    const matchFav = showFavorites ? favorites.includes(p.symbol) : true
    return matchSearch && matchCategory && matchFav
  })

  // Open default pair if manual trade is launched from header
  const handleOpenManualTrade = () => {
    const defaultPair = prices[0] || {
      symbol: 'EURUSD',
      bid: 1.12046,
      ask: 1.12047,
      spread: 0.1,
    }
    setSelectedPair(defaultPair)
  }

  return (
    <div style={{ padding: '24px', minHeight: '100vh', background: '#0c0e15', color: '#f8fafc' }}>
      {/* Top Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '24px',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: '800', color: '#ffffff', letterSpacing: '-0.3px', marginBottom: '4px' }}>
            Live Financial Markets & Manual Trading
          </h1>
          <p style={{ color: '#94a3b8', fontSize: '13px', margin: 0 }}>
            Inspect high-frequency candlestick charts and execute manual trades directly via MetaTrader 5
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {accountInfo && (
            <div style={{
              background: '#131722',
              border: '1px solid #1c2233',
              borderRadius: '10px',
              padding: '6px 14px',
              fontSize: '12px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}>
              <Wallet size={14} color="#3b5bf5" />
              <span style={{ color: '#94a3b8' }}>MT5 #{accountInfo.login}:</span>
              <span style={{ color: '#ffffff', fontWeight: '700' }}>
                ${Number(accountInfo.balance || 0).toLocaleString()}
              </span>
            </div>
          )}

          <button
            onClick={handleOpenManualTrade}
            style={{
              padding: '10px 18px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, #3b5bf5, #4f46e5)',
              border: 'none',
              color: '#ffffff',
              fontSize: '13px',
              fontWeight: '700',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              boxShadow: '0 4px 16px rgba(59, 91, 245, 0.35)',
              transition: 'all 0.2s'
            }}
            onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-1px)'}
            onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}
          >
            <Zap size={16} /> + New Manual Trade
          </button>
        </div>
      </div>

      {/* View Switcher Tabs: Watchlist vs Open Positions */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        <button
          onClick={() => setViewTab('markets')}
          style={{
            padding: '9px 18px',
            borderRadius: '10px',
            border: 'none',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer',
            background: viewTab === 'markets' ? '#1c2438' : '#131722',
            color: viewTab === 'markets' ? '#ffffff' : '#64748b',
            border: `1px solid ${viewTab === 'markets' ? '#3b5bf5' : '#1c2233'}`,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <span>Market Instruments</span>
          <span style={{
            fontSize: '11px',
            background: viewTab === 'markets' ? 'rgba(59, 91, 245, 0.25)' : '#1e2538',
            color: viewTab === 'markets' ? '#818cf8' : '#64748b',
            padding: '2px 7px',
            borderRadius: '10px'
          }}>
            {prices.length}
          </span>
        </button>

        <button
          onClick={() => setViewTab('positions')}
          style={{
            padding: '9px 18px',
            borderRadius: '10px',
            border: 'none',
            fontSize: '13px',
            fontWeight: '600',
            cursor: 'pointer',
            background: viewTab === 'positions' ? '#1c2438' : '#131722',
            color: viewTab === 'positions' ? '#ffffff' : '#64748b',
            border: `1px solid ${viewTab === 'positions' ? '#3b5bf5' : '#1c2233'}`,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <Layers size={14} color={openPositions.length > 0 ? '#10b981' : '#64748b'} />
          <span>Active Positions</span>
          <span style={{
            fontSize: '11px',
            background: openPositions.length > 0 ? 'rgba(16, 185, 129, 0.2)' : '#1e2538',
            color: openPositions.length > 0 ? '#10b981' : '#64748b',
            padding: '2px 7px',
            borderRadius: '10px',
            fontWeight: 700
          }}>
            {openPositions.length}
          </span>
        </button>
      </div>

      {viewTab === 'markets' ? (
        <>
          {/* Filters & Search Bar */}
          <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ position: 'relative', flex: 1, minWidth: 220 }}>
              <Search size={14} style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: '#64748b' }} />
              <input
                placeholder="Search currency pairs, indices, crypto..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{
                  width: '100%', padding: '10px 14px 10px 38px', borderRadius: '10px',
                  background: '#131722', border: '1px solid #1c2233', color: '#f8fafc',
                  fontSize: '13px', outline: 'none', boxSizing: 'border-box'
                }}
              />
            </div>
            {categories.map(c => (
              <button
                key={c}
                onClick={() => setCategory(c)}
                style={{
                  padding: '8px 16px', borderRadius: '10px', border: 'none', cursor: 'pointer',
                  fontSize: '12px', fontWeight: '600',
                  background: category === c ? '#3b5bf5' : '#131722',
                  color: category === c ? '#ffffff' : '#94a3b8',
                  border: '1px solid ' + (category === c ? '#3b5bf5' : '#1c2233')
                }}
              >
                {c}
              </button>
            ))}
            <button
              onClick={() => setShowFavorites(!showFavorites)}
              style={{
                padding: '8px 16px', borderRadius: '10px', border: '1px solid #1c2233', cursor: 'pointer',
                fontSize: '12px', fontWeight: '600',
                background: showFavorites ? 'rgba(245, 158, 11, 0.15)' : '#131722',
                color: showFavorites ? '#f59e0b' : '#94a3b8',
                display: 'flex', alignItems: 'center', gap: '6px'
              }}
            >
              <Star size={13} fill={showFavorites ? '#f59e0b' : 'none'} /> Favorites {favorites.length > 0 && `(${favorites.length})`}
            </button>
          </div>

          {/* Markets Table */}
          <div style={{
            background: '#131722', border: '1px solid #1c2233', borderRadius: '16px',
            overflow: 'hidden'
          }}>
            <div className="responsive-table-wrapper">
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #1c2233', color: '#64748b' }}>
                    {['', 'Instrument', 'Bid Price', 'Ask Price', 'Spread', 'Category', 'Action'].map(h => (
                      <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontWeight: '600' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    loading ? (
                      [1, 2, 3, 4, 5, 6].map((idx) => (
                        <tr key={`skel-${idx}`} style={{ borderBottom: '1px solid #161b2a' }}>
                          <td style={{ padding: '14px 16px' }}><div style={{ width: 14, height: 14, borderRadius: 4, background: '#1c2233' }} /></td>
                          <td style={{ padding: '14px 16px' }}><div style={{ width: 90, height: 16, borderRadius: 6, background: '#1c2233', animation: 'pulseGlow 1.5s infinite' }} /></td>
                          <td style={{ padding: '14px 16px' }}><div style={{ width: 70, height: 16, borderRadius: 6, background: '#1c2233', animation: 'pulseGlow 1.5s infinite' }} /></td>
                          <td style={{ padding: '14px 16px' }}><div style={{ width: 70, height: 16, borderRadius: 6, background: '#1c2233', animation: 'pulseGlow 1.5s infinite' }} /></td>
                          <td style={{ padding: '14px 16px' }}><div style={{ width: 45, height: 16, borderRadius: 6, background: '#1c2233', animation: 'pulseGlow 1.5s infinite' }} /></td>
                          <td style={{ padding: '14px 16px' }}><div style={{ width: 60, height: 16, borderRadius: 6, background: '#1c2233', animation: 'pulseGlow 1.5s infinite' }} /></td>
                          <td style={{ padding: '14px 16px' }}><div style={{ width: 65, height: 24, borderRadius: 6, background: '#1c2233', animation: 'pulseGlow 1.5s infinite' }} /></td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={7} style={{ padding: '36px', textAlign: 'center', color: '#64748b' }}>
                          No instruments matching filter.
                        </td>
                      </tr>
                    )
                  ) : (
                    filtered.map((p) => (
                      <tr
                        key={p.symbol}
                        onClick={() => setSelectedPair(p)}
                        style={{
                          borderBottom: '1px solid #161b2a', cursor: 'pointer',
                          transition: 'background 0.15s'
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = '#181d2d'}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      >
                        <td style={{ padding: '12px 16px' }}>
                          <Star
                            size={14}
                            onClick={e => toggleFavorite(e, p.symbol)}
                            fill={favorites.includes(p.symbol) ? '#f59e0b' : 'none'}
                            color={favorites.includes(p.symbol) ? '#f59e0b' : '#64748b'}
                            style={{ cursor: 'pointer' }}
                          />
                        </td>
                        <td style={{ padding: '12px 16px', color: '#ffffff', fontWeight: '700' }}>
                          {p.displaySymbol}
                        </td>
                        <td style={{ padding: '12px 16px', color: '#10b981', fontFamily: 'var(--font-mono)' }}>
                          {typeof p.bid === 'number' ? p.bid.toFixed(p.bid > 100 ? 2 : 5) : p.bid}
                        </td>
                        <td style={{ padding: '12px 16px', color: '#f43f5e', fontFamily: 'var(--font-mono)' }}>
                          {typeof p.ask === 'number' ? p.ask.toFixed(p.ask > 100 ? 2 : 5) : p.ask}
                        </td>
                        <td style={{ padding: '12px 16px', color: '#94a3b8' }}>
                          {p.spread ? `${p.spread} pips` : '--'}
                        </td>
                        <td style={{ padding: '12px 16px' }}>
                          <span style={{
                            fontSize: '11px', padding: '3px 8px', borderRadius: '6px', fontWeight: '600',
                            background: p.category === 'Forex' ? 'rgba(59, 91, 245, 0.12)' : p.category === 'Crypto' ? 'rgba(139, 92, 246, 0.12)' : 'rgba(245, 158, 11, 0.12)',
                            color: p.category === 'Forex' ? '#818cf8' : p.category === 'Crypto' ? '#a78bfa' : '#fbbf24',
                          }}>
                            {p.category}
                          </span>
                        </td>
                        <td style={{ padding: '12px 16px' }}>
                          <span style={{
                            color: '#3b5bf5',
                            fontSize: '12px',
                            fontWeight: '700',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px'
                          }}>
                            <Zap size={13} /> Trade & Chart →
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        /* ACTIVE POSITIONS TABLE */
        <div style={{
          background: '#131722',
          border: '1px solid #1c2233',
          borderRadius: '16px',
          padding: '24px',
          overflow: 'hidden'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
            <div>
              <h2 style={{ fontSize: '16px', fontWeight: '700', color: '#ffffff', margin: '0 0 4px 0' }}>
                Open MetaTrader 5 Positions ({openPositions.length})
              </h2>
              <p style={{ fontSize: '12px', color: '#94a3b8', margin: 0 }}>
                Live positions managed either manually or by your AI bots
              </p>
            </div>
            <button
              onClick={fetchPositions}
              style={{
                background: '#1e2538',
                border: '1px solid #2d3748',
                color: '#94a3b8',
                padding: '6px 12px',
                borderRadius: '8px',
                fontSize: '12px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              <RefreshCw size={13} className={loadingPositions ? 'spin' : ''} /> Refresh Positions
            </button>
          </div>

          {openPositions.length === 0 ? (
            <div style={{
              padding: '60px 20px',
              textAlign: 'center',
              background: '#0c0e15',
              borderRadius: '12px',
              border: '1px solid #1a2233'
            }}>
              <Shield size={36} color="#475569" style={{ margin: '0 auto 12px auto' }} />
              <h3 style={{ color: '#ffffff', fontSize: '15px', margin: '0 0 6px 0' }}>No Active Trades Found</h3>
              <p style={{ color: '#64748b', fontSize: '13px', margin: '0 0 16px 0' }}>
                You have no open market orders on your connected MT5 terminal.
              </p>
              <button
                onClick={handleOpenManualTrade}
                style={{
                  padding: '8px 18px',
                  borderRadius: '8px',
                  background: '#3b5bf5',
                  border: 'none',
                  color: '#fff',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Open a Manual Trade Now
              </button>
            </div>
          ) : (
            <div className="responsive-table-wrapper">
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #1c2233', color: '#64748b' }}>
                    {['Ticket', 'Symbol', 'Type', 'Volume', 'Open Price', 'Current Price', 'Profit ($)', 'Action'].map(h => (
                      <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontWeight: '600' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {openPositions.map(pos => {
                    const isBuy = pos.type?.toUpperCase() === 'BUY'
                    const profitNum = Number(pos.profit || 0)
                    const isProfitable = profitNum >= 0
                    return (
                      <tr key={pos.ticket} style={{ borderBottom: '1px solid #161b2a' }}>
                        <td style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)', color: '#94a3b8' }}>
                          #{pos.ticket}
                        </td>
                        <td style={{ padding: '12px 16px', fontWeight: '700', color: '#fff' }}>
                          {pos.symbol}
                        </td>
                        <td style={{ padding: '12px 16px' }}>
                          <span style={{
                            padding: '3px 8px',
                            borderRadius: '6px',
                            fontSize: '11px',
                            fontWeight: '800',
                            background: isBuy ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                            color: isBuy ? '#10b981' : '#f43f5e',
                            border: `1px solid ${isBuy ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`
                          }}>
                            {pos.type}
                          </span>
                        </td>
                        <td style={{ padding: '12px 16px', color: '#f8fafc', fontWeight: 600 }}>
                          {pos.volume} Lots
                        </td>
                        <td style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)', color: '#94a3b8' }}>
                          {pos.open_price}
                        </td>
                        <td style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)', color: '#f8fafc' }}>
                          {pos.current_price || '--'}
                        </td>
                        <td style={{
                          padding: '12px 16px',
                          fontFamily: 'var(--font-mono)',
                          fontWeight: '800',
                          color: isProfitable ? '#10b981' : '#f43f5e'
                        }}>
                          {isProfitable ? '+' : ''}${profitNum.toFixed(2)}
                        </td>
                        <td style={{ padding: '12px 16px' }}>
                          <button
                            onClick={() => handleClosePosition(pos.ticket)}
                            disabled={closingTicket === pos.ticket}
                            style={{
                              background: 'rgba(244, 63, 94, 0.12)',
                              border: '1px solid rgba(244, 63, 94, 0.3)',
                              color: '#f43f5e',
                              padding: '5px 12px',
                              borderRadius: '7px',
                              fontSize: '11px',
                              fontWeight: '700',
                              cursor: closingTicket === pos.ticket ? 'not-allowed' : 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px'
                            }}
                          >
                            {closingTicket === pos.ticket ? <RefreshCw size={11} className="spin" /> : <X size={11} />}
                            Close Trade
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Candlestick & Trade Execution Modal */}
      {selectedPair && <ChartModal pair={selectedPair} onClose={() => setSelectedPair(null)} />}
    </div>
  )
}
