import { useState, useEffect } from 'react'

export default function KVStore() {
  const [data, setData] = useState({})

  useEffect(() => {
    const fetchData = () => {
      fetch('/api/kv')
        .then(res => res.json())
        .then(data => setData(data))
        .catch(console.error)
    }
    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="panel">
      <h2>Key-Value Store</h2>
      <pre className="code-block">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )
}
