import { useState, useEffect } from 'react'
import Status from './components/Status'
import Thoughts from './components/Thoughts'
import Batons from './components/Batons'
import KVStore from './components/KVStore'
import Logs from './components/Logs'
import Discussions from './components/Discussions'
import NetworkGraph from './components/NetworkGraph'
import Login from './components/Login'
import './App.css'

function App() {
  const [activeTab, setActiveTab] = useState('status')
  const [isAuthenticated, setIsAuthenticated] = useState(null)

  useEffect(() => {
    fetch('/api/status')
      .then(res => {
        if (res.status === 401) {
          setIsAuthenticated(false)
        } else {
          setIsAuthenticated(true)
        }
      })
      .catch(() => setIsAuthenticated(false))
  }, [])

  const handleLogout = () => {
    fetch('/api/logout', { method: 'POST' })
      .then(() => setIsAuthenticated(false))
  }

  if (isAuthenticated === null) return <div className="container"><p>Connecting to Liminal...</p></div>
  if (isAuthenticated === false) return <div className="container"><Login onLoginSuccess={() => setIsAuthenticated(true)} /></div>

  return (
    <div className="container">
      <header>
        <h1>Liminal Swarm</h1>
        <nav>
          <button onClick={() => setActiveTab('status')} className={activeTab === 'status' ? 'active' : ''}>Status</button>
          <button onClick={() => setActiveTab('network')} className={activeTab === 'network' ? 'active' : ''}>Network</button>
          <button onClick={() => setActiveTab('thoughts')} className={activeTab === 'thoughts' ? 'active' : ''}>Thoughts</button>
          <button onClick={() => setActiveTab('discussions')} className={activeTab === 'discussions' ? 'active' : ''}>Discussions</button>
          <button onClick={() => setActiveTab('batons')} className={activeTab === 'batons' ? 'active' : ''}>Batons</button>
          <button onClick={() => setActiveTab('kv')} className={activeTab === 'kv' ? 'active' : ''}>KV Store</button>
          <button onClick={() => setActiveTab('logs')} className={activeTab === 'logs' ? 'active' : ''}>Logs</button>
        </nav>
        <button onClick={handleLogout} style={{ marginLeft: 'auto', padding: '5px 10px', background: '#333' }}>Logout</button>
      </header>
      <main>
        {activeTab === 'status' && <Status />}
        {activeTab === 'network' && <NetworkGraph />}
        {activeTab === 'thoughts' && <Thoughts />}
        {activeTab === 'discussions' && <Discussions />}
        {activeTab === 'batons' && <Batons />}
        {activeTab === 'kv' && <KVStore />}
        {activeTab === 'logs' && <Logs />}
      </main>
    </div>
  )
}

export default App
