import { useState, useEffect } from 'react'

export default function Batons() {
  const [data, setData] = useState({})
  const [nodeId, setNodeId] = useState(null)
  const [batonName, setBatonName] = useState('')
  const [acquiring, setAcquiring] = useState(false)

  useEffect(() => {
    // Fetch Node ID
    fetch('/api/status')
      .then(res => res.json())
      .then(data => setNodeId(data.node_id))
      .catch(console.error)

    const fetchData = () => {
      fetch('/api/batons')
        .then(res => res.json())
        .then(data => setData(data))
        .catch(console.error)
    }
    fetchData()
    const interval = setInterval(fetchData, 2000)
    return () => clearInterval(interval)
  }, [])

  const handleAcquire = (e) => {
    e.preventDefault()
    if (!batonName.trim()) return

    setAcquiring(true)
    fetch('/api/batons', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resource: batonName, action: 'acquire' })
    })
      .then(res => res.json())
      .then(resp => {
        setAcquiring(false)
        if (resp.success) {
          setBatonName('')
          // Refresh
          fetch('/api/batons').then(res => res.json()).then(data => setData(data))
        } else {
          alert('Failed to acquire baton (already held or denied).')
        }
      })
      .catch(err => {
        console.error(err)
        setAcquiring(false)
      })
  }

  const handleRelease = (resource) => {
    fetch('/api/batons', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resource: resource, action: 'release' })
    })
      .then(res => res.json())
      .then(() => {
         // Refresh
         fetch('/api/batons').then(res => res.json()).then(data => setData(data))
      })
      .catch(console.error)
  }

  return (
    <div className="panel">
      <h2>Active Locks (Batons)</h2>

      <form onSubmit={handleAcquire} style={{ marginBottom: '20px' }}>
        <input
          type="text"
          value={batonName}
          onChange={(e) => setBatonName(e.target.value)}
          placeholder="Resource name..."
          disabled={acquiring}
          style={{ width: '50%', padding: '8px', marginRight: '10px' }}
        />
        <button type="submit" disabled={acquiring}>
          {acquiring ? 'Acquiring...' : 'Acquire Baton'}
        </button>
      </form>

      {Object.entries(data).length === 0 ? <p>No active locks.</p> : (
        <ul>
          {Object.entries(data).map(([resource, owner]) => (
            <li key={resource} style={{ marginBottom: '5px' }}>
              <strong>{resource}:</strong> Held by {owner === nodeId ? 'YOU' : owner}
              {owner === nodeId && (
                <button
                  onClick={() => handleRelease(resource)}
                  style={{ marginLeft: '10px', padding: '2px 8px', fontSize: '0.8em' }}
                >
                  Release
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
