import React, { useState } from 'react'
import {
  Brain, Shield, TrendingUp, AlertTriangle, Scale,
  CheckCircle, ArrowUpRight, ArrowDownRight, RefreshCw, X, Play, Zap
} from 'lucide-react'
import api from '../api'
import { useToast } from './Toast'

export default function AIAgentsModal({ isOpen, onClose, onDeployBot }) {
  const [symbol, setSymbol] = useState('XAUUSD')
  const [timeframe, setTimeframe] = useState('H1')
  const [loading, setLoading] = useState(false)
  const [report, setReport] = useState(null)
  const toast = useToast()

  if (!isOpen) return null

  const handleRunDeliberation = async () => {
    setLoading(true)
    try {
      const data = await api.post('/api/ai-agents/deliberate', {
        symbol,
        timeframe,
        candles_count: 100
      })
      setReport(data)
      toast.success(`Multi-agent deliberation completed for ${symbol}`)
    } catch (e) {
      toast.error(`Deliberation failed: ${e?.response?.data?.detail || e.message}`)
    } finally {
      setLoading(false)
    }
  }

  const reports = report?.committee_reports
  const decision = report?.decision || 'HOLD'
  const confidence = Math.round((report?.confidence || 0) * 100)

  const isBuy = decision === 'BUY'
  const isSell = decision === 'SELL'
  const decisionColor = isBuy ? '#10b981' : isSell ? '#ef4444' : '#f59e0b'

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0,0,0,0.85)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: '20px'
    }}>
      <div style={{
        background: '#0d1117',
        border: '1px solid #1e293b',
        borderRadius: '20px',
        width: '100%',
        maxWidth: '960px',
        maxHeight: '90vh',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)',
        overflow: 'hidden'
      }}>
        {/* Header */}
        <div style={{
          padding: '20px 24px',
          borderBottom: '1px solid #1e293b',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: '#0c0f17'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              width: '40px',
              height: '40px',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, #38bdf822, #818cf822)',
              border: '1px solid #38bdf844',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#38bdf8'
            }}>
              <Brain size={22} />
            </div>
            <div>
              <h2 style={{ fontSize: '18px', fontWeight: '800', color: '#f8fafc', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                TradingAgents Multi-Agent Committee
                <span style={{ fontSize: '11px', background: '#38bdf822', color: '#38bdf8', padding: '2px 8px', borderRadius: '6px', fontWeight: '600' }}>
                  TauricResearch v1.0
                </span>
              </h2>
              <p style={{ fontSize: '12px', color: '#64748b', margin: '2px 0 0 0' }}>
                Institutional debate: Technicals, Macro Fundamentals, Sentiment, Bull/Bear duel, and Risk Officer
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: '6px' }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Controls Toolbar */}
        <div style={{
          padding: '16px 24px',
          background: '#111622',
          borderBottom: '1px solid #1e293b',
          display: 'flex',
          gap: '16px',
          alignItems: 'center',
          flexWrap: 'wrap'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '600' }}>Asset:</span>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              style={{
                background: '#0c0e15',
                border: '1px solid #1e293b',
                color: '#ffffff',
                padding: '8px 12px',
                borderRadius: '8px',
                fontSize: '13px',
                fontWeight: '600',
                outline: 'none'
              }}
            >
              <option value="XAUUSD">XAUUSD (Gold)</option>
              <option value="EURUSD">EURUSD</option>
              <option value="GBPUSD">GBPUSD</option>
              <option value="USDJPY">USDJPY</option>
              <option value="BTCUSD">BTCUSD</option>
              <option value="US30">US30 (Dow Jones)</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '12px', color: '#94a3b8', fontWeight: '600' }}>Timeframe:</span>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              style={{
                background: '#0c0e15',
                border: '1px solid #1e293b',
                color: '#ffffff',
                padding: '8px 12px',
                borderRadius: '8px',
                fontSize: '13px',
                fontWeight: '600',
                outline: 'none'
              }}
            >
              <option value="M15">M15 (15 Min)</option>
              <option value="H1">H1 (1 Hour)</option>
              <option value="H4">H4 (4 Hours)</option>
              <option value="D1">D1 (Daily)</option>
            </select>
          </div>

          <button
            onClick={handleRunDeliberation}
            disabled={loading}
            style={{
              marginLeft: 'auto',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: loading ? '#1e293b' : 'linear-gradient(135deg, #38bdf8, #6366f1)',
              border: 'none',
              color: '#ffffff',
              padding: '9px 18px',
              borderRadius: '10px',
              fontSize: '13px',
              fontWeight: '700',
              cursor: loading ? 'not-allowed' : 'pointer',
              boxShadow: '0 4px 14px rgba(56, 189, 248, 0.25)'
            }}
          >
            <RefreshCw size={15} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            <span>{loading ? 'Committee Deliberating...' : 'Start Committee Deliberation'}</span>
          </button>
        </div>

        {/* Content Body */}
        <div style={{ padding: '24px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {!report && !loading && (
            <div style={{
              textAlign: 'center',
              padding: '60px 20px',
              border: '1px dashed #1e293b',
              borderRadius: '16px'
            }}>
              <Brain size={48} color="#38bdf8" style={{ margin: '0 auto 16px', opacity: 0.6 }} />
              <h3 style={{ fontSize: '16px', fontWeight: '700', color: '#f8fafc', marginBottom: '8px' }}>
                No Active Deliberation
              </h3>
              <p style={{ fontSize: '13px', color: '#64748b', maxWidth: '440px', margin: '0 auto 20px' }}>
                Click "Start Committee Deliberation" above to initiate institutional multi-agent analysis for {symbol}.
              </p>
            </div>
          )}

          {report && (
            <>
              {/* Verdict Summary Card */}
              <div style={{
                background: `linear-gradient(135deg, ${decisionColor}15, #111622)`,
                border: `1px solid ${decisionColor}55`,
                borderRadius: '16px',
                padding: '20px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '16px'
              }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                    <span style={{
                      background: decisionColor,
                      color: '#000000',
                      padding: '4px 12px',
                      borderRadius: '8px',
                      fontSize: '14px',
                      fontWeight: '800',
                      letterSpacing: '0.5px'
                    }}>
                      CONSENSUS: {decision}
                    </span>
                    <span style={{ fontSize: '13px', color: '#cbd5e1', fontWeight: '600' }}>
                      Confidence: {confidence}%
                    </span>
                    <span style={{ fontSize: '13px', color: '#94a3b8' }}>
                      R:R {report.risk_reward_ratio}
                    </span>
                  </div>
                  <div style={{ fontSize: '14px', color: '#e2e8f0', fontWeight: '500', maxWidth: '650px' }}>
                    {report.summary}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '11px', color: '#64748b', fontWeight: '600' }}>ESTIMATED ENTRY / SL / TP</div>
                    <div style={{ fontSize: '14px', color: '#f8fafc', fontWeight: '700' }}>
                      ${report.entry_price} · SL ${report.stop_loss} · TP ${report.take_profit}
                    </div>
                  </div>
                  {onDeployBot && decision !== 'HOLD' && (
                    <button
                      onClick={() => onDeployBot({
                        strategy: 'trading_agents',
                        pair: symbol,
                        timeframe: timeframe,
                        lot_size: 0.05,
                        stop_loss: report.stop_loss,
                        take_profit: report.take_profit
                      })}
                      style={{
                        background: '#10b981',
                        border: 'none',
                        color: '#000000',
                        fontWeight: '700',
                        fontSize: '13px',
                        padding: '10px 18px',
                        borderRadius: '10px',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}
                    >
                      <Zap size={15} />
                      Deploy Bot
                    </button>
                  )}
                </div>
              </div>

              {/* Three Specialist Analyst Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px' }}>
                {/* Technical Analyst */}
                <div style={{ background: '#111622', border: '1px solid #1e293b', borderRadius: '14px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                    <span style={{ fontSize: '13px', fontWeight: '700', color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <TrendingUp size={15} /> Technical Analyst
                    </span>
                    <span style={{
                      fontSize: '11px',
                      padding: '2px 8px',
                      borderRadius: '6px',
                      fontWeight: '700',
                      background: reports?.technical_analyst?.bias === 'BULLISH' ? '#10b98122' : '#ef444422',
                      color: reports?.technical_analyst?.bias === 'BULLISH' ? '#10b981' : '#ef4444'
                    }}>
                      {reports?.technical_analyst?.bias || 'NEUTRAL'}
                    </span>
                  </div>
                  <p style={{ fontSize: '12px', color: '#94a3b8', lineHeight: '1.5', margin: 0 }}>
                    {reports?.technical_analyst?.commentary}
                  </p>
                  <div style={{ marginTop: '12px', fontSize: '11px', color: '#64748b', display: 'flex', gap: '10px' }}>
                    <span>RSI: {report.metrics?.rsi}</span>
                    <span>ATR: {report.metrics?.atr}</span>
                    <span>SMA20: {report.metrics?.sma_20}</span>
                  </div>
                </div>

                {/* Fundamental Macro Analyst */}
                <div style={{ background: '#111622', border: '1px solid #1e293b', borderRadius: '14px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                    <span style={{ fontSize: '13px', fontWeight: '700', color: '#a855f7', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Brain size={15} /> Macro & Fundamental
                    </span>
                    <span style={{
                      fontSize: '11px',
                      padding: '2px 8px',
                      borderRadius: '6px',
                      fontWeight: '700',
                      background: '#a855f722',
                      color: '#c084fc'
                    }}>
                      {reports?.fundamental_analyst?.bias || 'NEUTRAL'}
                    </span>
                  </div>
                  <p style={{ fontSize: '12px', color: '#94a3b8', lineHeight: '1.5', margin: 0 }}>
                    {reports?.fundamental_analyst?.commentary}
                  </p>
                </div>

                {/* Sentiment Analyst */}
                <div style={{ background: '#111622', border: '1px solid #1e293b', borderRadius: '14px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                    <span style={{ fontSize: '13px', fontWeight: '700', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Scale size={15} /> Order Flow Sentiment
                    </span>
                    <span style={{
                      fontSize: '11px',
                      padding: '2px 8px',
                      borderRadius: '6px',
                      fontWeight: '700',
                      background: '#f59e0b22',
                      color: '#fbbf24'
                    }}>
                      {reports?.sentiment_analyst?.bias || 'BALANCED'}
                    </span>
                  </div>
                  <p style={{ fontSize: '12px', color: '#94a3b8', lineHeight: '1.5', margin: 0 }}>
                    {reports?.sentiment_analyst?.commentary}
                  </p>
                </div>
              </div>

              {/* The Bull vs Bear Debate Duel */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
                {/* Bull Thesis */}
                <div style={{
                  background: 'rgba(16, 185, 129, 0.05)',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                  borderRadius: '14px',
                  padding: '18px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', color: '#10b981', fontWeight: '700', fontSize: '14px' }}>
                    <ArrowUpRight size={18} /> Lead Bull Researcher Thesis
                  </div>
                  <div style={{ fontSize: '13px', color: '#cbd5e1', fontWeight: '600', marginBottom: '8px' }}>
                    {reports?.bull_researcher?.view}
                  </div>
                  <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '12px', color: '#94a3b8', lineHeight: '1.6' }}>
                    {(reports?.bull_researcher?.catalysts || []).map((cat, i) => (
                      <li key={i}>{cat}</li>
                    ))}
                  </ul>
                  <div style={{ marginTop: '12px', fontSize: '11px', color: '#6ee7b7' }}>
                    <strong>Invalidation:</strong> {reports?.bull_researcher?.invalidation}
                  </div>
                </div>

                {/* Bear Thesis */}
                <div style={{
                  background: 'rgba(239, 68, 68, 0.05)',
                  border: '1px solid rgba(239, 68, 68, 0.25)',
                  borderRadius: '14px',
                  padding: '18px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', color: '#ef4444', fontWeight: '700', fontSize: '14px' }}>
                    <ArrowDownRight size={18} /> Lead Bear Researcher Thesis
                  </div>
                  <div style={{ fontSize: '13px', color: '#cbd5e1', fontWeight: '600', marginBottom: '8px' }}>
                    {reports?.bear_researcher?.view}
                  </div>
                  <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '12px', color: '#94a3b8', lineHeight: '1.6' }}>
                    {(reports?.bear_researcher?.vulnerabilities || []).map((vul, i) => (
                      <li key={i}>{vul}</li>
                    ))}
                  </ul>
                  <div style={{ marginTop: '12px', fontSize: '11px', color: '#fca5a5' }}>
                    <strong>Invalidation:</strong> {reports?.bear_researcher?.invalidation}
                  </div>
                </div>
              </div>

              {/* Risk Officer Card */}
              <div style={{
                background: '#111622',
                border: '1px solid #1e293b',
                borderRadius: '14px',
                padding: '16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '12px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Shield size={20} color="#38bdf8" />
                  <div>
                    <span style={{ fontSize: '13px', fontWeight: '700', color: '#ffffff' }}>
                      Chief Risk Officer Audit
                    </span>
                    <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                      {reports?.risk_manager?.notes}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '16px' }}>
                  <div>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>STATUS</div>
                    <div style={{ fontSize: '13px', fontWeight: '700', color: reports?.risk_manager?.status === 'APPROVED' ? '#10b981' : '#f59e0b' }}>
                      {reports?.risk_manager?.status}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>DRAWDOWN RISK</div>
                    <div style={{ fontSize: '13px', fontWeight: '700', color: '#cbd5e1' }}>
                      {reports?.risk_manager?.max_drawdown_risk}
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
