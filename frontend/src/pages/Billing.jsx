import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const TIERS = {
  starter: { name: 'Starter', desc: '1 bank template, single user, basic register' },
  growth: { name: 'Growth', desc: '3\u20135 bank templates, saved payees, multi-account' },
  business: { name: 'Business', desc: 'Unlimited templates, maker-checker, multi-user, priority support' },
}

export default function Billing() {
  const [status, setStatus] = useState(null)
  const [note, setNote] = useState(null)

  useEffect(() => { api('/billing/status').then(setStatus).catch(e => setNote(e.message)) }, [])

  if (note) return <><h1>Billing</h1><div className="error-note">{note}</div></>
  if (!status) return <><h1>Billing</h1><div className="sub">Loading…</div></>

  const tier = TIERS[status.plan_tier] || { name: status.plan_tier, desc: '' }
  const s = status.subscription_status

  return (
    <>
      <h1>Billing</h1>
      <div className="sub">Your plan and subscription state.</div>
      <div style={{ maxWidth: 480 }}>
        {status.on_trial && status.trial_ends_at && s === 'active' && (
          <div className="ok-note" style={{ marginBottom: 16 }}>
            Free trial — ends {new Date(status.trial_ends_at).toLocaleDateString()}.
            Subscribe on the Settings page before then to avoid read-only mode.
          </div>
        )}
        <table>
          <tbody>
            <tr><td>Plan</td><td><strong>{tier.name}</strong><br /><span style={{ fontSize: 13, color: 'var(--ink-soft)' }}>{tier.desc}</span></td></tr>
            <tr><td>Status</td><td><span className={`badge ${s === 'active' ? 'approved' : s === 'grace' ? 'pending_approval' : 'rejected'}`}>{s}</span></td></tr>
            {status.grace_until && <tr><td>Grace until</td><td className="num">{new Date(status.grace_until).toLocaleString()}</td></tr>}
          </tbody>
        </table>

        {s === 'grace' && (
          <div className="error-note" style={{ marginTop: 16 }}>
            A recent payment failed. Everything keeps working during the grace period — update your
            payment method before it ends to avoid read-only mode.
          </div>
        )}
        {s === 'lapsed' && status.on_trial && (
          <div className="error-note" style={{ marginTop: 16 }}>
            Your free trial has ended without a subscription. You can still view, search, and export
            your full register — creating and printing cheques resumes as soon as you subscribe.
          </div>
        )}
        {s === 'lapsed' && !status.on_trial && (
          <div className="error-note" style={{ marginTop: 16 }}>
            Your subscription has lapsed. You can still view, search, and export your full register —
            creating and printing cheques resumes as soon as a payment goes through.
          </div>
        )}
        <p style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 16 }}>
          Payments are handled by Razorpay. Renewals apply automatically within a minute of the
          payment confirmation reaching us.
        </p>
      </div>
    </>
  )
}
