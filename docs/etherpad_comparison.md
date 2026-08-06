# Etherpad vs. Keystone Polyphony: A Concurrency & Storage Comparison

Both Etherpad and Keystone Polyphony are designed to manage concurrent changes and collaborative state, yet their architectural paradigms represent two fundamentally different approaches to distributed systems: the traditional centralized Operations Transformation (OT) model versus the modern decentralized Conflict-free Replicated Data Type (CRDT) and Mesh model.

## 1. Concurrency Management

### Etherpad: Operational Transformation (OT)
- **Mechanism:** Etherpad relies on Operational Transformation (OT) to provide extremely fine-grained concurrency control (character-by-character editing). Changesets (deltas) are sent to a central server which transforms operations to maintain consistency across all connected clients.
- **Benefits:** Ideal for real-time collaborative text editing where multiple users modify the same block of text simultaneously.
- **Drawbacks:** Requires a central server (single point of failure) to resolve and sequence the transformations.

### Keystone Polyphony: CRDTs and Batons
- **Mechanism:** Keystone relies heavily on Conflict-free Replicated Data Types (CRDTs) such as `LWWRegister` (Last-Write-Wins), `PNCounter`, `GSet`, and `ORSet`, broadcasted over a P2P Mesh. Additionally, for file-level conflict avoidance, it employs a `Baton` locking mechanism (`polyphony baton acquire`).
- **Benefits:** Decentralized, offline-first, and highly resilient. CRDTs guarantee eventual consistency without requiring a central authority.
- **Drawbacks:** The current `Baton` locking is relatively coarse (file-level). Fine-grained, real-time simultaneous editing of the same file block by multiple agents requires more complex CRDTs (like sequence CRDTs).

## 2. Storage and Database Architecture

### Etherpad: UeberDB (Key-Value Abstraction)
- **Mechanism:** Etherpad utilizes an abstraction layer called `UeberDB`. Regardless of the underlying backend (DirtyDB, MySQL, Postgres, Redis), it treats the database as a simple Key-Value store. Everything is flattened into keys like `pad:$PADID`, `pad:$PADID:revs:$REVNUM`, and `globalAuthor:$AUTHORID`.
- **Benefits:** Extreme portability. Users can trivially swap out database engines (e.g., from SQLite to Postgres) using a unified configuration (`settings.json`).

### Keystone Polyphony: CRDT Key-Value Store & DistributedKVCache
- **Mechanism:** Keystone maintains an in-memory Key-Value store where the values are CRDT objects (persisted via `_save_kv` to SQLite or snapshots). Furthermore, for large blobs (like LLM KV caches), it utilizes `DistributedKVCache`, which seeds binary blobs via Pollen P2P and broadcasts the resulting hashes via Keystone's CRDT mesh.
- **Benefits:** Native P2P support for large binary assets and eventual consistency baked directly into the state model, avoiding the need for a dedicated relational database backend.

## 3. Network and Messaging Topology

### Etherpad: Client-Server WebSockets
- **Mechanism:** A centralized Node.js backend handles all incoming WebSocket connections, processes transformations, and broadcasts the finalized state out to clients.

### Keystone Polyphony: P2P Mesh
- **Mechanism:** Agents communicate through decentralized encrypted broadcasts. The `LiminalMesh` handles local state merging and gossiping. Bounded mailboxes with active load-shedding policies (e.g., `FAIL_FAST`, `DROP_OLDEST`) handle backpressure locally within agent boundaries (`BaseIsolate`).

---

## 4. Lessons Learned and Integration Recommendations (TODO)

Etherpad's history provides valuable insights into scaling collaborative systems. Based on this comparison, here are recommended integration steps and features we can consider porting or adapting:

- [ ] **Finer-Grained CRDTs for Text:** Evaluate replacing or augmenting the coarse file-level `Baton` lock with a Sequence CRDT (like Yjs or Automerge). This would allow fine-grained, character-by-character resolution similar to Etherpad's OT without sacrificing our P2P architecture.
- [ ] **Adopt UeberDB-like Storage Portability:** While our current KV/CRDT store is effective, implementing an abstraction layer (similar to UeberDB) could allow node operators to persist mesh state in scalable backends like Redis or PostgreSQL instead of just local SQLite/JSON snapshots.
- [ ] **Granular Revision History:** Etherpad explicitly stores a sequence of revisions (`pad:$PADID:revs:$REVNUM`). We should consider adding a dedicated CRDT or logging mechanism that specifically tracks incremental code changesets/deltas, enabling agents to "rewind" state similar to Etherpad's timeslider feature.
