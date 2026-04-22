import { NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

const BASE = process.env.APEE_LOGS || 'C:\\Users\\karra\\Downloads\\APEE\\logs'
const readJSON  = f => { try { const p=path.join(BASE,f); return fs.existsSync(p)?JSON.parse(fs.readFileSync(p,'utf8')):null } catch{return null} }
const readJSONL = (f,n=50) => { try { const p=path.join(BASE,f); return fs.existsSync(p)?fs.readFileSync(p,'utf8').split('\n').filter(Boolean).slice(-n).map(l=>JSON.parse(l)):[] } catch{return[]} }

export async function GET() {
  return NextResponse.json({
    state:       readJSON('state.json'),
    gateHistory: readJSONL('gate_decisions.jsonl', 30),
    portHistory: readJSONL('portfolio_history.jsonl', 60),
    events:      readJSONL('events.jsonl', 20),
  })
}
