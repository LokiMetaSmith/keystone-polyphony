const Hyperswarm = require('hyperswarm');
const crypto = require('hypercore-crypto');
const b4a = require('b4a');
const readline = require('readline');

// Get topic from args
const topicHex = process.argv[2];
if (!topicHex) {
  process.stderr.write(JSON.stringify({ type: 'error', message: 'No topic provided' }) + '\n');
  process.exit(1);
}

const topic = b4a.from(topicHex, 'hex');

// Check for bootstrap nodes
let bootstrap = undefined;
if (process.argv.includes('--bootstrap')) {
  const idx = process.argv.indexOf('--bootstrap');
  if (idx !== -1 && process.argv[idx + 1]) {
    const addr = process.argv[idx + 1];
    const [host, port] = addr.split(':');
    bootstrap = [{ host, port: parseInt(port) }];
    process.stderr.write(`[Sidecar] Using bootstrap node: ${host}:${port}\n`);
  }
}

// Check for seed
let keyPair = undefined;
if (process.argv.includes('--seed')) {
  const idx = process.argv.indexOf('--seed');
  if (idx !== -1 && process.argv[idx + 1]) {
    const seedHex = process.argv[idx + 1];
    const seed = b4a.from(seedHex, 'hex');
    keyPair = crypto.keyPair(seed);
    process.stderr.write(`[Sidecar] Using stable identity: ${b4a.toString(keyPair.publicKey, 'hex')}\n`);
  }
}

// Initialize Hyperswarm
const swarm = new Hyperswarm({ bootstrap, keyPair });
const peers = new Map();
const discoveries = new Map(); // Store discovery objects

// Join the swarm
const discovery = swarm.join(topic, { client: true, server: true });
discoveries.set(topicHex, discovery);
discovery.flushed().then(() => {
  process.stderr.write(`[Sidecar] Joined topic ${topicHex}\n`);
});

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

  // Prevent uncaught stream errors from crashing the sidecar
  rl.on('error', (err) => {
    // Silently ignore connection timeouts/resets from short-lived CLI scripts
  });

  // Hyperswarm streams can emit errors unconditionally.
  conn.on('error', () => { });

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
    // Suppress ETIMEDOUT when short-lived wrapper scripts disconnect instantly
    // process.stderr.write(JSON.stringify({ type: 'debug', message: 'Connection error', peer_id: peerId, err: err.message }) + '\n');
  });
});

// Handle local input from Python (stdin)
const rl = readline.createInterface({
  input: process.stdin,
  terminal: false
});

rl.on('line', (line) => {
  try {
    if (!line.trim()) return;
    const command = JSON.parse(line);

    if (command.type === 'broadcast') {
      const msg = JSON.stringify(command.payload) + '\n';
      for (const [id, conn] of peers) {
        try {
          conn.write(msg);
        } catch (err) {
          // Ignore write errors to dead connections
        }
      }
    } else if (command.type === 'join') {
      const tHex = command.payload.topic;
      if (!discoveries.has(tHex)) {
        const newTopic = b4a.from(tHex, 'hex');
        const d = swarm.join(newTopic, { client: true, server: true });
        discoveries.set(tHex, d);
        d.flushed().then(() => {
          process.stderr.write(`[Sidecar] Joined additional topic ${tHex}\n`);
        });
      }
    } else if (command.type === 'leave') {
      const tHex = command.payload.topic;
      if (discoveries.has(tHex)) {
        const d = discoveries.get(tHex);
        d.destroy().then(() => {
          process.stderr.write(`[Sidecar] Left topic ${tHex}\n`);
        });
        discoveries.delete(tHex);
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

// Prevent unhandled errors from internal Hyperswarm dependencies (like ETIMEDOUT on Stream) from crashing the sidecar
process.removeAllListeners('uncaughtException');
process.removeAllListeners('unhandledRejection');

process.on('uncaughtException', (err) => {
  // We explicitly silently swallow network IO faults here to keep the master bridge alive.
});

process.on('unhandledRejection', (err) => {
  // Catch rogue ETIMEDOUT promises
});
