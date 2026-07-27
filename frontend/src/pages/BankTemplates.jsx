import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api, apiDownloadFile, currentClaims } from '../api.js'

const FIELD_DEFS = [
  { key: 'payee_name', label: 'Payee name', short: 'Payee', hasMaxWidth: true },
  { key: 'amount_words', label: 'Amount in words', short: 'Words', hasMaxWidth: true },
  { key: 'amount_figures', label: 'Amount in figures', short: 'Figures', hasMaxWidth: false },
  { key: 'date_day', label: 'Date — day', short: 'DD', hasMaxWidth: false },
  { key: 'date_month', label: 'Date — month', short: 'MM', hasMaxWidth: false },
  { key: 'date_year', label: 'Date — year', short: 'YYYY', hasMaxWidth: false },
]

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))

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

function TemplateCanvas({ pageWidthMm, pageHeightMm, form, setField, selectedKey, setSelectedKey,
                          armedKey, setArmedKey, onConfirm, refImage, opacity, pxPerMm }) {
  const canvasRef = useRef(null)
  const w = pageWidthMm * pxPerMm
  const h = pageHeightMm * pxPerMm

  function toMm(clientX, clientY) {
    const rect = canvasRef.current.getBoundingClientRect()
    return {
      x: clamp((clientX - rect.left) / pxPerMm, 0, pageWidthMm),
      y: clamp((clientY - rect.top) / pxPerMm, 0, pageHeightMm),
    }
  }

  function handleCanvasClick(e) {
    if (!armedKey) return
    const { x, y } = toMm(e.clientX, e.clientY)
    setField(armedKey, { enabled: true, x_mm: x.toFixed(1), y_mm: y.toFixed(1) })
    setSelectedKey(armedKey)
    onConfirm(armedKey, x.toFixed(1), y.toFixed(1))
  }

  function startDragMarker(key, e) {
    e.stopPropagation()
    setSelectedKey(key)
    setArmedKey(null)
    const move = ev => {
      const { x, y } = toMm(ev.clientX, ev.clientY)
      setField(key, { x_mm: x.toFixed(1), y_mm: y.toFixed(1) })
    }
    const up = ev => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      const { x, y } = toMm(ev.clientX, ev.clientY)
      onConfirm(key, x.toFixed(1), y.toFixed(1))
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  function startDragMaxWidth(key, e) {
    e.stopPropagation()
    setSelectedKey(key)
    const s = form[key]
    const baseX = parseFloat(s.x_mm) || 0
    const move = ev => {
      const { x } = toMm(ev.clientX, ev.clientY)
      const width = clamp(x - baseX, 2, pageWidthMm - baseX)
      setField(key, { max_width_mm: width.toFixed(1) })
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  function onKeyDown(e) {
    if (!selectedKey) return
    const s = form[selectedKey]
    if (!s?.enabled) return
    const step = e.shiftKey ? 2 : 0.5
    let dx = 0, dy = 0
    if (e.key === 'ArrowLeft') dx = -step
    else if (e.key === 'ArrowRight') dx = step
    else if (e.key === 'ArrowUp') dy = -step
    else if (e.key === 'ArrowDown') dy = step
    else return
    e.preventDefault()
    const nx = clamp((parseFloat(s.x_mm) || 0) + dx, 0, pageWidthMm)
    const ny = clamp((parseFloat(s.y_mm) || 0) + dy, 0, pageHeightMm)
    setField(selectedKey, { x_mm: nx.toFixed(1), y_mm: ny.toFixed(1) })
  }

  const gridPx = 10 * pxPerMm

  return (
    <div
      ref={canvasRef}
      tabIndex={0}
      onClick={handleCanvasClick}
      onKeyDown={onKeyDown}
      style={{
        position: 'relative', width: w, height: h, maxWidth: '100%',
        border: '1px solid var(--rule)', borderRadius: 6, overflow: 'hidden',
        cursor: armedKey ? 'crosshair' : 'default', background: '#fff',
        backgroundImage: `linear-gradient(to right, rgba(0,0,0,0.08) 1px, transparent 1px), `
          + `linear-gradient(to bottom, rgba(0,0,0,0.08) 1px, transparent 1px)`,
        backgroundSize: `${gridPx}px ${gridPx}px`,
        outline: 'none',
      }}
    >
      {refImage && (
        <img src={refImage} alt="" draggable={false}
             style={{ position: 'absolute', inset: 0, width: '100%', height: '100%',
                      objectFit: 'fill', opacity, pointerEvents: 'none' }} />
      )}
      {FIELD_DEFS.filter(f => form[f.key].enabled).map(f => {
        const s = form[f.key]
        const x = (parseFloat(s.x_mm) || 0) * pxPerMm
        const y = (parseFloat(s.y_mm) || 0) * pxPerMm
        const isSelected = selectedKey === f.key
        return (
          <React.Fragment key={f.key}>
            {f.hasMaxWidth && s.max_width_mm !== '' && (
              <>
                <div style={{ position: 'absolute', left: x, top: y - 2, height: 2,
                              width: (parseFloat(s.max_width_mm) || 0) * pxPerMm,
                              background: 'var(--guilloche)', opacity: 0.6, pointerEvents: 'none' }} />
                <div onPointerDown={e => startDragMaxWidth(f.key, e)}
                     title="Drag to resize max width"
                     style={{ position: 'absolute',
                              left: x + (parseFloat(s.max_width_mm) || 0) * pxPerMm - 4, top: y - 6,
                              width: 8, height: 8, borderRadius: 2, background: 'var(--guilloche)',
                              cursor: 'ew-resize' }} />
              </>
            )}
            <div
              onPointerDown={e => startDragMarker(f.key, e)}
              title={`${f.label}: ${s.x_mm}mm, ${s.y_mm}mm — drag to reposition`}
              style={{
                position: 'absolute', left: x, top: y, transform: 'translate(-50%, -50%)',
                display: 'flex', alignItems: 'center', gap: 4, cursor: 'grab', userSelect: 'none',
              }}
            >
              <div style={{ width: 10, height: 10, borderRadius: '50%',
                            background: isSelected ? 'var(--stamp)' : 'var(--guilloche)',
                            border: '2px solid #fff', boxShadow: '0 0 0 1px rgba(0,0,0,0.3)' }} />
              <span style={{ fontSize: 10, fontWeight: 700, color: isSelected ? 'var(--stamp)' : 'var(--guilloche)',
                            background: 'rgba(255,255,255,0.85)', padding: '1px 4px', borderRadius: 3,
                            whiteSpace: 'nowrap' }}>{f.short}</span>
            </div>
          </React.Fragment>
        )
      })}
    </div>
  )
}

function TemplateForm({ initial, onSave, onCancel, busy }) {
  const [bankName, setBankName] = useState(initial?.bank_name || '')
  const [pageWidth, setPageWidth] = useState(initial?.page_width_mm ? String(initial.page_width_mm) : '203')
  const [pageHeight, setPageHeight] = useState(initial?.page_height_mm ? String(initial.page_height_mm) : '92')
  const [form, setForm] = useState(fieldsToForm(initial?.fields))
  const [selectedKey, setSelectedKey] = useState(null)
  const [armedKey, setArmedKey] = useState(null)
  const [confirmation, setConfirmation] = useState(null)
  const [refImage, setRefImage] = useState(null)
  const [opacity, setOpacity] = useState(0.6)
  const [zoom, setZoom] = useState(3.5)
  const [gridBusy, setGridBusy] = useState(false)
  const [gridNote, setGridNote] = useState(null)

  const storageKey = `chequedesk_ref_image_${initial?.id || 'new'}`

  useEffect(() => {
    const saved = localStorage.getItem(storageKey)
    if (saved) setRefImage(saved)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setField = (key, patch) => setForm(f => ({ ...f, [key]: { ...f[key], ...patch } }))

  function confirmPlacement(key, x, y) {
    const label = FIELD_DEFS.find(f => f.key === key)?.label || key
    setConfirmation(`${label} set to x = ${x}mm, y = ${y}mm`)
    window.clearTimeout(confirmPlacement._t)
    confirmPlacement._t = window.setTimeout(() => setConfirmation(null), 3000)
  }

  function onPickImage(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      setRefImage(reader.result)
      try { localStorage.setItem(storageKey, reader.result) } catch { /* storage full — ignore, still usable this session */ }
    }
    reader.readAsDataURL(file)
  }

  function clearImage() {
    setRefImage(null)
    localStorage.removeItem(storageKey)
  }

  async function downloadGrid() {
    setGridBusy(true); setGridNote(null)
    try {
      await apiDownloadFile(`/bank-templates/${initial.id}/alignment-grid`)
    } catch (err) {
      setGridNote(err.message)
    } finally {
      setGridBusy(false)
    }
  }

  function submit(e) {
    e.preventDefault()
    onSave({
      bank_name: bankName,
      page_width_mm: parseFloat(pageWidth) || 0,
      page_height_mm: parseFloat(pageHeight) || 0,
      fields: formToFields(form),
    })
  }

  const pageWidthMm = parseFloat(pageWidth) || 1
  const pageHeightMm = parseFloat(pageHeight) || 1

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
        Visual field placement
      </p>
      <p style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 0 }}>
        Click a field below to arm it, then click on the canvas where it should print. Or drag an
        existing dot to reposition it, and use arrow keys (Shift = bigger step) to nudge the
        selected field by fractions of a millimetre.
      </p>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
        {FIELD_DEFS.map(f => (
          <button key={f.key} type="button"
                  onClick={() => setArmedKey(armedKey === f.key ? null : f.key)}
                  className={armedKey === f.key ? 'primary' : 'quiet'}
                  style={{ fontSize: 12.5, padding: '5px 10px' }}>
            {form[f.key].enabled ? '✓ ' : '+ '}{f.label}
          </button>
        ))}
      </div>

      {confirmation && <div className="ok-note" style={{ marginBottom: 10 }}>{confirmation}</div>}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', marginBottom: 10 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
          <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0, fontSize: 12.5 }}>Zoom</span>
          <input type="range" min="1.5" max="6" step="0.5" value={zoom}
                 onChange={e => setZoom(parseFloat(e.target.value))} style={{ width: 100 }} />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
          <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0, fontSize: 12.5 }}>Reference image</span>
          <input type="file" accept="image/*" onChange={onPickImage} style={{ fontSize: 12 }} />
        </label>
        {refImage && (
          <>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
              <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0, fontSize: 12.5 }}>Opacity</span>
              <input type="range" min="0.15" max="1" step="0.05" value={opacity}
                     onChange={e => setOpacity(parseFloat(e.target.value))} style={{ width: 80 }} />
            </label>
            <button type="button" className="quiet" onClick={clearImage} style={{ fontSize: 12.5 }}>Remove image</button>
          </>
        )}
        {initial?.id && (
          <button type="button" className="quiet" disabled={gridBusy} onClick={downloadGrid} style={{ fontSize: 12.5 }}>
            {gridBusy ? 'Preparing…' : 'Download alignment grid (printer calibration)'}
          </button>
        )}
      </div>
      {gridNote && <div className="error-note" style={{ marginBottom: 10 }}>{gridNote}</div>}
      {!refImage && (
        <p style={{ fontSize: 12.5, color: 'var(--ink-soft)', marginTop: 0 }}>
          Tip: photograph or scan a blank leaf and upload it here as a reference — then you can
          click directly on the payee/amount/date boxes in the photo instead of guessing coordinates.
        </p>
      )}

      <TemplateCanvas
        pageWidthMm={pageWidthMm} pageHeightMm={pageHeightMm}
        form={form} setField={setField}
        selectedKey={selectedKey} setSelectedKey={setSelectedKey}
        armedKey={armedKey} setArmedKey={setArmedKey}
        onConfirm={confirmPlacement}
        refImage={refImage} opacity={opacity} pxPerMm={zoom}
      />

      <p style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink-soft)', margin: '18px 0 4px', textTransform: 'uppercase', letterSpacing: '0.02em' }}>
        Exact values (optional — for typing precise numbers)
      </p>
      {FIELD_DEFS.map(f => {
        const s = form[f.key]
        return (
          <div key={f.key}
               onClick={() => setSelectedKey(f.key)}
               style={{ border: `1px solid ${selectedKey === f.key ? 'var(--stamp)' : 'var(--rule)'}`,
                        borderRadius: 8, padding: 10, marginTop: 8, cursor: 'pointer' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0 }} onClick={e => e.stopPropagation()}>
              <input type="checkbox" checked={s.enabled} style={{ width: 'auto' }}
                     onChange={e => setField(f.key, { enabled: e.target.checked })} />
              <span style={{ fontWeight: 600, textTransform: 'none', letterSpacing: 0, color: 'var(--ink)' }}>{f.label}</span>
            </label>
            {s.enabled && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginTop: 8 }}
                   onClick={e => e.stopPropagation()}>
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
