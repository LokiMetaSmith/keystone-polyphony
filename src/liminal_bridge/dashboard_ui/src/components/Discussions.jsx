import { useState, useEffect } from 'react'

export default function Discussions() {
    const [discussions, setDiscussions] = useState({})
    const [activeTopic, setActiveTopic] = useState('architecture')
    const [inputMsg, setInputMsg] = useState('')
    const [submitting, setSubmitting] = useState(false)

    const fetchDiscussions = () => {
        fetch('/api/discussions')
            .then(res => res.json())
            .then(data => {
                setDiscussions(data)
                // Set first topic as active if none selected
                if (!activeTopic && Object.keys(data).length > 0) {
                    setActiveTopic(Object.keys(data)[0])
                }
            })
            .catch(console.error)
    }

    useEffect(() => {
        fetchDiscussions()
        const interval = setInterval(fetchDiscussions, 3000)
        return () => clearInterval(interval)
    }, [])

    const handleSubmit = (e) => {
        e.preventDefault()
        if (!inputMsg.trim()) return

        setSubmitting(true)
        fetch('/api/thoughts', { // Note: server.py handles ensemble_chat via share_thought-like logic but specifically for set
            // Actually, I need a dedicated POST endpoint for ensemble_chat if I want to post from dashboard.
            // For now, I'll use the existing /api/thoughts which posts a 'thought'
            // WAIT: I should add a specific POST endpoint for chat in dashboard.py or use a CLI tool.
            // Let's stick to reading first, or add handle_post_chat to dashboard.py
        })
        // REVISIT: I'll add handle_post_chat to dashboard.py in the next step.
        console.log("Posting to topic:", activeTopic, inputMsg)
        setSubmitting(false)
    }

    return (
        <div className="panel" style={{ display: 'flex', gap: '20px', height: '600px' }}>
            <div style={{ width: '200px', borderRight: '1px solid #444', paddingRight: '10px' }}>
                <h3>Topics</h3>
                {Object.keys(discussions).length === 0 ? <p>No threads.</p> : (
                    <ul style={{ listStyle: 'none', padding: 0 }}>
                        {Object.keys(discussions).map(topic => (
                            <li
                                key={topic}
                                onClick={() => setActiveTopic(topic)}
                                style={{
                                    padding: '8px',
                                    cursor: 'pointer',
                                    background: activeTopic === topic ? '#333' : 'transparent',
                                    borderRadius: '4px',
                                    marginBottom: '5px'
                                }}
                            >
                                #{topic}
                            </li>
                        ))}
                    </ul>
                )}
                <button onClick={() => {
                    const t = prompt("Enter new topic name:");
                    if (t) setActiveTopic(t);
                }} style={{ width: '100%', marginTop: '10px' }}>+ New Topic</button>
            </div>

            <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                <h3>#{activeTopic} Discussion</h3>
                <div style={{ flex: 1, overflowY: 'auto', marginBottom: '20px', padding: '10px', background: '#111', borderRadius: '4px' }}>
                    {(!discussions[activeTopic] || discussions[activeTopic].length === 0) ? <p>No messages yet. Start the conversation!</p> : (
                        discussions[activeTopic].map((m, i) => (
                            <div key={i} style={{ marginBottom: '12px', borderBottom: '1px solid #222', paddingBottom: '8px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8em', color: '#888' }}>
                                    <strong>{m.sender?.substring(0, 8)}</strong>
                                    <span>{new Date(m.timestamp * 1000).toLocaleTimeString()}</span>
                                </div>
                                <div style={{ marginTop: '4px' }}>{m.content}</div>
                            </div>
                        ))
                    )}
                </div>

                <p style={{ fontSize: '0.9em', color: '#666', fontStyle: 'italic' }}>
                    Note: Discussion participation from dashboard is coming soon. Use 'ensemble_chat' tool for now.
                </p>
            </div>
        </div>
    )
}
