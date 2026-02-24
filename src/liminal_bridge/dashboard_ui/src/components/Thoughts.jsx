import { useState, useEffect } from 'react'

export default function Thoughts() {
  const [data, setData] = useState({})
  const [inputThought, setInputThought] = useState('')
  const [submitting, setSubmitting] = useState(false)

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

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!inputThought.trim()) return

    setSubmitting(true)
    fetch('/api/thoughts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ thought: inputThought })
    })
      .then(res => res.json())
      .then(() => {
        setInputThought('')
        setSubmitting(false)
        // Refresh immediately
        fetch('/api/thoughts').then(res => res.json()).then(data => setData(data))
      })
      .catch(err => {
        console.error(err)
        setSubmitting(false)
      })
  }

  return (
    <div className="panel">
      <h2>Thoughts Stream</h2>

      <form onSubmit={handleSubmit} style={{ marginBottom: '20px' }}>
        <input
          type="text"
          value={inputThought}
          onChange={(e) => setInputThought(e.target.value)}
          placeholder="Share a thought..."
          disabled={submitting}
          style={{ width: '70%', padding: '8px', marginRight: '10px' }}
        />
        <button type="submit" disabled={submitting}>
          {submitting ? 'Sending...' : 'Send Thought'}
        </button>
      </form>

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
