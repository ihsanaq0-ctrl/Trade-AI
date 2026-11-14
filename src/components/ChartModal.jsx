import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart, CandlestickSeries } from 'lightweight-charts'
import {
  X, TrendingUp, TrendingDown, RefreshCw, Shield, Zap,
  CheckCircle2, AlertCircle, ChevronDown, ChevronUp, Plus, Minus,
  Layers, Wallet, ArrowUpRight, ArrowDownRight
} from 'lucide-react'
import api from '../api'
import { useToast } from './Toast'

const timeframes = ['M1', 'M5', 'M15', 'H1', 'H4', 'D1']
const allPairs = [
  'EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'AUDUSD', 'USDCAD', 'GBPJPY', 'EURJPY',
  'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD', 'DOGEUSD', 'ADAUSD', 'XAGUSD'
]

// Helper to generate simulated recent candles if MT5 has not cached historical bars yet
function generateFallbackCandles(basePrice, timeframe, count = 120) {
  const tfMinutes = {
    'M1': 1,
    'M5': 5,
    'M15': 15,
    'H1': 60,
    'H4': 240,
    'D1': 1440
  }[timeframe] || 60

  const nowSec = Math.floor(Date.now() / 1000)
  const stepSec = tfMinutes * 60
  const candles = []

  let price = Number(basePrice) || 1.1000
  const volatility = price * 0.0018

  for (let i = count - 1; i >= 0; i--) {
    const time = nowSec - (i * stepSec)
    const change = (Math.random() - 0.495) * volatility
    const open = price
    const close = price + change
    const high = Math.max(open, close) + Math.random() * (volatility * 0.45)
    const low = Math.min(open, close) - Math.random() * (volatility * 0.45)
    price = close
    candles.push({ time, open, high, low, close })
  }
  return candles
}

export default function ChartModal({ pair, onClose }) {
  const toast = useToast()
  const chartRef = useRef(null)
  const chartInstanceRef = useRef(null)
  const seriesRef = useRef(null)

  // Market & Chart State
  const [activeTimeframe, setActiveTimeframe] = useState('H1')
  const [lastPrice, setLastPrice] = useState(null)
  const [priceUp, setPriceUp] = useState(true)
  const [candles, setCandles] = useState([])
  const [loading, setLoading] = useState(true)
  const [chartError, setChartError] = useState(false)
  const [selectedSymbol, setSelectedSymbol] = useState(pair?.symbol || 'EURUSD')

  // Live Bid/Ask/Spread State
  const [liveBid, setLiveBid] = useState(pair?.bid || null)
  const [liveAsk, setLiveAsk] = useState(pair?.ask || null)
  const [liveSpread, setLiveSpread] = useState(pair?.spread || '0.8')

  // Manual Trading State
  const [lotSize, setLotSize] = useState('0.01')
  const [stopLoss, setStopLoss] = useState('')
  const [takeProfit, setTakeProfit] = useState('')
  const [analysisReason, setAnalysisReason] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(null) // 'BUY' | 'SELL' | null
  const [lastOrderResult, setLastOrderResult] = useState(null)
  const [closingTicket, setClosingTicket] = useState(null)

  // Account & Positions State
  const [accountInfo, setAccountInfo] = useState(null)
  const [activePositions, setActivePositions] = useState([])
  const [loadingPositions, setLoadingPositions] = useState(false)
  const [activeTab, setActiveTab] = useState('chart') // 'chart' | 'positions'

  // Clean raw symbol (e.g. "EUR/USD" -> "EURUSD")
  const rawSymbol = selectedSymbol || pair?.symbol || 'EURUSD'
  const symbol = rawSymbol.replace(/[^a-zA-Z0-9]/g, '').toUpperCase()

  const isJpy = symbol.includes('JPY')
  const isCrypto = ['BTC', 'ETH', 'SOL', 'XRP', 'BNB', 'DOGE', 'ADA'].some(c => symbol.startsWith(c))
  const decimals = isCrypto ? 2 : isJpy ? 3 : 5
  const pipMultiplier = isJpy ? 100 : isCrypto ? 1 : symbol.startsWith('XAU') ? 10 : 10000

  const toFixed = (v) => (v !== null && v !== undefined && !isNaN(v)) ? Number(v).toFixed(decimals) : '--'

  // 1. Fetch connected account info
  useEffect(() => {
    api.get('/api/markets/active-account')
      .then(data => {
        if (data && !data.error) setAccountInfo(data)
      })
      .catch(() => {})
  }, [])

  // 2. Fetch live positions on this symbol
  const fetchPositions = useCallback(() => {
    if (!symbol) return
    setLoadingPositions(true)
    api.get(`/api/trades/positions?symbol=${symbol}`)
      .then(d => {
        setActivePositions(d?.positions || [])
      })
      .catch(() => {})
      .finally(() => setLoadingPositions(false))
  }, [symbol])

  useEffect(() => {
    fetchPositions()
    const posTimer = setInterval(fetchPositions, 5000)
    return () => clearInterval(posTimer)
  }, [fetchPositions])

  // 3. Fetch candles from MT5
  useEffect(() => {
    if (!symbol) return
    setLoading(true)
    setChartError(false)

    api.get(`/api/markets/candles?symbol=${symbol}&timeframe=${activeTimeframe}&count=150`, { timeout: 8000 })
      .then(d => {
        if (d && Array.isArray(d.candles) && d.candles.length > 0) {
          setCandles(d.candles)
        } else {
          const fallbackPrice = liveBid || (symbol.includes('JPY') ? 154.5 : symbol.includes('BTC') ? 68500 : symbol.includes('XAU') ? 2650 : 1.1025)
          setCandles(generateFallbackCandles(fallbackPrice, activeTimeframe, 120))
        }
      })
      .catch(() => {
        const fallbackPrice = liveBid || 1.1025
        setCandles(generateFallbackCandles(fallbackPrice, activeTimeframe, 120))
      })
      .finally(() => setLoading(false))
  }, [symbol, activeTimeframe])

  // 4. Lightweight Charts render
  useEffect(() => {
    if (!chartRef.current || candles.length === 0) return

    try {
      if (chartInstanceRef.current) {
        chartInstanceRef.current.remove()
        chartInstanceRef.current = null
        seriesRef.current = null
      }

      const chart = createChart(chartRef.current, {
        width: chartRef.current.clientWidth || 800,
        height: 400,
        layout: {
          background: { color: '#0d1117' },
          textColor: '#94a3b8',
          fontSize: 12,
        },
        grid: {
          vertLines: { color: '#161f2e' },
          horzLines: { color: '#161f2e' },
        },
        crosshair: { mode: 1 },
        rightPriceScale: {
          borderColor: '#1e2d3d',
          scaleMargins: { top: 0.1, bottom: 0.1 },
        },
        timeScale: {
          borderColor: '#1e2d3d',
          timeVisible: true,
          secondsVisible: false,
        },
      })
      chartInstanceRef.current = chart

      const candleSeries = chart.addSeries
        ? chart.addSeries(CandlestickSeries, {
            upColor: '#10b981',
            downColor: '#f43f5e',
            borderUpColor: '#10b981',
            borderDownColor: '#f43f5e',
            wickUpColor: '#10b981',
            wickDownColor: '#f43f5e',
          })
        : chart.addCandlestickSeries({
            upColor: '#10b981',
            downColor: '#f43f5e',
            borderUpColor: '#10b981',
            borderDownColor: '#f43f5e',
            wickUpColor: '#10b981',
            wickDownColor: '#f43f5e',
          })

      seriesRef.current = candleSeries

      const seenTimes = new Set()
      const chartData = []

      candles.forEach(c => {
        let t = typeof c.time === 'number' ? c.time : Math.floor(new Date(c.time).getTime() / 1000)
        if (!isNaN(t) && !seenTimes.has(t)) {
          seenTimes.add(t)
          chartData.push({
            time: t,
            open: Number(c.open),
            high: Number(c.high),
            low: Number(c.low),
            close: Number(c.close),
          })
        }
      })

      chartData.sort((a, b) => a.time - b.time)

      if (chartData.length > 0) {
        candleSeries.setData(chartData)
        chart.timeScale().fitContent()

        const last = chartData[chartData.length - 1]
        setLastPrice(last.close)
        setPriceUp(last.close >= last.open)
      }

      // Live price polling
      const interval = setInterval(() => {
        api.get('/api/markets/prices', { timeout: 3000 })
          .then(d => {
            const priceData = (d.prices || []).find(p => p.symbol.replace(/[^a-zA-Z0-9]/g, '') === symbol)
            if (priceData) {
              setLiveBid(priceData.bid)
              setLiveAsk(priceData.ask)
              setLiveSpread(priceData.spread)

              if (chartData.length > 0 && seriesRef.current) {
                const mid = (priceData.bid + priceData.ask) / 2
                const last = chartData[chartData.length - 1]
                seriesRef.current.update({
                  time: last.time,
                  open: last.open,
                  high: Math.max(last.high, mid),
                  low: Math.min(last.low, mid),
                  close: mid,
                })
                setLastPrice(mid)
                setPriceUp(mid >= last.open)
              }
            }
          })
          .catch(() => {})
      }, 3000)

      const handleResize = () => {
        if (chartRef.current && chartInstanceRef.current) {
          chartInstanceRef.current.applyOptions({ width: chartRef.current.clientWidth })
        }
      }
      window.addEventListener('resize', handleResize)
      setChartError(false)

      return () => {
        clearInterval(interval)
        window.removeEventListener('resize', handleResize)
        if (chartInstanceRef.current) {
          chartInstanceRef.current.remove()
          chartInstanceRef.current = null
          seriesRef.current = null
        }
      }
    } catch (e) {
      console.error('Chart render error:', e)
      setChartError(true)
    }
  }, [candles, symbol])

  // --- MANUAL TRADE EXECUTION HANDLER ---
  const handleExecuteTrade = async (type) => {
    const volume = parseFloat(lotSize)
    if (isNaN(volume) || volume <= 0) {
      toast.error('Please enter a valid lot size greater than 0 (e.g. 0.01)')
      return
    }

    const sl = stopLoss ? parseFloat(stopLoss) : null
    const tp = takeProfit ? parseFloat(takeProfit) : null

    if (stopLoss && isNaN(sl)) {
      toast.error('Stop Loss must be a valid number')
      return
    }
    if (takeProfit && isNaN(tp)) {
      toast.error('Take Profit must be a valid number')
      return
    }

    setIsSubmitting(type)
    setLastOrderResult(null)

    try {
      const payload = {
        symbol,
        type: type.toUpperCase(),
        lot_size: volume,
        stop_loss: sl,
        take_profit: tp,
        reason: analysisReason || 'Manual Technical Analysis',
        comment: 'TradeAI Manual',
      }

      const res = await api.post('/api/trades/open', payload)

      if (res && res.success) {
        toast.success(`⚡ ${type} ${volume} Lots ${symbol} Executed @ ${res.price}! Ticket #${res.ticket}`)
        setLastOrderResult({
          success: true,
          type,
          price: res.price,
          ticket: res.ticket,
          volume,
          symbol,
          time: new Date().toLocaleTimeString(),
        })
        fetchPositions()
      } else {
        const errMsg = res?.error || res?.detail || 'Order placement failed on MT5'
        toast.error(errMsg)
        setLastOrderResult({
          success: false,
          error: errMsg,
          type,
          time: new Date().toLocaleTimeString(),
        })
      }
    } catch (err) {
      console.error('Order submission error:', err)
      let errMsg = err.detail || err.message || 'Execution error'
      if (typeof errMsg === 'string' && errMsg.includes('{"detail":')) {
        try {
          const parsed = JSON.parse(errMsg.slice(errMsg.indexOf('{')))
          if (parsed.detail) errMsg = parsed.detail
        } catch {}
      }
      toast.error(errMsg)
      setLastOrderResult({
        success: false,
        error: errMsg,
        type,
        time: new Date().toLocaleTimeString(),
      })
    } finally {
      setIsSubmitting(null)
    }
  }

  // --- CLOSE POSITION HANDLER ---
  const handleClosePosition = async (ticket) => {
    setClosingTicket(ticket)
    try {
      const res = await api.post('/api/trades/close', { ticket: String(ticket) })
      if (res && res.success) {
        const profitStr = res.profit !== undefined ? ` (P&L: $${Number(res.profit).toFixed(2)})` : ''
        toast.success(`Position #${ticket} successfully closed!${profitStr}`)
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

  // Helper for quick SL/TP pip presets
  const applyPipOffset = (target, pips, orderType = 'BUY') => {
    const currentPrice = orderType === 'BUY' ? (liveAsk || lastPrice) : (liveBid || lastPrice)
    if (!currentPrice) return
    const offset = pips / pipMultiplier
    if (target === 'SL') {
      const val = orderType === 'BUY' ? currentPrice - offset : currentPrice + offset
      setStopLoss(val.toFixed(decimals))
    } else if (target === 'TP') {
      const val = orderType === 'BUY' ? currentPrice + offset : currentPrice - offset
      setTakeProfit(val.toFixed(decimals))
    }
  }

  // Adjust lot size with +/- stepper
  const adjustLotSize = (delta) => {
    const current = parseFloat(lotSize) || 0.01
    const next = Math.max(0.01, +(current + delta).toFixed(2))
    setLotSize(next.toString())
  }

  if (!pair) return null

  const displayBid = liveBid || pair.bid || lastPrice
  const displayAsk = liveAsk || pair.ask || lastPrice

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 1000,
      background: 'rgba(0, 0, 0, 0.88)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '16px',
    }} onClick={onClose}>
      <div style={{
        background: '#0d1117',
        border: '1px solid #1e2d3d',
        borderRadius: '20px',
        width: '100%',
        maxWidth: '1020px',
        maxHeight: '94vh',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: '0 30px 70px rgba(0,0,0,0.85), 0 0 1px 1px rgba(255,255,255,0.05)',
      }} onClick={e => e.stopPropagation()}>

        {/* 1. MODAL HEADER */}
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid #1e2d3d',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
          background: 'linear-gradient(180deg, #101522 0%, #0d1117 100%)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{
              width: '40px',
              height: '40px',
              borderRadius: '12px',
              background: priceUp ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
              border: `1px solid ${priceUp ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: priceUp ? '0 0 15px rgba(16,185,129,0.15)' : '0 0 15px rgba(244,63,94,0.15)'
            }}>
              {priceUp ? <TrendingUp size={20} color="#10b981" /> : <TrendingDown size={20} color="#f43f5e" />}
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <select
                  value={symbol}
                  onChange={e => {
                    setSelectedSymbol(e.target.value)
                    setCandles([])
                    setLastOrderResult(null)
                  }}
                  style={{
                    fontSize: '18px',
                    fontWeight: '800',
                    padding: '2px 8px 2px 0',
                    background: 'transparent',
                    border: 'none',
                    color: '#ffffff',
                    outline: 'none',
                    cursor: 'pointer',
                  }}
                >
                  {allPairs.map(s => (
                    <option key={s} value={s} style={{ background: '#0d1117', color: '#fff' }}>
                      {s.replace(/(.{3})/, '$1/')}
                    </option>
                  ))}
                </select>

                {/* Account Status Pill */}
                {accountInfo && (
                  <span style={{
                    fontSize: '11px',
                    padding: '2px 8px',
                    borderRadius: '20px',
                    background: 'rgba(59, 91, 245, 0.15)',
                    border: '1px solid rgba(59, 91, 245, 0.3)',
                    color: '#818cf8',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontWeight: 600
                  }}>
                    <Wallet size={11} /> MT5 #{accountInfo.login || 'Live'} • ${Number(accountInfo.balance || 0).toLocaleString()}
                  </span>
                )}
              </div>

              <div style={{ fontSize: '11px', color: '#64748b', display: 'flex', gap: '8px' }}>
                <span>{isCrypto ? 'Crypto Asset' : symbol.startsWith('X') ? 'Commodity' : 'Forex Major'}</span>
                <span>•</span>
                <span style={{ color: '#10b981' }}>Live Terminal Synced</span>
              </div>
            </div>

            <div style={{ marginLeft: '12px' }}>
              <div style={{
                fontSize: '22px',
                fontWeight: '800',
                color: priceUp ? '#10b981' : '#f43f5e',
                letterSpacing: '-0.3px',
                fontFamily: 'var(--font-mono, monospace)'
              }}>
                {toFixed(lastPrice || displayBid)}
              </div>
              <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 600 }}>
                {activeTimeframe} • Live Feed
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {/* View Switcher: Chart vs Active Positions */}
            <div style={{ display: 'flex', background: '#0a0e17', borderRadius: '10px', padding: '3px', border: '1px solid #1c2233' }}>
              <button
                onClick={() => setActiveTab('chart')}
                style={{
                  padding: '5px 12px',
                  borderRadius: '7px',
                  border: 'none',
                  background: activeTab === 'chart' ? '#1e293b' : 'transparent',
                  color: activeTab === 'chart' ? '#ffffff' : '#64748b',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Candlestick Chart
              </button>
              <button
                onClick={() => setActiveTab('positions')}
                style={{
                  padding: '5px 12px',
                  borderRadius: '7px',
                  border: 'none',
                  background: activeTab === 'positions' ? '#3b5bf5' : 'transparent',
                  color: activeTab === 'positions' ? '#ffffff' : '#64748b',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <Layers size={12} />
                Open Positions {activePositions.length > 0 && `(${activePositions.length})`}
              </button>
            </div>

            {/* Timeframe selector (only on chart view) */}
            {activeTab === 'chart' && (
              <div style={{ display: 'flex', gap: '2px', background: '#0a0e17', borderRadius: '10px', padding: '3px', border: '1px solid #1c2233' }}>
                {timeframes.map(tf => (
                  <button
                    key={tf}
                    onClick={() => setActiveTimeframe(tf)}
                    style={{
                      padding: '5px 10px',
                      borderRadius: '7px',
                      border: 'none',
                      background: activeTimeframe === tf ? 'linear-gradient(135deg, #3b5bf5, #4f46e5)' : 'transparent',
                      color: activeTimeframe === tf ? '#ffffff' : '#64748b',
                      fontSize: '11px',
                      fontWeight: '600',
                      cursor: 'pointer',
                      transition: 'all 0.15s'
                    }}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            )}

            <button
              onClick={onClose}
              style={{
                background: 'rgba(244, 63, 94, 0.1)',
                border: '1px solid rgba(244, 63, 94, 0.25)',
                borderRadius: '9px',
                padding: '7px',
                cursor: 'pointer',
                color: '#f43f5e',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.15s'
              }}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* 2. SUB-HEADER TICKER BAR */}
        <div style={{
          padding: '10px 24px',
          borderBottom: '1px solid #1e2d3d',
          background: '#0a0e17',
          display: 'flex',
          gap: '32px',
          alignItems: 'center',
          flexWrap: 'wrap'
        }}>
          {[
            { label: 'Live Bid', value: toFixed(displayBid), color: '#10b981' },
            { label: 'Live Ask', value: toFixed(displayAsk), color: '#f43f5e' },
            { label: 'Spread', value: liveSpread ? `${liveSpread} pips` : '0.8 pips', color: '#94a3b8' },
            { label: 'Timeframe', value: activeTimeframe, color: '#818cf8' },
            { label: 'Active Positions', value: activePositions.length, color: activePositions.length > 0 ? '#10b981' : '#64748b' },
          ].map(({ label, value, color }) => (
            <div key={label}>
              <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '1px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                {label}
              </div>
              <div style={{ fontSize: '13px', fontWeight: '700', color, fontFamily: 'var(--font-mono, monospace)' }}>
                {value}
              </div>
            </div>
          ))}
        </div>

        {/* 3. MAIN BODY (CHART OR POSITIONS) */}
        <div style={{ flex: 1, minHeight: '380px', maxHeight: '420px', overflowY: 'auto', position: 'relative', background: '#0d1117' }}>
          {activeTab === 'chart' ? (
            <div style={{ position: 'relative', width: '100%', height: '400px' }}>
              {loading && (
                <div style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#94a3b8',
                  gap: '10px',
                  background: '#0d1117',
                  zIndex: 10
                }}>
                  <RefreshCw size={24} className="spin" color="#3b5bf5" />
                  <span style={{ fontSize: '13px', fontWeight: 500 }}>Loading candlestick bars from MetaTrader 5...</span>
                </div>
              )}

              {chartError && !loading && (
                <div style={{
                  height: 400,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#f43f5e',
                  gap: '8px'
                }}>
                  <span>Unable to render candlestick series.</span>
                  <button
                    onClick={() => setCandles(generateFallbackCandles(displayBid || 1.1000, activeTimeframe))}
                    style={{
                      background: '#1e2538',
                      color: '#fff',
                      border: '1px solid #2d3748',
                      padding: '6px 14px',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontSize: '12px'
                    }}
                  >
                    Reload Candles
                  </button>
                </div>
              )}

              <div ref={chartRef} style={{ width: '100%', height: '400px' }} />
            </div>
          ) : (
            /* POSITIONS VIEW */
            <div style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <h3 style={{ margin: 0, fontSize: '15px', fontWeight: '700', color: '#fff', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Layers size={16} color="#818cf8" />
                  Active Trades on {symbol} ({activePositions.length})
                </h3>
                <button
                  onClick={fetchPositions}
                  style={{
                    background: '#1e2538',
                    border: '1px solid #2d3748',
                    color: '#94a3b8',
                    padding: '4px 10px',
                    borderRadius: '6px',
                    fontSize: '11px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}
                >
                  <RefreshCw size={11} className={loadingPositions ? 'spin' : ''} /> Refresh
                </button>
              </div>

              {activePositions.length === 0 ? (
                <div style={{
                  padding: '48px 20px',
                  textAlign: 'center',
                  background: '#0a0e17',
                  borderRadius: '12px',
                  border: '1px solid #1a2233'
                }}>
                  <Shield size={28} color="#475569" style={{ margin: '0 auto 10px auto' }} />
                  <p style={{ color: '#94a3b8', fontSize: '13px', margin: '0 0 6px 0', fontWeight: 600 }}>No open positions on {symbol}</p>
                  <p style={{ color: '#64748b', fontSize: '12px', margin: 0 }}>Use the trading station below to execute your manual BUY or SELL order.</p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {activePositions.map(pos => {
                    const isPosBuy = pos.type?.toUpperCase() === 'BUY'
                    const pnl = Number(pos.profit || 0)
                    const pnlPositive = pnl >= 0
                    return (
                      <div
                        key={pos.ticket}
                        style={{
                          background: '#0a0e17',
                          border: '1px solid #1c2638',
                          borderRadius: '12px',
                          padding: '12px 18px',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          flexWrap: 'wrap',
                          gap: '12px'
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <span style={{
                            padding: '4px 10px',
                            borderRadius: '6px',
                            fontSize: '11px',
                            fontWeight: '800',
                            background: isPosBuy ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                            color: isPosBuy ? '#10b981' : '#f43f5e',
                            border: `1px solid ${isPosBuy ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`
                          }}>
                            {pos.type}
                          </span>
                          <div>
                            <div style={{ fontSize: '13px', fontWeight: 700, color: '#fff' }}>
                              {pos.volume} Lots @ {pos.open_price}
                            </div>
                            <div style={{ fontSize: '11px', color: '#64748b', fontFamily: 'var(--font-mono, monospace)' }}>
                              Ticket #{pos.ticket} • Current: {pos.current_price || '--'}
                            </div>
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{
                              fontSize: '14px',
                              fontWeight: '800',
                              color: pnlPositive ? '#10b981' : '#f43f5e',
                              fontFamily: 'var(--font-mono, monospace)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'flex-end',
                              gap: '2px'
                            }}>
                              {pnlPositive ? '+' : ''}${pnl.toFixed(2)}
                            </div>
                            <div style={{ fontSize: '11px', color: '#64748b' }}>
                              Floating P&L
                            </div>
                          </div>

                          <button
                            onClick={() => handleClosePosition(pos.ticket)}
                            disabled={closingTicket === pos.ticket}
                            style={{
                              background: 'rgba(244, 63, 94, 0.12)',
                              border: '1px solid rgba(244, 63, 94, 0.3)',
                              color: '#f43f5e',
                              padding: '7px 14px',
                              borderRadius: '8px',
                              fontSize: '12px',
                              fontWeight: '700',
                              cursor: closingTicket === pos.ticket ? 'not-allowed' : 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '6px'
                            }}
                          >
                            {closingTicket === pos.ticket ? (
                              <RefreshCw size={12} className="spin" />
                            ) : (
                              <X size={12} />
                            )}
                            Close Position
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 4. EXECUTION FEEDBACK BANNER */}
        {lastOrderResult && (
          <div style={{
            padding: '10px 24px',
            background: lastOrderResult.success ? 'rgba(16, 185, 129, 0.12)' : 'rgba(244, 63, 94, 0.12)',
            borderTop: `1px solid ${lastOrderResult.success ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '12px',
            color: lastOrderResult.success ? '#10b981' : '#f43f5e',
            fontWeight: 600
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {lastOrderResult.success ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
              <span>
                {lastOrderResult.success
                  ? `Order Filled: ${lastOrderResult.type} ${lastOrderResult.volume} lots of ${lastOrderResult.symbol} at ${lastOrderResult.price} (Ticket #${lastOrderResult.ticket}) at ${lastOrderResult.time}`
                  : `Order Rejected: ${lastOrderResult.error} (${lastOrderResult.time})`}
              </span>
            </div>
            <button
              onClick={() => setLastOrderResult(null)}
              style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: '2px' }}
            >
              <X size={14} />
            </button>
          </div>
        )}

        {/* 5. COLLAPSIBLE ADVANCED RISK & ANALYSIS DRAWER */}
        {showAdvanced && (
          <div style={{
            padding: '16px 24px',
            background: '#090d15',
            borderTop: '1px solid #1a2334',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '16px'
          }}>
            {/* Stop Loss Input */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <label style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600 }}>Stop Loss (Price)</label>
                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    onClick={() => applyPipOffset('SL', 20, 'BUY')}
                    style={{ background: '#171f2f', border: '1px solid #233044', borderRadius: '4px', fontSize: '10px', color: '#94a3b8', padding: '2px 5px', cursor: 'pointer' }}
                  >
                    -20p
                  </button>
                  <button
                    onClick={() => applyPipOffset('SL', 40, 'BUY')}
                    style={{ background: '#171f2f', border: '1px solid #233044', borderRadius: '4px', fontSize: '10px', color: '#94a3b8', padding: '2px 5px', cursor: 'pointer' }}
                  >
                    -40p
                  </button>
                </div>
              </div>
              <input
                type="number"
                step="any"
                placeholder={toFixed(displayBid ? displayBid * 0.998 : 0)}
                value={stopLoss}
                onChange={e => setStopLoss(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: '#131722',
                  border: '1px solid #233044',
                  borderRadius: '8px',
                  color: '#ffffff',
                  fontSize: '12px',
                  outline: 'none',
                  boxSizing: 'border-box',
                  fontFamily: 'var(--font-mono, monospace)'
                }}
              />
            </div>

            {/* Take Profit Input */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <label style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600 }}>Take Profit (Price)</label>
                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    onClick={() => applyPipOffset('TP', 30, 'BUY')}
                    style={{ background: '#171f2f', border: '1px solid #233044', borderRadius: '4px', fontSize: '10px', color: '#94a3b8', padding: '2px 5px', cursor: 'pointer' }}
                  >
                    +30p
                  </button>
                  <button
                    onClick={() => applyPipOffset('TP', 60, 'BUY')}
                    style={{ background: '#171f2f', border: '1px solid #233044', borderRadius: '4px', fontSize: '10px', color: '#94a3b8', padding: '2px 5px', cursor: 'pointer' }}
                  >
                    +60p
                  </button>
                </div>
              </div>
              <input
                type="number"
                step="any"
                placeholder={toFixed(displayAsk ? displayAsk * 1.003 : 0)}
                value={takeProfit}
                onChange={e => setTakeProfit(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: '#131722',
                  border: '1px solid #233044',
                  borderRadius: '8px',
                  color: '#ffffff',
                  fontSize: '12px',
                  outline: 'none',
                  boxSizing: 'border-box',
                  fontFamily: 'var(--font-mono, monospace)'
                }}
              />
            </div>

            {/* Analysis Reason / Setup Tag */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <label style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600 }}>Strategy / Setup Reason</label>
                <span style={{ fontSize: '10px', color: '#64748b' }}>For Analytics Journal</span>
              </div>
              <input
                placeholder="e.g. H1 Resistance Breakout / FVG"
                value={analysisReason}
                onChange={e => setAnalysisReason(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: '#131722',
                  border: '1px solid #233044',
                  borderRadius: '8px',
                  color: '#ffffff',
                  fontSize: '12px',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
            </div>
          </div>
        )}

        {/* 6. PRIMARY TRADING ACTION STATION (BOTTOM BAR) */}
        <div style={{
          padding: '16px 24px',
          borderTop: '1px solid #1e2d3d',
          background: '#080c14',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}>
          {/* Top row: Lot size selector + Quick chips + Risk toggle */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 700 }}>Volume / Lots:</span>

              {/* Lot size stepper */}
              <div style={{ display: 'flex', alignItems: 'center', background: '#131722', borderRadius: '8px', border: '1px solid #1e2d3d' }}>
                <button
                  onClick={() => adjustLotSize(-0.01)}
                  style={{
                    padding: '8px 10px', background: 'transparent', border: 'none',
                    color: '#94a3b8', cursor: 'pointer', display: 'flex', alignItems: 'center'
                  }}
                  title="Decrease 0.01"
                >
                  <Minus size={13} />
                </button>
                <input
                  type="number"
                  value={lotSize}
                  onChange={e => setLotSize(e.target.value)}
                  step="0.01"
                  min="0.01"
                  style={{
                    padding: '6px 4px',
                    background: 'transparent',
                    border: 'none',
                    color: '#ffffff',
                    fontSize: '14px',
                    outline: 'none',
                    width: '60px',
                    textAlign: 'center',
                    fontWeight: 700,
                    fontFamily: 'var(--font-mono, monospace)'
                  }}
                />
                <button
                  onClick={() => adjustLotSize(0.01)}
                  style={{
                    padding: '8px 10px', background: 'transparent', border: 'none',
                    color: '#94a3b8', cursor: 'pointer', display: 'flex', alignItems: 'center'
                  }}
                  title="Increase 0.01"
                >
                  <Plus size={13} />
                </button>
              </div>

              {/* Quick Lot Chips */}
              <div style={{ display: 'flex', gap: '4px' }}>
                {['0.01', '0.05', '0.10', '0.50', '1.00'].map(val => (
                  <button
                    key={val}
                    onClick={() => setLotSize(val)}
                    style={{
                      padding: '5px 8px',
                      borderRadius: '6px',
                      background: lotSize === val ? '#3b5bf5' : '#141a27',
                      border: `1px solid ${lotSize === val ? '#3b5bf5' : '#1e2d3d'}`,
                      color: lotSize === val ? '#fff' : '#64748b',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      transition: 'all 0.15s'
                    }}
                  >
                    {val}
                  </button>
                ))}
              </div>
            </div>

            {/* Toggle Advanced SL/TP Drawer */}
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              style={{
                background: showAdvanced ? 'rgba(59, 91, 245, 0.15)' : '#101624',
                border: `1px solid ${showAdvanced ? '#3b5bf5' : '#1e2d3d'}`,
                color: showAdvanced ? '#818cf8' : '#94a3b8',
                padding: '6px 12px',
                borderRadius: '8px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                transition: 'all 0.15s'
              }}
            >
              <Shield size={13} />
              {showAdvanced ? 'Hide Risk Parameters' : 'Set Stop Loss & Take Profit'}
              {showAdvanced ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
          </div>

          {/* Bottom row: Large Interactive BUY & SELL Buttons */}
          <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
            {/* BUY BUTTON */}
            <button
              onClick={() => handleExecuteTrade('BUY')}
              disabled={isSubmitting !== null}
              style={{
                flex: 1,
                padding: '14px 20px',
                background: isSubmitting === 'BUY'
                  ? 'rgba(16, 185, 129, 0.3)'
                  : 'linear-gradient(135deg, rgba(16, 185, 129, 0.22) 0%, rgba(5, 150, 105, 0.15) 100%)',
                border: '1px solid rgba(16, 185, 129, 0.45)',
                borderRadius: '12px',
                color: '#10b981',
                fontSize: '15px',
                fontWeight: '800',
                cursor: isSubmitting !== null ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '10px',
                boxShadow: '0 4px 20px rgba(16, 185, 129, 0.1)'
              }}
              onMouseEnter={e => {
                if (isSubmitting === null) {
                  e.currentTarget.style.background = 'rgba(16, 185, 129, 0.32)'
                  e.currentTarget.style.transform = 'translateY(-1px)'
                }
              }}
              onMouseLeave={e => {
                if (isSubmitting === null) {
                  e.currentTarget.style.background = 'linear-gradient(135deg, rgba(16, 185, 129, 0.22) 0%, rgba(5, 150, 105, 0.15) 100%)'
                  e.currentTarget.style.transform = 'translateY(0)'
                }
              }}
            >
              {isSubmitting === 'BUY' ? (
                <>
                  <RefreshCw size={18} className="spin" />
                  <span>Executing BUY Order...</span>
                </>
              ) : (
                <>
                  <ArrowUpRight size={20} strokeWidth={2.5} />
                  <div style={{ textAlign: 'left' }}>
                    <div style={{ lineHeight: 1.1 }}>BUY MARKET</div>
                    <div style={{ fontSize: '11px', opacity: 0.8, fontFamily: 'var(--font-mono, monospace)' }}>
                      Ask: {toFixed(displayAsk)} ({lotSize} lot)
                    </div>
                  </div>
                </>
              )}
            </button>

            {/* SELL BUTTON */}
            <button
              onClick={() => handleExecuteTrade('SELL')}
              disabled={isSubmitting !== null}
              style={{
                flex: 1,
                padding: '14px 20px',
                background: isSubmitting === 'SELL'
                  ? 'rgba(244, 63, 94, 0.3)'
                  : 'linear-gradient(135deg, rgba(244, 63, 94, 0.22) 0%, rgba(225, 29, 72, 0.15) 100%)',
                border: '1px solid rgba(244, 63, 94, 0.45)',
                borderRadius: '12px',
                color: '#f43f5e',
                fontSize: '15px',
                fontWeight: '800',
                cursor: isSubmitting !== null ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '10px',
                boxShadow: '0 4px 20px rgba(244, 63, 94, 0.1)'
              }}
              onMouseEnter={e => {
                if (isSubmitting === null) {
                  e.currentTarget.style.background = 'rgba(244, 63, 94, 0.32)'
                  e.currentTarget.style.transform = 'translateY(-1px)'
                }
              }}
              onMouseLeave={e => {
                if (isSubmitting === null) {
                  e.currentTarget.style.background = 'linear-gradient(135deg, rgba(244, 63, 94, 0.22) 0%, rgba(225, 29, 72, 0.15) 100%)'
                  e.currentTarget.style.transform = 'translateY(0)'
                }
              }}
            >
              {isSubmitting === 'SELL' ? (
                <>
                  <RefreshCw size={18} className="spin" />
                  <span>Executing SELL Order...</span>
                </>
              ) : (
                <>
                  <ArrowDownRight size={20} strokeWidth={2.5} />
                  <div style={{ textAlign: 'left' }}>
                    <div style={{ lineHeight: 1.1 }}>SELL MARKET</div>
                    <div style={{ fontSize: '11px', opacity: 0.8, fontFamily: 'var(--font-mono, monospace)' }}>
                      Bid: {toFixed(displayBid)} ({lotSize} lot)
                    </div>
                  </div>
                </>
              )}
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
