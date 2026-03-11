'use client'
import { useState, useEffect, useCallback } from 'react'

// Design system — white/indigo, Stripe/Linear aesthetic
const C = {
  bg:       '#ffffff',
  surface:  '#f8fafc',
  card:     '#ffffff',
  border:   '#e2e8f0',
  borderHover: '#cbd5e1',
  accent:   '#4f46e5',
  accentL:  '#eef2ff',
  accentD:  '#3730a3',
  green:    '#10b981',
  greenL:   '#ecfdf5',
  red:      '#ef4444',
  redL:     '#fef2f2',
  yellow:   '#f59e0b',
  yellowL:  '#fffbeb',
  blue:     '#3b82f6',
  blueL:    '#eff6ff',
  text:     '#0f172a',
  sub:      '#64748b',
  muted:    '#94a3b8',
  tabBg:    '#f1f5f9',
}

const S = {
  page:     { minHeight:'100vh', background:C.bg, color:C.text, fontFamily:"'Inter',system-ui,sans-serif" },
  topbar:   { background:C.card, borderBottom:`1px solid ${C.border}`, padding:'0 32px', display:'flex', alignItems:'center', justifyContent:'space-between', height:'56px', position:'sticky', top:0, zIndex:100 },
  logo:     { fontSize:'18px', fontWeight:700, color:C.text, letterSpacing:'-0.02em' },
  logoDot:  { color:C.accent },
  badge:    { background:C.accentL, color:C.accent, fontSize:'11px', fontWeight:600, padding:'2px 8px', borderRadius:'999px' },
  body:     { padding:'32px', maxWidth:'1200px', margin:'0 auto' },
  tabs:     { display:'flex', gap:'4px', background:C.tabBg, padding:'4px', borderRadius:'10px', marginBottom:'32px', width:'fit-content' },
  tab:      { padding:'7px 16px', borderRadius:'7px', fontSize:'13px', fontWeight:500, cursor:'pointer', border:'none', background:'transparent', color:C.sub, transition:'all 0.15s' },
  tabActive:{ padding:'7px 16px', borderRadius:'7px', fontSize:'13px', fontWeight:600, cursor:'pointer', border:'none', background:C.card, color:C.text, boxShadow:'0 1px 3px rgba(0,0,0,0.1)', transition:'all 0.15s' },
  grid4:    { display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:'16px', marginBottom:'24px' },
  grid3:    { display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:'16px', marginBottom:'24px' },
  grid2:    { display:'grid', gridTemplateColumns:'1fr 1fr', gap:'16px', marginBottom:'24px' },
  card:     { background:C.card, border:`1px solid ${C.border}`, borderRadius:'12px', padding:'24px' },
  cardHd:   { fontSize:'13px', fontWeight:600, color:C.sub, textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:'16px' },
  kpi:      { background:C.card, border:`1px solid ${C.border}`, borderRadius:'12px', padding:'20px 24px' },
  kpiLabel: { fontSize:'12px', fontWeight:500, color:C.sub, marginBottom:'6px' },
  kpiVal:   { fontSize:'28px', fontWeight:700, color:C.text, letterSpacing:'-0.02em', lineHeight:1 },
  kpiSub:   { fontSize:'12px', color:C.muted, marginTop:'4px' },
  dot:      (color) => ({ width:'7px', height:'7px', borderRadius:'50%', background:color, display:'inline-block', marginRight:'6px' }),
  pill:     (color, bg) => ({ background:bg, color:color, fontSize:'11px', fontWeight:600, padding:'2px 8px', borderRadius:'999px', display:'inline-block' }),
  row:      { display:'flex', alignItems:'center', gap:'8px' },
  divider:  { borderTop:`1px solid ${C.border}`, margin:'16px 0' },
  th:       { padding:'10px 16px', fontSize:'11px', fontWeight:600, color:C.sub, textTransform:'uppercase', letterSpacing:'0.06em', borderBottom:`1px solid ${C.border}`, textAlign:'left', background:C.surface },
  td:       { padding:'12px 16px', fontSize:'13px', color:C.text, borderBottom:`1px solid ${C.border}` },
  btn:      { background:C.accent, color:'#fff', border:'none', borderRadius:'8px', padding:'9px 18px', fontSize:'13px', fontWeight:600, cursor:'pointer' },
  btnGhost: { background:'transparent', color:C.accent, border:`1px solid ${C.accent}`, borderRadius:'8px', padding:'8px 16px', fontSize:'13px', fontWeight:600, cursor:'pointer' },
  input:    { border:`1px solid ${C.border}`, borderRadius:'8px', padding:'9px 14px', fontSize:'13px', color:C.text, background:C.card, outline:'none', width:'100%', boxSizing:'border-box' },
  section:  { marginBottom:'24px' },
  empty:    { textAlign:'center', color:C.muted, padding:'48px 0', fontSize:'14px' },
  logLine:  { fontFamily:'monospace', fontSize:'12px', color:C.sub, padding:'4px 0', borderBottom:`1px solid ${C.border}` },
}

function KPI({ label, value, sub, color }) {
  return (
    <div style={S.kpi}>
      <div style={S.kpiLabel}>{label}</div>
      <div style={{ ...S.kpiVal, color: color || C.text }}>{value ?? '—'}</div>
      {sub && <div style={S.kpiSub}>{sub}</div>}
    </div>
  )
}

function Card({ title, children, action }) {
  return (
    <div style={S.card}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'16px' }}>
        <div style={S.cardHd}>{title}</div>
        {action}
      </div>
      {children}
    </div>
  )
}

function StatusDot({ ok }) {
  return <span style={S.dot(ok ? C.green : C.red)} />
}

// ── TABS ────────────────────────────────────────────────────────────────────

function OverviewTab({ data }) {
  const u = data?.users || {}
  const r = data?.revenue || {}
  const i = data?.investigations || {}
  const e = data?.engine || {}

  return (
    <>
      <div style={S.grid4}>
        <KPI label="Total Users"      value={u.total?.toLocaleString()}       sub={`${u.active24h || 0} active today`} />
        <KPI label="Total Searches"   value={u.totalSearches?.toLocaleString()} sub="all time" />
        <KPI label="MRR"              value={r.mrr ? `$${r.mrr.toLocaleString()}` : '$0'} color={C.accent} sub="monthly recurring" />
        <KPI label="Active Cases"     value={i.active ?? 0} sub={`${i.total || 0} total`} />
      </div>
      <div style={S.grid3}>
        <KPI label="Pro Users"        value={u.byTier?.pro?.count ?? 0}        sub="paid tier" color={C.accent} />
        <KPI label="Business Users"   value={u.byTier?.business?.count ?? 0}   sub="enterprise tier" color={C.blue} />
        <KPI label="Free Users"       value={u.byTier?.free?.count ?? 0}       sub="free tier" />
      </div>
      <div style={S.grid2}>
        <Card title="Engine Status">
          <div style={{ display:'flex', flexDirection:'column', gap:'12px' }}>
            {[
              { label:'OSINT Modules', val: e.modules ?? 29 },
              { label:'Avg Report Cost', val: e.avgCost ? `$${e.avgCost}` : '~$0.05' },
              { label:'Reports Run', val: e.totalReports ?? 0 },
              { label:'Bot Status', val: data?.bot?.running ? 'Running' : 'Offline' },
            ].map(r => (
              <div key={r.label} style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <span style={{ fontSize:'13px', color:C.sub }}>{r.label}</span>
                <span style={{ fontSize:'13px', fontWeight:600, color:C.text }}>{r.val}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Revenue Breakdown">
          {r.byTier ? (
            <div style={{ display:'flex', flexDirection:'column', gap:'12px' }}>
              {Object.entries(r.byTier).map(([tier, amt]) => (
                <div key={tier} style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                  <span style={{ fontSize:'13px', color:C.sub, textTransform:'capitalize' }}>{tier}</span>
                  <span style={{ fontSize:'13px', fontWeight:600 }}>${(amt||0).toLocaleString()}</span>
                </div>
              ))}
            </div>
          ) : <div style={S.empty}>No revenue data</div>}
        </Card>
      </div>
    </>
  )
}

function UsersTab({ data }) {
  const u = data?.users || {}
  const users = data?.userList || []

  return (
    <>
      <div style={S.grid4}>
        <KPI label="Total Users"   value={u.total?.toLocaleString()} />
        <KPI label="Active 24h"    value={u.active24h ?? 0} color={C.green} />
        <KPI label="Active 7d"     value={u.active7d ?? 0} />
        <KPI label="Total Searches" value={u.totalSearches?.toLocaleString()} />
      </div>
      <Card title="User Directory">
        {users.length > 0 ? (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr>
                {['ID','Tier','Searches','Last Seen','Status'].map(h => <th key={h} style={S.th}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {users.map((u, i) => (
                <tr key={i}>
                  <td style={S.td}><code style={{ fontSize:'12px', color:C.accent }}>{u.id || u.user_id || '—'}</code></td>
                  <td style={S.td}><span style={S.pill(u.tier==='pro'?C.accent:u.tier==='business'?C.blue:C.sub, u.tier==='pro'?C.accentL:u.tier==='business'?C.blueL:C.surface)}>{u.tier||'free'}</span></td>
                  <td style={S.td}>{(u.total_searches||0).toLocaleString()}</td>
                  <td style={S.td} >{u.last_seen ? new Date(u.last_seen*1000).toLocaleDateString() : '—'}</td>
                  <td style={S.td}><StatusDot ok={u.active} />{u.active ? 'Active' : 'Inactive'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div style={S.empty}>No users yet</div>}
      </Card>
    </>
  )
}

function CostsTab({ data }) {
  const c = data?.costs || {}

  return (
    <>
      <div style={S.grid4}>
        <KPI label="Today"     value={c.today    ? `$${c.today.toFixed(4)}`    : '$0.00'} />
        <KPI label="This Week" value={c.week     ? `$${c.week.toFixed(2)}`     : '$0.00'} />
        <KPI label="This Month" value={c.month   ? `$${c.month.toFixed(2)}`   : '$0.00'} color={C.accent} />
        <KPI label="All Time"  value={c.allTime  ? `$${c.allTime.toFixed(2)}` : '$0.00'} />
      </div>
      <Card title="Cost Breakdown by Model">
        {c.byModel && Object.keys(c.byModel).length > 0 ? (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr>{['Model','Calls','Total Cost','Avg/Call'].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {Object.entries(c.byModel).map(([model, d], i) => (
                <tr key={i}>
                  <td style={S.td}><code style={{ fontSize:'12px' }}>{model}</code></td>
                  <td style={S.td}>{(d.calls||0).toLocaleString()}</td>
                  <td style={S.td}>${(d.total||0).toFixed(4)}</td>
                  <td style={S.td}>${d.calls ? (d.total/d.calls).toFixed(5) : '0.00000'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div style={S.empty}>No cost data yet</div>}
      </Card>
    </>
  )
}

function FeaturesTab({ data }) {
  const f = data?.features || {}
  const flags = data?.featureList || []

  return (
    <>
      <div style={S.grid3}>
        <KPI label="Total Flags"   value={flags.length} />
        <KPI label="Enabled"       value={flags.filter(f=>f.enabled).length} color={C.green} />
        <KPI label="Disabled"      value={flags.filter(f=>!f.enabled).length} color={C.red} />
      </div>
      <Card title="Feature Flags">
        {flags.length > 0 ? (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr>{['Feature','Status','Description','Last Updated'].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {flags.map((f, i) => (
                <tr key={i}>
                  <td style={S.td}><code style={{ fontSize:'12px', color:C.accent }}>{f.name||f.key||'—'}</code></td>
                  <td style={S.td}>
                    <span style={S.pill(f.enabled?C.green:C.red, f.enabled?C.greenL:C.redL)}>
                      {f.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </td>
                  <td style={S.td} style={{ color:C.sub, fontSize:'12px' }}>{f.description||'—'}</td>
                  <td style={S.td}>{f.updated_at ? new Date(f.updated_at).toLocaleDateString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div style={S.empty}>No feature flags configured</div>}
      </Card>
    </>
  )
}

function SourcesTab({ data }) {
  const sources = data?.sourceList || []

  return (
    <>
      <div style={S.grid3}>
        <KPI label="Total Sources" value={sources.length} />
        <KPI label="Online"        value={sources.filter(s=>s.status==='online'||s.ok).length} color={C.green} />
        <KPI label="Offline"       value={sources.filter(s=>s.status==='offline'||s.ok===false).length} color={C.red} />
      </div>
      <Card title="Data Sources">
        {sources.length > 0 ? (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr>{['Source','Type','Status','Last Check'].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {sources.map((s, i) => (
                <tr key={i}>
                  <td style={S.td}><strong style={{ fontSize:'13px' }}>{s.name||'—'}</strong></td>
                  <td style={S.td}><span style={S.pill(C.blue, C.blueL)}>{s.type||'api'}</span></td>
                  <td style={S.td}><StatusDot ok={s.ok||s.status==='online'} />{s.status||'unknown'}</td>
                  <td style={S.td}>{s.last_check ? new Date(s.last_check*1000).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div style={S.empty}>No sources configured</div>}
      </Card>
    </>
  )
}

function DiscoveryTab({ data }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(data?.discoveryList || [])
  const [loading, setLoading] = useState(false)

  async function search() {
    if (!query.trim()) return
    setLoading(true)
    try {
      const r = await fetch(`/api/herkulio/discovery?q=${encodeURIComponent(query)}`)
      const d = await r.json()
      setResults(d.results || [])
    } catch(e) { console.error(e) }
    setLoading(false)
  }

  return (
    <>
      <Card title="Dealer Discovery">
        <div style={{ display:'flex', gap:'10px', marginBottom:'20px' }}>
          <input
            style={S.input}
            placeholder="Search dealers, companies, people..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key==='Enter' && search()}
          />
          <button style={S.btn} onClick={search} disabled={loading}>
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
        {results.length > 0 ? (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr>{['Name','Location','Type','Source','Risk'].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i}>
                  <td style={S.td}><strong>{r.name||'—'}</strong></td>
                  <td style={S.td} style={{ color:C.sub }}>{r.location||r.city||'—'}</td>
                  <td style={S.td}>{r.type||'dealer'}</td>
                  <td style={S.td}><code style={{ fontSize:'11px' }}>{r.source||'—'}</code></td>
                  <td style={S.td}>
                    <span style={S.pill(
                      r.risk==='high'?C.red:r.risk==='medium'?C.yellow:C.green,
                      r.risk==='high'?C.redL:r.risk==='medium'?C.yellowL:C.greenL
                    )}>{r.risk||'low'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div style={S.empty}>Enter a search query above</div>}
      </Card>
    </>
  )
}

function InvestigateTab({ data }) {
  const [target, setTarget] = useState('')
  const [type, setType] = useState('auto')
  const [depth, setDepth] = useState('standard')
  const [state, setState] = useState('')
  const [notes, setNotes] = useState('')
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState([])

  async function investigate() {
    if (!target.trim()) return
    setRunning(true)
    setLogs([{ ts: new Date().toISOString(), level: 'info', msg: `🔍 Starting investigation: ${target}` }])
    
    try {
      const res = await fetch('/api/herkulio/investigate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target, type, depth, state, notes })
      })
      const d = await res.json()
      setLogs(prev => [...prev, { ts: new Date().toISOString(), level: 'success', msg: `Investigation started: ${d.status}` }])
    } catch(e) {
      setLogs(prev => [...prev, { ts: new Date().toISOString(), level: 'error', msg: e.message }])
    }
    setRunning(false)
  }

  return (
    <>
      <Card title="New Investigation">
        <div style={{ display:'flex', flexDirection:'column', gap:'16px' }}>
          <div>
            <label style={{ fontSize:'12px', color:C.sub, marginBottom:'6px', display:'block' }}>Target</label>
            <input style={S.input} placeholder="Name, company, phone, email, or domain..." value={target} onChange={e=>setTarget(e.target.value)} />
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:'12px' }}>
            <div>
              <label style={{ fontSize:'12px', color:C.sub, marginBottom:'6px', display:'block' }}>Type</label>
              <select style={S.input} value={type} onChange={e=>setType(e.target.value)}>
                <option value="auto">Auto-detect</option>
                <option value="person">Person</option>
                <option value="company">Company</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize:'12px', color:C.sub, marginBottom:'6px', display:'block' }}>Depth</label>
              <select style={S.input} value={depth} onChange={e=>setDepth(e.target.value)}>
                <option value="quick">Quick (~$0.02)</option>
                <option value="standard">Standard (~$0.05)</option>
                <option value="deep">Deep (~$0.10)</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize:'12px', color:C.sub, marginBottom:'6px', display:'block' }}>State (optional)</label>
              <input style={S.input} placeholder="FL, CA, NY..." value={state} onChange={e=>setState(e.target.value)} />
            </div>
          </div>
          <div>
            <label style={{ fontSize:'12px', color:C.sub, marginBottom:'6px', display:'block' }}>Notes</label>
            <input style={S.input} placeholder="Context, red flags, or specific questions..." value={notes} onChange={e=>setNotes(e.target.value)} />
          </div>
          <button style={{ ...S.btn, opacity: running ? 0.6 : 1 }} onClick={investigate} disabled={running}>
            {running ? 'Investigating...' : 'Start Investigation'}
          </button>
        </div>
      </Card>
      <Card title="Live Log">
        <div style={{ maxHeight:'300px', overflow:'auto', background:C.surface, borderRadius:'8px', padding:'12px' }}>
          {logs.length > 0 ? logs.map((l, i) => (
            <div key={i} style={{ fontSize:'12px', fontFamily:'monospace', marginBottom:'4px' }}>
              <span style={{ color:C.muted }}>{new Date(l.ts).toLocaleTimeString()}</span>
              <span style={{ marginLeft:'8px', color: l.level==='error'?C.red:l.level==='success'?C.green:C.accent }}>{l.level?.toUpperCase()}</span>
              <span style={{ marginLeft:'8px', color:C.text }}>{l.msg}</span>
            </div>
          )) : <div style={{ color:C.muted, fontSize:'13px' }}>No activity yet. Start an investigation above.</div>}
        </div>
      </Card>
    </>
  )
}

function CasesTab({ data }) {
  const cases = data?.cases || []

  return (
    <>
      <div style={S.grid4}>
        <KPI label="Total Cases" value={cases.length} />
        <KPI label="High Risk" value={cases.filter(c=>c.risk==='high').length} color={C.red} />
        <KPI label="Medium Risk" value={cases.filter(c=>c.risk==='medium').length} color={C.yellow} />
        <KPI label="Low Risk" value={cases.filter(c=>c.risk==='low'||!c.risk).length} color={C.green} />
      </div>
      <Card title="Investigation Cases">
        {cases.length > 0 ? (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr>{['Target','Type','Risk','Confidence','Date','Report'].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {cases.map((c, i) => (
                <tr key={i}>
                  <td style={S.td}><strong style={{ color:C.accent }}>{c.target}</strong></td>
                  <td style={S.td}><span style={S.pill(C.blue, C.blueL)}>{c.type||'auto'}</span></td>
                  <td style={S.td}>
                    <span style={S.pill(
                      c.risk==='high'?C.red:c.risk==='medium'?C.yellow:C.green,
                      c.risk==='high'?C.redL:c.risk==='medium'?C.yellowL:C.greenL
                    )}>{c.risk||'low'}</span>
                  </td>
                  <td style={S.td}>{c.confidence ? `${c.confidence}%` : '—'}</td>
                  <td style={S.td}>{c.date ? new Date(c.date).toLocaleDateString() : '—'}</td>
                  <td style={S.td}>
                    {c.reportUrl ? <a href={c.reportUrl} style={{ color:C.accent, fontSize:'12px' }}>Download ↓</a> : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div style={S.empty}>No cases yet. Run an investigation in the Investigate tab.</div>}
      </Card>
    </>
  )
}

function EngineTab({ data }) {
  const e = data?.engine || {}

  return (
    <>
      <div style={S.grid4}>
        <KPI label="Modules"        value={e.modules ?? 29} />
        <KPI label="Reports Run"    value={e.totalReports ?? 0} />
        <KPI label="Avg Cost"       value={e.avgCost ? `$${e.avgCost}` : '~$0.05'} />
        <KPI label="Avg Duration"   value={e.avgDuration ? `${e.avgDuration}s` : '—'} />
      </div>
      <div style={S.grid2}>
        <Card title="Module Status">
          <div style={{ display:'flex', flexDirection:'column', gap:'10px' }}>
            {(e.moduleList || ['Corporate Registry','Sanctions Screening','Court Records','Social Media','Domain Intel','Phone/Email OSINT','Marketplace Presence','Risk Synthesis']).map((m, i) => (
              <div key={i} style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <span style={{ fontSize:'13px', color:C.sub }}>{m.name || m}</span>
                <span style={S.pill(C.green, C.greenL)}>Active</span>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Recent Reports">
          {e.recentReports?.length > 0 ? (
            <div style={{ display:'flex', flexDirection:'column', gap:'10px' }}>
              {e.recentReports.map((r, i) => (
                <div key={i} style={{ display:'flex', justifyContent:'space-between', fontSize:'13px' }}>
                  <span style={{ color:C.text }}>{r.target}</span>
                  <span style={{ color:C.muted }}>{r.date}</span>
                </div>
              ))}
            </div>
          ) : <div style={S.empty}>No reports yet</div>}
        </Card>
      </div>
    </>
  )
}

function LogsTab({ data }) {
  const logs = data?.logs?.recent || []

  return (
    <Card title="System Logs">
      {logs.length > 0 ? (
        <div style={{ maxHeight:'600px', overflow:'auto' }}>
          {logs.map((l, i) => (
            <div key={i} style={S.logLine}>
              <span style={{ color:C.muted, marginRight:'12px' }}>{l.ts || l.timestamp || ''}</span>
              <span style={{ color: l.level==='error'?C.red:l.level==='warn'?C.yellow:C.sub }}>
                {l.level?.toUpperCase() || 'INFO'}
              </span>
              <span style={{ marginLeft:'12px', color:C.text }}>{l.msg || l.message || JSON.stringify(l)}</span>
            </div>
          ))}
        </div>
      ) : <div style={S.empty}>No logs available</div>}
    </Card>
  )
}

// ── MAIN ────────────────────────────────────────────────────────────────────

const TABS = ['Overview','Users','Costs','Features','Sources','Discovery','Investigate','Cases','Engine','Logs']

export default function HerkulioPage() {
  const [tab, setTab] = useState('Overview')
  const [data, setData] = useState({})
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)

  const load = useCallback(async () => {
    try {
      const [stats, users, costs, features, sources, discovery] = await Promise.allSettled([
        fetch('/api/herkulio/stats').then(r=>r.json()),
        fetch('/api/herkulio/users').then(r=>r.json()),
        fetch('/api/herkulio/costs').then(r=>r.json()),
        fetch('/api/herkulio/features').then(r=>r.json()),
        fetch('/api/herkulio/sources').then(r=>r.json()),
        fetch('/api/herkulio/discovery').then(r=>r.json()),
      ])

      setData({
        ...(stats.value || {}),
        userList:      users.value?.users || [],
        costs:         costs.value?.costs || costs.value || {},
        featureList:   features.value?.features || [],
        sourceList:    sources.value?.sources || [],
        discoveryList: discovery.value?.results || [],
      })
      setLastUpdated(new Date())
    } catch(e) { console.error('Load error:', e) }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { const t = setInterval(load, 30000); return () => clearInterval(t) }, [load])

  const renderTab = () => {
    if (loading) return <div style={S.empty}>Loading...</div>
    switch(tab) {
      case 'Overview':   return <OverviewTab   data={data} />
      case 'Users':      return <UsersTab      data={data} />
      case 'Costs':      return <CostsTab      data={data} />
      case 'Features':   return <FeaturesTab   data={data} />
      case 'Sources':    return <SourcesTab    data={data} />
      case 'Discovery':  return <DiscoveryTab  data={data} />
      case 'Investigate': return <InvestigateTab data={data} />
      case 'Cases':      return <CasesTab      data={data} />
      case 'Engine':     return <EngineTab     data={data} />
      case 'Logs':       return <LogsTab       data={data} />
      default:           return null
    }
  }

  return (
    <div style={S.page}>
      {/* Topbar */}
      <div style={S.topbar}>
        <div style={{ display:'flex', alignItems:'center', gap:'16px' }}>
          <div style={S.logo}>Herkul<span style={S.logoDot}>io</span></div>
          <span style={S.badge}>Intelligence Platform</span>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:'12px' }}>
          {lastUpdated && (
            <span style={{ fontSize:'12px', color:C.muted }}>
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button style={S.btnGhost} onClick={load}>Refresh</button>
        </div>
      </div>

      {/* Body */}
      <div style={S.body}>
        {/* Tab bar */}
        <div style={S.tabs}>
          {TABS.map(t => (
            <button
              key={t}
              style={tab===t ? S.tabActive : S.tab}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {renderTab()}
      </div>
    </div>
  )
}
