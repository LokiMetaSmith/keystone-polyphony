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

- [x] **Finer-Grained CRDTs for Text:** Evaluate replacing or augmenting the coarse file-level `Baton` lock with a Sequence CRDT (like Yjs or Automerge). This would allow fine-grained, character-by-character resolution similar to Etherpad's OT without sacrificing our P2P architecture.
- [ ] **Adopt UeberDB-like Storage Portability:** While our current KV/CRDT store is effective, implementing an abstraction layer (similar to UeberDB) could allow node operators to persist mesh state in scalable backends like Redis or PostgreSQL instead of just local SQLite/JSON snapshots.
- [ ] **Granular Revision History:** Etherpad explicitly stores a sequence of revisions (`pad:$PADID:revs:$REVNUM`). We should consider adding a dedicated CRDT or logging mechanism that specifically tracks incremental code changesets/deltas, enabling agents to "rewind" state similar to Etherpad's timeslider feature.

---

## 5. Technical Evaluation: Finer-Grained Text CRDTs

To move beyond our current coarse file-level `Baton` locking and unlock true fine-grained, concurrent text editing (similar to Etherpad's Operational Transformation), we need to implement a Sequence CRDT. The two primary paths forward are adopting an established library (like Yjs via `y-py` or Automerge) versus building a bespoke Sequence CRDT natively into `LiminalMesh`.

### Path A: Integrating Existing Libraries (`y-py` / `automerge-repo`)

**Pros:**
- **Robustness & Performance:** Libraries like Yjs and Automerge have years of optimizations (e.g., block-based updates, optimized binary encoding) specifically designed to handle massive text documents and millions of edits without memory bloat.
- **Ecosystem Compatibility:** They come with robust ecosystems, including pre-built bindings for frontend editors (ProseMirror, Monaco, Quill), which would make UI integration seamless if we ever expose agent scratchpads to human users.
- **Advanced Features:** Built-in support for undo/redo tracking, selective state synchronization, and efficient garbage collection.

**Cons:**
- **Architectural Impedance Mismatch:** These libraries often have their own specific networking paradigms (e.g., `y-webrtc`, `y-websocket`). Integrating them directly into our existing `LiminalMesh` encrypted gossip protocol would require writing custom provider adapters.
- **Binary Blobs in CRDTs:** The state updates are often opaque binary blobs. If we broadcast these blobs over our mesh, they cannot be easily introspected or audited by our existing declarative effects (`BaseEffect`).
- **Dependency Weight:** Introduces native Rust/C++ dependencies (via `y-py` or `automerge-python`), complicating our current build matrix and WASM engine integration.

### Path B: Building a Bespoke Sequence CRDT (Native `LiminalMesh`)

**Pros:**
- **Perfect Architectural Fit:** We can build it as a native subclass of our abstract `CRDT` base class in `src/liminal_bridge/crdt.py`. It would perfectly integrate with our `LiminalMesh._deserialize_crdt` routing and `_save_kv` persistence without complex adapters.
- **Introspectability:** Plain text/JSON diffs over the mesh are completely transparent. This makes our `audit_log` and role-based access control (RBAC) rules much simpler to enforce.
- **Minimal Dependencies:** Keeps our python environment purely native and lightweight, which is highly beneficial for deployment alongside our hybrid WASM compute fabric.

**Cons:**
- **Reinventing the Wheel:** Text-based Sequence CRDTs (like Logoot, LSEQ, or RGA) are notoriously difficult to get right. Handling edge cases around concurrent insertion/deletion anomalies ("interleaving") requires significant effort.
- **Performance Overhead:** A pure-Python implementation of a sequence CRDT without block-level compression will likely suffer from memory bloat and CPU overhead if agents are concurrently appending thousands of tokens in long-running contexts.

### Conclusion

If the immediate goal is to rapidly prototype collaborative agent scratchpads where the total document size and edit frequency remain relatively constrained, **Path B (Bespoke Native CRDT)** is the safest bet to maintain architectural purity and auditability.

However, if agents are expected to collaboratively author large codebases or generate massive context files in real-time, the performance limits of a native Python Sequence CRDT will quickly become a bottleneck. In that scenario, the engineering effort of writing a `LiminalMesh` provider adapter for **Path A (`y-py`)** would be vastly outweighed by the performance gains.
