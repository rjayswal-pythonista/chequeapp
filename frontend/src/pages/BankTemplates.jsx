import React, { useEffect, useState } from 'react'
import { api, currentClaims } from '../api.js'

const FIELD_DEFS = [
  { key: 'payee_name', label: 'Payee name', hasMaxWidth: true },
  { key: 'amount_words', label: 'Amount in words', hasMaxWidth: true },
  { key: 'amount_figures', label: 'Amount in figures', hasMaxWidth: false },
  { key: 'date_day', label: 'Date — day', hasMaxWidth: false },
  { key: 'date_month', label: 'Date — month', hasMaxWidth: false },
  { key: 'date_year', label: 'Date — year', hasMaxWidth: false },
]

const DEFAULT_FIELD_STATE = FIELD_DEFS.reduce((acc, f) => {
  acc[f.key] = { enabled: false, x_mm: '', y_mm: '', font_size: '10', max_width_mm: '',
                 font_family: 'Helvetica', bold: false, underline: false }
  return acc
}, {})

function fieldsToForm(fields) {
  const state = JSON.parse(JSON.stringify(DEFAULT_FIELD_STATE))
  for (const f of FIELD_DEFS) {
    const spec = fields?.[f.key]
    if (spec) {
      state[f.key] = {
        enabled: true,
        x_mm: String(spec.x_mm ?? ''),
        y_mm: String(spec.y_mm ?? ''),
        font_size: String(spec.font_size ?? '10'),
        max_width_mm: spec.max_width_mm != null ? String(spec.max_width_mm) : '',
        font_family: spec.font_family || 'Helvetica',
        bold: !!spec.bold,
        underline: !!spec.underline,
      }
    }
  }
  return state
}

function formToFields(form) {
  const fields = {}
  for (const f of FIELD_DEFS) {
    const s = form[f.key]
    if (!s.enabled) continue
    const spec = {
      x_mm: parseFloat(s.x_mm) || 0,
      y_mm: parseFloat(s.y_mm) || 0,
      font_size: parseFloat(s.font_size) || 10,
      font_family: s.font_family,
      bold: s.bold,
      underline: s.underline,
    }
    if (f.hasMaxWidth && s.max_width_mm !== '') spec.max_width_mm = parseFloat(s.max_width_mm)
    fields[f.key] = spec
  }
  return fields
}

function TemplateForm({ initial, onSave, onCancel, busy }) {
  const [bankName, setBankName] = useState(initial?.bank_name || '')
  const [pageWidth, setPageWidth] = useState(initial?.page_width_mm ? String(initial.page_width_mm) : '203')
  const [pageHeight, setPageHeight] = useState(initial?.page_height_mm ? String(initial.page_height_mm) : '92')
  const [form, setForm] = useState(fieldsToForm(initial?.fields))

  const setField = (key, patch) => setForm(f => ({ ...f, [key]: { ...f[key], ...patch } }))

  function submit(e) {
    e.preventDefault()
    onSave({
      bank_name: bankName,
      page_width_mm: parseFloat(pageWidth) || 0,
      page_height_mm: parseFloat(pageHeight) || 0,
      fields: formToFields(form),
    })
  }

  return (
    <form onSubmit={submit} style={{ marginTop: 16 }}>
      <label htmlFor="bank_name">Bank name</label>
      <input id="bank_name" value={bankName} onChange={e => setBankName(e.target.value)} required placeholder="SBI" />

      <div style={{ display: 'flex', gap: 12 }}>
        <div style={{ flex: 1 }}>
          <label htmlFor="pw">Page width (mm)</label>
          <input id="pw" type="number" step="0.1" value={pageWidth} onChange={e => setPageWidth(e.target.value)} required />
        </div>
        <div style={{ flex: 1 }}>
          <label htmlFor="ph">Page height (mm)</label>
          <input id="ph" type="number" step="0.1" value={pageHeight} onChange={e => setPageHeight(e.target.value)} required />
        </div>
      </div>

      <p style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-soft)', margin: '18px 0 4px', textTransform: 'uppercase', letterSpacing: '0.02em' }}>
        Field positions (verify against your own leaf)
      </p>
      {FIELD_DEFS.map(f => {
        const s = form[f.key]
        return (
          <div key={f.key} style={{ border: '1px solid var(--rule)', borderRadius: 8, padding: 10, marginTop: 8 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
              <input type="checkbox" checked={s.enabled} style={{ width: 'auto' }}
                     onChange={e => setField(f.key, { enabled: e.target.checked })} />
              <span style={{ fontWeight: 600, textTransform: 'none', letterSpacing: 0, color: 'var(--ink)' }}>{f.label}</span>
            </label>
            {s.enabled && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginTop: 8 }}>
                <input type="number" step="0.1" placeholder="x (mm)" value={s.x_mm}
                       onChange={e => setField(f.key, { x_mm: e.target.value })} />
                <input type="number" step="0.1" placeholder="y (mm)" value={s.y_mm}
                       onChange={e => setField(f.key, { y_mm: e.target.value })} />
                <input type="number" step="0.5" placeholder="font size" value={s.font_size}
                       onChange={e => setField(f.key, { font_size: e.target.value })} />
                {f.hasMaxWidth && (
                  <input type="number" step="0.1" placeholder="max width (mm)" value={s.max_width_mm}
                         onChange={e => setField(f.key, { max_width_mm: e.target.value })} />
                )}
                <select value={s.font_family} onChange={e => setField(f.key, { font_family: e.target.value })}>
                  <option value="Helvetica">Helvetica</option>
                  <option value="Times-Roman">Times-Roman</option>
                  <option value="Courier">Courier</option>
                </select>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
                  <input type="checkbox" checked={s.bold} style={{ width: 'auto' }}
                         onChange={e => setField(f.key, { bold: e.target.checked })} />
                  <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>Bold</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
                  <input type="checkbox" checked={s.underline} style={{ width: 'auto' }}
                         onChange={e => setField(f.key, { underline: e.target.checked })} />
                  <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>Underline</span>
                </label>
              </div>
            )}
          </div>
        )
      })}

      <div style={{ marginTop: 16 }}>
        <button className="primary" disabled={busy}>{initial ? 'Save changes' : 'Create template'}</button>{' '}
        {onCancel && <button type="button" className="quiet" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  )
}

export default function BankTemplates() {
  const [templates, setTemplates] = useState([])
  const [editing, setEditing] = useState(null)   // full template detail being edited, or 'new'
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState(null)
  const isAdmin = currentClaims()?.role === 'admin'

  const load = () => api('/bank-templates').then(setTemplates).catch(e => setNote(e.message))
  useEffect(() => { load() }, [])

  async function startEdit(t) {
    setNote(null)
    const full = await api(`/bank-templates/${t.id}`)
    setEditing(full)
  }

  async function save(payload) {
    setBusy(true); setNote(null)
    try {
      if (editing && editing.id) {
        await api(`/bank-templates/${editing.id}`, { method: 'PATCH', body: payload })
      } else {
        await api('/bank-templates', { method: 'POST', body: payload })
      }
      setEditing(null)
      load()
    } catch (err) {
      setNote(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!isAdmin) {
    return (
      <>
        <h1>Bank templates</h1>
        <div className="empty">Only an organization admin can create or edit bank templates.</div>
      </>
    )
  }

  return (
    <>
      <h1>Bank templates</h1>
      <div className="sub">Field coordinates are in mm from the top-left of the cheque leaf — verify against your own leaf before printing.</div>
      {note && <div className="error-note" style={{ marginTop: 12 }}>{note}</div>}

      {!editing && (
        <>
          {templates.length === 0 && <div className="empty">No bank templates yet.</div>}
          {templates.length > 0 && (
            <table style={{ marginTop: 16 }}>
              <thead><tr><th>Bank</th><th>Print offset (mm)</th><th></th></tr></thead>
              <tbody>
                {templates.map(t => (
                  <tr key={t.id}>
                    <td>{t.bank_name}</td>
                    <td className="num">{t.printer_offset_x_mm}, {t.printer_offset_y_mm}</td>
                    <td><button className="quiet" onClick={() => startEdit(t)}>Edit</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button className="primary" style={{ marginTop: 16 }} onClick={() => setEditing('new')}>Add bank template</button>
        </>
      )}

      {editing && (
        <TemplateForm
          initial={editing === 'new' ? null : editing}
          busy={busy}
          onSave={save}
          onCancel={() => setEditing(null)}
        />
      )}
    </>
  )
}
