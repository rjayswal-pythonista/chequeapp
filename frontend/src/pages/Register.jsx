import React, { useEffect, useState } from 'react'
import { api, downloadBase64, openPdf, apiDownloadFile } from '../api.js'

function PrintModal({ cheque, onDone, onClose }) {
  const [note, setNote] = useState(null)
  const [crossing, setCrossing] = useState('none')
  const [crossingText, setCrossingText] = useState('')
  const [cancelled, setCancelled] = useState(false)
  const isReprint = cheque.status === 'printed'
  const verb = isReprint ? 'reprint' : 'print'

  function stampParams() {
    const p = new URLSearchParams()
    if (crossing !== 'none') p.set('crossing', crossing)
    if (crossing === 'custom' && crossingText.trim()) p.set('crossing_text', crossingText.trim())
    if (cancelled) p.set('watermark_cancelled', 'true')
    return p.toString()
  }

  async function run(format, deliver) {
    setNote(null)
    try {
      const extra = stampParams()
      const qs = `format=${format}${extra ? `&${extra}` : ''}`
      const r = await api(`/cheques/${cheque.id}/${verb}?${qs}`, { method: 'POST' })
      if (format === 'pdf') {
        if (deliver === 'open') openPdf(r.pdf_base64)
        else downloadBase64(r.pdf_base64, `cheque-${cheque.id.slice(0, 8)}.pdf`, 'application/pdf')
      } else {
        downloadBase64(r.escp_base64, `cheque-${cheque.id.slice(0, 8)}.prn`, 'application/octet-stream')
      }
      onDone()
    } catch (e) { setNote(e.message) }
  }

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>{isReprint ? 'Reprint cheque' : 'Print cheque'}</h2>
        <p style={{ fontSize: 13.5, color: 'var(--ink-soft)' }}>
          Choose the printer this cheque leaf is loaded in.
          {isReprint && ' Reprinting regenerates the output without creating a duplicate register entry.'}
        </p>

        <label htmlFor="crossing">Crossing stamp (optional)</label>
        <select id="crossing" value={crossing} onChange={e => setCrossing(e.target.value)}>
          <option value="none">None</option>
          <option value="ac_payee">A/C Payee Only</option>
          <option value="not_negotiable">Not Negotiable</option>
          <option value="custom">Custom text</option>
        </select>
        {crossing === 'custom' && (
          <input value={crossingText} onChange={e => setCrossingText(e.target.value)}
                 placeholder="e.g. Pay self only" style={{ marginTop: 8 }} />
        )}
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12 }}>
          <input type="checkbox" checked={cancelled} onChange={e => setCancelled(e.target.checked)}
                 style={{ width: 'auto' }} />
          <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>Cancelled watermark</span>
        </label>

        <div style={{ marginTop: 16 }}>
          <button className="printer-opt" onClick={() => run('pdf', 'open')}>
            <strong>Inkjet or laser</strong>
            <span>Opens the positioned PDF — print it from the dialog onto the loaded cheque leaf.</span>
          </button>
          <button className="printer-opt" onClick={() => run('escp', 'download')}>
            <strong>Dot matrix (continuous booklet)</strong>
            <span>Downloads a raw ESC/P file (.prn). Send it straight to the printer, e.g. <code>copy /b file.prn LPT1</code> or <code>lp -o raw</code>.</span>
          </button>
          <button className="printer-opt" onClick={() => run('pdf', 'download')}>
            <strong>Digital PDF only</strong>
            <span>Downloads the PDF for records or email — nothing goes to a printer.</span>
          </button>
        </div>
        {note && <div className="error-note">{note}</div>}
        <div style={{ textAlign: 'right', marginTop: 16 }}>
          <button className="quiet" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function Register() {
  const [rows, setRows] = useState(null)
  const [status, setStatus] = useState('')
  const [printing, setPrinting] = useState(null)
  const [note, setNote] = useState(null)
  const [exporting, setExporting] = useState(false)

  const load = () => api(`/cheques${status ? `?status=${status}` : ''}`).then(setRows).catch(e => setNote(e.message))
  useEffect(() => { load() }, [status])

  async function submit(id) {
    setNote(null)
    try { await api(`/cheques/${id}/submit`, { method: 'POST' }); load() }
    catch (e) { setNote(e.message) }
  }

  async function exportRegister(format) {
    setExporting(true); setNote(null)
    try {
      const qs = status ? `&status=${status}` : ''
      await apiDownloadFile(`/cheques/export?format=${format}${qs}`)
    } catch (e) { setNote(e.message) }
    finally { setExporting(false) }
  }

  return (
    <>
      <h1>Cheque register</h1>
      <div className="sub">Every cheque ever printed, searchable. Reprints never create duplicates.</div>
      <div className="filters" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <select value={status} onChange={e => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {['draft', 'pending_approval', 'pending_second_approval', 'approved', 'rejected', 'printed'].map(s =>
            <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
        </select>
        <div style={{ marginLeft: 'auto' }}>
          <button className="quiet" disabled={exporting} onClick={() => exportRegister('csv')}>Export CSV</button>{' '}
          <button className="quiet" disabled={exporting} onClick={() => exportRegister('pdf')}>Export PDF</button>
        </div>
      </div>
      {note && <div className="error-note" style={{ marginBottom: 14 }}>{note}</div>}
      {rows && rows.length === 0 && <div className="empty">No cheques yet. Create your first one from “New cheque”.</div>}
      {rows && rows.length > 0 && (
        <table>
          <thead><tr><th>Date</th><th>Amount</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {rows.map(c => (
              <tr key={c.id}>
                <td className="num">{c.cheque_date}</td>
                <td className="num">{'\u20B9'} {(c.amount_paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                <td><span className={`badge ${c.status}`}>{c.status.replace('_', ' ')}</span></td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  {c.status === 'draft' && <>
                    <button className="quiet" onClick={() => submit(c.id)}>Submit for approval</button>{' '}
                    <button className="quiet" onClick={() => setPrinting(c)}>Print</button>
                  </>}
                  {c.status === 'approved' && <button className="quiet" onClick={() => setPrinting(c)}>Print</button>}
                  {c.status === 'printed' && <button className="quiet" onClick={() => setPrinting(c)}>Reprint</button>}
                  {c.status === 'rejected' && <span style={{ fontSize: 13, color: 'var(--stamp)' }}>{c.rejected_reason}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {printing && <PrintModal cheque={printing} onClose={() => setPrinting(null)} onDone={() => { setPrinting(null); load() }} />}
    </>
  )
}
