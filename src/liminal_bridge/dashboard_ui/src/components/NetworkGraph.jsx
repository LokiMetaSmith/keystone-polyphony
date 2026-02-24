import { useState, useEffect, useRef } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

export default function NetworkGraph() {
  const [data, setData] = useState({ nodes: [], links: [] })
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const containerRef = useRef(null)

  useEffect(() => {
    const updateDimensions = () => {
        if (containerRef.current) {
            setDimensions({
                width: containerRef.current.clientWidth - 40, // padding adjustment
                height: 600
            })
        }
    }

    window.addEventListener('resize', updateDimensions)
    updateDimensions()

    const fetchData = () => {
      fetch('/api/network')
        .then(res => res.json())
        .then(map => {
            const nodes = new Set()
            const links = []

            // map is node_id -> [connected_ids]
            Object.entries(map).forEach(([source, targets]) => {
                nodes.add(source)
                targets.forEach(target => {
                    nodes.add(target)
                    links.push({ source, target })
                })
            })

            // If empty (e.g. single node tracking itself only if self-loop? usually map has entry for self)
            // Backend implementation: self.network_map[self.node_id] = connected_nodes
            // So if I am alone, map = { "my_id": [] }
            // So nodes = ["my_id"], links = []

            setData({
                nodes: Array.from(nodes).map(id => ({ id, name: id })),
                links
            })
        })
        .catch(console.error)
    }

    fetchData()
    const interval = setInterval(fetchData, 5000)

    return () => {
        clearInterval(interval)
        window.removeEventListener('resize', updateDimensions)
    }
  }, [])

  return (
    <div className="panel" ref={containerRef}>
      <h2>Network Graph</h2>
      <div style={{ border: '1px solid #333', borderRadius: '4px', overflow: 'hidden' }}>
        <ForceGraph2D
            width={dimensions.width}
            height={dimensions.height}
            graphData={data}
            nodeLabel="id"
            nodeAutoColorBy="id"
            linkDirectionalParticles={2}
            linkDirectionalParticleSpeed={0.005}
            backgroundColor="#1a1a1a"
        />
      </div>
    </div>
  )
}
