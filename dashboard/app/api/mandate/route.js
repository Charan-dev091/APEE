import { NextResponse } from 'next/server'
const WEBHOOK = process.env.APEE_WEBHOOK || 'http://localhost:8766'
export async function POST(req) {
  const { mandate_id, action } = await req.json()
  try {
    const res = await fetch(`${WEBHOOK}/mandate/${action}`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ mandate_id, signature:'dashboard_approved' }),
    })
    return NextResponse.json(await res.json())
  } catch(e) { return NextResponse.json({ success:false, error:e.message }, {status:500}) }
}
