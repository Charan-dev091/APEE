import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const LOG_DIR     = process.env.APEE_LOGS || 'C:\\Users\\karra\\Downloads\\APEE\\logs'
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
    wishlist: [{ id: 1, product: intent.product, min_price: intent.min_price || 0,
      max_price: intent.max_price || 999, tax_pct: intent.tax_pct || 8,
      deadline_days: intent.deadline_days || 10, active: true }]
  }
}

function tradingConfig(intent) {
  return {
    mode: 'trading', assets: intent.assets?.length ? intent.assets : ['NVDA','AAPL','TSLA'],
    initial_balance: intent.initial_balance || 10000,
    interval_minutes: 5, max_alloc: 1000, daily_cap: 3000,
  }
}

// ── Trading Parsers ───────────────────────────────────────────────────────────

const KNOWN_ASSETS = ['NVDA','AAPL','TSLA','BTC','ETH','MSFT','AMZN','GOOGL','META','SOL','BNB','XRP','ADA','DOT']

/**
 * Extract known ticker symbols from any message.
 * Splits on non-alphanumeric chars for exact whole-word matching.
 * Avoids false positives like "META" in "metadata".
 */
function parseAssets(msg) {
  const words = msg.toUpperCase().split(/[^A-Z0-9]+/)
  return KNOWN_ASSETS.filter(a => words.includes(a))
}

/**
 * Extract initial balance from message.
 * Handles: $5000 | $5,000 | 5000 balance | balance $20000 | starting 15000
 */
function parseBalance(msg) {
  const patterns = [
    /\$\s*(\d[\d,]+)/,                                    // $5000 or $5,000
    /(\d[\d,]+)\s*(?:dollars?|usd)\b/i,                   // 5000 dollars
    /(?:balance|starting|capital|fund)\s*[=:]?\s*\$?\s*(\d[\d,]+)/i,  // balance $5000
    /\$?\s*(\d[\d,]+)\s*(?:balance|starting|capital)/i,   // $5000 balance
  ]
  for (const re of patterns) {
    const m = msg.match(re)
    if (m) {
      const val = parseInt(m[1].replace(/,/g, ''))
      if (val >= 100) return val  // ignore small numbers like "15" minutes
    }
  }
  return null
}

/**
 * Parse full trading intent from a message.
 * Returns assets, balance, and whether we have enough to activate.
 */
function parseTradingMessage(msg) {
  const assets  = parseAssets(msg)
  const balance = parseBalance(msg)
  const isDefault = /\bdefault\b/i.test(msg)
  return {
    assets,
    initial_balance: balance || 10000,
    hasAssets:  assets.length > 0,
    isDefault,
    canActivate: assets.length > 0 || isDefault,
  }
}

// ── Smart Parsers ─────────────────────────────────────────────────────────────

/**
 * Extract price range from message.
 * Handles ALL formats:
 *   $80-$100  |  80$-100$  |  80-100  |  80 to 100
 *   price range 80$-100$  |  between 80 and 100
 */
function parsePriceRange(msg) {
  // Pattern: any combo of optional $, digits, optional $, separator, optional $, digits, optional $
  const patterns = [
    /(?:price\s*range|range|between)\s*\$?(\d+(?:\.\d+)?)\$?\s*[-–to]+\s*\$?(\d+(?:\.\d+)?)\$?/i,
    /\$?(\d+(?:\.\d+)?)\$?\s*[-–]\s*\$?(\d+(?:\.\d+)?)\$?/,
    /(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)/i,
  ]
  for (const re of patterns) {
    const m = msg.match(re)
    if (m) {
      const a = parseFloat(m[1]), b = parseFloat(m[2])
      return { min: Math.min(a, b), max: Math.max(a, b) }
    }
  }
  return null
}

/**
 * Extract maximum/budget price.
 * Handles: under $150 | below 150 | max $120 | up to 200 | budget 300
 */
function parseMaxPrice(msg) {
  const m = msg.match(/(?:under|below|max(?:imum)?|up\s*to|at\s*most|budget|within)\s*\$?(\d+(?:\.\d+)?)\$?/i)
  return m ? parseFloat(m[1]) : null
}

/**
 * Extract tax percentage.
 * Handles: 8% | 8% tax | + 8% | plus 8 percent
 */
function parseTax(msg) {
  const m = msg.match(/[+]?\s*(\d+(?:\.\d+)?)\s*(?:%|percent)\s*(?:tax)?/i)
         || msg.match(/tax\s*(?:of\s*)?\$?(\d+(?:\.\d+)?)\s*%?/i)
  return m ? parseFloat(m[1]) : null
}

/**
 * Extract deadline in days.
 * Handles: 10 days | next 10 days | for 10 days | within 2 weeks
 */
function parseDays(msg) {
  const d = msg.match(/(?:next|for|within)?\s*(\d+)\s*days?/i)
  if (d) return parseInt(d[1])
  const w = msg.match(/(?:next|for|within)?\s*(\d+)\s*weeks?/i)
  if (w) return parseInt(w[1]) * 7
  return null
}

/**
 * Extract product name from a multi-line or comma-separated message.
 * Takes the first meaningful line, strips price/tax/size/color noise.
 */
function extractProduct(msg) {
  // Take first line as the product line
  const firstLine = msg.split(/\n/)[0].trim()

  let product = firstLine
    // Remove price ranges like $80-$100 or 80$-100$
    .replace(/\$?\d+(?:\.\d+)?\$?\s*[-–]\s*\$?\d+(?:\.\d+)?\$?/g, '')
    // Remove "under/max/up to $X"
    .replace(/(?:under|below|max(?:imum)?|up\s*to)\s*\$?\d+/gi, '')
    // Remove tax pattern: +8% tax, 8%, 8% tax
    .replace(/[+\s]*\d+\s*%\s*(?:tax)?/gi, '')
    // Remove "for next X days"
    .replace(/(?:for\s+)?(?:next\s+)?\d+\s*days?/gi, '')
    // Remove color/size details
    .replace(/color\s*:\s*[^,\n]*/gi, '')
    .replace(/\bsize\s+\d+[a-z]?\b/gi, '')
    // Remove "price range" prefix
    .replace(/price\s*range/gi, '')
    // Remove trailing junk
    .replace(/[\s,;+]+$/, '')
    .trim()

  // If first line was empty after cleanup, try to find product keywords
  if (!product || product.length < 3) {
    const lines = msg.split(/\n/)
    for (const line of lines) {
      const cleaned = line.replace(/\$\d+|\d+\$|\d+%/g, '').trim()
      if (cleaned.length > 4) { product = cleaned; break }
    }
  }

  return product || null
}

/**
 * Parse ALL ecommerce intent from a single message.
 * Returns null if no clear ecommerce signal found.
 */
function parseEcommerceMessage(msg) {
  const range   = parsePriceRange(msg)
  const maxOnly = parseMaxPrice(msg)
  const tax     = parseTax(msg)
  const days    = parseDays(msg)
  const product = extractProduct(msg)

  const max = range?.max ?? maxOnly
  const min = range?.min ?? 0

  return {
    product,
    min_price:     min,
    max_price:     max,
    tax_pct:       tax ?? 8,
    deadline_days: days ?? 10,
    hasPrice:      max != null,
    hasProduct:    product != null && product.length > 2,
  }
}

// ── Main Handler ──────────────────────────────────────────────────────────────

export async function POST(request) {
  const { messages, conversationState } = await request.json()
  const userMsgs = messages.filter(m => m.role === 'user')
  const lastMsg  = userMsgs[userMsgs.length - 1]?.content || ''
  const lower    = lastMsg.toLowerCase()

  // Combine all user messages for context
  const allUserText = userMsgs.map(m => m.content).join('\n')

  writeRAGQuery(messages)
  const rag = await readRAGResult(3000)   // reduced timeout — don't block UI

  // ── RAG fast-path ─────────────────────────────────────────────────────────
  if (rag && rag.confidence >= 0.7) {
    if (rag.mode === 'ecommerce' && rag.product && rag.max_price) {
      const maxTax = (rag.max_price * (1 + (rag.tax_pct || 8) / 100)).toFixed(2)
      const config = shoppingConfig(rag)
      writeConfig(config)
      const rc   = rag.rag_context || {}
      const note = rc.matched_product && rc.relevance > 0.6
        ? `\n\n*RAG: ${rc.matched_product} — typical $${rc.suggested_min}–$${rc.suggested_max}*` : ''
      return NextResponse.json({
        message: `**Shopping Mode activated!** ✅\n\nProduct: **${rag.product}**\nRange: $${rag.min_price || 0}–$${rag.max_price} (+${rag.tax_pct || 8}% tax = $${maxTax})\nMonitor: ${rag.deadline_days || 10} days${note}\n\nSwitching to dashboard...`,
        state: 'activated', intent: 'ecommerce', activate: true, config,
      })
    }
    if (rag.mode === 'trading' && (userMsgs.length > 1 || rag.assets?.length)) {
      const config = tradingConfig(rag)
      writeConfig(config)
      return NextResponse.json({
        message: `**Trading Mode activated!** ✅\n\nMonitoring: **${config.assets.join(', ')}**\nBalance: $${config.initial_balance.toLocaleString()}\n\nSwitching to dashboard...`,
        state: 'activated', intent: 'trading', activate: true, config,
      })
    }
  }

  // ── Detect intent keywords ─────────────────────────────────────────────────
  const isTrading  = ['trade','stock','nvda','aapl','tsla','crypto','btc','eth','invest','market'].some(k => lower.includes(k))
  const isShopping = ['buy','find','track','price','under','sneaker','shoe','gpu','laptop','phone','monitor','keyboard','headphone','watch','balance','jordan','nike','adidas','console','ps5','xbox'].some(k => lower.includes(k))

  // ── Always attempt smart parse on any message ─────────────────────────────
  const parsed = parseEcommerceMessage(allUserText)

  // If we have both product + price anywhere in conversation → activate immediately
  if ((conversationState?.intent === 'ecommerce' || isShopping) && parsed.hasPrice) {
    const product = parsed.product
                 || conversationState?.product
                 || 'Product'

    const config = shoppingConfig({ ...parsed, product })
    writeConfig(config)

    const taxTotal = (parsed.max_price * (1 + parsed.tax_pct / 100)).toFixed(2)
    return NextResponse.json({
      message: `**Shopping Mode activated!** ✅\n\nTracking: **${product}**\nPrice range: $${parsed.min_price}–$${parsed.max_price} (+${parsed.tax_pct}% tax = **$${taxTotal}**)\nDuration: ${parsed.deadline_days} days\n\nSwitching to dashboard...`,
      state: 'activated', intent: 'ecommerce', activate: true, config,
    })
  }

  // ── First message ──────────────────────────────────────────────────────────
  if (userMsgs.length === 1) {
    if (isTrading) {
      const tp = parseTradingMessage(lastMsg)

      // User already gave assets or said "default" → activate immediately
      if (tp.canActivate) {
        const config = tradingConfig(tp)
        writeConfig(config)
        const balStr = tp.initial_balance !== 10000
          ? `$${tp.initial_balance.toLocaleString()}`
          : `$10,000 (default)`
        return NextResponse.json({
          message: `**Trading Mode activated!** ✅\n\nMonitoring: **${config.assets.join(', ')}**\nStarting balance: ${balStr}\n\nSwitching to dashboard...`,
          state: 'activated', intent: 'trading', activate: true, config,
        })
      }

      // No assets yet → ask for them
      return NextResponse.json({
        message: `Which assets would you like to monitor?\n\nExamples:\n• *"NVDA, AAPL, TSLA"*\n• *"BTC and ETH with $5,000"*\n• *"default"* → NVDA, AAPL, TSLA · $10,000`,
        state: 'trading_collecting', intent: 'trading',
      })
    }
    if (isShopping && parsed.hasProduct && !parsed.hasPrice) {
      return NextResponse.json({
        message: `Got it — **${parsed.product}**!\n\nWhat's your price range and tax rate?\nExample: *"$80–$120, 8% tax, 10 days"*`,
        state: 'ecommerce_collecting', intent: 'ecommerce', product: parsed.product,
      })
    }
    if (isShopping) {
      return NextResponse.json({
        message: `What product are you looking for and what's your budget?\n\nExample: *"New Balance 9060 under $120, 8% tax, 10 days"*`,
        state: 'ecommerce_collecting', intent: 'ecommerce',
      })
    }
    return NextResponse.json({
      message: `Hi! I'm **APEE** — Autonomous Personal Economy Engine.\n\nI can help you:\n\n📈 **Trade stocks & crypto** — AI agents monitor markets and alert you\n🛒 **Track product prices** — Get alerted when price hits your target\n\nWhat would you like to do?`,
      state: 'greeting',
    })
  }

  // ── Follow-up in trading flow ──────────────────────────────────────────────
  if (conversationState?.intent === 'trading') {
    const tp = parseTradingMessage(lastMsg)

    // "default" → activate with defaults
    if (tp.isDefault && !tp.hasAssets) {
      const config = tradingConfig({ assets: ['NVDA','AAPL','TSLA'], initial_balance: 10000 })
      writeConfig(config)
      return NextResponse.json({
        message: `**Trading Mode activated!** ✅\n\nMonitoring: **NVDA, AAPL, TSLA** (defaults)\nBalance: **$10,000**\n\nSwitching to dashboard...`,
        state: 'activated', intent: 'trading', activate: true, config,
      })
    }

    // Use parsed assets + balance, fall back to defaults for each
    const assets  = tp.hasAssets ? tp.assets : ['NVDA','AAPL','TSLA']
    const balance = tp.initial_balance
    const config  = tradingConfig({ assets, initial_balance: balance })
    writeConfig(config)

    const balStr = balance !== 10000
      ? `$${balance.toLocaleString()}`
      : `$10,000 (default)`
    return NextResponse.json({
      message: `**Trading Mode activated!** ✅\n\nMonitoring: **${config.assets.join(', ')}**\nBalance: ${balStr}\n\nSwitching to dashboard...`,
      state: 'activated', intent: 'trading', activate: true, config,
    })
  }

  // ── Follow-up in ecommerce flow — ask only what's missing ─────────────────
  if (conversationState?.intent === 'ecommerce') {
    // Re-parse just the latest message for any new info
    const latest = parseEcommerceMessage(lastMsg)
    const product = latest.product || conversationState?.product || parsed.product

    if (!product || product.length < 3) {
      return NextResponse.json({
        message: `What product are you looking for?\n\nExample: *"New Balance 9060 Kids"*`,
        state: 'ecommerce_collecting', intent: 'ecommerce',
      })
    }
    if (!latest.hasPrice && !parsed.hasPrice) {
      return NextResponse.json({
        message: `What's your price range for **${product}**?\n\nExample: *"$80–$120, 8% tax, 10 days"*`,
        state: 'ecommerce_collecting', intent: 'ecommerce', product,
      })
    }

    // Have both product + price → activate
    const finalParsed = latest.hasPrice ? latest : parsed
    const config = shoppingConfig({ ...finalParsed, product })
    writeConfig(config)
    const taxTotal = (finalParsed.max_price * (1 + finalParsed.tax_pct / 100)).toFixed(2)
    return NextResponse.json({
      message: `**Shopping Mode activated!** ✅\n\nTracking: **${product}**\nPrice range: $${finalParsed.min_price}–$${finalParsed.max_price} (+${finalParsed.tax_pct}% tax = **$${taxTotal}**)\nDuration: ${finalParsed.deadline_days} days\n\nSwitching to dashboard...`,
      state: 'activated', intent: 'ecommerce', activate: true, config,
    })
  }

  // ── Catch-all ──────────────────────────────────────────────────────────────
  return NextResponse.json({
    message: `Try:\n• *"Track New Balance 9060 under $120, 8% tax"*\n• *"Trade NVDA and TSLA"*`,
    state: 'greeting',
  })
}
