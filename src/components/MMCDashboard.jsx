import React, { useState, useEffect } from 'react'
import api from '../api'

export default function MMCDashboard({ session }) {
  const [trades, setTrades] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!session?.access_token) return
    const fetchTrades = async () => {
      try {
        const res = await api.get('/api/trades?strategy=mmc_mirror&status=closed', {
          headers: { 'Authorization': `Bearer ${session.access_token}` }
        })
        setTrades(res.trades || [])
      } catch (e) {
        console.error("Failed to fetch MMC trades", e)
      } finally {
        setLoading(false)
      }
    }
    fetchTrades()
    const intv = setInterval(fetchTrades, 30000)
    return () => clearInterval(intv)
  }, [session])

  const n = trades.length
  const wins = trades.filter(t => t.profit > 0).length
  const wr = n > 0 ? (wins / n) * 100 : 0

  const getR = (t) => {
    if (!t.open_price || !t.stop_loss || !t.close_price) return 0
    const riskDiff = Math.abs(t.open_price - t.stop_loss)
    if (riskDiff === 0) return 0
    const profitDiff = t.direction === 'buy' ? t.close_price - t.open_price : t.open_price - t.close_price
    return profitDiff / riskDiff
  }

  const rValues = trades.map(getR)
  const totalR = rValues.reduce((sum, r) => sum + r, 0)
  const meanR = n > 0 ? totalR / n : 0

  let tStat = 0
  if (n > 1) {
    const variance = rValues.reduce((sum, r) => sum + Math.pow(r - meanR, 2), 0) / (n - 1)
    const stdDev = Math.sqrt(variance)
    if (stdDev > 0) tStat = meanR / (stdDev / Math.sqrt(n))
  }

  const styles = {
    card: { background: '#0d1117', border: '1px solid #1e2d3d', borderRadius: 16, padding: 20, marginBottom: 28, width: '100%', boxSizing: 'border-box' },
    title: { color: '#e1e4e8', fontSize: 18, fontWeight: 600, margin: '0 0 16px 0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 },
    grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 16 },
    statBox: { background: '#161b22', padding: 16, borderRadius: 12 },
    label: { color: '#8b949e', fontSize: 12, marginBottom: 4 },
    val: { color: '#e1e4e8', fontSize: 20, fontWeight: 700 },
    alertRed: { background: '#ff475722', color: '#ff4757', padding: '12px 16px', borderRadius: 8, marginTop: 16, fontWeight: 600 },
    alertGreen: { background: '#00ff8822', color: '#00ff88', padding: '12px 16px', borderRadius: 8, marginTop: 16, fontWeight: 600 },
    note: { color: '#8b949e', fontSize: 11, marginTop: 8 }
  }

  return (
    <div style={styles.card}>
      <div style={styles.title}>
        <span>MMC Strategy Cumulative Dashboard</span>
        {loading && <span style={{ fontSize: 11, color: '#64748b', fontWeight: 400 }}>Syncing...</span>}
      </div>
      <div style={styles.grid}>
        <div style={styles.statBox}>
          <div style={styles.label}>Trades</div>
          <div style={styles.val}>{n}</div>
        </div>
        <div style={styles.statBox}>
          <div style={styles.label}>Win Rate</div>
          <div style={{ ...styles.val, color: wr >= 50 ? '#00ff88' : '#ff4757' }}>{wr.toFixed(1)}%</div>
        </div>
        <div style={styles.statBox}>
          <div style={styles.label}>Total Net R</div>
          <div style={{ ...styles.val, color: totalR >= 0 ? '#00ff88' : '#ff4757' }}>{totalR > 0 ? '+' : ''}{totalR.toFixed(2)}R</div>
        </div>
        <div style={styles.statBox}>
          <div style={styles.label}>Expectancy</div>
          <div style={styles.val}>{meanR > 0 ? '+' : ''}{meanR.toFixed(3)}R</div>
        </div>
        <div style={styles.statBox}>
          <div style={styles.label}>t-Statistic</div>
          <div style={styles.val}>{tStat.toFixed(2)}</div>
        </div>
      </div>
      <div style={styles.note}>* t-statistic below 2.0 = not yet statistically proven</div>

      {n >= 20 && (wr < 45 || meanR < -0.05) && (
        <div style={styles.alertRed}>⚠ KILL CRITERIA HIT — STOP THIS BOT</div>
      )}
      {n >= 20 && wr >= 50 && meanR > 0 && (
        <div style={styles.alertGreen}>✓ Eligible for live (small size)</div>
      )}
    </div>
  )
}
