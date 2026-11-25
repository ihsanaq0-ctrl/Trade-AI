import React from 'react'
import { Play, Square, Settings, TrendingUp, Activity, Shield, Brain, Layers, Crosshair, GitBranch, Bot as BotIcon, Lock, Zap } from 'lucide-react'

const strategyIcons = {
  smart_money: Brain,
  mirror: Activity,
  mmc_mirror: Activity,
  classic: Shield,
  full_confluence: TrendingUp,
  scalp_pyramid: Layers,
  scalp_fvg: Crosshair,
  signal_strength_hedge: GitBranch,
  nyao_scalper: Activity,
  trading_agents: Brain,
  ai_committee: Brain,
  pipstep_reversal: Zap
}

const strategyColors = {
  smart_money: '#7c3aed',
  mirror: '#00d4ff',
  mmc_mirror: '#00d4ff',
  classic: '#00ff88',
  full_confluence: '#f59e0b',
  scalp_pyramid: '#ff6b35',
  scalp_fvg: '#ff00ff',
  signal_strength_hedge: '#ffa94d',
  nyao_scalper: '#38ef7d',
  trading_agents: '#38bdf8',
  ai_committee: '#38bdf8',
  pipstep_reversal: '#00d4ff'
}

const strategyNames = {
  smart_money: 'SMC',
  mirror: 'MMC',
  mmc_mirror: 'MMC Mirror',
  classic: 'Classic Mode',
  full_confluence: 'Full Confluence',
  scalp_pyramid: 'Scalp Pyramid',
  scalp_fvg: 'Scalp (FVG)',
  signal_strength_hedge: 'Signal Strength Hedge',
  nyao_scalper: 'Nyao Trade Manager',
  trading_agents: 'TradingAgents AI',
  ai_committee: 'AI Multi-Agent Desk',
  pipstep_reversal: 'PipStep Reversal EA'
}

const riskLevels = {
  smart_money: { label: 'Medium', color: '#f59e0b' },
  mirror: { label: 'Medium', color: '#f59e0b' },
  mmc_mirror: { label: 'Medium', color: '#f59e0b' },
  classic: { label: 'Low', color: '#00ff88' },
  full_confluence: { label: 'Low', color: '#00ff88' },
  scalp_pyramid: { label: 'High', color: '#ff6b35' },
  scalp_fvg: { label: 'High', color: '#ff00ff' },
  signal_strength_hedge: { label: 'High', color: '#ffa94d' },
  nyao_scalper: { label: 'Medium', color: '#38ef7d' },
  trading_agents: { label: 'Adaptive', color: '#38bdf8' },
  ai_committee: { label: 'Adaptive', color: '#38bdf8' },
  pipstep_reversal: { label: 'Medium', color: '#00d4ff' }
}

export default function BotCard({
  strategy,
  title,
  description,
  risk,
  color,
  userPlan = 'free',
  isRunning,
  onStart,
  onStop,
  onConfigure,
  onUpgrade
}) {
  const Icon = strategyIcons[strategy] || BotIcon
  const accent = color || strategyColors[strategy] || '#8b949e'
  const name = title || strategyNames[strategy] ||
    (typeof strategy === 'string' ? strategy.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : 'Strategy')
  const riskInfo = risk ? { label: risk, color: accent } :
    (riskLevels[strategy] || { label: 'Custom', color: accent })

  const plan = (userPlan || 'free').toLowerCase()
  const isElite = ['trading_agents', 'signal_strength_hedge', 'ai_committee'].includes(strategy)
  const isPro = strategy === 'pipstep_reversal'
  const isProLocked = isPro && plan === 'free'
  const isEliteLocked = isElite && plan !== 'elite'

  const tierInfo = isPro
    ? {
        label: isProLocked ? 'PRO · UPGRADE →' : 'PRO UNLOCKED',
        color: '#00d4ff',
        bg: 'rgba(0, 212, 255, 0.12)',
        border: 'rgba(0, 212, 255, 0.35)'
      }
    : isElite
    ? {
        label: 'ELITE (SOON)',
        color: '#f59e0b',
        bg: 'rgba(245, 158, 11, 0.12)',
        border: 'rgba(245, 158, 11, 0.35)'
      }
    : {
        label: 'FREE TIER',
        color: '#10b981',
        bg: 'rgba(16, 185, 129, 0.12)',
        border: 'rgba(16, 185, 129, 0.3)'
      }

  const styles = {
    card: {
      background: '#0d1117',
      border: `1px solid ${isRunning ? accent : (isProLocked ? 'rgba(0, 212, 255, 0.25)' : '#1e2d3d')}`,
      borderRadius: 16,
      padding: 20,
      width: '100%',
      boxSizing: 'border-box',
      display: 'flex',
      flexDirection: 'column',
      gap: 12,
      transition: 'border-color 0.3s, box-shadow 0.3s',
      boxShadow: isRunning ? `0 0 20px ${accent}22` : 'none',
      cursor: 'pointer'
    },
    header: { display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'space-between' },
    iconBox: {
      width: 40, height: 40, borderRadius: 12,
      background: `${accent}22`, display: 'flex',
      alignItems: 'center', justifyContent: 'center',
      flexShrink: 0
    },
    name: { color: '#e1e4e8', fontSize: 14, fontWeight: 600, flex: 1 },
    riskBadge: {
      fontSize: 11, color: riskInfo.color, background: `${riskInfo.color}22`,
      padding: '2px 8px', borderRadius: 8, fontWeight: 500, whiteSpace: 'nowrap'
    },
    statusDot: {
      width: 8, height: 8, borderRadius: '50%',
      background: isRunning ? '#00ff88' : (isProLocked ? '#00d4ff' : isEliteLocked ? '#f59e0b' : '#6b7a8d'),
      display: 'inline-block', marginRight: 6
    },
    statusText: {
      fontSize: 12,
      color: isRunning ? '#00ff88' : (isProLocked ? '#00d4ff' : isEliteLocked ? '#f59e0b' : '#6b7a8d')
    },
    actions: { display: 'flex', gap: 8, marginTop: 'auto' },
    btn: {
      flex: 1, padding: '8px 12px', border: 'none', borderRadius: 8,
      fontSize: 12, fontWeight: 600, cursor: 'pointer',
      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6
    },
    startBtn: isRunning
      ? { background: '#ff475722', color: '#ff4757' }
      : isProLocked
      ? { background: 'linear-gradient(135deg, rgba(0, 212, 255, 0.22), rgba(59, 91, 245, 0.22))', color: '#00d4ff', border: '1px solid rgba(0, 212, 255, 0.35)' }
      : isEliteLocked
      ? { background: 'rgba(245, 158, 11, 0.14)', color: '#f59e0b' }
      : { background: '#00ff8822', color: '#00ff88' },
    configBtn: { background: '#1e2d3d', color: '#8b949e' }
  }

  const handleCardClick = () => {
    if (isProLocked && onUpgrade) {
      onUpgrade('pro')
    } else if (isEliteLocked && onUpgrade) {
      onUpgrade('elite')
    } else {
      onConfigure()
    }
  }

  return (
    <div style={styles.card} onClick={handleCardClick}>
      <div style={styles.header}>
        <div style={styles.iconBox}>
          <Icon size={20} color={accent} />
        </div>
        <div style={styles.name}>{name}</div>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <button
            type="button"
            onClick={e => {
              e.stopPropagation()
              if (isProLocked && onUpgrade) onUpgrade('pro')
              else if (isElite && onUpgrade) onUpgrade('elite')
            }}
            style={{
              fontSize: '10px',
              fontWeight: '700',
              letterSpacing: '0.04em',
              color: tierInfo.color,
              background: tierInfo.bg,
              border: `1px solid ${tierInfo.border}`,
              padding: '2px 7px',
              borderRadius: '6px',
              whiteSpace: 'nowrap',
              cursor: (isProLocked || isElite) ? 'pointer' : 'default'
            }}
            title={isProLocked ? 'Click to upgrade to Pro' : isElite ? 'View Elite Tier details' : 'Included in Free Tier'}
          >
            {tierInfo.label}
          </button>
          <div style={styles.riskBadge}>{riskInfo.label}</div>
        </div>
      </div>

      {description && (
        <div style={{ fontSize: 12, color: '#8b949e', marginTop: -4, marginBottom: 4, lineHeight: 1.4 }}>
          {description}
        </div>
      )}

      <div>
        <span style={styles.statusDot}></span>
        <span style={styles.statusText}>
          {isRunning
            ? 'Running'
            : isProLocked
            ? 'Locked (Requires Pro Plan)'
            : isEliteLocked
            ? 'Locked (Elite — Coming Soon)'
            : 'Stopped'}
        </span>
      </div>

      <div style={styles.actions}>
        <button
          style={{ ...styles.btn, ...styles.startBtn }}
          onClick={e => {
            e.stopPropagation()
            if (isRunning) onStop()
            else if (isProLocked && onUpgrade) onUpgrade('pro')
            else if (isEliteLocked && onUpgrade) onUpgrade('elite')
            else onStart()
          }}
        >
          {isRunning ? <Square size={14} /> : (isProLocked || isEliteLocked) ? <Lock size={14} /> : <Play size={14} />}
          {isRunning ? 'Stop' : isProLocked ? 'Buy Pro ($29)' : isEliteLocked ? 'Elite Soon' : 'Start'}
        </button>
        <button
          style={{ ...styles.btn, ...styles.configBtn }}
          onClick={e => {
            e.stopPropagation()
            if (isProLocked && onUpgrade) onUpgrade('pro')
            else if (isEliteLocked && onUpgrade) onUpgrade('elite')
            else onConfigure()
          }}
        >
          <Settings size={14} />
          {isProLocked || isEliteLocked ? 'Plans' : 'Config'}
        </button>
      </div>
    </div>
  )
}
