const Hyperswarm = require('hyperswarm');
const crypto = require('hypercore-crypto');
const b4a = require('b4a');
const readline = require('readline');

// Initialize Hyperswarm
const swarm = new Hyperswarm();
const peers = new Map();

// Get topic from args
const topicHex = process.argv[2];
if (!topicHex) {
  process.stderr.write(JSON.stringify({ type: 'error', message: 'No topic provided' }) + '\n');
  process.exit(1);
}

const topic = b4a.from(topicHex, 'hex');

// Join the swarm
// Wait for discovery to be fully announced
swarm.join(topic);

// Handle connections
swarm.on('connection', (conn, info) => {
  const peerId = b4a.toString(info.publicKey, 'hex');
  peers.set(peerId, conn);

  // Notify Python
  process.stdout.write(JSON.stringify({ type: 'peer_connected', peer_id: peerId }) + '\n');

  // Handle incoming data as line-delimited JSON
  const rl = readline.createInterface({
    input: conn,
    crlfDelay: Infinity
  });

  rl.on('line', (line) => {
    try {
      if (!line.trim()) return;
      const message = JSON.parse(line);
      process.stdout.write(JSON.stringify({ type: 'message', peer_id: peerId, payload: message }) + '\n');
    } catch (e) {
      // Ignore malformed JSON from peers
    }
  });

  conn.on('close', () => {
    peers.delete(peerId);
    process.stdout.write(JSON.stringify({ type: 'peer_disconnected', peer_id: peerId }) + '\n');
  });

  conn.on('error', (err) => {
    peers.delete(peerId);
    // process.stderr.write(JSON.stringify({ type: 'debug', message: 'Connection error', peer_id: peerId }) + '\n');
  });
});

// Handle local input from Python (stdin)
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: false
});

rl.on('line', (line) => {
  try {
    if (!line.trim()) return;
    const command = JSON.parse(line);

    if (command.type === 'broadcast') {
      const msg = JSON.stringify(command.payload) + '\n';
      for (const [id, conn] of peers) {
        conn.write(msg);
      }
    }
  } catch (e) {
    process.stderr.write(JSON.stringify({ type: 'error', message: 'Invalid input from Python', details: e.message }) + '\n');
  }
});

// Cleanup on exit
process.on('SIGINT', async () => {
  await swarm.destroy();
  process.exit(0);
});
