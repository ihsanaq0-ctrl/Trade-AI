import React, { useState } from 'react'
import { X } from 'lucide-react'

// Per-strategy UI defaults only: display name, tradable pairs, timeframes.
// No hardcoded strategy parameters — the start flow asks for essentials only
// (pair, timeframe, lot size, max trades, max daily loss).
const strategyDefaults = {
  smart_money: {
    name: 'SMC',
    pairs: ['EURUSD', 'GBPUSD', 'XAUUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD', 'DOGEUSD', 'ADAUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'GBPJPY'],
    timeframes: ['H1', 'H4', 'D1'], defaultPair: 'EURUSD', defaultTimeframe: 'H1'
  },
  mirror: {
    name: 'MMC',
    pairs: ['EURUSD', 'GBPUSD', 'XAUUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD', 'DOGEUSD', 'ADAUSD', 'USDJPY', 'AUDUSD'],
    timeframes: ['H1', 'H4', 'D1'], defaultPair: 'EURUSD', defaultTimeframe: 'H1'
  },
  classic: {
    name: 'Classic Mode',
    pairs: ['EURUSD', 'GBPUSD', 'XAUUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD', 'DOGEUSD', 'ADAUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'GBPJPY', 'EURJPY', 'NZDUSD'],
    timeframes: ['H4', 'D1'], defaultPair: 'EURUSD', defaultTimeframe: 'H4'
  },
  full_confluence: {
    name: 'Full Confluence',
    pairs: ['EURUSD', 'GBPUSD', 'XAUUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD'],
    timeframes: ['H1', 'H4', 'D1'], defaultPair: 'EURUSD', defaultTimeframe: 'H4'
  },
  scalp_pyramid: {
    name: 'Scalp Pyramid',
    pairs: ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD', 'DOGEUSD', 'ADAUSD', 'AUDUSD', 'GBPJPY'],
    timeframes: ['M1', 'M5', 'M15'], defaultPair: 'EURUSD', defaultTimeframe: 'M1'
  },
  scalp_fvg: {
    name: 'Scalp (FVG)',
    pairs: ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD', 'DOGEUSD', 'ADAUSD', 'AUDUSD', 'GBPJPY'],
    timeframes: ['M1', 'M5', 'M15'], defaultPair: 'EURUSD', defaultTimeframe: 'M1'
  },
  signal_strength_hedge: {
    name: 'Signal Strength Hedge',
    pairs: ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD', 'DOGEUSD', 'ADAUSD', 'AUDUSD', 'GBPJPY'],
    timeframes: ['M5'], defaultPair: 'EURUSD', defaultTimeframe: 'M5'
  },
  nyao_scalper: {
    name: 'Nyao Trade Manager',
    pairs: ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD', 'DOGEUSD', 'ADAUSD', 'AUDUSD', 'GBPJPY'],
    timeframes: ['M1', 'M5', 'M15', 'H1'], defaultPair: 'EURUSD', defaultTimeframe: 'M1'
  },
  pipstep_reversal: {
    name: 'PipStep Reversal EA',
    pairs: ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'AUDUSD', 'USDCAD', 'GBPJPY'],
    timeframes: ['M1', 'M5'], defaultPair: 'EURUSD', defaultTimeframe: 'M1'
  }
}

// Admin-added strategies have no preset block — use sensible generic options.
const FALLBACK = {
  name: 'Custom Strategy',
  pairs: ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD', 'DOGEUSD', 'ADAUSD', 'AUDUSD', 'USDCAD', 'GBPJPY'],
  timeframes: ['M1', 'M5', 'M15', 'H1', 'H4', 'D1'],
  defaultPair: 'EURUSD', defaultTimeframe: 'M5'
}

export default function StrategyConfigModal({ strategy, onClose, onSave, initialConfig }) {
  const config = strategyDefaults[strategy] || FALLBACK
  const init = initialConfig || {}
  const [pair, setPair] = useState(init.pair || config.defaultPair)
  const [timeframe, setTimeframe] = useState(init.timeframe || config.defaultTimeframe)
  const [lotSize, setLotSize] = useState(init.lot_size ?? init.lotSize ?? 0.01)
  const [maxTrades, setMaxTrades] = useState(init.max_trades ?? init.maxTrades ?? 1)
  const [maxDailyLoss, setMaxDailyLoss] = useState(init.max_daily_loss ?? init.maxDailyLoss ?? 100)

  const backdrop = {
    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
    background: 'rgba(0,0,0,0.7)', display: 'flex',
    alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    padding: 16
  }
  const modal = {
    background: '#13131a', borderRadius: 16,
    border: '1px solid #1e2d3d', padding: 'clamp(18px, 4vw, 28px)',
    width: 'min(480px, 95vw)', maxHeight: '90vh', overflow: 'auto',
    boxSizing: 'border-box'
  }
  const label = { color: '#8b949e', fontSize: 12, fontWeight: 500, marginBottom: 6, display: 'block' }
  const input = {
    width: '100%', padding: '10px 14px', background: '#0a0e17',
    border: '1px solid #1e2d3d', borderRadius: 8, color: '#e1e4e8',
    fontSize: 14, outline: 'none', boxSizing: 'border-box'
  }
  const row = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16, marginBottom: 16 }

  const handleSave = () => {
    onSave({
      pair,
      timeframe,
      lot_size: parseFloat(lotSize) || 0.01,
      max_trades: parseInt(maxTrades) || 1,
      max_daily_loss: parseFloat(maxDailyLoss) || 100,
    })
  }

  return (
    <div style={backdrop} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <h2 style={{ color: '#e1e4e8', fontSize: 18, fontWeight: 600, margin: 0 }}>{config.name}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#6b7a8d', cursor: 'pointer', padding: 4 }}>
            <X size={20} />
          </button>
        </div>

        <div style={row}>
          <div>
            <label style={label}>Trading Pair</label>
            <select style={input} value={pair} onChange={e => setPair(e.target.value)}>
              {config.pairs.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label style={label}>Timeframe</label>
            <select style={input} value={timeframe} onChange={e => setTimeframe(e.target.value)}>
              {config.timeframes.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>

        <div style={row}>
          <div>
            <label style={label}>Lot Size</label>
            <input style={input} type="number" step="0.01" min="0.01" max="100" value={lotSize} onChange={e => setLotSize(e.target.value)} />
          </div>
          <div>
            <label style={label}>Max Trades</label>
            <input style={input} type="number" min="1" max="100" value={maxTrades} onChange={e => setMaxTrades(e.target.value)} />
          </div>
        </div>

        <div style={row}>
          <div>
            <label style={label}>Max Daily Loss ($)</label>
            <input style={input} type="number" step="10" min="10" value={maxDailyLoss} onChange={e => setMaxDailyLoss(e.target.value)} />
          </div>
        </div>

        <p style={{ color: '#6b7a8d', fontSize: 12, lineHeight: 1.6, margin: '0 0 20px 0' }}>
          Take profit and stop loss use server defaults (50 / 25). Strategy-specific
          parameters can be tuned via the API config dict if needed.
          {strategy === 'nyao_scalper' && (
            <span style={{ display: 'block', marginTop: 8, color: '#e1e4e8', background: '#1e2d3d', padding: '8px', borderRadius: '4px' }}>
              <strong>Note:</strong> The Nyao Trade Manager only manages <em>manually opened trades</em>. It will not autonomously enter new positions.
            </span>
          )}
          {strategy === 'mmc_mirror' && (
            <span style={{ display: 'block', marginTop: 8, color: '#f59e0b', background: '#f59e0b22', padding: '8px', borderRadius: '4px' }}>
              <strong>Demo/Paper Mode Default:</strong> Orders will route to your demo account until manually promoted.
            </span>
          )}
          {strategy === 'pipstep_reversal' && (
            <span style={{ display: 'block', marginTop: 8, color: '#38bdf8', background: 'rgba(56, 189, 248, 0.1)', padding: '8px 12px', borderRadius: '6px', border: '1px solid rgba(56, 189, 248, 0.2)' }}>
              <strong>PipStep Straddle:</strong> Places symmetrical BuyStop & SellStop pending orders (10 pips). Automatically trails SL in steps and reverses trade instantly if SL is hit.
            </span>
          )}
        </p>

        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <button onClick={onClose}
            style={{ padding: '10px 20px', background: '#1e2d3d', border: 'none', borderRadius: 8, color: '#8b949e', cursor: 'pointer', fontSize: 14 }}>
            Cancel
          </button>
          <button onClick={handleSave}
            style={{ padding: '10px 24px', background: '#00d4ff', border: 'none', borderRadius: 8, color: '#0a0e17', cursor: 'pointer', fontSize: 14, fontWeight: 600 }}>
            Save & Start Bot
          </button>
        </div>
      </div>
    </div>
  )
}
