import { useState } from 'react'
import Status from './components/Status'
import Thoughts from './components/Thoughts'
import Batons from './components/Batons'
import KVStore from './components/KVStore'
import Logs from './components/Logs'
import NetworkGraph from './components/NetworkGraph'
import './App.css'

function App() {
  const [activeTab, setActiveTab] = useState('status')

  return (
    <div className="container">
      <header>
        <h1>Liminal Swarm</h1>
        <nav>
          <button onClick={() => setActiveTab('status')} className={activeTab === 'status' ? 'active' : ''}>Status</button>
          <button onClick={() => setActiveTab('network')} className={activeTab === 'network' ? 'active' : ''}>Network</button>
          <button onClick={() => setActiveTab('thoughts')} className={activeTab === 'thoughts' ? 'active' : ''}>Thoughts</button>
          <button onClick={() => setActiveTab('batons')} className={activeTab === 'batons' ? 'active' : ''}>Batons</button>
          <button onClick={() => setActiveTab('kv')} className={activeTab === 'kv' ? 'active' : ''}>KV Store</button>
          <button onClick={() => setActiveTab('logs')} className={activeTab === 'logs' ? 'active' : ''}>Logs</button>
        </nav>
      </header>
      <main>
        {activeTab === 'status' && <Status />}
        {activeTab === 'network' && <NetworkGraph />}
        {activeTab === 'thoughts' && <Thoughts />}
        {activeTab === 'batons' && <Batons />}
        {activeTab === 'kv' && <KVStore />}
        {activeTab === 'logs' && <Logs />}
      </main>
    </div>
  )
}

export default App
