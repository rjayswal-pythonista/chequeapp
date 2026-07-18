import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setToken } from '../api.js'

export default function Login() {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ org_name: '', email: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()

  const set = k => e => setForm({ ...form, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      const data = mode === 'login'
        ? await api('/auth/login', { method: 'POST', body: { email: form.email, password: form.password } })
        : await api('/auth/signup', { method: 'POST', body: form })
      setToken(data.token)
      nav('/new')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <div className="brand">ChequeDesk</div>
      <div className="tag">Enter once. Print exactly. No more cheque errors.</div>
      <div className="auth-card">
        <form onSubmit={submit}>
          {mode === 'signup' && (<>
            <label htmlFor="org">Business name</label>
            <input id="org" value={form.org_name} onChange={set('org_name')} required placeholder="Sharma Traders Pvt Ltd" />
          </>)}
          <label htmlFor="email">Email</label>
          <input id="email" type="email" value={form.email} onChange={set('email')} required />
          <label htmlFor="pw">Password</label>
          <input id="pw" type="password" value={form.password} onChange={set('password')} required minLength={7} />
          {error && <div className="error-note">{error}</div>}
          <button className="primary" disabled={busy} style={{ width: '100%' }}>
            {mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>
        <div className="auth-toggle">
          {mode === 'login' ? <>New here? <button onClick={() => setMode('signup')}>Create your business account</button></>
            : <>Already registered? <button onClick={() => setMode('login')}>Sign in</button></>}
        </div>
      </div>
    </div>
  )
}
