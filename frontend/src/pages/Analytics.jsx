import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const STATUS_LABELS = {
  draft: 'Draft', pending_approval: 'Pending approval', pending_second_approval: 'Pending 2nd approval',
  approved: 'Approved', rejected: 'Rejected', printed: 'Printed',
}

function money(paise) {
  return `\u20B9 ${(paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}

export default function Analytics() {
  const [data, setData] = useState(null)
  const [note, setNote] = useState(null)

  useEffect(() => {
    api('/analytics/summary').then(setData).catch(e => setNote(e.message))
  }, [])

  if (note) return <div className="error-note">{note}</div>
  if (!data) return null

  const maxMonth = Math.max(1, ...data.spend_by_month.map(m => m.total_paise))
  const maxPayee = Math.max(1, ...data.spend_by_payee.map(p => p.total_paise))

  return (
    <>
      <h1>Analytics</h1>
      <div className="sub">Spend, approval throughput, and status breakdown for this organization.</div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 14, margin: '20px 0' }}>
        {Object.entries(STATUS_LABELS).map(([key, label]) => (
          <div key={key} style={{ border: '1px solid var(--rule)', borderRadius: 10, padding: 14 }}>
            <div style={{ fontSize: 12.5, color: 'var(--ink-soft)', fontWeight: 600 }}>{label}</div>
            <div style={{ fontSize: 26, fontWeight: 700 }}>{data.by_status[key] || 0}</div>
          </div>
        ))}
        <div style={{ border: '1px solid var(--rule)', borderRadius: 10, padding: 14 }}>
          <div style={{ fontSize: 12.5, color: 'var(--ink-soft)', fontWeight: 600 }}>Avg. approval time</div>
          <div style={{ fontSize: 26, fontWeight: 700 }}>
            {data.avg_approval_hours != null ? `${data.avg_approval_hours.toFixed(1)}h` : '—'}
          </div>
        </div>
      </div>

      <h2 style={{ fontSize: 16, marginTop: 28 }}>Spend by month</h2>
      {data.spend_by_month.length === 0 && <div className="empty">No issued cheques yet.</div>}
      {data.spend_by_month.map(m => (
        <div key={m.month} style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 6 }}>
          <div style={{ width: 70, fontSize: 13, color: 'var(--ink-soft)' }}>{m.month}</div>
          <div style={{ flex: 1, background: 'var(--leaf)', borderRadius: 4 }}>
            <div style={{ width: `${(m.total_paise / maxMonth) * 100}%`, background: 'var(--guilloche)',
                          borderRadius: 4, height: 18, minWidth: 2 }} />
          </div>
          <div style={{ width: 130, textAlign: 'right', fontSize: 13 }}>{money(m.total_paise)} ({m.count})</div>
        </div>
      ))}

      <h2 style={{ fontSize: 16, marginTop: 28 }}>Top payees by spend</h2>
      {data.spend_by_payee.length === 0 && <div className="empty">No issued cheques yet.</div>}
      {data.spend_by_payee.map(p => (
        <div key={p.payee_name} style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 6 }}>
          <div style={{ width: 160, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.payee_name}</div>
          <div style={{ flex: 1, background: 'var(--leaf)', borderRadius: 4 }}>
            <div style={{ width: `${(p.total_paise / maxPayee) * 100}%`, background: 'var(--stamp)',
                          borderRadius: 4, height: 18, minWidth: 2 }} />
          </div>
          <div style={{ width: 130, textAlign: 'right', fontSize: 13 }}>{money(p.total_paise)} ({p.count})</div>
        </div>
      ))}
    </>
  )
}
