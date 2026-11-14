// Live Real-Time Market Data Service
// Aggregates MT5 broker live quotes and Binance ticker streams

import api from '../api'

const BINANCE_BASE = 'https://api.binance.com/api/v3'

export const DEFAULT_TOP_PAIRS = [
  { symbol: 'EURUSD', name: 'EUR / USD', type: 'Forex', price: 0, changePct: 0, direction: 'up', high: 0, low: 0, volume: '—' },
  { symbol: 'GBPUSD', name: 'GBP / USD', type: 'Forex', price: 0, changePct: 0, direction: 'up', high: 0, low: 0, volume: '—' },
  { symbol: 'XAUUSD', name: 'Gold Spot', type: 'Commodity', price: 0, changePct: 0, direction: 'up', high: 0, low: 0, volume: '—' },
  { symbol: 'BTCUSD', name: 'Bitcoin', type: 'Crypto', price: 0, changePct: 0, direction: 'up', high: 0, low: 0, volume: '—' }
]

export const EXTENDED_PAIRS = [
  { symbol: 'USDJPY', name: 'USD / JPY', type: 'Forex', price: 0, changePct: 0, direction: 'up' },
  { symbol: 'ETHUSD', name: 'Ethereum', type: 'Crypto', price: 0, changePct: 0, direction: 'up' },
  { symbol: 'SOLUSD', name: 'Solana', type: 'Crypto', price: 0, changePct: 0, direction: 'up' },
  { symbol: 'USDCAD', name: 'USD / CAD', type: 'Forex', price: 0, changePct: 0, direction: 'up' }
]

/**
 * Fetch live top pairs from backend MT5 and Binance public endpoints
 */
export async function fetchLiveMarketData() {
  const result = {
    overview: DEFAULT_TOP_PAIRS.map(p => ({ ...p })),
    extended: EXTENDED_PAIRS.map(p => ({ ...p })),
    lastUpdated: new Date()
  }

  // 1. Fetch live quotes from MT5 backend service
  try {
    const mt5Res = await api.get('/api/markets/prices')
    if (mt5Res?.prices && Array.isArray(mt5Res.prices)) {
      const priceMap = new Map()
      mt5Res.prices.forEach(p => {
        const clean = p.symbol.toUpperCase()
        priceMap.set(clean, p)
      })

      result.overview = result.overview.map(item => {
        const quote = priceMap.get(item.symbol)
        if (quote && quote.bid) {
          return {
            ...item,
            price: quote.bid,
            direction: quote.ask >= quote.bid ? 'up' : 'down'
          }
        }
        return item
      })

      result.extended = result.extended.map(item => {
        const quote = priceMap.get(item.symbol)
        if (quote && quote.bid) {
          return {
            ...item,
            price: quote.bid,
            direction: quote.ask >= quote.bid ? 'up' : 'down'
          }
        }
        return item
      })
    }
  } catch {
    // Backend MT5 might be initializing
  }

  // 2. Fetch live crypto and gold proxy from Binance public API
  try {
    const cryptoSymbols = ['"BTCUSDT"', '"ETHUSDT"', '"SOLUSDT"', '"PAXGUSDT"']
    const url = `${BINANCE_BASE}/ticker/24hr?symbols=[${cryptoSymbols.join(',')}]`

    const response = await fetch(url, { signal: AbortSignal.timeout(3500) })
    if (response.ok) {
      const data = await response.json()

      const btc = data.find(d => d.symbol === 'BTCUSDT')
      const eth = data.find(d => d.symbol === 'ETHUSDT')
      const sol = data.find(d => d.symbol === 'SOLUSDT')
      const gold = data.find(d => d.symbol === 'PAXGUSDT')

      if (btc) {
        const btcPrice = parseFloat(btc.lastPrice)
        const btcChange = parseFloat(btc.priceChangePercent)
        const btcIdx = result.overview.findIndex(p => p.symbol === 'BTCUSD' || p.symbol === 'BTCUSDT')
        if (btcIdx !== -1) {
          result.overview[btcIdx] = {
            ...result.overview[btcIdx],
            price: result.overview[btcIdx].price > 0 ? result.overview[btcIdx].price : btcPrice,
            changePct: btcChange,
            direction: btcChange >= 0 ? 'up' : 'down',
            high: parseFloat(btc.highPrice),
            low: parseFloat(btc.lowPrice),
            volume: `${(parseFloat(btc.volume) / 1000).toFixed(1)}K`
          }
        }
      }

      if (gold) {
        const goldPrice = parseFloat(gold.lastPrice)
        const goldChange = parseFloat(gold.priceChangePercent)
        const goldIdx = result.overview.findIndex(p => p.symbol === 'XAUUSD')
        if (goldIdx !== -1) {
          result.overview[goldIdx] = {
            ...result.overview[goldIdx],
            price: result.overview[goldIdx].price > 0 ? result.overview[goldIdx].price : goldPrice,
            changePct: goldChange,
            direction: goldChange >= 0 ? 'up' : 'down',
            high: parseFloat(gold.highPrice),
            low: parseFloat(gold.lowPrice),
            volume: `${parseFloat(gold.volume).toFixed(0)} oz`
          }
        }
      }

      if (eth) {
        const ethPrice = parseFloat(eth.lastPrice)
        const ethChange = parseFloat(eth.priceChangePercent)
        const ethIdx = result.extended.findIndex(p => p.symbol === 'ETHUSD' || p.symbol === 'ETHUSDT')
        if (ethIdx !== -1) {
          result.extended[ethIdx] = {
            ...result.extended[ethIdx],
            price: result.extended[ethIdx].price > 0 ? result.extended[ethIdx].price : ethPrice,
            changePct: ethChange,
            direction: ethChange >= 0 ? 'up' : 'down'
          }
        }
      }

      if (sol) {
        const solPrice = parseFloat(sol.lastPrice)
        const solChange = parseFloat(sol.priceChangePercent)
        const solIdx = result.extended.findIndex(p => p.symbol === 'SOLUSD' || p.symbol === 'SOLUSDT')
        if (solIdx !== -1) {
          result.extended[solIdx] = {
            ...result.extended[solIdx],
            price: result.extended[solIdx].price > 0 ? result.extended[solIdx].price : solPrice,
            changePct: solChange,
            direction: solChange >= 0 ? 'up' : 'down'
          }
        }
      }
    }
  } catch {
    // Binance public rate-limit fallback
  }

  return result
}
