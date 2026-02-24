import { useState, useEffect } from 'react'

export default function Thoughts() {
  const [data, setData] = useState({})

  useEffect(() => {
    const fetchThoughts = () => {
      fetch('/api/thoughts')
        .then(res => res.json())
        .then(data => setData(data))
        .catch(console.error)
    }
    fetchThoughts()
    const interval = setInterval(fetchThoughts, 2000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="panel">
      <h2>Thoughts Stream</h2>
      {Object.entries(data).length === 0 ? <p>No thoughts yet.</p> : (
        <ul>
          {Object.entries(data).map(([node, thought]) => (
            <li key={node}>
              <strong>{node}:</strong> {thought}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
