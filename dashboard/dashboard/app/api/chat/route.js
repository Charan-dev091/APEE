import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const LOG_DIR     = process.env.APEE_LOGS || 'C:\\Users\\karra\\Downloads\\apee_unified\\apee_unified\\logs'
const CONFIG_PATH = path.join(LOG_DIR, 'app_config.json')
const RAG_PATH    = path.join(LOG_DIR, 'rag_query.json')
const RAG_RESULT  = path.join(LOG_DIR, 'rag_result.json')

function writeRAGQuery(messages) {
  try {
    if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true })
    fs.writeFileSync(RAG_PATH, JSON.stringify({ messages, timestamp: Date.now() }))
  } catch(e) {}
}

function readRAGResult(timeout = 8000) {
  return new Promise((resolve) => {
    const start = Date.now()
    const check = () => {
      try {
        if (fs.existsSync(RAG_RESULT)) {
          const data = JSON.parse(fs.readFileSync(RAG_RESULT, 'utf8'))
          if (Date.now() - data.processed_at < 15000) {
            fs.unlinkSync(RAG_RESULT)
            return resolve(data)
          }
        }
      } catch(e) {}
      if (Date.now() - start > timeout) return resolve(null)
      setTimeout(check, 200)
    }
    check()
  })
}

function writeConfig(config) {
  try {
    if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true })
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2))
  } catch(e) {}
}

function shoppingConfig(intent) {
  return {
    mode: 'ecommerce', interval_minutes: 30,
    budget: (intent.max_price || 500) * 3,
    wishlist: [{ id:1, product:intent.product, min_price:intent.min_price||0,
      max_price:intent.max_price||999, tax_pct:intent.tax_pct||8,
      deadline_days:intent.deadline_days||10, active:true }]
  }
}

function tradingConfig(intent) {
  return {
    mode:'trading', assets:intent.assets?.length?intent.assets:['NVDA','AAPL','TSLA'],
    initial_balance:intent.initial_balance||10000,
    interval_minutes:5, max_alloc:1000, daily_cap:3000,
  }
}

export async function POST(request) {
  const { messages, conversationState } = await request.json()
  const userMsgs = messages.filter(m => m.role === 'user')
  const lastMsg  = userMsgs[userMsgs.length-1]?.content || ''
  const lower    = lastMsg.toLowerCase()

  writeRAGQuery(messages)
  const rag = await readRAGResult(8000)

  if (rag && rag.confidence >= 0.7) {
    if (rag.mode === 'ecommerce' && rag.product && rag.max_price) {
      const maxTax = (rag.max_price*(1+(rag.tax_pct||8)/100)).toFixed(2)
      const config = shoppingConfig(rag)
      writeConfig(config)
      const rc   = rag.rag_context || {}
      const note = rc.matched_product && rc.relevance > 0.6
        ? `\n\n*RAG identified: ${rc.matched_product} — typical $${rc.suggested_min}–$${rc.suggested_max}*` : ''
      return NextResponse.json({
        message:`**Shopping Mode activated!** ✅\n\nProduct: **${rag.product}**\nRange: $${rag.min_price||0}–$${rag.max_price} (+${rag.tax_pct||8}% tax = $${maxTax})\nMonitor: ${rag.deadline_days||10} days${note}\n\nSwitching to dashboard...`,
        state:'activated', intent:'ecommerce', activate:true, config,
      })
    }
    if (rag.mode === 'ecommerce') {
      const rc  = rag.rag_context || {}
      const sug = rc.matched_product && rc.relevance > 0.5
        ? ` I found **${rc.matched_product}** (typical $${rc.suggested_min}–$${rc.suggested_max}).` : ''
      return NextResponse.json({
        message: !rag.max_price ? `What's your budget for **${rag.product||'this product'}**?${sug}` : `What product are you looking for?`,
        state:'ecommerce_collecting', intent:'ecommerce', product:rag.product,
      })
    }
    if (rag.mode === 'trading') {
      if (userMsgs.length > 1 || rag.assets?.length) {
        const config = tradingConfig(rag)
        writeConfig(config)
        return NextResponse.json({
          message:`**Trading Mode activated!** ✅\n\nMonitoring: **${config.assets.join(', ')}**\nBalance: $${config.initial_balance.toLocaleString()}\n\nSwitching to dashboard...`,
          state:'activated', intent:'trading', activate:true, config,
        })
      }
      return NextResponse.json({
        message:`I'll monitor **${rag.assets?.join(', ')||'NVDA, AAPL, TSLA'}**.\n\nWhat's your starting balance? (or say "default" for $10,000)`,
        state:'trading_collecting', intent:'trading',
      })
    }
  }

  const isTrading  = ['trade','stock','nvda','aapl','tsla','crypto','btc','invest'].some(k=>lower.includes(k))
  const isShopping = ['buy','find','track','price','under','sneaker','gpu','laptop','phone','monitor','keyboard','headphone','watch'].some(k=>lower.includes(k))

  if (userMsgs.length === 1) {
    if (isTrading) return NextResponse.json({ message:`Which assets? (NVDA, AAPL, TSLA, BTC etc.) Or say "default".\n\nStarting balance?`, state:'trading_collecting', intent:'trading' })
    if (isShopping) return NextResponse.json({ message:`What's your price range and tax rate?\n\nExample: *"$80–$120, 8% tax, 10 days"*`, state:'ecommerce_collecting', intent:'ecommerce' })
    return NextResponse.json({
      message:`Hi! I'm **APEE** — Autonomous Personal Economy Engine.\n\nI can help you:\n\n📈 **Trade stocks & crypto** — AI agents monitor and alert you\n🛒 **Track product prices** — Alert when price hits your target\n\nWhat would you like to do?`,
      state:'greeting',
    })
  }

  if (conversationState?.intent === 'trading') {
    const assets = ['NVDA','AAPL','TSLA','BTC','ETH','MSFT'].filter(a=>lower.includes(a.toLowerCase()))
    const config = tradingConfig({ assets:assets.length?assets:['NVDA','AAPL','TSLA'], initial_balance:10000 })
    writeConfig(config)
    return NextResponse.json({ message:`**Trading Mode activated!** ✅\n\nMonitoring: **${config.assets.join(', ')}**\n\nSwitching to dashboard...`, state:'activated', intent:'trading', activate:true, config })
  }

  if (conversationState?.intent === 'ecommerce') {
    const pr  = lastMsg.match(/\$?(\d+)\s*[-–]\s*\$?(\d+)/)
    const mx  = lastMsg.match(/(?:under|below|max)\s*\$?(\d+)/i)
    const tx  = lastMsg.match(/(\d+)\s*%/)
    const dy  = lastMsg.match(/(\d+)\s*days?/i)
    const max = pr?parseInt(pr[2]):mx?parseInt(mx[1]):null
    if (max) {
      const config = shoppingConfig({ product:conversationState.product||'Product', min_price:pr?parseInt(pr[1]):0, max_price:max, tax_pct:tx?parseInt(tx[1]):8, deadline_days:dy?parseInt(dy[1]):10 })
      writeConfig(config)
      return NextResponse.json({ message:`**Shopping Mode activated!** ✅\n\nTracking **${conversationState.product||'Product'}** up to $${max}\n\nSwitching to dashboard...`, state:'activated', intent:'ecommerce', activate:true, config })
    }
    return NextResponse.json({ message:`What's your price range? (e.g. "$80–$120" or "under $150")`, state:'ecommerce_collecting', intent:'ecommerce', product:conversationState.product })
  }

  return NextResponse.json({ message:`Try: *"Find New Balance 9060 under $120"* or *"Trade NVDA and TSLA"*`, state:'greeting' })
}
