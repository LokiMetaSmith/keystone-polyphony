import { useState, useEffect } from 'react'
import { getIdentity, toHex, signHex, signString } from '../crypto'

export default function Login({ onLoginSuccess }) {
  const [identity, setIdentity] = useState(null)
  const [inviteCode, setInviteCode] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [mode, setMode] = useState('login') // 'login' or 'register'

  useEffect(() => {
    const id = getIdentity()
    setIdentity(id)

    // Auto-attempt login on mount
    attemptLogin(id)
  }, [])

  const attemptLogin = (id) => {
    setLoading(true)
    const pubKeyHex = toHex(id.publicKey)

    // 1. Get Challenge
    fetch('/api/auth/challenge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ public_key: pubKeyHex })
    })
    .then(res => res.json())
    .then(data => {
      if (data.nonce) {
        // 2. Sign Challenge
        const signature = signHex(data.nonce, id)

        // 3. Verify
        return fetch('/api/auth/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ public_key: pubKeyHex, signature })
        })
      }
      throw new Error(data.error || 'Challenge failed')
    })
    .then(res => res.json())
    .then(data => {
      if (data.status === 'ok') {
        onLoginSuccess()
      } else if (data.status === 'unauthorized') {
        setMode('register')
        setError('Identity not authorized. Please enter invite code.')
      } else {
        throw new Error(data.error || 'Verification failed')
      }
    })
    .catch(err => {
      console.warn("Auto-login failed:", err)
      // If purely network error, maybe retry?
      // If 401/400, stay on login screen
      setError(err.message)
    })
    .finally(() => setLoading(false))
  }

  const handleRegister = (e) => {
    e.preventDefault()
    if (!inviteCode) return

    setLoading(true)
    setError(null)
    const pubKeyHex = toHex(identity.publicKey)

    // Sign the invite code to prove we own the key we are registering
    const signature = signString(inviteCode, identity)

    fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        public_key: pubKeyHex,
        invite_code: inviteCode,
        signature: signature
      })
    })
    .then(res => res.json())
    .then(data => {
      if (data.status === 'registered') {
        onLoginSuccess()
      } else {
        throw new Error(data.error || 'Registration failed')
      }
    })
    .catch(err => setError(err.message))
    .finally(() => setLoading(false))
  }

  if (!identity) return <div>Initializing Identity...</div>

  return (
    <div className="panel" style={{ maxWidth: '500px', margin: '50px auto', textAlign: 'center' }}>
      <h2>Liminal Access</h2>

      <div style={{ marginBottom: '20px', wordBreak: 'break-all', fontSize: '0.8em', color: '#888' }}>
        <strong>Your Identity (Public Key):</strong><br/>
        {toHex(identity.publicKey)}
      </div>

      {mode === 'login' && (
        <div>
          <p>Authenticating...</p>
          {error && (
            <div style={{ marginTop: '20px' }}>
              <p style={{ color: 'red' }}>{error}</p>
              <button onClick={() => attemptLogin(identity)} disabled={loading}>Retry Login</button>
              <button onClick={() => setMode('register')} style={{ marginLeft: '10px' }}>Register</button>
            </div>
          )}
        </div>
      )}

      {mode === 'register' && (
        <form onSubmit={handleRegister}>
          <p>This identity is not authorized. Please enter an invite code to join the swarm.</p>
          <div style={{ marginBottom: '15px' }}>
            <input
              type="text"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              placeholder="Enter Invite Code (Check Server Logs)"
              style={{ width: '100%', padding: '10px' }}
            />
          </div>
          {error && <div style={{ color: 'red', marginBottom: '10px' }}>{error}</div>}
          <button type="submit" disabled={loading} style={{ width: '100%', padding: '10px' }}>
            {loading ? 'Registering...' : 'Join Swarm'}
          </button>
          <button type="button" onClick={() => { setMode('login'); setError(null); }} style={{ marginTop: '10px', background: 'transparent', border: 'none', color: '#888', cursor: 'pointer' }}>
            Back to Login
          </button>
        </form>
      )}
    </div>
  )
}
