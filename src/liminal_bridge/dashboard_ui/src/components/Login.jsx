import { useState } from 'react'

export default function Login({ onLoginSuccess }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    })
    .then(res => {
      if (res.ok) {
        onLoginSuccess()
      } else {
        setError('Invalid password')
      }
    })
    .catch(() => setError('Login failed'))
    .finally(() => setLoading(false))
  }

  return (
    <div className="panel" style={{ maxWidth: '400px', margin: '50px auto', textAlign: 'center' }}>
      <h2>Liminal Access</h2>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '15px' }}>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter Access Key"
            style={{ width: '100%', padding: '10px' }}
          />
        </div>
        {error && <div style={{ color: 'red', marginBottom: '10px' }}>{error}</div>}
        <button type="submit" disabled={loading} style={{ width: '100%', padding: '10px' }}>
          {loading ? 'Verifying...' : 'Unlock'}
        </button>
      </form>
    </div>
  )
}
