import { useState, useEffect } from 'react'

export default function Batons() {
  const [data, setData] = useState({})

  useEffect(() => {
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

  return (
    <div className="panel">
      <h2>Active Locks (Batons)</h2>
      {Object.entries(data).length === 0 ? <p>No active locks.</p> : (
        <ul>
          {Object.entries(data).map(([resource, owner]) => (
            <li key={resource}>
              <strong>{resource}:</strong> Held by {owner}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
