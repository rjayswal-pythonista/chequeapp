import React, { useEffect, useState } from 'react'
import { api, currentClaims } from '../api.js'

export default function Settings() {
  const [settings, setSettings] = useState(null)
  const [threshold, setThreshold] = useState('')
  const [makerChecker, setMakerChecker] = useState(false)
  const [note, setNote] = useState(null)
  const [busy, setBusy] = useState(false)
  const isAdmin = currentClaims()?.role === 'admin'

  const load = () => api('/org/settings').then(s => {
    setSettings(s)
    setMakerChecker(s.maker_checker_enabled)
    setThreshold(s.dual_approval_threshold_paise != null ? (s.dual_approval_threshold_paise / 100).toString() : '')
  }).catch(e => setNote(e.message))

  useEffect(() => { load() }, [])

  async function saveMakerChecker(e) {
    e.preventDefault()
    setBusy(true); setNote(null)
    try {
      await api('/org/settings', { method: 'PATCH', body: { maker_checker_enabled: makerChecker } })
      setNote({ kind: 'ok', text: 'Saved.' })
      load()
    } catch (err) { setNote({ kind: 'err', text: err.message }) }
    finally { setBusy(false) }
  }

  async function saveThreshold(e) {
    e.preventDefault()
    setBusy(true); setNote(null)
    try {
      const n = parseFloat(threshold)
      if (threshold.trim() === '') {
        await api('/org/settings', { method: 'PATCH', body: { clear_dual_approval_threshold: true } })
      } else if (Number.isFinite(n) && n > 0) {
        await api('/org/settings', { method: 'PATCH', body: { dual_approval_threshold_paise: Math.round(n * 100) } })
      }
      setNote({ kind: 'ok', text: 'Saved.' })
      load()
    } catch (err) { setNote({ kind: 'err', text: err.message }) }
    finally { setBusy(false) }
  }

  if (!isAdmin) {
    return (
      <>
        <h1>Settings</h1>
        <div className="empty">Only an organization admin can view and change these settings.</div>
      </>
    )
  }

  return (
    <>
      <h1>Settings</h1>
      <div className="sub">Organization-wide approval controls.</div>
      {note && <div className={note.kind === 'ok' ? 'ok-note' : 'error-note'} style={{ marginBottom: 14 }}>{note.text}</div>}
      {settings && (
        <div style={{ maxWidth: 460 }}>
          <form onSubmit={saveMakerChecker}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" checked={makerChecker} onChange={e => setMakerChecker(e.target.checked)}
                     style={{ width: 'auto' }} />
              <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
                Require maker-checker approval before printing
              </span>
            </label>
            <button className="primary" disabled={busy} style={{ marginTop: 14 }}>Save</button>
          </form>

          <form onSubmit={saveThreshold} style={{ marginTop: 28 }}>
            <label htmlFor="threshold">Dual-approval threshold ({'\u20B9'})</label>
            <input id="threshold" type="number" step="0.01" min="0.01" value={threshold}
                   onChange={e => setThreshold(e.target.value)}
                   placeholder="Leave blank to disable" />
            <p style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 8 }}>
              Cheques at or above this amount need two different checkers to approve
              (the same checker cannot give both approvals, and the creator can never approve).
              Leave blank to require only a single approval regardless of amount.
            </p>
            <button className="primary" disabled={busy} style={{ marginTop: 8 }}>Save</button>
          </form>
        </div>
      )}
    </>
  )
}
