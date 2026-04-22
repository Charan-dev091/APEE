'use client'
import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'

const f2  = n => n==null?'—':Number(n).toFixed(2)
const f4  = n => n==null?'—':Number(n).toFixed(4)
const pct = n => `${Number(n)>=0?'+':''}${Number(n).toFixed(2)}%`
const ago = iso => { if(!iso)return''; const s=Math.floor((Date.now()-new Date(iso))/1000); return s<60?`${s}s`:s<3600?`${Math.floor(s/60)}m`:`${Math.floor(s/3600)}h` }
const COLORS = { NVDA:'#26a69a', AAPL:'#2962ff', TSLA:'#7c4dff', BTC:'#f5c518', ETH:'#00bcd4' }
const RAG_URL = 'http://localhost:8767'

// ── Typing dots ───────────────────────────────────────────────────────────────
function TypingDots() {
  return (
    <div style={{display:'flex',gap:4,padding:'10px 14px',background:'var(--bg2)',border:'1px solid var(--border)',borderRadius:'12px 12px 12px 2px',width:'fit-content'}}>
      {[0,1,2].map(i=>(
        <motion.div key={i} animate={{opacity:[0.3,1,0.3],y:[0,-3,0]}} transition={{duration:0.8,repeat:Infinity,delay:i*0.2}}
          style={{width:6,height:6,borderRadius:'50%',background:'var(--text2)'}}/>
      ))}
    </div>
  )
}

// ── Mode cards ────────────────────────────────────────────────────────────────
function ModeCards({ onSelect }) {
  return (
    <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10,margin:'8px 0'}}>
      {[
        {type:'trade',icon:'📈',title:'Trade Stocks & Crypto',desc:'AI agents monitor NVDA, AAPL, TSLA and alert you on opportunities'},
        {type:'shop', icon:'🛒',title:'Track Product Prices', desc:'Get alerted when products hit your target price'},
      ].map(m=>(
        <div key={m.type} className="mode-card" onClick={()=>onSelect(m.type)}
          style={{borderColor:m.type==='trade'?'rgba(41,98,255,.2)':'rgba(38,166,154,.2)'}}>
          <div style={{fontSize:22,marginBottom:6}}>{m.icon}</div>
          <p style={{fontWeight:600,marginBottom:3,fontSize:13}}>{m.title}</p>
          <p style={{fontSize:11,color:'var(--text2)',lineHeight:1.4}}>{m.desc}</p>
        </div>
      ))}
    </div>
  )
}

// ── Markdown renderer ─────────────────────────────────────────────────────────
function Markdown({ text }) {
  return (
    <div>
      {text.split('\n').map((line,i) => (
        <p key={i} style={{marginBottom:line===''?6:2,lineHeight:1.6,fontSize:13}}>
          {line.split(/\*\*(.*?)\*\*/g).map((part,j) =>
            j%2===1 ? <strong key={j} style={{color:'var(--text)',fontWeight:600}}>{part}</strong> : part
          )}
        </p>
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
      setMessages([{ role:'apee', content:`Hi! I'm **APEE** — Autonomous Personal Economy Engine.\n\nI can help you with:\n\n📈 **Trade stocks & crypto** — AI agents monitor markets and alert you on opportunities.\n\n🛒 **Track product prices** — Tell me what you want to buy and I'll alert you when the price is right.\n\nWhat would you like to do today?`, showCards:true, timestamp:new Date() }])
      setShowCards(true)
    }, 300)
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({behavior:'smooth'}) }, [messages, typing])

  const sendMessage = async (text) => {
    if (!text.trim()) return
    const userMsg = { role:'user', content:text, timestamp:new Date() }
    const newMsgs = [...messages, userMsg]
    setMessages(newMsgs)
    setInput('')
    setTyping(true)
    setShowCards(false)

    // Query RAG first
    try { await fetch(`${RAG_URL}/rag/query?q=${encodeURIComponent(text)}`) } catch {}

    try {
      const res  = await fetch('/api/chat', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          messages: newMsgs.map(m=>({role:m.role==='apee'?'assistant':m.role, content:m.content})),
          conversationState: convState,
        }),
      })
      const data = await res.json()
      setTyping(false)
      setMessages(m=>[...m, { role:'apee', content:data.message, timestamp:new Date() }])
      setConvState({ intent:data.intent, state:data.state, ...data })
      if (data.activate && data.config) setTimeout(()=>onActivate(data.config), 1500)
    } catch {
      setTyping(false)
      setMessages(m=>[...m, { role:'apee', content:'Something went wrong. Please try again.', timestamp:new Date() }])
    }
  }

  return (
    <div style={{display:'flex',flexDirection:'column',height:'100%'}}>
      {/* Header */}
      <div style={{padding:'14px 20px',borderBottom:'1px solid var(--border)',display:'flex',alignItems:'center',gap:12,background:'var(--bg1)'}}>
        <div style={{width:36,height:36,borderRadius:8,background:'rgba(41,98,255,.2)',border:'1px solid rgba(41,98,255,.4)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:18}}>⚡</div>
        <div>
          <p style={{fontWeight:600,fontSize:15}}>APEE</p>
          <p style={{fontSize:11,color:'var(--text2)'}}>Autonomous Personal Economy Engine</p>
        </div>
        <div style={{marginLeft:'auto',display:'flex',alignItems:'center',gap:5,background:'rgba(38,166,154,.1)',border:'1px solid rgba(38,166,154,.25)',borderRadius:6,padding:'3px 10px'}}>
          <div style={{width:6,height:6,borderRadius:'50%',background:'var(--green)'}}/>
          <span style={{fontSize:11,color:'var(--green)'}}>Online</span>
        </div>
      </div>

      {/* Messages */}
      <div style={{flex:1,overflow:'auto',padding:'20px',display:'flex',flexDirection:'column',gap:10}}>
        <AnimatePresence initial={false}>
          {messages.map((msg,i)=>(
            <motion.div key={i} initial={{opacity:0,y:8}} animate={{opacity:1,y:0}}
              style={{display:'flex',flexDirection:'column',alignItems:msg.role==='user'?'flex-end':'flex-start'}}>
              {msg.role==='apee' && (
                <div style={{display:'flex',alignItems:'center',gap:6,marginBottom:4}}>
                  <div style={{width:18,height:18,borderRadius:4,background:'rgba(41,98,255,.2)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:10}}>⚡</div>
                  <span style={{fontSize:11,color:'var(--text2)',fontWeight:500}}>APEE</span>
                  <span style={{fontSize:10,color:'var(--text3)'}}>{ago(msg.timestamp?.toISOString())} ago</span>
                </div>
              )}
              <div className={msg.role==='user'?'bubble-user':'bubble-apee'} style={{color:msg.role==='user'?'#c8d8f8':'var(--text)'}}>
                <Markdown text={msg.content}/>
              </div>
              {msg.showCards && showCards && (
                <motion.div initial={{opacity:0,y:6}} animate={{opacity:1,y:0}} transition={{delay:0.3}} style={{width:'100%',marginTop:8}}>
                  <ModeCards onSelect={t=>sendMessage(t==='trade'?'I want to trade stocks and crypto':'I want to track product prices')}/>
                </motion.div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
        {typing && <motion.div initial={{opacity:0}} animate={{opacity:1}}><TypingDots/></motion.div>}
        <div ref={bottomRef}/>
      </div>

      {/* Input */}
      <div style={{padding:'12px 16px',borderTop:'1px solid var(--border)',background:'var(--bg1)'}}>
        <div style={{display:'flex',gap:8,alignItems:'flex-end'}}>
          <textarea className="chat-input" rows={2} value={input} onChange={e=>setInput(e.target.value)}
            onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage(input)}}}
            placeholder='e.g. "New Balance 9060 $80-$100, 8% tax, 10 days" or "trade NVDA and AAPL"'
            style={{flex:1}}/>
          <button className="btn btn-primary" onClick={()=>sendMessage(input)} style={{height:44,padding:'0 20px'}}>Send</button>
        </div>
        <p style={{fontSize:10,color:'var(--text3)',marginTop:5}}>Enter to send • Shift+Enter for new line</p>
      </div>
    </div>
  )
}

// ── Sparkline ─────────────────────────────────────────────────────────────────
function Spark({ data, w=80, h=32 }) {
  if (!data?.length) return null
  const vals = data.map(d=>d.v||d.val||d.total_value||0)
  const min=Math.min(...vals), max=Math.max(...vals), range=max-min||1
  const pts = data.map((d,i)=>{
    const x=(i/(data.length-1))*w, y=h-((vals[i]-min)/range)*(h-4)-2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const isUp = vals[vals.length-1]>=vals[0]
  return <svg width={w} height={h} style={{display:'block'}}><polyline points={pts} fill="none" stroke={isUp?'#26a69a':'#ef5350'} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round"/></svg>
}

// ── Mandate approval card ─────────────────────────────────────────────────────
function MandateCard({ mandate, onApprove, onReject, approving }) {
  return (
    <motion.div initial={{opacity:0,y:-10}} animate={{opacity:1,y:0}} exit={{opacity:0}}
      style={{background:'rgba(245,197,24,.06)',border:'1px solid rgba(245,197,24,.3)',borderRadius:8,padding:'12px 14px',marginBottom:10}}>
      <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:10}}>
        <motion.div animate={{opacity:[1,.3,1]}} transition={{duration:1.2,repeat:Infinity}}
          style={{width:7,height:7,borderRadius:'50%',background:'var(--yellow)'}}/>
        <span style={{fontSize:12,fontWeight:600,color:'var(--yellow)'}}>AWAITING YOUR AUTHORIZATION</span>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10,marginBottom:10}}>
        {[{l:'Asset',v:mandate.asset,c:'var(--text)'},{l:'Action',v:(mandate.action||'').toUpperCase(),c:'var(--green)'},
          {l:'Amount',v:`$${f2(mandate.alloc_usd)}`,c:'var(--text)'},{l:'Price',v:`$${f2(mandate.oracle_price)}`,c:'var(--text2)'}
        ].map(s=>(
          <div key={s.l}><p style={{fontSize:10,color:'var(--text2)',marginBottom:2}}>{s.l}</p>
            <p className="mono" style={{fontSize:15,fontWeight:600,color:s.c}}>{s.v}</p></div>
        ))}
      </div>
      <div style={{display:'flex',gap:8,justifyContent:'flex-end'}}>
        <button className="btn btn-red" onClick={()=>onReject(mandate.mandate_id)} disabled={approving}>Reject</button>
        <button className="btn btn-green" onClick={()=>onApprove(mandate.mandate_id)} disabled={approving}>
          {approving?'Processing…':'✓ Approve Trade'}
        </button>
      </div>
    </motion.div>
  )
}

// ── Trading dashboard ─────────────────────────────────────────────────────────
function TradingDashboard({ state, gateHistory, portHistory, events, onApprove, onReject, approving }) {
  const [tab, setTab] = useState('overview')
  const port   = state?.portfolio || {}
  const prices = state?.prices    || {}
  const gate   = state?.gate_stats|| {}
  const pos    = port.positions   || {}
  const isUp   = (port.total_return_pct||0) >= 0
  const mandates = (events||[]).filter(e=>e.type==='BIOMETRIC_PENDING').map(e=>e.data).filter(Boolean)
  const chartData = (portHistory||[]).map((d,i)=>({...d,val:d.total_value||d.v||0,idx:i}))
  const vals = chartData.map(d=>d.val)
  const cMin = Math.min(...vals)*0.998, cMax = Math.max(...vals)*1.002

  const CustomTip = ({active,payload}) => {
    if(!active||!payload?.length) return null
    return <div style={{background:'var(--bg3)',border:'1px solid var(--border2)',borderRadius:6,padding:'8px 12px'}}>
      <p className="mono" style={{fontSize:11,color:'var(--text2)',marginBottom:2}}>Cycle #{payload[0].payload.cycle||payload[0].payload.idx}</p>
      <p className="mono" style={{fontSize:14,fontWeight:600,color:isUp?'#26a69a':'#ef5350'}}>${Number(payload[0].value).toFixed(2)}</p>
    </div>
  }

  return (
    <div style={{display:'flex',flexDirection:'column',height:'100%'}}>
      {/* Ticker */}
      <div className="ticker-wrap">
        {[...Object.entries(prices),...Object.entries(prices)].map(([s,p],i)=>(
          <div key={i} style={{display:'flex',alignItems:'center',gap:8,padding:'0 20px',borderRight:'1px solid var(--border)',height:30}}>
            <span style={{fontSize:11,fontWeight:600,color:COLORS[s]||'var(--text2)'}}>{s}</span>
            <span className="mono" style={{fontSize:12}}>${Number(p).toFixed(2)}</span>
          </div>
        ))}
      </div>

      <div style={{display:'flex',flex:1,overflow:'hidden'}}>
        {/* Sidebar */}
        <div style={{width:178,background:'var(--bg1)',borderRight:'1px solid var(--border)',display:'flex',flexDirection:'column',padding:'12px 8px',flexShrink:0}}>
          <div style={{padding:'0 8px 12px',borderBottom:'1px solid var(--border)',marginBottom:10}}>
            <p style={{fontWeight:700,fontSize:14}}>APEE Trading</p>
            <div style={{display:'flex',alignItems:'center',gap:5,marginTop:2}}>
              <div style={{width:6,height:6,borderRadius:'50%',background:'var(--green)'}}/>
              <span style={{fontSize:11,color:'var(--green)'}}>Live</span>
              <span style={{fontSize:11,color:'var(--text3)',marginLeft:4}}>Cycle #{state?.cycle||0}</span>
            </div>
          </div>
          {['Overview','Positions','Gate Log','Security'].map(t=>(
            <div key={t} onClick={()=>setTab(t.toLowerCase())}
              style={{display:'flex',alignItems:'center',gap:8,padding:'7px 10px',borderRadius:6,cursor:'pointer',
                marginBottom:2,color:tab===t.toLowerCase()?'#7aa4ff':'var(--text2)',
                background:tab===t.toLowerCase()?'rgba(41,98,255,.12)':'transparent',fontSize:13,fontWeight:500}}>
              {t==='Overview'?'▦':t==='Positions'?'◈':t==='Gate Log'?'⊞':'⛨'} {t}
            </div>
          ))}
          <div style={{marginTop:'auto',padding:'10px 8px',borderTop:'1px solid var(--border)'}}>
            {[{l:'Balance',v:`$${Number(port.balance||10000).toFixed(0)}`,c:'var(--text)'},
              {l:'Return', v:pct(port.total_return_pct||0),c:isUp?'var(--green)':'var(--red)'},
              {l:'Win Rate',v:`${Number(port.win_rate||0).toFixed(1)}%`,c:'var(--text2)'},
            ].map(r=>(
              <div key={r.l} style={{display:'flex',justifyContent:'space-between',marginBottom:5}}>
                <span style={{fontSize:11,color:'var(--text2)'}}>{r.l}</span>
                <span className="mono" style={{fontSize:11,fontWeight:600,color:r.c}}>{r.v}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Content */}
        <div style={{flex:1,overflow:'auto',padding:'12px 14px'}}>
          <AnimatePresence>
            {mandates.map(m=><MandateCard key={m.mandate_id} mandate={m} onApprove={onApprove} onReject={onReject} approving={approving}/>)}
          </AnimatePresence>

          {tab==='overview' && (
            <div style={{display:'flex',flexDirection:'column',gap:10}}>
              {/* Asset cards */}
              <div style={{display:'grid',gridTemplateColumns:`repeat(${Math.max(Object.keys(prices).length,1)},1fr)`,gap:8}}>
                {Object.entries(prices).map(([sym,price])=>{
                  const p=pos[sym]||{}, isUp=(p.pnl||0)>=0
                  return (
                    <div key={sym} className="card" style={{padding:'12px 14px'}}>
                      <div style={{display:'flex',justifyContent:'space-between',marginBottom:6}}>
                        <div style={{display:'flex',alignItems:'center',gap:6}}>
                          <div style={{width:24,height:24,borderRadius:5,background:`${COLORS[sym]||'#888'}22`,border:`1px solid ${COLORS[sym]||'#888'}44`,display:'flex',alignItems:'center',justifyContent:'center',fontSize:9,fontWeight:700,color:COLORS[sym]||'#888'}}>{sym[0]}</div>
                          <span style={{fontWeight:600}}>{sym}</span>
                        </div>
                        <span className={`pill ${isUp?'pill-buy':'pill-sell'}`}>{isUp?'▲':'▼'} {pct(p.pnl_pct||0)}</span>
                      </div>
                      <p className="mono" style={{fontSize:18,fontWeight:600,marginBottom:6}}>${f2(price)}</p>
                      <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-end'}}>
                        <div>
                          <p style={{fontSize:10,color:'var(--text2)'}}>P&L</p>
                          <p className="mono" style={{fontSize:11,fontWeight:600,color:isUp?'var(--green)':'var(--red)'}}>{isUp?'+':''}{f2(p.pnl||0)}</p>
                        </div>
                        <Spark data={[...Array(12)].map((_,i)=>({val:Number(price)*(0.97+i*0.004+(Math.random()-.5)*.01)}))} w={70} h={28}/>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Chart + gate */}
              <div style={{display:'grid',gridTemplateColumns:'1fr 220px',gap:10}}>
                <div className="card" style={{padding:'14px 16px'}}>
                  <div style={{display:'flex',justifyContent:'space-between',marginBottom:10}}>
                    <div>
                      <p style={{fontSize:11,color:'var(--text2)',marginBottom:2}}>Portfolio Analytics</p>
                      <div style={{display:'flex',alignItems:'baseline',gap:10}}>
                        <span className="mono" style={{fontSize:22,fontWeight:700}}>${f2(port.total_value||10000)}</span>
                        <span className="mono" style={{fontSize:12,color:isUp?'var(--green)':'var(--red)',fontWeight:600}}>{pct(port.total_return_pct||0)}</span>
                      </div>
                    </div>
                  </div>
                  <div style={{height:140}}>
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData} margin={{top:4,right:4,left:0,bottom:0}}>
                        <defs>
                          <linearGradient id="pg" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={isUp?'#26a69a':'#ef5350'} stopOpacity={0.2}/>
                            <stop offset="95%" stopColor={isUp?'#26a69a':'#ef5350'} stopOpacity={0}/>
                          </linearGradient>
                        </defs>
                        <XAxis dataKey="idx" hide/>
                        <YAxis domain={[cMin,cMax]} hide/>
                        <Tooltip content={<CustomTip/>}/>
                        <Area type="monotone" dataKey="val" stroke={isUp?'#26a69a':'#ef5350'} strokeWidth={1.5} fill="url(#pg)" dot={false} activeDot={{r:4}} animationDuration={800}/>
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="card" style={{padding:'14px 16px'}}>
                  <p style={{fontSize:11,color:'var(--text2)',marginBottom:10}}>Gate Performance</p>
                  {[{k:'EXECUTE',c:'var(--green)'},{k:'HOLD',c:'var(--yellow)'},{k:'REVIEW',c:'var(--red)'}].map(b=>{
                    const v=gate[b.k]||0, tot=gate.total||1, p=Math.round((v/tot)*100)
                    return (
                      <div key={b.k} style={{marginBottom:10}}>
                        <div style={{display:'flex',justifyContent:'space-between',marginBottom:3}}>
                          <span style={{fontSize:11,color:b.c,fontWeight:500}}>{b.k}</span>
                          <span className="mono" style={{fontSize:11,color:'var(--text2)'}}>{v} / {p}%</span>
                        </div>
                        <div style={{height:3,borderRadius:2,background:'rgba(0,0,0,.5)',overflow:'hidden'}}>
                          <motion.div initial={{width:0}} animate={{width:`${p}%`}} transition={{duration:.8}}
                            style={{height:'100%',background:b.c,borderRadius:2}}/>
                        </div>
                      </div>
                    )
                  })}
                  <div style={{marginTop:10,paddingTop:10,borderTop:'1px solid var(--border)',display:'flex',justifyContent:'space-between'}}>
                    <span style={{fontSize:11,color:'var(--text2)'}}>Execute rate</span>
                    <span className="mono" style={{fontSize:12,fontWeight:600,color:'var(--cyan)'}}>{gate.execute_rate||0}%</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {tab==='positions' && (
            <div className="card" style={{padding:'14px 16px'}}>
              <p style={{fontWeight:600,marginBottom:12}}>Open Positions</p>
              <table className="data-table">
                <thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Current</th><th>P&L</th><th>P&L%</th></tr></thead>
                <tbody>
                  {Object.entries(pos).map(([sym,p])=>(
                    <tr key={sym}>
                      <td style={{fontWeight:600,color:COLORS[sym]||'var(--text)'}}>{sym}</td>
                      <td><span className={`pill ${p.direction==='long'?'pill-buy':'pill-sell'}`}>{p.direction?.toUpperCase()}</span></td>
                      <td className="mono" style={{color:'var(--text2)'}}>{f4(p.size)}</td>
                      <td className="mono">${f2(p.entry_price)}</td>
                      <td className="mono">${f2(p.current_price)}</td>
                      <td className="mono" style={{color:(p.pnl||0)>=0?'var(--green)':'var(--red)',fontWeight:600}}>{(p.pnl||0)>=0?'+':''}{f2(p.pnl)}</td>
                      <td className="mono" style={{color:(p.pnl_pct||0)>=0?'var(--green)':'var(--red)'}}>{pct(p.pnl_pct||0)}</td>
                    </tr>
                  ))}
                  {!Object.keys(pos).length&&<tr><td colSpan={7} style={{textAlign:'center',color:'var(--text2)',padding:20}}>No open positions</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          {tab==='gate log' && (
            <div className="card" style={{padding:'14px 16px'}}>
              <p style={{fontWeight:600,marginBottom:12}}>Gate Decision Log</p>
              <table className="data-table">
                <thead><tr><th>Time</th><th>Asset</th><th>Decision</th><th>Quant</th><th>Vision</th><th>Reason</th></tr></thead>
                <tbody>
                  <AnimatePresence initial={false}>
                    {[...(gateHistory||[])].reverse().slice(0,15).map((r,i)=>(
                      <motion.tr key={`${r.timestamp}-${i}`} initial={{opacity:0,y:-6}} animate={{opacity:1,y:0}} style={{opacity:Math.max(.3,1-i*.06)}}>
                        <td className="mono" style={{color:'var(--text2)',fontSize:11}}>{ago(r.timestamp)}</td>
                        <td style={{fontWeight:600,color:COLORS[r.asset||r.query]||'var(--text)'}}>{r.asset||r.query}</td>
                        <td><span className={`pill pill-${r.decision?.toLowerCase()}`}>{r.decision}</span></td>
                        <td className="mono" style={{color:'var(--text2)',fontSize:11}}>{f2(r.quant_confidence)}</td>
                        <td className="mono" style={{color:'var(--text2)',fontSize:11}}>{f2(r.visionary_confidence)}</td>
                        <td style={{color:'var(--text2)',fontSize:11,maxWidth:200,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{r.reason?.slice(0,45)}</td>
                      </motion.tr>
                    ))}
                  </AnimatePresence>
                </tbody>
              </table>
            </div>
          )}

          {tab==='security' && (
            <div className="card" style={{padding:'16px'}}>
              <p style={{fontWeight:600,marginBottom:14}}>Valid(M) — Six-Condition Invariant</p>
              {[
                {n:1,l:'Challenge Binding',d:'SHA-256 mandate hash'},
                {n:2,l:'WebAuthn UV=required',d:'Biometric hardware sign-off'},
                {n:3,l:'TEE Attestation',d:'Simulated SGX enclave'},
                {n:4,l:'Oracle Consensus',d:'yfinance dual-sample δ≤0.5%'},
                {n:5,l:'Atomic Quota Lock',d:'Thread-safe TOCTOU fix'},
                {n:6,l:'Revocation Registry',d:'Instant kill switch active'},
              ].map(c=>(
                <div key={c.n} style={{display:'flex',gap:10,padding:'8px 0',borderBottom:'1px solid var(--border)'}}>
                  <div style={{width:22,height:22,borderRadius:4,background:'rgba(38,166,154,.12)',border:'1px solid rgba(38,166,154,.3)',display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0}}>
                    <span style={{fontSize:10,fontWeight:700,color:'var(--green)'}}>{c.n}</span>
                  </div>
                  <div style={{flex:1}}>
                    <p style={{fontSize:12,fontWeight:500}}>{c.l}</p>
                    <p style={{fontSize:11,color:'var(--text2)'}}>{c.d}</p>
                  </div>
                  <span style={{color:'var(--green)',fontSize:14}}>✓</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Status bar */}
      <div style={{height:24,background:'var(--bg1)',borderTop:'1px solid var(--border)',display:'flex',alignItems:'center',padding:'0 12px',gap:16,flexShrink:0}}>
        {[{l:'APEE Trading',c:'var(--blue)'},{l:`Cycle #${state?.cycle||0}`,c:'var(--text2)'},{l:'LIVE',c:'var(--green)'},
          {l:`${Object.keys(pos).length} positions`,c:'var(--text2)'},{l:`${gate.execute_rate||0}% execute rate`,c:'var(--text2)'},
          {l:new Date().toLocaleTimeString(),c:'var(--text3)'}
        ].map((it,i)=><span key={i} className="mono" style={{fontSize:11,color:it.c}}>{it.l}</span>)}
      </div>
    </div>
  )
}

// ── Shopping dashboard ────────────────────────────────────────────────────────
function ShoppingDashboard({ state, gateHistory }) {
  const wishlist  = state?.wishlist   || []
  const gate      = state?.gate_stats || {}
  const decisions = (gateHistory||[]).filter(r=>r.decision==='EXECUTE')

  return (
    <div style={{display:'flex',flexDirection:'column',height:'100%'}}>
      <div style={{padding:'12px 16px',borderBottom:'1px solid var(--border)',display:'flex',alignItems:'center',justifyContent:'space-between',background:'var(--bg1)'}}>
        <div style={{display:'flex',alignItems:'center',gap:10}}>
          <span style={{fontSize:18}}>🛒</span>
          <div><p style={{fontWeight:600}}>APEE Shopping</p><p style={{fontSize:11,color:'var(--text2)'}}>Price monitoring active</p></div>
        </div>
        <div style={{display:'flex',gap:20}}>
          {[{l:'Watching',v:wishlist.length},{l:'Alerts',v:decisions.length},{l:'Cycle',v:`#${state?.cycle||0}`}].map(s=>(
            <div key={s.l} style={{textAlign:'center'}}>
              <p style={{fontSize:10,color:'var(--text2)'}}>{s.l}</p>
              <p className="mono" style={{fontSize:14,fontWeight:600,color:'var(--cyan)'}}>{s.v}</p>
            </div>
          ))}
        </div>
      </div>

      <div style={{flex:1,overflow:'auto',padding:'14px 16px'}}>
        {decisions.length>0 && (
          <div style={{marginBottom:14}}>
            <p style={{fontSize:11,color:'var(--text2)',textTransform:'uppercase',letterSpacing:'.06em',marginBottom:8}}>Buy Alerts</p>
            {decisions.slice(-3).reverse().map((d,i)=>(
              <motion.div key={i} initial={{opacity:0,x:-10}} animate={{opacity:1,x:0}}
                style={{background:'rgba(38,166,154,.06)',border:'1px solid rgba(38,166,154,.25)',borderRadius:8,padding:'12px 14px',marginBottom:8}}>
                <div style={{display:'flex',justifyContent:'space-between',marginBottom:4}}>
                  <span style={{fontWeight:600,color:'var(--green)'}}>🎯 BUY SIGNAL — {d.asset||d.query}</span>
                  <span style={{fontSize:11,color:'var(--text2)'}}>{ago(d.timestamp)}</span>
                </div>
                <p style={{fontSize:12,color:'var(--text2)'}}>{d.reason?.slice(0,100)}</p>
              </motion.div>
            ))}
          </div>
        )}

        <p style={{fontSize:11,color:'var(--text2)',textTransform:'uppercase',letterSpacing:'.06em',marginBottom:8}}>Watchlist</p>
        <div style={{display:'flex',flexDirection:'column',gap:8}}>
          {wishlist.map((item,i)=>(
            <div key={i} className="card" style={{padding:'14px 16px'}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:8}}>
                <div>
                  <p style={{fontWeight:600,fontSize:14,marginBottom:2}}>{item.product}</p>
                  <p style={{fontSize:11,color:'var(--text2)'}}>
                    ${item.min_price}–${item.max_price} (+{item.tax_pct}% tax) · {item.deadline_days} days
                  </p>
                </div>
                <div style={{display:'flex',alignItems:'center',gap:5,background:'rgba(41,98,255,.1)',border:'1px solid rgba(41,98,255,.25)',borderRadius:4,padding:'2px 8px'}}>
                  <motion.div animate={{opacity:[1,.3,1]}} transition={{duration:2,repeat:Infinity}} style={{width:5,height:5,borderRadius:'50%',background:'var(--blue)'}}/>
                  <span style={{fontSize:10,color:'#7aa4ff'}}>Watching</span>
                </div>
              </div>
              <div style={{height:3,borderRadius:2,background:'var(--bg3)',overflow:'hidden'}}>
                <motion.div initial={{width:0}} animate={{width:'45%'}} transition={{duration:1}} style={{height:'100%',background:'var(--blue)',borderRadius:2}}/>
              </div>
              <p style={{fontSize:10,color:'var(--text3)',marginTop:4}}>Monitoring every 30 minutes via SerpAPI + AI agents</p>
            </div>
          ))}
          {!wishlist.length && (
            <div style={{textAlign:'center',padding:40,color:'var(--text2)'}}>
              <p style={{fontSize:28,marginBottom:8}}>🔍</p>
              <p>Waiting for product data from backend...</p>
            </div>
          )}
        </div>

        <div className="card" style={{padding:'14px 16px',marginTop:14}}>
          <p style={{fontSize:11,color:'var(--text2)',marginBottom:10}}>Gate Performance</p>
          <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8}}>
            {[{l:'Buy Signals',v:gate.EXECUTE||0,c:'var(--green)'},{l:'Wait',v:gate.HOLD||0,c:'var(--yellow)'},{l:'Review',v:gate.REVIEW||0,c:'var(--red)'}].map(s=>(
              <div key={s.l} style={{background:'var(--bg3)',borderRadius:6,padding:'10px',textAlign:'center'}}>
                <p className="mono" style={{fontSize:20,fontWeight:700,color:s.c}}>{s.v}</p>
                <p style={{fontSize:10,color:'var(--text2)',marginTop:2}}>{s.l}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{height:24,background:'var(--bg1)',borderTop:'1px solid var(--border)',display:'flex',alignItems:'center',padding:'0 12px',gap:16,flexShrink:0}}>
        {[{l:'APEE Shopping',c:'var(--green)'},{l:`Cycle #${state?.cycle||0}`,c:'var(--text2)'},{l:'ACTIVE',c:'var(--green)'},
          {l:`${wishlist.length} products`,c:'var(--text2)'},{l:new Date().toLocaleTimeString(),c:'var(--text3)'}
        ].map((it,i)=><span key={i} className="mono" style={{fontSize:11,color:it.c}}>{it.l}</span>)}
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
    const iv = setInterval(fetchData, 8000)
    return () => clearInterval(iv)
  }, [fetchData])

  const approve = async id => {
    setApproving(true)
    try { await fetch('/api/mandate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mandate_id:id,action:'approve'})}) }
    finally { setApproving(false) }
  }
  const reject = async id => {
    await fetch('/api/mandate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mandate_id:id,action:'reject'})})
  }

  return (
    <div style={{height:'100vh',display:'flex',flexDirection:'column',background:'var(--bg)'}}>
      <AnimatePresence mode="wait">
        {mode==='chat' && (
          <motion.div key="chat" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} style={{flex:1,overflow:'hidden'}}>
            <ChatView onActivate={cfg=>setMode(cfg.mode==='trading'?'trading':'ecommerce')}/>
          </motion.div>
        )}
        {mode==='trading' && (
          <motion.div key="trading" initial={{opacity:0}} animate={{opacity:1}} style={{flex:1,overflow:'hidden'}}>
            <TradingDashboard state={data?.state} gateHistory={data?.gateHistory}
              portHistory={data?.portHistory} events={data?.events}
              onApprove={approve} onReject={reject} approving={approving}/>
          </motion.div>
        )}
        {mode==='ecommerce' && (
          <motion.div key="ecommerce" initial={{opacity:0}} animate={{opacity:1}} style={{flex:1,overflow:'hidden'}}>
            <ShoppingDashboard state={data?.state} gateHistory={data?.gateHistory}/>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
