// In dev, Vite proxies /api -> localhost:8000 (see vite.config.js).
// In production, set VITE_API_BASE to the full backend URL, e.g.
// https://my-backend.onrender.com
const BASE = import.meta.env.VITE_API_BASE || '/api'

let token = localStorage.getItem('cd_token') || null

export function setToken(t) {
  token = t
  if (t) localStorage.setItem('cd_token', t)
  else localStorage.removeItem('cd_token')
}

export function hasToken() { return !!token }

// Client-side-only convenience for showing/hiding nav items. The backend
// independently enforces every role check regardless of what the UI shows.
export function currentClaims() {
  if (!token) return null
  try {
    const payload = token.split('.')[1]
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(decodeURIComponent(escape(json)))
  } catch {
    return null
  }
}

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = data?.error || { code: 'UNKNOWN', message: 'Something went wrong.' }
    err.status = res.status
    throw err
  }
  return data
}

// For multipart uploads (e.g. bulk CSV) — no Content-Type header so the
// browser sets the multipart boundary itself.
export async function apiUpload(path, formData) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: formData,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = data?.error || { code: 'UNKNOWN', message: 'Something went wrong.' }
    err.status = res.status
    throw err
  }
  return data
}

// For file downloads (e.g. register export) — the response body isn't JSON,
// so this streams it straight to a browser download instead of parsing it.
export async function apiDownloadFile(path) {
  const res = await fetch(BASE + path, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const err = data?.error || { code: 'UNKNOWN', message: 'Something went wrong.' }
    err.status = res.status
    throw err
  }
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') || ''
  const match = /filename="?([^"]+)"?/.exec(disposition)
  const filename = match ? match[1] : 'download'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

export function downloadBase64(b64, filename, mime) {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
  const url = URL.createObjectURL(new Blob([bytes], { type: mime }))
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

export function openPdf(b64) {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
  const url = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }))
  window.open(url, '_blank')
}
