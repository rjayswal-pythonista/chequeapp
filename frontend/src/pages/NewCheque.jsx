import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

function ChequeLeaf({ bankName, payee, figures, words, date }) {
  const d = date ? new Date(date + 'T00:00:00') : null
  const dateStr = d ? `${String(d.getDate()).padStart(2, '0')} ${String(d.getMonth() + 1).padStart(2, '0')} ${d.getFullYear()}` : ''
  return (
    <div className="leaf" aria-label="Live cheque preview">
      <div className="bank">{bankName || 'BANK'}</div>
      <div className="date">{dateStr || <span className="placeholder">DD MM YYYY</span>}</div>
      <div className="payee">{payee || <span className="placeholder">Payee name</span>}</div>
      <div className="figures">{figures ? `\u20B9 ${figures}` : <span className="placeholder">{'\u20B9'} 0.00</span>}</div>
      <div className="words">{words ? `Rupees ${words.replace(/ Only$/, '')} Only` : <span className="placeholder">Amount in words appears here as you type</span>}</div>
      <div className="micr">{'\u2446'}000000{'\u2446'} 000000000 {'\u2446'}</div>
    </div>
  )
}

export default function NewCheque() {
  const [payees, setPayees] = useState([])
  const [templates, setTemplates] = useState([])
  const [form, setForm] = useState({ payee_id: '', bank_template_id: '', amount: '', cheque_date: new Date().toISOString().slice(0, 10), memo: '' })
  const [words, setWords] = useState('')
  const [newPayee, setNewPayee] = useState('')
  const [note, setNote] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api('/payees').then(setPayees).catch(() => {})
    api('/bank-templates').then(ts => {
      setTemplates(ts)
      if (ts.length && !form.bank_template_id) setForm(f => ({ ...f, bank_template_id: ts[0].id }))
    }).catch(() => {})
  }, [])

  const amountPaise = useMemo(() => {
    const n = parseFloat(form.amount)
    return Number.isFinite(n) && n > 0 ? Math.round(n * 100) : 0
  }, [form.amount])

  useEffect(() => {
    if (!amountPaise) { setWords(''); return }
    const t = setTimeout(() => {
      api(`/util/amount-words?amount_paise=${amountPaise}`).then(r => setWords(r.words)).catch(() => setWords(''))
    }, 250)
    return () => clearTimeout(t)
  }, [amountPaise])

  const figures = amountPaise ? (amountPaise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 }) : ''
  const selPayee = payees.find(p => p.id === form.payee_id)
  const selTpl = templates.find(t => t.id === form.bank_template_id)

  async function addPayee() {
    if (!newPayee.trim()) return
    const p = await api('/payees', { method: 'POST', body: { name: newPayee.trim() } })
    setPayees([...payees, p]); setForm({ ...form, payee_id: p.id }); setNewPayee('')
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setNote(null)
    try {
      await api('/cheques', {
        method: 'POST',
        body: { bank_template_id: form.bank_template_id, payee_id: form.payee_id, amount_paise: amountPaise, cheque_date: form.cheque_date, memo: form.memo || null },
      })
      setNote({ kind: 'ok', text: 'Cheque saved as draft. Find it in the Register to submit or print.' })
      setForm(f => ({ ...f, amount: '', memo: '' }))
    } catch (err) {
      setNote({ kind: 'err', text: err.field ? `${err.message}` : err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1>New cheque</h1>
      <div className="sub">Every field is validated before anything can be printed.</div>
      <div className="entry-grid">
        <form onSubmit={submit}>
          <label htmlFor="tpl">Bank</label>
          <select id="tpl" value={form.bank_template_id} onChange={e => setForm({ ...form, bank_template_id: e.target.value })} required>
            <option value="" disabled>Select bank template</option>
            {templates.map(t => <option key={t.id} value={t.id}>{t.bank_name}</option>)}
          </select>

          <label htmlFor="payee">Payee</label>
          <select id="payee" value={form.payee_id} onChange={e => setForm({ ...form, payee_id: e.target.value })} required>
            <option value="" disabled>Select from saved payees</option>
            {payees.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <input value={newPayee} onChange={e => setNewPayee(e.target.value)} placeholder="Add a new payee" aria-label="New payee name" />
            <button type="button" className="quiet" onClick={addPayee}>Add</button>
          </div>

          <label htmlFor="amt">Amount ({'\u20B9'})</label>
          <input id="amt" type="number" step="0.01" min="0.01" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} required placeholder="45000.00" />

          <label htmlFor="date">Date</label>
          <input id="date" type="date" value={form.cheque_date} onChange={e => setForm({ ...form, cheque_date: e.target.value })} required />

          <label htmlFor="memo">Memo (optional)</label>
          <input id="memo" value={form.memo} onChange={e => setForm({ ...form, memo: e.target.value })} placeholder="Invoice #341" />

          {note && <div className={note.kind === 'ok' ? 'ok-note' : 'error-note'}>{note.text}</div>}
          <button className="primary" disabled={busy || !amountPaise || !form.payee_id || !form.bank_template_id}>Save cheque</button>
        </form>

        <div>
          <ChequeLeaf bankName={selTpl?.bank_name} payee={selPayee?.name} figures={figures} words={words} date={form.cheque_date} />
          <p style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 12 }}>
            This preview mirrors what will be printed on the physical leaf. The amount in words is
            generated by the system, so figures and words can never disagree.
          </p>
        </div>
      </div>
    </>
  )
}
