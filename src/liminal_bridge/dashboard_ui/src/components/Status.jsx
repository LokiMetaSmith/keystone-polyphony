import { useState, useEffect } from 'react'

export default function Status() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchStatus = () => {
      fetch('/api/status')
        .then(res => res.json())
        .then(data => setData(data))
        .catch(err => setError(err.message))
    }
    fetchStatus()
    const interval = setInterval(fetchStatus, 2000)
    return () => clearInterval(interval)
  }, [])

  if (error) return <div className="error">Error: {error}</div>
  if (!data) return <div>Loading...</div>

  return (
    <div className="panel">
      <h2>Network Status</h2>
      <ul>
        <li><strong>Node ID:</strong> {data.node_id}</li>
        <li><strong>Topic:</strong> {data.topic}</li>
        <li><strong>Running:</strong> {data.running ? 'Yes' : 'No'}</li>
        <li><strong>Peers ({data.peers.length}):</strong>
          <ul>
            {data.peers.map(p => <li key={p}>{p}</li>)}
          </ul>
        </li>
      </ul>
    </div>
  )
}
