'use client'
import { useState, useEffect, useCallback } from 'react'

// API Configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Design system — white/indigo
const C = {
  bg: '#ffffff', surface: '#f8fafc', card: '#ffffff', border: '#e2e8f0',
  accent: '#4f46e5', accentL: '#eef2ff', accentD: '#3730a3',
  green: '#10b981', greenL: '#ecfdf5', red: '#ef4444', redL: '#fef2f2',
  yellow: '#f59e0b', yellowL: '#fffbeb',
  text: '#0f172a', sub: '#64748b', muted: '#94a3b8'
}

export default function HerkulioDashboard() {
  const [activeTab, setActiveTab] = useState('investigate')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  
  // Investigation state
  const [target, setTarget] = useState('')
  const [depth, setDepth] = useState('standard')
  const [investigation, setInvestigation] = useState(null)
  const [result, setResult] = useState(null)
  
  // Data states
  const [investigations, setInvestigations] = useState([])
  const [stats, setStats] = useState({ users: {}, revenue: {}, searches: 0 })

  // Fetch investigations on load
  useEffect(() => {
    fetchInvestigations()
    fetchStats()
  }, [])

  const fetchInvestigations = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/investigations/?limit=10`)
      if (res.ok) {
        const data = await res.json()
        setInvestigations(data.items || [])
      }
    } catch (e) {
      console.error('Failed to fetch investigations:', e)
    }
  }

  const fetchStats = async () => {
    try {
      // Mock stats for now - would fetch from /api/v1/tenants/me/usage
      setStats({
        users: { total: 1, active24h: 1 },
        revenue: { mrr: 0 },
        searches: investigations.length
      })
    } catch (e) {
      console.error('Failed to fetch stats:', e)
    }
  }

  const startInvestigation = async (e) => {
    e.preventDefault()
    if (!target.trim()) return
    
    setLoading(true)
    setError(null)
    setResult(null)
    
    try {
      const res = await fetch(`${API_URL}/api/v1/investigations/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target: target.trim(),
          target_type: 'auto',
          depth: depth
        })
      })
      
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to start investigation')
      }
      
      const data = await res.json()
      setInvestigation(data)
      setActiveTab('status')
      
      // Poll for results
      pollForResults(data.id)
      
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const pollForResults = async (id) => {
    const checkStatus = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/investigations/${id}`)
        if (res.ok) {
          const data = await res.json()
          if (data.status === 'completed') {
            setResult(data)
            setInvestigations(prev => [data, ...prev])
            return true
          } else if (data.status === 'failed') {
            setError('Investigation failed')
            return true
          }
        }
        return false
      } catch (e) {
        return false
      }
    }
    
    // Poll every 3 seconds for up to 2 minutes
    let attempts = 0
    const interval = setInterval(async () => {
      attempts++
      const done = await checkStatus()
      if (done || attempts > 40) {
        clearInterval(interval)
      }
    }, 3000)
  }

  const getRiskEmoji = (level) => {
    const map = { 'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡', 'LOW': '🟢', 'MINIMAL': '✅' }
    return map[level] || '⚪'
  }

  const getRiskColor = (level) => {
    const map = { 'CRITICAL': C.red, 'HIGH': '#ea580c', 'MEDIUM': C.yellow, 'LOW': C.green, 'MINIMAL': C.green }
    return map[level] || C.sub
  }

  return (
    <div style={{ minHeight: '100vh', background: C.bg, fontFamily: "'Inter',system-ui,sans-serif" }}>
      {/* Header */}
      <div style={{ background: C.card, borderBottom: `1px solid ${C.border}`, padding: '16px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ fontSize: '20px', fontWeight: 700, color: C.text }}>
            Herkul<span style={{ color: C.accent }}>io</span>
          </div>
          <span style={{ background: C.accentL, color: C.accent, fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '999px' }}>
            Intelligence Platform
          </span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button 
            onClick={() => setActiveTab('investigate')}
            style={{ 
              padding: '8px 16px', borderRadius: '8px', border: 'none', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
              background: activeTab === 'investigate' ? C.accent : 'transparent',
              color: activeTab === 'investigate' ? 'white' : C.sub
            }}
          >
            🔍 Investigate
          </button>
          <button 
            onClick={() => setActiveTab('cases')}
            style={{ 
              padding: '8px 16px', borderRadius: '8px', border: 'none', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
              background: activeTab === 'cases' ? C.accent : 'transparent',
              color: activeTab === 'cases' ? 'white' : C.sub
            }}
          >
            📁 Cases ({investigations.length})
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div style={{ padding: '32px', maxWidth: '900px', margin: '0 auto' }}>
        
        {/* Error Display */}
        {error && (
          <div style={{ background: C.redL, border: `1px solid ${C.red}`, borderRadius: '8px', padding: '16px', marginBottom: '24px', color: C.red }}>
            ⚠️ {error}
          </div>
        )}

        {/* INVESTIGATE TAB */}
        {activeTab === 'investigate' && (
          <>
            {/* Hero */}
            <div style={{ textAlign: 'center', marginBottom: '40px' }}>
              <h1 style={{ fontSize: '32px', fontWeight: 700, color: C.text, marginBottom: '8px' }}>
                Investigate Anyone
              </h1>
              <p style={{ color: C.sub, fontSize: '16px' }}>
                Watch dealers, companies, people — know who you're dealing with
              </p>
            </div>

            {/* Investigation Form */}
            <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: '12px', padding: '32px', marginBottom: '24px' }}>
              <form onSubmit={startInvestigation}>
                <div style={{ marginBottom: '20px' }}>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: C.sub, marginBottom: '6px' }}>
                    Target
                  </label>
                  <input
                    type="text"
                    value={target}
                    onChange={(e) => setTarget(e.target.value)}
                    placeholder="Name, company, email, phone, or URL..."
                    style={{ 
                      width: '100%', padding: '12px 16px', border: `1px solid ${C.border}`, borderRadius: '8px',
                      fontSize: '15px', outline: 'none', boxSizing: 'border-box'
                    }}
                    disabled={loading}
                  />
                </div>

                <div style={{ marginBottom: '24px' }}>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: C.sub, marginBottom: '6px' }}>
                    Depth
                  </label>
                  <div style={{ display: 'flex', gap: '12px' }}>
                    {['quick', 'standard', 'deep'].map((d) => (
                      <button
                        key={d}
                        type="button"
                        onClick={() => setDepth(d)}
                        style={{
                          flex: 1, padding: '12px', borderRadius: '8px', border: `1px solid ${depth === d ? C.accent : C.border}`,
                          background: depth === d ? C.accentL : C.card, cursor: 'pointer',
                          color: depth === d ? C.accent : C.text, fontWeight: depth === d ? 600 : 400
                        }}
                      >
                        <div style={{ fontSize: '14px', textTransform: 'capitalize' }}>{d}</div>
                        <div style={{ fontSize: '11px', color: C.sub, marginTop: '4px' }}>
                          {d === 'quick' && '~$0.02 • 15 sources'}
                          {d === 'standard' && '~$0.05 • 29 sources'}
                          {d === 'deep' && '~$0.10 • 60+ sources'}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading || !target.trim()}
                  style={{
                    width: '100%', padding: '14px', background: loading ? C.sub : C.accent, color: 'white',
                    border: 'none', borderRadius: '8px', fontSize: '15px', fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer'
                  }}
                >
                  {loading ? '⏳ Starting Investigation...' : '🔍 Start Investigation'}
                </button>
              </form>
            </div>

            {/* Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
              <div style={{ background: C.surface, borderRadius: '8px', padding: '20px', textAlign: 'center' }}>
                <div style={{ fontSize: '24px', fontWeight: 700, color: C.text }}>{stats.users.total || 1}</div>
                <div style={{ fontSize: '12px', color: C.sub }}>Active Users</div>
              </div>
              <div style={{ background: C.surface, borderRadius: '8px', padding: '20px', textAlign: 'center' }}>
                <div style={{ fontSize: '24px', fontWeight: 700, color: C.text }}>{investigations.length}</div>
                <div style={{ fontSize: '12px', color: C.sub }}>Investigations</div>
              </div>
              <div style={{ background: C.surface, borderRadius: '8px', padding: '20px', textAlign: 'center' }}>
                <div style={{ fontSize: '24px', fontWeight: 700, color: C.text }}>29</div>
                <div style={{ fontSize: '12px', color: C.sub }}>Data Sources</div>
              </div>
            </div>
          </>
        )}

        {/* STATUS/RESULT TAB */}
        {activeTab === 'status' && investigation && (
          <>
            {!result ? (
              // Loading State
              <div style={{ textAlign: 'center', padding: '60px 20px' }}>
                <div style={{ fontSize: '48px', marginBottom: '16px' }}>🔍</div>
                <h2 style={{ fontSize: '24px', fontWeight: 600, marginBottom: '8px' }}>Investigating {investigation.target}</h2>
                <p style={{ color: C.sub }}>Running {depth} search with 29+ data sources...</p>
                <div style={{ marginTop: '24px', height: '4px', background: C.border, borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: '60%', background: C.accent, animation: 'pulse 1.5s infinite' }} />
                </div>
                <style>{`
                  @keyframes pulse { 0% { opacity: 0.6 } 50% { opacity: 1 } 100% { opacity: 0.6 } }
                `}</style>
              </div>
            ) : (
              // Results Display
              <>
                <button 
                  onClick={() => { setActiveTab('investigate'); setResult(null); setInvestigation(null); setTarget(''); }}
                  style={{ marginBottom: '24px', padding: '8px 16px', border: `1px solid ${C.border}`, borderRadius: '8px', background: 'transparent', cursor: 'pointer' }}
                >
                  ← Back to Search
                </button>

                {/* Risk Card */}
                <div style={{ 
                  background: C.card, border: `2px solid ${getRiskColor(result.risk_level)}`, borderRadius: '12px', 
                  padding: '32px', marginBottom: '24px', textAlign: 'center'
                }}>
                  <div style={{ fontSize: '48px', marginBottom: '8px' }}>{getRiskEmoji(result.risk_level)}</div>
                  <h2 style={{ fontSize: '28px', fontWeight: 700, color: getRiskColor(result.risk_level), marginBottom: '4px' }}>
                    {result.risk_level} RISK
                  </h2>
                  <div style={{ fontSize: '16px', color: C.sub }}>
                    Score: {result.risk_score}/100 • Confidence: {result.confidence_score}%
                  </div>
                  <div style={{ marginTop: '16px', padding: '16px', background: C.surface, borderRadius: '8px' }}>
                    <p style={{ margin: 0, color: C.text }}><strong>Target:</strong> {result.target}</p>
                    <p style={{ margin: '8px 0 0 0, color: C.sub, fontSize: '14px' }}>{result.report_json?.summary || 'Investigation completed'}</p>
                  </div>
                </div>

                {/* Key Findings */}
                {result.report_json?.key_findings && (
                  <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: '12px', padding: '24px', marginBottom: '24px' }}>
                    <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 600 }}>Key Findings</h3>
                    <ul style={{ margin: 0, paddingLeft: '20px' }}>
                      {result.report_json.key_findings.map((finding, i) => (
                        <li key={i} style={{ marginBottom: '8px', color: C.text }}>{finding}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Red Flags */}
                {result.report_json?.red_flags?.length > 0 && (
                  <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: '12px', padding: '24px', marginBottom: '24px' }}>
                    <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 600, color: C.red }}>Red Flags</h3>
                    {result.report_json.red_flags.slice(0, 5).map((flag, i) => (
                      <div key={i} style={{ 
                        display: 'flex', alignItems: 'center', gap: '8px', padding: '12px', 
                        background: flag.severity === 'CRITICAL' ? C.redL : flag.severity === 'HIGH' ? C.yellowL : C.surface,
                        borderRadius: '8px', marginBottom: '8px'
                      }}>
                        <span style={{ fontWeight: 600, color: flag.severity === 'CRITICAL' ? C.red : C.yellow }}>
                          {flag.severity}
                        </span>
                        <span style={{ color: C.text }}>{flag.description}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Recommendations */}
                {result.report_json?.recommendations && (
                  <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: '12px', padding: '24px' }}>
                    <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 600 }}>Recommendations</h3>
                    <ul style={{ margin: 0, paddingLeft: '20px' }}>
                      {result.report_json.recommendations.map((rec, i) => (
                        <li key={i} style={{ marginBottom: '8px', color: C.text }}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* CASES TAB */}
        {activeTab === 'cases' && (
          <>
            <h2 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>Investigation History</h2>
            
            {investigations.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '60px', color: C.sub }}>
                No investigations yet. Start your first one!
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {investigations.map((inv) => (
                  <div key={inv.id} style={{ 
                    background: C.card, border: `1px solid ${C.border}`, borderRadius: '8px', 
                    padding: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between'
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, color: C.text }}>{inv.target}</div>
                      <div style={{ fontSize: '13px', color: C.sub, marginTop: '4px' }}>
                        {new Date(inv.created_at).toLocaleDateString()} • {inv.status}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      {inv.risk_level && (
                        <span style={{ 
                          background: getRiskColor(inv.risk_level) + '20', color: getRiskColor(inv.risk_level),
                          padding: '4px 12px', borderRadius: '999px', fontSize: '12px', fontWeight: 600
                        }}>
                          {inv.risk_level}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
