import React, { useState } from 'react'
import { X } from 'lucide-react'

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
  mmc_mirror: {
    name: 'MMC Mirror',
    pairs: ['XAUUSD', 'EURUSD', 'GBPUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'USDJPY', 'AUDUSD'],
    timeframes: ['M5', 'M15', 'H1', 'H4'], defaultPair: 'XAUUSD', defaultTimeframe: 'M5'
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

const FALLBACK = {
  name: 'Custom Strategy',
  pairs: ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD', 'DOGEUSD', 'ADAUSD', 'AUDUSD', 'USDCAD', 'GBPJPY'],
  timeframes: ['M1', 'M5', 'M15', 'H1', 'H4', 'D1'],
  defaultPair: 'EURUSD', defaultTimeframe: 'M5'
}

function getAutoPipInfo(sym) {
  const s = (sym || '').toUpperCase()
  if (s.includes('XAU') || s.includes('XAG') || s.includes('GOLD') || s.includes('SILVER')) {
    return { size: 0.10, decimals: 2, isStandardForex: false }
  }
  if (s.includes('JPY')) {
    return { size: 0.01, decimals: 3, isStandardForex: false }
  }
  if (s.includes('BTC') || s.includes('ETH') || s.includes('SOL')) {
    return { size: 0.01, decimals: 2, isStandardForex: false }
  }
  return { size: 0.0001, decimals: 5, isStandardForex: true }
}

export default function StrategyConfigModal({ strategy, onClose, onSave, initialConfig }) {
  const config = strategyDefaults[strategy] || FALLBACK
  const init = initialConfig || {}
  const initCfg = init.config || {}
  const isPipStep = strategy === 'pipstep_reversal'
  const initPair = init.pair || config.defaultPair
  const initAuto = getAutoPipInfo(initPair)
  const savedPipPrice = parseFloat(initCfg.pip_price || 0) || 0
  // Auto-reset clearly erroneous forex override (e.g. 0.01 accidentally saved for EURUSD)
  const hadBadForexOverride = initAuto.isStandardForex && savedPipPrice >= 0.005
  const effectiveInitPipPrice = hadBadForexOverride ? 0 : savedPipPrice

  const [pair, setPair] = useState(initPair)
  const [timeframe, setTimeframe] = useState(init.timeframe || config.defaultTimeframe)
  const [lotSize, setLotSize] = useState(init.lot_size ?? init.lotSize ?? initCfg.lots ?? 0.01)
  const [maxTrades, setMaxTrades] = useState(init.max_trades ?? init.maxTrades ?? 1)
  const [maxDailyLoss, setMaxDailyLoss] = useState(init.max_daily_loss ?? init.maxDailyLoss ?? 100)

  // PipStep_Reversal_EA.mq5 inputs
  const [entryPips, setEntryPips] = useState(initCfg.entry_pips ?? 10)
  const [slPips, setSlPips] = useState(initCfg.sl_pips ?? 10)
  const [stepPips, setStepPips] = useState(initCfg.step_pips ?? 10)
  const [useCustomPip, setUseCustomPip] = useState(effectiveInitPipPrice > 0)
  const [pipPrice, setPipPrice] = useState(effectiveInitPipPrice)
  const [maxSpreadPips, setMaxSpreadPips] = useState(initCfg.max_spread_pips ?? 0)
  const [deviationPips, setDeviationPips] = useState(initCfg.deviation_pips ?? 3)
  const [dailyLossPct, setDailyLossPct] = useState(initCfg.daily_loss_pct ?? 10)
  const [dailyProfitPct, setDailyProfitPct] = useState(initCfg.daily_profit_pct ?? 20)
  const [magicNumber, setMagicNumber] = useState(initCfg.magic_number ?? 26110401)
  const [deleteOnRemove, setDeleteOnRemove] = useState(initCfg.delete_on_remove ?? true)

  const autoInfo = getAutoPipInfo(pair)
  const activePipSize = useCustomPip && (parseFloat(pipPrice) || 0) > 0 ? parseFloat(pipPrice) : autoInfo.size
  const entryOffsetPrice = ((parseFloat(entryPips) || 10) * activePipSize).toFixed(autoInfo.decimals)
  const slOffsetPrice = ((parseFloat(slPips) || 10) * activePipSize).toFixed(autoInfo.decimals)
  const isSuspiciousForexPip = autoInfo.isStandardForex && useCustomPip && activePipSize >= 0.005

  const preventWheelChange = e => e.target.blur()

  const backdrop = {
    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
    background: 'rgba(0,0,0,0.7)', display: 'flex',
    alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    padding: 16
  }
  const modal = {
    background: '#13131a', borderRadius: 16,
    border: '1px solid #1e2d3d', padding: 'clamp(18px, 4vw, 28px)',
    width: isPipStep ? 'min(540px, 95vw)' : 'min(480px, 95vw)', maxHeight: '90vh', overflow: 'auto',
    boxSizing: 'border-box'
  }
  const label = { color: '#8b949e', fontSize: 12, fontWeight: 500, marginBottom: 6, display: 'block' }
  const input = {
    width: '100%', padding: '10px 14px', background: '#0a0e17',
    border: '1px solid #1e2d3d', borderRadius: 8, color: '#e1e4e8',
    fontSize: 14, outline: 'none', boxSizing: 'border-box'
  }
  const row = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 14, marginBottom: 14 }

  const handleSave = () => {
    const parsedLots = Math.max(0.01, parseFloat(lotSize) || 0.01)
    if (isPipStep) {
      let finalPipPrice = useCustomPip ? Math.max(0, parseFloat(pipPrice) || 0) : 0
      if (autoInfo.isStandardForex && finalPipPrice >= 0.005) {
        finalPipPrice = 0
      }
      onSave({
        pair,
        timeframe,
        lot_size: parsedLots,
        max_trades: 1,
        max_daily_loss: 100,
        config: {
          lots: parsedLots,
          entry_pips: Math.max(0.1, parseFloat(entryPips) || 10),
          sl_pips: Math.max(0.1, parseFloat(slPips) || 10),
          step_pips: Math.max(0.1, parseFloat(stepPips) || 10),
          pip_price: finalPipPrice,
          max_spread_pips: Math.max(0, parseFloat(maxSpreadPips) || 0),
          deviation_pips: Math.max(0.1, parseFloat(deviationPips) || 3),
          daily_loss_pct: Math.max(0.1, parseFloat(dailyLossPct) || 10),
          daily_profit_pct: Math.max(0.1, parseFloat(dailyProfitPct) || 20),
          magic_number: parseInt(magicNumber, 10) || 26110401,
          delete_on_remove: Boolean(deleteOnRemove),
          comment: 'PIPSTEP',
        },
      })
      return
    }
    onSave({
      pair,
      timeframe,
      lot_size: parsedLots,
      max_trades: parseInt(maxTrades, 10) || 1,
      max_daily_loss: parseFloat(maxDailyLoss) || 100,
    })
  }

  return (
    <div style={backdrop} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
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
          {isPipStep && (
            <div>
              <label style={label}>Lot Size</label>
              <input style={input} type="number" step="0.01" min="0.01" max="100" value={lotSize} onWheel={preventWheelChange} onChange={e => setLotSize(e.target.value)} />
            </div>
          )}
        </div>

        {isPipStep ? (
          <>
            <div style={row}>
              <div>
                <label style={label}>Entry Distance (pips)</label>
                <input style={input} type="number" step="0.5" min="1" value={entryPips} onWheel={preventWheelChange} onChange={e => setEntryPips(e.target.value)} />
              </div>
              <div>
                <label style={label}>Initial SL (pips)</label>
                <input style={input} type="number" step="0.5" min="1" value={slPips} onWheel={preventWheelChange} onChange={e => setSlPips(e.target.value)} />
              </div>
              <div>
                <label style={label}>Trail Step (pips)</label>
                <input style={input} type="number" step="0.5" min="1" value={stepPips} onWheel={preventWheelChange} onChange={e => setStepPips(e.target.value)} />
              </div>
            </div>

            <div style={row}>
              <div>
                <label style={label}>Daily Loss Stop (%)</label>
                <input style={input} type="number" step="1" min="1" max="100" value={dailyLossPct} onWheel={preventWheelChange} onChange={e => setDailyLossPct(e.target.value)} />
              </div>
              <div>
                <label style={label}>Daily Profit Target (%)</label>
                <input style={input} type="number" step="1" min="1" max="500" value={dailyProfitPct} onWheel={preventWheelChange} onChange={e => setDailyProfitPct(e.target.value)} />
              </div>
              <div>
                <label style={label}>Max Spread (pips, 0=off)</label>
                <input style={input} type="number" step="0.5" min="0" value={maxSpreadPips} onWheel={preventWheelChange} onChange={e => setMaxSpreadPips(e.target.value)} />
              </div>
            </div>

            <div style={row}>
              <div>
                <label style={label}>Slippage / Deviation (pips)</label>
                <input style={input} type="number" step="0.5" min="0.5" value={deviationPips} onWheel={preventWheelChange} onChange={e => setDeviationPips(e.target.value)} />
              </div>
              <div>
                <label style={label}>Magic Number</label>
                <input style={input} type="number" step="1" min="1" value={magicNumber} onWheel={preventWheelChange} onChange={e => setMagicNumber(e.target.value)} />
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#cbd5e1', fontSize: 12.5, marginBottom: 8, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={deleteOnRemove}
                  onChange={e => setDeleteOnRemove(e.target.checked)}
                />
                Delete pending BuyStop/SellStop orders when bot stops
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#94a3b8', fontSize: 12, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={useCustomPip}
                  onChange={e => {
                    const checked = e.target.checked
                    setUseCustomPip(checked)
                    if (!checked) setPipPrice(0)
                  }}
                />
                Advanced: Override auto pip size manually (currently Auto: {autoInfo.size})
              </label>

              {useCustomPip && (
                <div style={{ marginTop: 8 }}>
                  <label style={label}>Manual Pip Size in Price Units (e.g. 0.0001 for EURUSD, 0.10 for XAUUSD)</label>
                  <input
                    style={input}
                    type="number"
                    step="0.0001"
                    min="0"
                    value={pipPrice}
                    onWheel={preventWheelChange}
                    onChange={e => setPipPrice(e.target.value)}
                  />
                </div>
              )}
            </div>

            {hadBadForexOverride && (
              <div style={{ marginBottom: 10, padding: '8px 12px', borderRadius: 6, background: 'rgba(245, 158, 11, 0.12)', border: '1px solid rgba(245, 158, 11, 0.3)', color: '#fbbf24', fontSize: 12 }}>
                Previous manual Pip Size ({savedPipPrice}) was reset to <strong>Auto ({initAuto.size})</strong> so orders place at {entryPips} real pips instead of 1,000+ pips away.
              </div>
            )}

            {isSuspiciousForexPip && (
              <div style={{ marginBottom: 10, padding: '8px 12px', borderRadius: 6, background: 'rgba(239, 68, 68, 0.12)', border: '1px solid rgba(239, 68, 68, 0.35)', color: '#fca5a5', fontSize: 12 }}>
                Warning: {activePipSize} is 100x+ larger than a normal {pair} pip ({autoInfo.size}). Uncheck manual override above to use Auto ({autoInfo.size}).
              </div>
            )}
          </>
        ) : (
          <>
            <div style={row}>
              <div>
                <label style={label}>Lot Size</label>
                <input style={input} type="number" step="0.01" min="0.01" max="100" value={lotSize} onWheel={preventWheelChange} onChange={e => setLotSize(e.target.value)} />
              </div>
              <div>
                <label style={label}>Max Trades</label>
                <input style={input} type="number" min="1" max="100" value={maxTrades} onWheel={preventWheelChange} onChange={e => setMaxTrades(e.target.value)} />
              </div>
            </div>

            <div style={row}>
              <div>
                <label style={label}>Max Daily Loss ($)</label>
                <input style={input} type="number" step="10" min="10" value={maxDailyLoss} onWheel={preventWheelChange} onChange={e => setMaxDailyLoss(e.target.value)} />
              </div>
            </div>
          </>
        )}

        <p style={{ color: '#6b7a8d', fontSize: 12, lineHeight: 1.6, margin: '0 0 20px 0' }}>
          {!isPipStep && 'Take profit and stop loss use server defaults (50 / 25). Strategy-specific parameters can be tuned via the API config dict if needed.'}
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
          {isPipStep && (
            <span style={{ display: 'block', marginTop: 4, color: '#38bdf8', background: 'rgba(56, 189, 248, 0.1)', padding: '8px 12px', borderRadius: '6px', border: '1px solid rgba(56, 189, 248, 0.2)' }}>
              <strong>PipStep Preview ({pair}):</strong> 1 pip = {useCustomPip ? activePipSize : `${autoInfo.size} (Auto)`} · BuyStop = Ask + {entryOffsetPrice} · SellStop = Bid − {entryOffsetPrice} · SL = {slOffsetPrice} · Trail = {stepPips} pips · No TP.
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
            Save &amp; Start Bot
          </button>
        </div>
      </div>
    </div>
  )
}
