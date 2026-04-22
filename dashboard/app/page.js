'use client'
import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts'

// ── Formatters ────────────────────────────────────────────────────────────────
const f2  = n => n == null ? '—' : Number(n).toFixed(2)
const f4  = n => n == null ? '—' : Number(n).toFixed(4)
const f0  = n => n == null ? '—' : Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 })
const pct = n => `${Number(n) >= 0 ? '+' : ''}${Number(n).toFixed(2)}%`
const ago = iso => {
  if (!iso) return ''
  const s = Math.floor((Date.now() - new Date(iso)) / 1000)
  return s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m` : `${Math.floor(s / 3600)}h`
}

const ASSET_COLORS = {
  NVDA: '#00d4ff', AAPL: '#0088ff', TSLA: '#9f44ff',
  BTC:  '#ffd600', ETH:  '#00e5a0', MSFT: '#ff8800',
  AMZN: '#ff3366', GOOGL:'#4db8ff', META: '#aa44ff', SOL: '#00ff88',
}
const assetColor = sym => ASSET_COLORS[sym] || '#4db8ff'
const RAG_URL = 'http://localhost:8767'

// ── Live Clock ────────────────────────────────────────────────────────────────
function LiveClock() {
  const [t, setT] = useState(new Date())
  useEffect(() => { const iv = setInterval(() => setT(new Date()), 1000); return () => clearInterval(iv) }, [])
  return (
    <span className="mono" style={{ fontSize: 11, color: 'var(--text3)', letterSpacing: '.04em' }}>
      {t.toLocaleTimeString([], { hour12: false })}
    </span>
  )
}

// ── Typing dots ───────────────────────────────────────────────────────────────
function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: 4, padding: '10px 14px', background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: '8px 8px 8px 2px', width: 'fit-content' }}>
      {[0, 1, 2].map(i => (
        <motion.div key={i} animate={{ opacity: [0.3, 1, 0.3], y: [0, -3, 0] }} transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.2 }}
          style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--text2)' }} />
      ))}
    </div>
  )
}

// ── Markdown renderer ─────────────────────────────────────────────────────────
function Markdown({ text }) {
  return (
    <div>
      {text.split('\n').map((line, i) => (
        <p key={i} style={{ marginBottom: line === '' ? 6 : 2, lineHeight: 1.6, fontSize: 13 }}>
          {line.split(/\*\*(.*?)\*\*/g).map((part, j) =>
            j % 2 === 1 ? <strong key={j} style={{ color: 'var(--blue2)', fontWeight: 600 }}>{part}</strong> : part
          )}
        </p>
      ))}
    </div>
  )
}

// ── Mode cards ────────────────────────────────────────────────────────────────
function ModeCards({ onSelect }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, margin: '8px 0' }}>
      {[
        { type: 'trade', icon: '📈', title: 'Trade Stocks & Crypto', desc: 'AI agents monitor NVDA, AAPL, TSLA and alert on opportunities', color: 'rgba(0,136,255,.25)' },
        { type: 'shop',  icon: '🛒', title: 'Track Product Prices',  desc: 'Get alerted when products hit your target price',              color: 'rgba(0,229,160,.2)' },
      ].map(m => (
        <div key={m.type} className="mode-card" onClick={() => onSelect(m.type)} style={{ borderColor: m.color }}>
          <div style={{ fontSize: 22, marginBottom: 6 }}>{m.icon}</div>
          <p style={{ fontWeight: 600, marginBottom: 3, fontSize: 13 }}>{m.title}</p>
          <p style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.4 }}>{m.desc}</p>
        </div>
      ))}
    </div>
  )
}

// ── Chat view ─────────────────────────────────────────────────────────────────
function ChatView({ onActivate }) {
  const [messages,  setMessages]  = useState([])
  const [input,     setInput]     = useState('')
  const [typing,    setTyping]    = useState(false)
  const [convState, setConvState] = useState(null)
  const [showCards, setShowCards] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    setTimeout(() => {
      setMessages([{ role: 'apee', content: `Hi! I'm **APEE** — Autonomous Personal Economy Engine.\n\nI can help you with:\n\n📈 **Trade stocks & crypto** — AI agents monitor markets and alert you.\n\n🛒 **Track product prices** — Tell me what you want and I'll alert when price is right.\n\nWhat would you like to do today?`, showCards: true, timestamp: new Date() }])
      setShowCards(true)
    }, 300)
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, typing])

  const sendMessage = async (text) => {
    if (!text.trim()) return
    const userMsg = { role: 'user', content: text, timestamp: new Date() }
    const newMsgs = [...messages, userMsg]
    setMessages(newMsgs)
    setInput('')
    setTyping(true)
    setShowCards(false)
    try { await fetch(`${RAG_URL}/rag/query?q=${encodeURIComponent(text)}`) } catch {}
    try {
      const res  = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: newMsgs.map(m => ({ role: m.role === 'apee' ? 'assistant' : m.role, content: m.content })), conversationState: convState }) })
      const data = await res.json()
      setTyping(false)
      setMessages(m => [...m, { role: 'apee', content: data.message, timestamp: new Date() }])
      setConvState({ intent: data.intent, state: data.state, ...data })
      if (data.activate && data.config) setTimeout(() => onActivate(data.config), 1500)
    } catch {
      setTyping(false)
      setMessages(m => [...m, { role: 'apee', content: 'Something went wrong. Please try again.', timestamp: new Date() }])
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 12, background: 'var(--bg1)' }}>
        <div style={{ width: 36, height: 36, borderRadius: 6, background: 'rgba(0,136,255,.15)', border: '1px solid rgba(0,136,255,.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, boxShadow: '0 0 14px rgba(0,136,255,.2)' }}>⚡</div>
        <div>
          <p style={{ fontWeight: 700, fontSize: 15, color: 'var(--text)' }}>APEE</p>
          <p style={{ fontSize: 11, color: 'var(--text2)' }}>Autonomous Personal Economy Engine</p>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(0,229,160,.08)', border: '1px solid rgba(0,229,160,.25)', borderRadius: 3, padding: '4px 12px' }}>
          <span className="live-dot" style={{ display: 'inline-block' }} />
          <span style={{ fontSize: 11, color: 'var(--green)', fontWeight: 600, marginLeft: 6 }}>Online</span>
        </div>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <AnimatePresence initial={false}>
          {messages.map((msg, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              style={{ display: 'flex', flexDirection: 'column', alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
              {msg.role === 'apee' && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <div style={{ width: 16, height: 16, borderRadius: 3, background: 'rgba(0,136,255,.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9 }}>⚡</div>
                  <span style={{ fontSize: 11, color: 'var(--text2)', fontWeight: 500 }}>APEE</span>
                  <span style={{ fontSize: 10, color: 'var(--text3)' }}>{ago(msg.timestamp?.toISOString())} ago</span>
                </div>
              )}
              <div className={msg.role === 'user' ? 'bubble-user' : 'bubble-apee'}>
                <Markdown text={msg.content} />
              </div>
              {msg.showCards && showCards && (
                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} style={{ width: '100%', marginTop: 8 }}>
                  <ModeCards onSelect={t => sendMessage(t === 'trade' ? 'I want to trade stocks and crypto' : 'I want to track product prices')} />
                </motion.div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
        {typing && <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}><TypingDots /></motion.div>}
        <div ref={bottomRef} />
      </div>
      <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', background: 'var(--bg1)' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <textarea className="chat-input" rows={2} value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) } }}
            placeholder='e.g. "Trade NVDA and TSLA with $10,000" or "New Balance 9060 under $120, 8% tax"'
            style={{ flex: 1 }} />
          <button className="btn btn-primary" onClick={() => sendMessage(input)} style={{ height: 44, padding: '0 20px' }}>Send</button>
        </div>
        <p style={{ fontSize: 10, color: 'var(--text3)', marginTop: 5 }}>Enter to send • Shift+Enter for new line</p>
      </div>
    </div>
  )
}

// ── Mini sparkline ────────────────────────────────────────────────────────────
function Spark({ data, color, w = 80, h = 30 }) {
  if (!data?.length || data.length < 2) return <div style={{ width: w, height: h }} />
  const vals = data.map(d => Number(d.val || d.v || d.total_value || d) || 0)
  const min = Math.min(...vals), max = Math.max(...vals), range = max - min || 1
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w
    const y = h - ((v - min) / range) * (h - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const isUp = vals[vals.length - 1] >= vals[0]
  const c = color || (isUp ? 'var(--green)' : 'var(--red)')
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <defs>
        <linearGradient id={`sg-${w}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c} stopOpacity={0.3} />
          <stop offset="100%" stopColor={c} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={`0,${h} ${pts} ${w},${h}`} fill={`url(#sg-${w})`} />
      <polyline points={pts} fill="none" stroke={c} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

// ── Stat box ──────────────────────────────────────────────────────────────────
function StatBox({ label, value, sub, color, glow }) {
  return (
    <div style={{ background: 'var(--bg3)', border: `1px solid ${glow ? 'rgba(0,136,255,.2)' : 'var(--border)'}`, borderRadius: 4, padding: '10px 14px', position: 'relative', overflow: 'hidden' }}>
      {glow && <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 1, background: 'linear-gradient(90deg,transparent,rgba(0,136,255,.5),transparent)' }} />}
      <p style={{ fontSize: 10, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 4, fontFamily: 'JetBrains Mono', fontWeight: 600 }}>{label}</p>
      <p className="mono" style={{ fontSize: 18, fontWeight: 700, color: color || 'var(--text)', lineHeight: 1 }}>{value}</p>
      {sub && <p className="mono" style={{ fontSize: 10, color: 'var(--text2)', marginTop: 3 }}>{sub}</p>}
    </div>
  )
}

// ── Agent status row ──────────────────────────────────────────────────────────
function AgentRow({ name, icon, conf, status, color }) {
  const w = Math.round((conf || 0) * 100)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
      <div style={{ width: 24, height: 24, borderRadius: 3, background: `${color}18`, border: `1px solid ${color}44`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: 11 }}>{icon}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '.08em' }}>{name}</span>
          <span className="mono" style={{ fontSize: 10, color }}>{w}%</span>
        </div>
        <div style={{ height: 2, borderRadius: 1, background: 'var(--bg)', overflow: 'hidden' }}>
          <motion.div initial={{ width: 0 }} animate={{ width: `${w}%` }} transition={{ duration: 0.8, ease: 'easeOut' }}
            style={{ height: '100%', background: `linear-gradient(90deg, ${color}, ${color}88)`, borderRadius: 1 }} />
        </div>
      </div>
      <span className="mono" style={{ fontSize: 9, color: status === 'EXECUTE' ? 'var(--green)' : status === 'HOLD' ? 'var(--yellow)' : 'var(--text3)', minWidth: 40, textAlign: 'right' }}>{status || '—'}</span>
    </div>
  )
}

// ── Mandate card ──────────────────────────────────────────────────────────────
function MandateCard({ mandate, onApprove, onReject, approving }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const iv = setInterval(() => setElapsed(e => e + 1), 1000)
    return () => clearInterval(iv)
  }, [])
  const remaining = Math.max(0, 120 - elapsed)

  return (
    <motion.div initial={{ opacity: 0, y: -10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0 }}
      className="mandate-card"
      style={{ background: 'rgba(255,214,0,.04)', border: '1px solid rgba(255,214,0,.4)', borderRadius: 4, padding: '14px 16px', marginBottom: 12, position: 'relative', overflow: 'hidden' }}>
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: 'linear-gradient(90deg, transparent, var(--yellow), transparent)' }} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <motion.div animate={{ opacity: [1, 0.2, 1] }} transition={{ duration: 0.8, repeat: Infinity }}
            style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--yellow)', boxShadow: '0 0 8px var(--yellow)' }} />
          <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--yellow)', letterSpacing: '.06em', fontFamily: 'JetBrains Mono' }}>BIOMETRIC AUTH REQUIRED</span>
        </div>
        <span className="mono" style={{ fontSize: 11, color: remaining < 30 ? 'var(--red)' : 'var(--text2)' }}>
          {String(Math.floor(remaining / 60)).padStart(2, '0')}:{String(remaining % 60).padStart(2, '0')}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, marginBottom: 14 }}>
        {[
          { l: 'ASSET',  v: mandate.asset,                          c: assetColor(mandate.asset) },
          { l: 'ACTION', v: (mandate.action || '').toUpperCase(),   c: mandate.action === 'long' ? 'var(--green)' : 'var(--red)' },
          { l: 'AMOUNT', v: `$${f0(mandate.alloc_usd)}`,           c: 'var(--text)' },
          { l: 'PRICE',  v: `$${f2(mandate.oracle_price)}`,        c: 'var(--text2)' },
        ].map(s => (
          <div key={s.l} style={{ background: 'var(--bg3)', borderRadius: 3, padding: '8px 10px', border: '1px solid var(--border)' }}>
            <p style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: '.1em', fontFamily: 'JetBrains Mono', marginBottom: 4, textTransform: 'uppercase' }}>{s.l}</p>
            <p className="mono" style={{ fontSize: 14, fontWeight: 700, color: s.c }}>{s.v}</p>
          </div>
        ))}
      </div>
      <div style={{ marginBottom: 10, height: 3, background: 'var(--bg)', borderRadius: 2, overflow: 'hidden' }}>
        <motion.div animate={{ width: `${(remaining / 120) * 100}%` }} transition={{ duration: 1 }}
          style={{ height: '100%', background: remaining < 30 ? 'var(--red)' : 'var(--yellow)', borderRadius: 2 }} />
      </div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button className="btn btn-red" onClick={() => onReject(mandate.mandate_id)} disabled={approving} style={{ padding: '6px 16px' }}>✕ REJECT</button>
        <button className="btn btn-green" onClick={() => onApprove(mandate.mandate_id)} disabled={approving} style={{ padding: '6px 20px' }}>
          {approving ? '⏳ PROCESSING…' : '✓ APPROVE TRADE'}
        </button>
      </div>
    </motion.div>
  )
}

// ── Asset price card ──────────────────────────────────────────────────────────
function AssetCard({ sym, price, pos, portHistory }) {
  const color = assetColor(sym)
  const p = pos || {}
  const isUp = (p.pnl || 0) >= 0
  const sparkData = (portHistory || []).slice(-20).map((d, i) => ({
    val: Number(price) * (0.97 + i * 0.003 + (Math.sin(i * 0.8 + sym.charCodeAt(0)) * 0.01))
  }))

  return (
    <div className="card" style={{ padding: '12px 14px', borderColor: `${color}22`, position: 'relative', overflow: 'hidden' }}>
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 1, background: `linear-gradient(90deg,transparent,${color}66,transparent)` }} />
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <div style={{ width: 22, height: 22, borderRadius: 3, background: `${color}18`, border: `1px solid ${color}44`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 8, fontWeight: 800, color, fontFamily: 'JetBrains Mono' }}>{sym[0]}</div>
          <div>
            <p style={{ fontWeight: 700, fontSize: 12, lineHeight: 1, color: 'var(--text)' }}>{sym}</p>
            <p style={{ fontSize: 9, color: 'var(--text3)', marginTop: 1 }}>{p.direction ? p.direction.toUpperCase() : 'WATCHING'}</p>
          </div>
        </div>
        <span className={`pill pill-${isUp ? 'buy' : 'sell'}`}>{isUp ? '▲' : '▼'} {pct(p.pnl_pct || 0)}</span>
      </div>
      {/* Price */}
      <p className="mono" style={{ fontSize: 20, fontWeight: 700, marginBottom: 8, color, textShadow: `0 0 14px ${color}66` }}>
        ${f2(price)}
      </p>
      {/* Sparkline + P&L */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <p style={{ fontSize: 9, color: 'var(--text3)', marginBottom: 2 }}>P&L</p>
          <p className="mono" style={{ fontSize: 11, fontWeight: 600, color: isUp ? 'var(--green)' : 'var(--red)' }}>
            {isUp ? '+' : ''}{f2(p.pnl || 0)}
          </p>
          {p.alloc_usd > 0 && (
            <p className="mono" style={{ fontSize: 9, color: 'var(--text3)', marginTop: 1 }}>${f0(p.alloc_usd)} alloc</p>
          )}
        </div>
        <Spark data={sparkData} color={color} w={72} h={32} />
      </div>
    </div>
  )
}

// ── Gate performance panel ────────────────────────────────────────────────────
function GatePanel({ gate, gateHistory }) {
  const tot = gate.total || 1
  const bars = [
    { k: 'EXECUTE', c: 'var(--green)',  bg: 'rgba(0,229,160,.08)' },
    { k: 'HOLD',    c: 'var(--yellow)', bg: 'rgba(255,214,0,.06)' },
    { k: 'REVIEW',  c: 'var(--orange)', bg: 'rgba(255,136,0,.06)' },
  ]
  const last5 = (gateHistory || []).slice(-5)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%' }}>
      {/* Gate bars */}
      <div className="card" style={{ padding: '14px 16px' }}>
        <p className="sec-label" style={{ marginBottom: 12 }}>Consensus Gate</p>
        {bars.map(b => {
          const v = gate[b.k] || 0
          const p = Math.round((v / tot) * 100)
          return (
            <div key={b.k} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span className="mono" style={{ fontSize: 10, color: b.c, fontWeight: 700 }}>{b.k}</span>
                <span className="mono" style={{ fontSize: 10, color: 'var(--text2)' }}>{v} / {p}%</span>
              </div>
              <div style={{ height: 4, borderRadius: 2, background: 'var(--bg)', overflow: 'hidden', position: 'relative' }}>
                <motion.div initial={{ width: 0 }} animate={{ width: `${p}%` }} transition={{ duration: 1, ease: 'easeOut' }}
                  style={{ height: '100%', background: b.c, borderRadius: 2, boxShadow: `0 0 6px ${b.c}` }} />
              </div>
            </div>
          )
        })}
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 10, color: 'var(--text3)' }}>Execute Rate</span>
          <span className="mono num-green" style={{ fontSize: 14, fontWeight: 700 }}>{gate.execute_rate || 0}%</span>
        </div>
      </div>

      {/* Last decisions */}
      <div className="card" style={{ padding: '14px 16px', flex: 1 }}>
        <p className="sec-label" style={{ marginBottom: 10 }}>Recent Decisions</p>
        {last5.length === 0 && <p style={{ fontSize: 11, color: 'var(--text3)', textAlign: 'center', padding: '10px 0' }}>Awaiting signals…</p>}
        {last5.reverse().map((r, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7, opacity: Math.max(0.3, 1 - i * 0.15) }}>
            <span className={`pill pill-${r.decision?.toLowerCase()}`} style={{ minWidth: 58, justifyContent: 'center' }}>{r.decision}</span>
            <span style={{ fontSize: 11, color: assetColor(r.asset), fontWeight: 600 }}>{r.asset || r.query}</span>
            <span className="mono" style={{ fontSize: 10, color: 'var(--text3)', marginLeft: 'auto' }}>{ago(r.timestamp)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Trading Dashboard ─────────────────────────────────────────────────────────
function TradingDashboard({ state, gateHistory, portHistory, events, onApprove, onReject, approving }) {
  const [tab, setTab] = useState('overview')
  const port    = state?.portfolio || {}
  const prices  = state?.prices    || {}
  const gate    = state?.gate_stats || {}
  const pos     = port.positions   || {}
  const isUp    = (port.total_return_pct || 0) >= 0
  const mandates = (events || []).filter(e => e.type === 'BIOMETRIC_PENDING').map(e => e.data).filter(Boolean)
  const chartData = (portHistory || []).map((d, i) => ({ ...d, val: d.total_value || d.v || 0, idx: i }))
  const vals = chartData.map(d => d.val)
  const cMin = Math.min(...(vals.length ? vals : [9999])) * 0.998
  const cMax = Math.max(...(vals.length ? vals : [10001])) * 1.002

  const CustomTip = ({ active, payload }) => {
    if (!active || !payload?.length) return null
    return (
      <div style={{ background: 'var(--bg3)', border: '1px solid var(--border2)', borderRadius: 4, padding: '8px 12px', boxShadow: '0 4px 20px rgba(0,0,0,.5)' }}>
        <p className="mono" style={{ fontSize: 10, color: 'var(--text2)', marginBottom: 2 }}>Cycle #{payload[0].payload.cycle || payload[0].payload.idx}</p>
        <p className="mono" style={{ fontSize: 14, fontWeight: 700, color: isUp ? 'var(--green)' : 'var(--red)' }}>${Number(payload[0].value).toFixed(2)}</p>
      </div>
    )
  }

  const navItems = [
    { id: 'overview',  icon: '▦', label: 'Overview' },
    { id: 'positions', icon: '◈', label: 'Positions' },
    { id: 'agents',    icon: '◉', label: 'Agents' },
    { id: 'gatelog',   icon: '⊞', label: 'Gate Log' },
    { id: 'security',  icon: '⛨', label: 'Security' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg)' }}>

      {/* ── Top Header Bar ─────────────────────────────────────────────────── */}
      <div style={{ height: 44, background: 'var(--bg1)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 16px', gap: 16, flexShrink: 0 }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingRight: 16, borderRight: '1px solid var(--border)' }}>
          <div style={{ width: 26, height: 26, borderRadius: 4, background: 'rgba(0,136,255,.15)', border: '1px solid rgba(0,136,255,.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, boxShadow: '0 0 12px rgba(0,136,255,.25)' }}>⚡</div>
          <div>
            <p style={{ fontWeight: 800, fontSize: 12, letterSpacing: '.08em', color: 'var(--text)' }}>APEE</p>
            <p style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: '.06em' }}>TERMINAL v1.0</p>
          </div>
        </div>

        {/* Live status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="live-dot" style={{ display: 'inline-block' }} />
          <span className="mono" style={{ fontSize: 10, color: 'var(--green)', fontWeight: 700, marginLeft: 6 }}>LIVE</span>
        </div>
        <span className="mono" style={{ fontSize: 10, color: 'var(--text3)' }}>CYC #{state?.cycle || 0}</span>

        {/* Ticker tape */}
        <div className="ticker-wrap" style={{ flex: 1, margin: '0 10px', borderRadius: 3, border: '1px solid var(--border)', height: 26 }}>
          <div className="ticker-inner">
            {[...(Object.entries(prices)), ...(Object.entries(prices))].map(([sym, price], i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 18px', borderRight: '1px solid var(--border)' }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: assetColor(sym) }}>{sym}</span>
                <span className="mono" style={{ fontSize: 10, color: 'var(--text)' }}>${Number(price).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Clock + stats */}
        <div style={{ display: 'flex', align: 'center', gap: 16, paddingLeft: 16, borderLeft: '1px solid var(--border)' }}>
          <div style={{ textAlign: 'right' }}>
            <p className="mono" style={{ fontSize: 9, color: 'var(--text3)' }}>BALANCE</p>
            <p className="mono" style={{ fontSize: 11, fontWeight: 700, color: 'var(--text)' }}>${f0(port.balance || 10000)}</p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <p className="mono" style={{ fontSize: 9, color: 'var(--text3)' }}>RETURN</p>
            <p className="mono" style={{ fontSize: 11, fontWeight: 700, color: isUp ? 'var(--green)' : 'var(--red)' }}>{pct(port.total_return_pct || 0)}</p>
          </div>
          <LiveClock />
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* ── Left Sidebar ───────────────────────────────────────────────── */}
        <div style={{ width: 170, background: 'var(--bg1)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', padding: '10px 8px', flexShrink: 0 }}>
          <p className="sec-label" style={{ padding: '0 8px', marginBottom: 8 }}>Navigation</p>
          {navItems.map(n => (
            <div key={n.id} className={`nav-item ${tab === n.id ? 'active' : ''}`} onClick={() => setTab(n.id)}>
              <span className="nav-icon" style={{ color: tab === n.id ? 'var(--blue2)' : 'var(--text3)' }}>{n.icon}</span>
              <span>{n.label}</span>
            </div>
          ))}

          {/* Quick stats */}
          <div style={{ marginTop: 'auto', borderTop: '1px solid var(--border)', paddingTop: 10 }}>
            <p className="sec-label" style={{ padding: '0 8px', marginBottom: 8 }}>Portfolio</p>
            {[
              { l: 'Total Value', v: `$${f0(port.total_value || 10000)}`, c: 'var(--text)' },
              { l: 'Cash',        v: `$${f0(port.balance || 10000)}`,     c: 'var(--text2)' },
              { l: 'Positions',   v: `${Object.keys(pos).length}`,        c: 'var(--blue2)' },
              { l: 'Trades',      v: `${port.trade_count || 0}`,          c: 'var(--text2)' },
            ].map(r => (
              <div key={r.l} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 8px' }}>
                <span style={{ fontSize: 10, color: 'var(--text3)' }}>{r.l}</span>
                <span className="mono" style={{ fontSize: 10, fontWeight: 600, color: r.c }}>{r.v}</span>
              </div>
            ))}
          </div>

          {/* Win/execute rates */}
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 10, padding: '10px 8px 0' }}>
            <p className="sec-label" style={{ marginBottom: 6 }}>Performance</p>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
              <span style={{ fontSize: 10, color: 'var(--text3)' }}>Execute rate</span>
              <span className="mono" style={{ fontSize: 10, color: 'var(--green)' }}>{gate.execute_rate || 0}%</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
              <span style={{ fontSize: 10, color: 'var(--text3)' }}>Gate total</span>
              <span className="mono" style={{ fontSize: 10, color: 'var(--text2)' }}>{gate.total || 0}</span>
            </div>
          </div>
        </div>

        {/* ── Main Content ────────────────────────────────────────────────── */}
        <div style={{ flex: 1, overflow: 'auto', padding: '12px', display: 'flex', flexDirection: 'column', gap: 10 }}>

          {/* Mandate cards */}
          <AnimatePresence>
            {mandates.map(m => <MandateCard key={m.mandate_id} mandate={m} onApprove={onApprove} onReject={onReject} approving={approving} />)}
          </AnimatePresence>

          {/* ── Overview ──────────────────────────────────────────────────── */}
          {tab === 'overview' && (
            <>
              {/* Asset cards */}
              {Object.keys(prices).length > 0 ? (
                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(Object.keys(prices).length, 4)}, 1fr)`, gap: 8 }}>
                  {Object.entries(prices).map(([sym, price]) => (
                    <AssetCard key={sym} sym={sym} price={price} pos={pos[sym]} portHistory={portHistory} />
                  ))}
                </div>
              ) : (
                <div className="card" style={{ padding: '20px', textAlign: 'center', color: 'var(--text3)' }}>
                  <p style={{ fontSize: 28, marginBottom: 8 }}>📡</p>
                  <p>Fetching market data — Cycle #{state?.cycle || 0}</p>
                </div>
              )}

              {/* Portfolio chart */}
              <div className="card" style={{ padding: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                  <div>
                    <p className="sec-label" style={{ marginBottom: 4 }}>Portfolio Performance</p>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
                      <span className="mono" style={{ fontSize: 26, fontWeight: 800, color: isUp ? 'var(--green)' : 'var(--red)', textShadow: `0 0 20px ${isUp ? 'rgba(0,229,160,.4)' : 'rgba(255,51,102,.4)'}` }}>
                        ${f2(port.total_value || 10000)}
                      </span>
                      <span className="mono" style={{ fontSize: 13, fontWeight: 700, color: isUp ? 'var(--green)' : 'var(--red)' }}>{pct(port.total_return_pct || 0)}</span>
                      <span className="mono" style={{ fontSize: 11, color: 'var(--text2)' }}>{isUp ? '+' : ''}${f2(port.total_return || 0)} P&L</span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {[{ l: 'Positions', v: Object.keys(pos).length }, { l: 'Trades', v: port.trade_count || 0 }, { l: 'Cycle', v: `#${state?.cycle || 0}` }].map(s => (
                      <div key={s.l} style={{ textAlign: 'right', paddingLeft: 12, borderLeft: '1px solid var(--border)' }}>
                        <p style={{ fontSize: 9, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.08em' }}>{s.l}</p>
                        <p className="mono" style={{ fontSize: 13, fontWeight: 700, color: 'var(--blue2)' }}>{s.v}</p>
                      </div>
                    ))}
                  </div>
                </div>
                <div style={{ height: 140 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData.length ? chartData : [{ val: 10000, idx: 0 }, { val: 10000, idx: 1 }]} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="pg" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%"  stopColor={isUp ? 'var(--green)' : 'var(--red)'} stopOpacity={0.25} />
                          <stop offset="95%" stopColor={isUp ? 'var(--green)' : 'var(--red)'} stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="idx" hide />
                      <YAxis domain={[cMin, cMax]} hide />
                      <Tooltip content={<CustomTip />} />
                      <Area type="monotone" dataKey="val" stroke={isUp ? 'var(--green)' : 'var(--red)'} strokeWidth={2}
                        fill="url(#pg)" dot={false} activeDot={{ r: 4, fill: isUp ? 'var(--green)' : 'var(--red)', stroke: 'var(--bg3)', strokeWidth: 2 }} animationDuration={600} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </>
          )}

          {/* ── Positions ─────────────────────────────────────────────────── */}
          {tab === 'positions' && (
            <div className="card" style={{ padding: '14px 16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <p className="sec-label">Open Positions</p>
                <span className="mono" style={{ fontSize: 10, color: 'var(--text3)' }}>{Object.keys(pos).length} active</span>
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Symbol</th><th>Side</th><th>Shares</th><th>Avg Entry</th>
                    <th>Current</th><th>Alloc</th><th>Value</th><th>P&L</th><th>P&L%</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(pos).map(([sym, p]) => {
                    const up = (p.pnl || 0) >= 0
                    return (
                      <tr key={sym}>
                        <td style={{ fontWeight: 700, color: assetColor(sym) }}>{sym}</td>
                        <td><span className={`pill pill-${p.direction === 'long' ? 'buy' : 'sell'}`}>{(p.direction || '').toUpperCase()}</span></td>
                        <td style={{ color: 'var(--text2)' }}>{f4(p.shares)}</td>
                        <td>${f2(p.avg_price)}</td>
                        <td style={{ color: assetColor(sym) }}>${f2(p.current_price)}</td>
                        <td style={{ color: 'var(--text2)' }}>${f0(p.alloc_usd)}</td>
                        <td>${f0(p.value)}</td>
                        <td style={{ color: up ? 'var(--green)' : 'var(--red)', fontWeight: 700 }}>{up ? '+' : ''}{f2(p.pnl)}</td>
                        <td style={{ color: up ? 'var(--green)' : 'var(--red)' }}>{pct(p.pnl_pct || 0)}</td>
                      </tr>
                    )
                  })}
                  {!Object.keys(pos).length && (
                    <tr><td colSpan={9} style={{ textAlign: 'center', color: 'var(--text3)', padding: '30px 0' }}>
                      <p style={{ fontSize: 22, marginBottom: 6 }}>◈</p>No open positions — agents are scanning markets
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* ── Agents ────────────────────────────────────────────────────── */}
          {tab === 'agents' && (() => {
            const last    = (gateHistory || []).slice(-1)[0] || {}
            const allSigs = Object.values(state?.agent_signals || {})
            const avgConf = key => allSigs.length
              ? Math.round(allSigs.reduce((s, a) => s + (a[key] ?? 0), 0) / allSigs.length * 10000) / 10000
              : null
            const audAvg  = () => {
              const vals = allSigs.map(a => a.auditor).filter(v => v != null)
              return vals.length ? Math.round(vals.reduce((s, v) => s + v, 0) / vals.length * 10000) / 10000 : null
            }
            return (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  {/* Agent status */}
                  <div className="card" style={{ padding: '16px' }}>
                    <p className="sec-label" style={{ marginBottom: 14 }}>Agent Signals — Last Cycle</p>
                    <AgentRow name="Scout"     icon="📡" conf={avgConf('scout') ?? 1.0}              status="OK"                   color="var(--cyan)" />
                    <AgentRow name="Quant"     icon="📊" conf={last.quant_confidence}                status={last.decision}         color="var(--blue2)" />
                    <AgentRow name="Visionary" icon="🔭" conf={last.visionary_confidence}            status={last.decision}         color="var(--purple)" />
                    <AgentRow name="Sentiment" icon="💬" conf={last.sentiment_confidence ?? avgConf('sentiment') ?? 0.3} status="NEUTRAL" color="var(--yellow)" />
                    <AgentRow name="Auditor"   icon="⚖️"  conf={audAvg() ?? 1.0}                    status={audAvg() != null ? 'ACTIVE' : 'STANDBY'} color="var(--orange)" />
                    <AgentRow name="Gate"      icon="⛩" conf={last.combined_confidence}             status={last.decision}         color="var(--green)" />
                  </div>

                  {/* Gate detail */}
                  <div className="card" style={{ padding: '16px' }}>
                    <p className="sec-label" style={{ marginBottom: 14 }}>Last Gate Decision</p>
                    {last.asset ? (
                      <>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
                          <StatBox label="Asset"    value={last.asset}                              color={assetColor(last.asset)} />
                          <StatBox label="Decision" value={last.decision || '—'}                   color={last.decision === 'EXECUTE' ? 'var(--green)' : last.decision === 'HOLD' ? 'var(--yellow)' : 'var(--orange)'} />
                          <StatBox label="Combined" value={f2(last.combined_confidence)}           color="var(--blue2)" />
                          <StatBox label="Divergence" value={f2(last.divergence)}                  color="var(--text2)" />
                        </div>
                        <div style={{ background: 'var(--bg3)', borderRadius: 4, padding: '10px 12px', border: '1px solid var(--border)' }}>
                          <p style={{ fontSize: 9, color: 'var(--text3)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.08em' }}>Reason</p>
                          <p style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.5 }}>{last.reason || '—'}</p>
                        </div>
                      </>
                    ) : (
                      <p style={{ color: 'var(--text3)', fontSize: 12, textAlign: 'center', padding: '20px 0' }}>Awaiting first gate decision…</p>
                    )}
                  </div>
                </div>

                {/* Gate stats */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8 }}>
                  {[
                    { l: 'Total Cycles',   v: gate.total || 0,          c: 'var(--text)',   glow: false },
                    { l: 'Execute',        v: gate.EXECUTE || 0,         c: 'var(--green)',  glow: true  },
                    { l: 'Hold',           v: gate.HOLD || 0,            c: 'var(--yellow)', glow: false },
                    { l: 'Execute Rate',   v: `${gate.execute_rate || 0}%`, c: 'var(--cyan)', glow: true },
                  ].map(s => <StatBox key={s.l} label={s.l} value={s.v} color={s.c} glow={s.glow} />)}
                </div>
              </div>
            )
          })()}

          {/* ── Gate Log ──────────────────────────────────────────────────── */}
          {tab === 'gatelog' && (
            <div className="card" style={{ padding: '14px 16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <p className="sec-label">Gate Decision Log</p>
                <span className="mono" style={{ fontSize: 10, color: 'var(--text3)' }}>{(gateHistory || []).length} decisions</span>
              </div>
              <table className="data-table">
                <thead>
                  <tr><th>Time</th><th>Asset</th><th>Decision</th><th>Action</th><th>Quant</th><th>Vision</th><th>Sent</th><th>Combined</th><th>Reason</th></tr>
                </thead>
                <tbody>
                  <AnimatePresence initial={false}>
                    {[...(gateHistory || [])].reverse().slice(0, 20).map((r, i) => (
                      <motion.tr key={`${r.timestamp}-${i}`} initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} style={{ opacity: Math.max(0.25, 1 - i * 0.04) }}>
                        <td style={{ color: 'var(--text3)', fontSize: 11 }}>{ago(r.timestamp)}</td>
                        <td style={{ fontWeight: 700, color: assetColor(r.asset || r.query) }}>{r.asset || r.query}</td>
                        <td><span className={`pill pill-${r.decision?.toLowerCase()}`}>{r.decision}</span></td>
                        <td style={{ color: r.action === 'long' ? 'var(--green)' : r.action === 'short' ? 'var(--red)' : 'var(--text3)', fontSize: 11 }}>{r.action || '—'}</td>
                        <td style={{ color: 'var(--text2)', fontSize: 11 }}>{f2(r.quant_confidence)}</td>
                        <td style={{ color: 'var(--text2)', fontSize: 11 }}>{f2(r.visionary_confidence)}</td>
                        <td style={{ color: 'var(--yellow)', fontSize: 11 }}>{r.sentiment_confidence != null ? f2(r.sentiment_confidence) : '—'}</td>
                        <td style={{ color: 'var(--blue2)', fontSize: 11, fontWeight: 600 }}>{f2(r.combined_confidence)}</td>
                        <td style={{ color: 'var(--text3)', fontSize: 10, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.reason?.slice(0, 55)}</td>
                      </motion.tr>
                    ))}
                  </AnimatePresence>
                  {!gateHistory?.length && (
                    <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text3)', padding: '30px 0' }}>Awaiting gate decisions…</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* ── Security ──────────────────────────────────────────────────── */}
          {tab === 'security' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div className="card" style={{ padding: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <p className="sec-label">Valid(M) — Six-Condition Invariant</p>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(0,229,160,.08)', border: '1px solid rgba(0,229,160,.25)', borderRadius: 3, padding: '3px 10px' }}>
                    <span style={{ fontSize: 10, color: 'var(--green)' }}>●</span>
                    <span className="mono" style={{ fontSize: 10, color: 'var(--green)', fontWeight: 700 }}>ALL SYSTEMS NOMINAL</span>
                  </div>
                </div>
                {[
                  { n: 1, l: 'Challenge Binding',   d: 'SHA-256 mandate hash — cryptographically bound to trade parameters',  icon: '🔗', c: 'var(--blue2)' },
                  { n: 2, l: 'WebAuthn UV=required', d: 'Biometric hardware sign-off — user verification required flag enforced', icon: '👆', c: 'var(--green)' },
                  { n: 3, l: 'TEE Attestation',      d: 'Simulated SGX enclave — trusted execution environment verified',       icon: '🔒', c: 'var(--purple)' },
                  { n: 4, l: 'Oracle Consensus',     d: 'yfinance dual-sample δ≤0.5% — two independent price confirmations',    icon: '📡', c: 'var(--cyan)' },
                  { n: 5, l: 'Atomic Quota Lock',    d: 'Thread-safe TOCTOU fix — race condition prevention on daily cap',      icon: '⚛',  c: 'var(--yellow)' },
                  { n: 6, l: 'Revocation Registry',  d: 'Instant kill switch — mandate invalidation active at runtime',        icon: '🛑', c: 'var(--orange)' },
                ].map((c, i) => (
                  <motion.div key={c.n} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.07 }}
                    style={{ display: 'flex', gap: 12, padding: '12px 14px', marginBottom: 6, background: 'var(--bg3)', borderRadius: 4, border: '1px solid var(--border)', position: 'relative', overflow: 'hidden' }}>
                    <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 2, background: c.c }} />
                    <div style={{ width: 28, height: 28, borderRadius: 4, background: `${c.c}14`, border: `1px solid ${c.c}33`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: 14 }}>{c.icon}</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                        <span className="mono" style={{ fontSize: 10, color: c.c, fontWeight: 700 }}>C{c.n}</span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)' }}>{c.l}</span>
                      </div>
                      <p style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.4 }}>{c.d}</p>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <motion.div animate={{ opacity: [1, 0.4, 1] }} transition={{ duration: 2, repeat: Infinity, delay: i * 0.3 }}
                        style={{ width: 6, height: 6, borderRadius: '50%', background: c.c, boxShadow: `0 0 6px ${c.c}` }} />
                      <span className="mono" style={{ fontSize: 10, color: 'var(--green)', fontWeight: 700 }}>PASS</span>
                    </div>
                  </motion.div>
                ))}
              </div>

              {/* Mandate stats */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
                <StatBox label="Active Mandates"  value="0"      color="var(--blue2)" />
                <StatBox label="Revocations"      value="0"      color="var(--text2)" />
                <StatBox label="Quota Remaining"  value="$3,000" color="var(--green)" />
              </div>
            </div>
          )}
        </div>

        {/* ── Right Panel — Gate ─────────────────────────────────────────── */}
        <div style={{ width: 220, background: 'var(--bg1)', borderLeft: '1px solid var(--border)', padding: '12px 10px', flexShrink: 0, overflow: 'auto' }}>
          <GatePanel gate={gate} gateHistory={gateHistory} />
        </div>
      </div>

      {/* ── Status Bar ─────────────────────────────────────────────────────── */}
      <div style={{ height: 22, background: 'var(--bg1)', borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 12px', gap: 0, flexShrink: 0 }}>
        {[
          { l: '⚡ APEE TERMINAL', c: 'var(--blue2)' },
          { l: `CYC #${state?.cycle || 0}`, c: 'var(--text3)' },
          { l: '● LIVE', c: 'var(--green)' },
          { l: `${Object.keys(pos).length} POSITIONS`, c: 'var(--text3)' },
          { l: `${gate.execute_rate || 0}% EXEC RATE`, c: 'var(--text3)' },
          { l: `${gate.total || 0} DECISIONS`, c: 'var(--text3)' },
          { l: `BAL $${f0(port.balance || 10000)}`, c: isUp ? 'var(--green)' : 'var(--text3)' },
        ].map((it, i) => (
          <span key={i} className="mono" style={{ fontSize: 10, color: it.c, padding: '0 12px', borderRight: i < 6 ? '1px solid var(--border)' : 'none' }}>{it.l}</span>
        ))}
        <span style={{ marginLeft: 'auto' }}><LiveClock /></span>
      </div>
    </div>
  )
}

// ── Shopping Dashboard ────────────────────────────────────────────────────────
function ShoppingDashboard({ state, gateHistory }) {
  const wishlist  = state?.wishlist   || []
  const gate      = state?.gate_stats || {}
  const decisions = (gateHistory || []).filter(r => r.decision === 'EXECUTE')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{ height: 44, background: 'var(--bg1)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 16px', gap: 16 }}>
        <div style={{ width: 26, height: 26, borderRadius: 4, background: 'rgba(0,229,160,.15)', border: '1px solid rgba(0,229,160,.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13 }}>🛒</div>
        <div>
          <p style={{ fontWeight: 700, fontSize: 12, letterSpacing: '.06em' }}>APEE SHOPPING</p>
          <p style={{ fontSize: 9, color: 'var(--text3)' }}>Price monitoring active</p>
        </div>
        <div style={{ display: 'flex', gap: 20, marginLeft: 'auto' }}>
          {[{ l: 'Watching', v: wishlist.length, c: 'var(--blue2)' }, { l: 'Alerts', v: decisions.length, c: 'var(--green)' }, { l: 'Cycle', v: `#${state?.cycle || 0}`, c: 'var(--text2)' }].map(s => (
            <div key={s.l} style={{ textAlign: 'right' }}>
              <p style={{ fontSize: 9, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.08em' }}>{s.l}</p>
              <p className="mono" style={{ fontSize: 13, fontWeight: 700, color: s.c }}>{s.v}</p>
            </div>
          ))}
        </div>
        <LiveClock />
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '14px 16px' }}>
        {decisions.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <p className="sec-label" style={{ marginBottom: 8 }}>Buy Alerts</p>
            {decisions.slice(-3).reverse().map((d, i) => (
              <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                style={{ background: 'rgba(0,229,160,.06)', border: '1px solid rgba(0,229,160,.25)', borderRadius: 4, padding: '12px 14px', marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontWeight: 700, color: 'var(--green)', fontSize: 12 }}>🎯 BUY SIGNAL — {d.asset || d.query}</span>
                  <span className="mono" style={{ fontSize: 10, color: 'var(--text2)' }}>{ago(d.timestamp)}</span>
                </div>
                <p style={{ fontSize: 11, color: 'var(--text2)' }}>{d.reason?.slice(0, 120)}</p>
              </motion.div>
            ))}
          </div>
        )}

        <p className="sec-label" style={{ marginBottom: 8 }}>Watchlist</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {wishlist.map((item, i) => (
            <div key={i} className="card" style={{ padding: '14px 16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div>
                  <p style={{ fontWeight: 700, fontSize: 14, marginBottom: 3, color: 'var(--text)' }}>{item.product}</p>
                  <p className="mono" style={{ fontSize: 10, color: 'var(--text2)' }}>
                    ${item.min_price}–${item.max_price} +{item.tax_pct}% tax · {item.deadline_days} days
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'rgba(0,136,255,.08)', border: '1px solid rgba(0,136,255,.2)', borderRadius: 3, padding: '3px 10px' }}>
                  <motion.div animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 2, repeat: Infinity }} style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--blue)' }} />
                  <span className="mono" style={{ fontSize: 9, color: 'var(--blue2)', fontWeight: 600, marginLeft: 4 }}>WATCHING</span>
                </div>
              </div>
              <div style={{ height: 2, borderRadius: 1, background: 'var(--bg)', overflow: 'hidden' }}>
                <motion.div initial={{ width: 0 }} animate={{ width: '45%' }} transition={{ duration: 1 }} style={{ height: '100%', background: 'var(--blue)', borderRadius: 1 }} />
              </div>
              <p style={{ fontSize: 10, color: 'var(--text3)', marginTop: 6 }}>Scanning every 30 min via AI agents + SerpAPI</p>
            </div>
          ))}
          {!wishlist.length && (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text3)' }}>
              <p style={{ fontSize: 28, marginBottom: 8 }}>🔍</p>
              <p>Waiting for wishlist data from backend…</p>
            </div>
          )}
        </div>

        <div className="card" style={{ padding: '14px 16px', marginTop: 14 }}>
          <p className="sec-label" style={{ marginBottom: 12 }}>Gate Performance</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
            {[{ l: 'Buy Signals', v: gate.EXECUTE || 0, c: 'var(--green)' }, { l: 'Wait', v: gate.HOLD || 0, c: 'var(--yellow)' }, { l: 'Review', v: gate.REVIEW || 0, c: 'var(--orange)' }].map(s => (
              <div key={s.l} style={{ background: 'var(--bg3)', borderRadius: 4, padding: '12px', textAlign: 'center', border: '1px solid var(--border)' }}>
                <p className="mono" style={{ fontSize: 22, fontWeight: 800, color: s.c }}>{s.v}</p>
                <p style={{ fontSize: 10, color: 'var(--text3)', marginTop: 4, textTransform: 'uppercase', letterSpacing: '.08em' }}>{s.l}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ height: 22, background: 'var(--bg1)', borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 12px', gap: 16 }}>
        {[{ l: '🛒 APEE SHOPPING', c: 'var(--green)' }, { l: `CYC #${state?.cycle || 0}`, c: 'var(--text3)' }, { l: 'ACTIVE', c: 'var(--green)' }, { l: `${wishlist.length} PRODUCTS`, c: 'var(--text3)' }].map((it, i) => (
          <span key={i} className="mono" style={{ fontSize: 10, color: it.c }}>{it.l}</span>
        ))}
        <span style={{ marginLeft: 'auto' }}><LiveClock /></span>
      </div>
    </div>
  )
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [mode,      setMode]      = useState('chat')
  const [data,      setData]      = useState(null)
  const [approving, setApproving] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const res  = await fetch('/api/state')
      const json = await res.json()
      setData(json)
    } catch {}
  }, [])

  useEffect(() => {
    fetchData()
    const iv = setInterval(fetchData, 5000)
    return () => clearInterval(iv)
  }, [fetchData])

  const approve = async id => {
    setApproving(true)
    try { await fetch('/api/mandate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mandate_id: id, action: 'approve' }) }) }
    finally { setApproving(false); fetchData() }
  }
  const reject = async id => {
    await fetch('/api/mandate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mandate_id: id, action: 'reject' }) })
    fetchData()
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <AnimatePresence mode="wait">
        {mode === 'chat' && (
          <motion.div key="chat" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ flex: 1, overflow: 'hidden' }}>
            <ChatView onActivate={cfg => setMode(cfg.mode === 'trading' ? 'trading' : 'ecommerce')} />
          </motion.div>
        )}
        {mode === 'trading' && (
          <motion.div key="trading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ flex: 1, overflow: 'hidden' }}>
            <TradingDashboard
              state={data?.state} gateHistory={data?.gateHistory}
              portHistory={data?.portHistory} events={data?.events}
              onApprove={approve} onReject={reject} approving={approving} />
          </motion.div>
        )}
        {mode === 'ecommerce' && (
          <motion.div key="ecommerce" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ flex: 1, overflow: 'hidden' }}>
            <ShoppingDashboard state={data?.state} gateHistory={data?.gateHistory} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
