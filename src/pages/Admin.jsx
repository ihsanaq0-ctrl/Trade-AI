import React, { useState, useEffect } from 'react'
import { Plus, Trash2, ShieldCheck, Clock, AlertCircle } from 'lucide-react'
import api from '../api'
import { useToast } from '../components/Toast'

const S = {
  container: { padding: 24, maxWidth: 1100, margin: '0 auto', fontFamily: 'inherit' },
  header: { marginBottom: 28 },
  title: { fontSize: 24, fontWeight: 700, color: '#e1e4e8', margin: '0 0 4px 0' },
  subtitle: { fontSize: 14, color: '#6b7a8d', margin: 0 },
  card: { background: '#0d1117', border: '1px solid #1e2d3d', borderRadius: 12, padding: 20, marginBottom: 24 },
  cardTitle: { fontSize: 14, fontWeight: 600, color: '#e1e4e8', margin: '0 0 4px 0' },
  cardHint: { fontSize: 12, color: '#6b7a8d', margin: '0 0 16px 0', lineHeight: 1.6 },
  label: { color: '#8b949e', fontSize: 12, fontWeight: 500, marginBottom: 6, display: 'block' },
  input: {
    width: '100%', padding: '10px 14px', background: '#0a0e17',
    border: '1px solid #1e2d3d', borderRadius: 8, color: '#e1e4e8',
    fontSize: 14, outline: 'none', boxSizing: 'border-box'
  },
  textarea: {
    width: '100%', padding: '12px 14px', background: '#0a0e17',
    border: '1px solid #1e2d3d', borderRadius: 8, color: '#e1e4e8',
    fontSize: 13, fontFamily: 'Consolas, Menlo, monospace', lineHeight: 1.6,
    outline: 'none', boxSizing: 'border-box', resize: 'vertical', minHeight: 220
  },
  primaryBtn: {
    padding: '10px 24px', background: '#00d4ff', border: 'none', borderRadius: 8,
    color: '#0a0e17', cursor: 'pointer', fontSize: 14, fontWeight: 600,
    display: 'inline-flex', alignItems: 'center', gap: 8
  },
  dangerBtn: {
    padding: '6px 12px', background: '#ff475722', border: 'none', borderRadius: 6,
    color: '#ff4757', fontSize: 12, cursor: 'pointer', fontWeight: 500,
    display: 'inline-flex', alignItems: 'center', gap: 6
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: {
    textAlign: 'left', color: '#6b7a8d', fontSize: 11, fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: '0.06em',
    padding: '8px 10px', borderBottom: '1px solid #1e2d3d'
  },
  td: { padding: '10px', borderBottom: '1px solid #131a26', color: '#e1e4e8', verticalAlign: 'top' },
  tag: {
    fontSize: 11, padding: '2px 8px', borderRadius: 8, fontWeight: 500,
    display: 'inline-block'
  },
  errorBanner: {
    background: '#ff475711', border: '1px solid #ff475733', borderRadius: 12,
    padding: '14px 18px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 10
  },
  details: { marginTop: 16, border: '1px solid #1e2d3d', borderRadius: 8, padding: '10px 14px' },
  code: {
    background: '#0a0e17', border: '1px solid #1e2d3d', borderRadius: 8,
    padding: 12, fontSize: 12, fontFamily: 'Consolas, Menlo, monospace',
    color: '#8b949e', whiteSpace: 'pre-wrap', lineHeight: 1.6
  }
}

const EXAMPLE_CODE = `from app.services.strategies.base import Signal

class MeanReversionBot:
    """Example custom strategy - analyze() is the contract the engine calls."""
    async def analyze(self, pair, candles, config):
        last = candles[-1]
        if last["close"] < last["open"]:  # red candle -> mean reversion buy
            return Signal(action="buy", pair=pair,
                          lot_size=config.get("lot_size", 0.01),
                          stop_loss=0, take_profit=0,
                          confidence=0.5, reason="custom: mean reversion")
        return None

STRATEGY_CLASS = MeanReversionBot   # optional explicit marker`

export default function Admin({ session }) {
  const [strategies, setStrategies] = useState([])
  const [audit, setAudit] = useState([])
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [saving, setSaving] = useState(false)
  const [removing, setRemoving] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const toast = useToast()

  const headers = { 'Authorization': `Bearer ${session?.access_token}` }

  const load = async () => {
    try {
      const [s, a] = await Promise.all([
        api.get('/api/admin/strategies', { headers }),
        api.get('/api/admin/audit', { headers }),
      ])
      setStrategies(Array.isArray(s) ? s : [])
      setAudit(Array.isArray(a) ? a : [])
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (session?.access_token) load()
  }, [session])

  const handleAdd = async (e) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) { toast.error('Strategy name is required'); return }
    if (!code.trim()) { toast.error('Paste your strategy code first'); return }
    setSaving(true)
    try {
      await api.post('/api/admin/strategies', { name: trimmed, code }, { headers })
      toast.success(`Strategy "${trimmed}" added — card is now on the Bots page`)
      setName('')
      setCode('')
      await load()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async (s) => {
    if (!window.confirm(`Remove strategy "${s.name}"? Its card will disappear from the Bots page.`)) return
    setRemoving(s.id)
    try {
      await api.del(`/api/admin/strategies/${s.id}`, { headers })
      toast.success(`Strategy "${s.name}" removed`)
      await load()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setRemoving(null)
    }
  }

  const custom = strategies.filter(s => s.source === 'custom')
  const builtin = strategies.filter(s => s.source === 'builtin')

  return (
    <div style={S.container}>
      <div style={S.header}>
        <h1 style={S.title}>Strategy Admin</h1>
        <p style={S.subtitle}>Add custom strategies by name and pasted code, or remove existing ones.</p>
      </div>

      {error && (
        <div style={S.errorBanner}>
          <AlertCircle size={18} color="#ff4757" />
          <div style={{ color: '#ff4757', fontSize: 13, fontWeight: 600 }}>Cannot reach backend</div>
          <div style={{ color: '#6b7a8d', fontSize: 12, marginTop: 2 }}>{error}</div>
        </div>
      )}

      {/* Add strategy */}
      <form style={S.card} onSubmit={handleAdd}>
        <h2 style={S.cardTitle}>Add Strategy</h2>
        <p style={S.cardHint}>
          Give the strategy a name and paste its code. A card for it will appear
          automatically on the Bots page. Name must be snake_case (lowercase letters,
          numbers, underscores), e.g. <span style={{ color: '#8b949e' }}>mean_reversion</span>.
        </p>
        <div style={{ marginBottom: 16 }}>
          <label style={S.label}>Strategy Name</label>
          <input
            style={{ ...S.input, maxWidth: 320 }}
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="mean_reversion"
            spellCheck={false}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={S.label}>Strategy Code</label>
          <textarea
            style={S.textarea}
            value={code}
            onChange={e => setCode(e.target.value)}
            placeholder="# Paste your strategy class here"
            spellCheck={false}
          />
        </div>
        <button type="submit" style={S.primaryBtn} disabled={saving}>
          <Plus size={16} />
          {saving ? 'Saving...' : 'Add Strategy'}
        </button>

        <details style={S.details}>
          <summary style={{ color: '#8b949e', fontSize: 12, cursor: 'pointer', fontWeight: 500 }}>
            Code contract & example (what the engine expects)
          </summary>
          <div style={{ marginTop: 10 }}>
            <p style={{ color: '#6b7a8d', fontSize: 12, lineHeight: 1.6, margin: '0 0 10px 0' }}>
              The engine calls <code>analyze(pair, candles, config)</code> every poll cycle.
              Return a <code>Signal</code> from <code>app.services.strategies.base</code>, or <code>None</code>.
              Your code runs as-is (trusted code — no sandbox).
            </p>
            <div style={S.code}>{EXAMPLE_CODE}</div>
          </div>
        </details>
      </form>

      {/* Strategy list */}
      <div style={S.card}>
        <h2 style={S.cardTitle}>Strategies</h2>
        <p style={S.cardHint}>Custom strategies can be removed; built-in strategies are part of the platform.</p>
        {loading ? (
          <p style={{ color: '#6b7a8d', fontSize: 13 }}>Loading...</p>
        ) : strategies.length === 0 ? (
          <p style={{ color: '#6b7a8d', fontSize: 13 }}>No strategies yet. Add one above.</p>
        ) : (
          <table style={S.table}>
            <thead>
              <tr>
                <th style={S.th}>Name</th>
                <th style={S.th}>Title</th>
                <th style={S.th}>Source</th>
                <th style={S.th}>Created</th>
                <th style={S.th}>Action</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map(s => (
                <tr key={s.id || s.name}>
                  <td style={S.td}><code style={{ color: '#e1e4e8' }}>{s.name}</code></td>
                  <td style={S.td}>{s.title}</td>
                  <td style={S.td}>
                    <span style={{
                      ...S.tag,
                      background: s.source === 'builtin' ? '#1e2d3d' : '#00d4ff22',
                      color: s.source === 'builtin' ? '#8b949e' : '#00d4ff'
                    }}>
                      {s.source === 'builtin' ? 'Built-in' : 'Custom'}
                    </span>
                  </td>
                  <td style={{ ...S.td, color: '#6b7a8d' }}>
                    {s.created_at ? new Date(s.created_at).toLocaleString() : '—'}
                  </td>
                  <td style={S.td}>
                    {s.source === 'custom' ? (
                      <button
                        style={S.dangerBtn}
                        onClick={() => handleRemove(s)}
                        disabled={removing === s.id}
                      >
                        <Trash2 size={13} />
                        {removing === s.id ? 'Removing...' : 'Remove'}
                      </button>
                    ) : (
                      <span style={{ color: '#3d4a5c', fontSize: 12 }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p style={{ ...S.cardHint, marginTop: 12, marginBottom: 0 }}>
          {builtin.length} built-in · {custom.length} custom
        </p>
      </div>

      {/* Audit log */}
      <div style={S.card}>
        <h2 style={{ ...S.cardTitle, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Clock size={15} color="#6b7a8d" /> Operation Log
        </h2>
        <p style={S.cardHint}>Every add / remove is recorded with a timestamp.</p>
        {audit.length === 0 ? (
          <p style={{ color: '#6b7a8d', fontSize: 13 }}>No operations recorded yet.</p>
        ) : (
          <table style={S.table}>
            <thead>
              <tr>
                <th style={S.th}>Time</th>
                <th style={S.th}>Action</th>
                <th style={S.th}>Strategy</th>
              </tr>
            </thead>
            <tbody>
              {audit.map(a => (
                <tr key={a.id}>
                  <td style={{ ...S.td, color: '#6b7a8d', whiteSpace: 'nowrap' }}>
                    {a.created_at ? new Date(a.created_at).toLocaleString() : 'â€”'}
                  </td>
                  <td style={S.td}>
                    <span style={{
                      ...S.tag,
                      background: a.action === 'add' ? '#00ff8822' : '#ff475722',
                      color: a.action === 'add' ? '#00ff88' : '#ff4757'
                    }}>
                      {a.action === 'add' ? 'ADD' : 'REMOVE'}
                    </span>
                  </td>
                  <td style={S.td}><code style={{ color: '#e1e4e8' }}>{a.strategy_name}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, color: '#6b7a8d', fontSize: 12 }}>
          <ShieldCheck size={14} /> Admin actions are logged to backend/data/admin_audit.json
        </div>
      </div>
    </div>
  )
}
