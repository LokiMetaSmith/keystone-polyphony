import { useState, useEffect } from 'react'

export default function Logs() {
  const [logs, setLogs] = useState([])

  useEffect(() => {
    const fetchData = () => {
      fetch('/api/logs')
        .then(res => res.json())
        .then(data => {
            // Sort by timestamp descending
            const sorted = data.sort((a, b) => b.timestamp - a.timestamp);
            setLogs(sorted);
        })
        .catch(console.error)
    }
    fetchData()
    const interval = setInterval(fetchData, 2000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="panel">
      <h2>Log Aggregation</h2>
      {logs.length === 0 ? <p>No logs.</p> : (
        <ul className="log-list">
          {logs.map((log, i) => (
            <li key={i} className={`log-entry log-${log.level}`}>
              [{new Date(log.timestamp * 1000).toLocaleTimeString()}] [{log.origin?.substring(0,8)}] {log.level.toUpperCase()}: {log.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
