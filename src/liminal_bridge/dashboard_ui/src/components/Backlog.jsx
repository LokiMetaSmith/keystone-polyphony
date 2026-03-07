import { useState, useEffect } from 'react'

export default function Backlog() {
  const [tasks, setTasks] = useState([])
  const [nodeId, setNodeId] = useState(null)
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [priority, setPriority] = useState('medium')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetch('/api/status')
      .then(res => res.json())
      .then(data => setNodeId(data.node_id))
      .catch(console.error)

    const fetchTasks = () => {
      fetch('/api/backlog')
        .then(res => res.json())
        .then(data => {
            // Deduplicate by task ID, keep latest status (heuristic)
            const map = {}
            data.forEach(t => {
                if (!map[t.id] || t.status !== 'todo') {
                    map[t.id] = t
                }
            })
            setTasks(Object.values(map))
        })
        .catch(console.error)
    }
    fetchTasks()
    const interval = setInterval(fetchTasks, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleAddTask = (e) => {
    e.preventDefault()
    if (!title.trim()) return

    setLoading(true)
    fetch('/api/backlog', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'add', title, description: desc, priority })
    })
      .then(res => res.json())
      .then(() => {
        setLoading(false)
        setTitle('')
        setDesc('')
        // Refresh
        fetch('/api/backlog').then(res => res.json()).then(setTasks)
      })
      .catch(err => {
        console.error(err)
        setLoading(false)
      })
  }

  const handleClaim = (taskId) => {
    fetch('/api/backlog', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'claim', task_id: taskId })
    })
      .then(res => res.json())
      .then(resp => {
        if (resp.error) alert(resp.error)
      })
      .catch(console.error)
  }

  const handleComplete = (taskId) => {
    fetch('/api/backlog', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'complete', task_id: taskId })
    })
      .then(res => res.json())
      .catch(console.error)
  }

  return (
    <div className="panel">
      <h2>Swarm Backlog</h2>

      <form onSubmit={handleAddTask} style={{ marginBottom: '30px', border: '1px solid #444', padding: '15px' }}>
        <h3>Add New Task</h3>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Task Title..."
          disabled={loading}
          style={{ width: '100%', padding: '8px', marginBottom: '10px' }}
        />
        <textarea
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder="Description..."
          disabled={loading}
          style={{ width: '100%', padding: '8px', marginBottom: '10px', height: '60px' }}
        />
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <select value={priority} onChange={(e) => setPriority(e.target.value)} disabled={loading}>
                <option value="low">Low Priority</option>
                <option value="medium">Medium Priority</option>
                <option value="high">High Priority</option>
            </select>
            <button type="submit" disabled={loading}>
            {loading ? 'Adding...' : 'Add Task'}
            </button>
        </div>
      </form>

      <div className="task-list">
        {tasks.length === 0 ? <p>No tasks found.</p> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            {tasks.sort((a,b) => (a.status === 'done' ? 1 : -1)).map(task => (
              <div key={task.id} style={{ border: '1px solid #555', padding: '10px', borderRadius: '4px', background: task.status === 'done' ? '#222' : '#2a2a2a' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <h4 style={{ margin: 0, textDecoration: task.status === 'done' ? 'line-through' : 'none' }}>{task.title}</h4>
                    <span style={{ fontSize: '0.8em', color: task.priority === 'high' ? '#ff5555' : task.priority === 'medium' ? '#ffff55' : '#55ff55' }}>
                        {task.priority.toUpperCase()}
                    </span>
                </div>
                <p style={{ fontSize: '0.9em', color: '#ccc', margin: '5px 0' }}>{task.description}</p>
                <div style={{ fontSize: '0.8em', color: '#999' }}>
                    Status: <strong>{task.status}</strong> | Owner: {task.owner === nodeId ? 'YOU' : (task.owner || 'Unassigned')}
                </div>
                <div style={{ marginTop: '10px' }}>
                    {task.status === 'todo' && (
                        <button onClick={() => handleClaim(task.id)} style={{ padding: '2px 10px' }}>Claim</button>
                    )}
                    {task.status === 'in_progress' && task.owner === nodeId && (
                        <button onClick={() => handleComplete(task.id)} style={{ padding: '2px 10px' }}>Complete</button>
                    )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
