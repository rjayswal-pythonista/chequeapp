import React, { useEffect, useState } from 'react'
import { api, apiUpload } from '../api.js'

export default function BulkUpload() {
  const [templates, setTemplates] = useState([])
  const [templateId, setTemplateId] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [note, setNote] = useState(null)

  useEffect(() => {
    api('/bank-templates').then(ts => {
      setTemplates(ts)
      if (ts.length && !templateId) setTemplateId(ts[0].id)
    }).catch(e => setNote(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function upload(e) {
    e.preventDefault()
    if (!file || !templateId) return
    setBusy(true); setNote(null); setResult(null)
    try {
      const fd = new FormData()
      fd.append('bank_template_id', templateId)
      fd.append('file', file)
      const r = await apiUpload('/cheques/bulk', fd)
      setResult(r)
    } catch (err) {
      setNote(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1>Bulk upload</h1>
      <div className="sub">
        Upload a CSV of cheques — every row goes through the same validation,
        amount-to-words generation, and audit trail as creating one cheque by hand.
      </div>

      {templates.length === 0 && <div className="empty">Add a bank template first, then come back here.</div>}

      {templates.length > 0 && (
        <form onSubmit={upload}>
          <label htmlFor="tpl">Bank template (applies to every row)</label>
          <select id="tpl" value={templateId} onChange={e => setTemplateId(e.target.value)} required>
            {templates.map(t => <option key={t.id} value={t.id}>{t.bank_name}</option>)}
          </select>

          <label htmlFor="file">CSV file</label>
          <input id="file" type="file" accept=".csv,text/csv"
                 onChange={e => setFile(e.target.files[0] || null)} required />

          <p style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 10 }}>
            Required columns: <code>payee_name</code>, <code>amount</code> (rupees, e.g. 1500.50),{' '}
            <code>cheque_date</code> (YYYY-MM-DD). Optional: <code>memo</code>.
            Payees not already saved are created automatically. Each row is validated and inserted
            independently — one bad row never blocks the rest of the batch.
          </p>

          {note && <div className="error-note">{note}</div>}
          <button className="primary" disabled={busy || !file || !templateId}>
            {busy ? 'Uploading…' : 'Upload and create cheques'}
          </button>
        </form>
      )}

      {result && (
        <div style={{ marginTop: 24 }}>
          <div className="sub">{result.created} created, {result.failed} failed</div>
          <table>
            <thead><tr><th>Row</th><th>Payee</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {result.rows.map(r => (
                <tr key={r.row}>
                  <td className="num">{r.row}</td>
                  <td>{r.payee_name || <span className="placeholder">—</span>}</td>
                  <td><span className={`badge ${r.status === 'created' ? 'approved' : 'rejected'}`}>{r.status}</span></td>
                  <td style={{ fontSize: 13, color: 'var(--ink-soft)' }}>
                    {r.status === 'created' ? `cheque ${r.cheque_id.slice(0, 8)}` : r.error}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
