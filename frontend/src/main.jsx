import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate } from 'react-router-dom'
import { hasToken, setToken } from './api.js'
import Login from './pages/Login.jsx'
import NewCheque from './pages/NewCheque.jsx'
import Approvals from './pages/Approvals.jsx'
import Register from './pages/Register.jsx'
import Calibration from './pages/Calibration.jsx'
import Billing from './pages/Billing.jsx'
import './styles.css'

function Shell({ children }) {
  const nav = useNavigate()
  if (!hasToken()) return <Navigate to="/login" replace />
  return (
    <>
      <nav className="rail">
        <div className="brand">ChequeDesk<small>error-proof cheque printing</small></div>
        <NavLink to="/new">New cheque</NavLink>
        <NavLink to="/approvals">Approvals</NavLink>
        <NavLink to="/register">Register</NavLink>
        <NavLink to="/calibration">Calibration</NavLink>
        <NavLink to="/billing">Billing</NavLink>
        <div className="spacer" />
        <button className="signout" onClick={() => { setToken(null); nav('/login') }}>Sign out</button>
      </nav>
      <main>{children}</main>
    </>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/new" element={<Shell><NewCheque /></Shell>} />
        <Route path="/approvals" element={<Shell><Approvals /></Shell>} />
        <Route path="/register" element={<Shell><Register /></Shell>} />
        <Route path="/calibration" element={<Shell><Calibration /></Shell>} />
        <Route path="/billing" element={<Shell><Billing /></Shell>} />
        <Route path="*" element={<Navigate to="/new" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />)
