import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Approvals() {
  const [rows, setRows] = useState(null)
  const [note, setNote] = useState(null)

  const load = () => api('/cheques?status=pending_approval').then(setRows).catch(e => setNote(e.message))
  useEffect(() => { load() }, [])

  async function act(id, action) {
    setNote(null)
    try {
      if (action === 'approve') await api(`/cheques/${id}/approve`, { method: 'POST' })
      else {
        const reason = window.prompt('Reason for rejection (goes back to the maker):')
        if (!reason) return
        await api(`/cheques/${id}/reject`, { method: 'POST', body: { reason } })
      }
      load()
    } catch (e) { setNote(e.message) }
  }

  return (
    <>
      <h1>Approvals</h1>
      <div className="sub">Cheques waiting for a second pair of eyes before they can print.</div>
      {note && <div className="error-note" style={{ marginBottom: 14 }}>{note}</div>}
      {rows && rows.length === 0 && <div className="empty">Nothing waiting for approval.</div>}
      {rows && rows.length > 0 && (
        <table>
          <thead><tr><th>Date</th><th>Amount</th><th>In words</th><th></th></tr></thead>
          <tbody>
            {rows.map(c => (
              <tr key={c.id}>
                <td className="num">{c.cheque_date}</td>
                <td className="num">{'\u20B9'} {(c.amount_paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                <td style={{ fontStyle: 'italic', color: 'var(--ink-soft)' }}>{c.amount_words}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button className="quiet" onClick={() => act(c.id, 'approve')}>Approve</button>{' '}
                  <button className="quiet danger" onClick={() => act(c.id, 'reject')}>Reject</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
