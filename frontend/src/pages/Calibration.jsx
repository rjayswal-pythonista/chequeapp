import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Calibration() {
  const [templates, setTemplates] = useState([])
  const [sel, setSel] = useState('')
  const [x, setX] = useState(0)
  const [y, setY] = useState(0)
  const [note, setNote] = useState(null)

  useEffect(() => {
    api('/bank-templates').then(ts => {
      setTemplates(ts)
      if (ts.length) pick(ts[0])
    }).catch(e => setNote({ kind: 'err', text: e.message }))
  }, [])

  function pick(t) { setSel(t.id); setX(t.printer_offset_x_mm); setY(t.printer_offset_y_mm) }

  async function save() {
    setNote(null)
    try {
      await api(`/bank-templates/${sel}/calibration`, {
        method: 'PATCH', body: { printer_offset_x_mm: x, printer_offset_y_mm: y },
      })
      setNote({ kind: 'ok', text: 'Offsets saved. The next print for this bank uses them automatically.' })
    } catch (e) { setNote({ kind: 'err', text: e.message }) }
  }

  const nudge = (setter, val, d) => () => setter(Math.round((val + d) * 10) / 10)

  return (
    <>
      <h1>Print calibration</h1>
      <div className="sub">
        Every printer feeds paper slightly differently. Print a test cheque, hold it against a real
        leaf, and nudge the offsets until the text sits exactly on the pre-printed lines. Offsets
        are saved per bank template.
      </div>
      {templates.length === 0 && <div className="empty">Add a bank template first (created with your first cheque setup).</div>}
      {templates.length > 0 && (
        <div style={{ maxWidth: 430 }}>
          <label htmlFor="tpl">Bank template</label>
          <select id="tpl" value={sel} onChange={e => pick(templates.find(t => t.id === e.target.value))}>
            {templates.map(t => <option key={t.id} value={t.id}>{t.bank_name}</option>)}
          </select>

          <div className="cal-row" style={{ marginTop: 16 }}>
            <div>
              <label htmlFor="ox">Horizontal offset (mm)</label>
              <input id="ox" type="number" step="0.1" value={x} onChange={e => setX(parseFloat(e.target.value) || 0)} />
            </div>
            <button className="quiet" onClick={nudge(setX, x, -0.5)} aria-label="Nudge left">{'\u2190'} 0.5</button>
            <button className="quiet" onClick={nudge(setX, x, 0.5)} aria-label="Nudge right">0.5 {'\u2192'}</button>
          </div>
          <div className="cal-row" style={{ marginTop: 12 }}>
            <div>
              <label htmlFor="oy">Vertical offset (mm)</label>
              <input id="oy" type="number" step="0.1" value={y} onChange={e => setY(parseFloat(e.target.value) || 0)} />
            </div>
            <button className="quiet" onClick={nudge(setY, y, -0.5)} aria-label="Nudge up">{'\u2191'} 0.5</button>
            <button className="quiet" onClick={nudge(setY, y, 0.5)} aria-label="Nudge down">0.5 {'\u2193'}</button>
          </div>

          {note && <div className={note.kind === 'ok' ? 'ok-note' : 'error-note'}>{note.text}</div>}
          <button className="primary" onClick={save}>Save offsets</button>
          <p style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 14 }}>
            Positive horizontal moves text right; positive vertical moves it down. Applies to both
            PDF (inkjet/laser) and dot matrix output for this bank.
          </p>
        </div>
      )}
    </>
  )
}
