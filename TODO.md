# Keystone Polyphony - Remaining Tasks & Future Roadmap

This document outlines the next steps and planned improvements for the "Liminal Bridge" system.

## 1. Persistence & Durability
- [x] **State Persistence**: Currently, the `LiminalMesh` KV store is ephemeral (in-memory). Implement a backing store (SQLite or local JSON file) to persist state across restarts.
- [x] **Snapshotting**: Periodic snapshots of the "Liminal Space" to the git repository (e.g., `.liminal/snapshot.json`) to allow recovery.

## 2. Conflict Resolution
- [x] **CRDTs**: Replace the basic "Last Write Wins" (LWW) strategy with Conflict-free Replicated Data Types (CRDTs) for the KV store and thoughts. This ensures better consistency in distributed environments.
- [x] **Vector Clocks**: Implement vector clocks to order events more accurately than wall-clock timestamps.

## 3. Security & Authentication
- [x] **Per-Agent Identity**: Currently, all agents share a single `SWARM_KEY`. Implement per-agent public/private key pairs for signing messages.
- [x] **Key Rotation**: Mechanism to rotate the `SWARM_KEY` without disrupting the entire mesh.
- [x] **Message Encryption**: Ensure all P2P traffic is encrypted (Hyperswarm does this by default, but application-level encryption for sensitive payloads might be needed).

## 4. Observability & Tooling
- [x] **Swarm Dashboard**: A web-based visualizer (React/Next.js) to see connected nodes, active locks (Batons), and the stream of thoughts in real-time.
- [x] **Log Aggregation**: Centralized logging for the swarm to debug distributed issues.
- [x] **Interactive Dashboard**: Allow sending thoughts and acquiring batons from the dashboard.
- [x] **Secure Dashboard**: Add authentication to the dashboard to prevent unauthorized access.

## 5. Advanced Architect Features
- [x] **Provider Agnosticism**: Abstract the `Architect` class to support Google (Gemini), Anthropic (Claude), and local LLMs (Ollama) in addition to OpenAI.
- [x] **Prompt Engineering**: Refine the system prompts for the Architect to better handle complex project backlogs and dependencies.

## 6. Testing & CI/CD
- [x] **Network Simulation**: Integration tests that simulate real-world NAT traversal and latency.
- [x] **Load Testing**: Verify the system behavior with 50+ agents to ensure scalability of the DHT and Gossipsub.
- [x] **Automated Sidecar Setup**: Ensure Node.js dependencies are installed automatically when the python package is installed or run.

## 7. Testing & Quality Improvements
- [x] **`tests/test_network_simulation.py`**: Replace `assert True` in `test_packet_loss` with meaningful probabilistic bounds assertions (e.g., `0 < val <= total_sent`).
- [x] **`tests/test_ensemble_chat.py`**: Replace conditional `print` statements with standard `assert` statements to ensure pytest correctly registers failures.
- [x] **`tests/test_architect_commands.py`**: Refactor to use idiomatic `assert` statements instead of boolean returns and prints for pass/fail logic.
- [x] **`scripts/load_test.py`**: Improve `KeyboardInterrupt` handling to ensure resources (DB files, identities) are cleaned up properly even on interrupted runs.
- [x] **`tests/test_ssh_exchange.py`**: Refine the `except SystemExit: pass` block to distinguish between expected successful exits and unexpected error exits (e.g., `sys.exit(1)`).

## 8. Hybrid WASM LLM Engine (Pollen + Keystone)
This section tracks the work required to build a fully decentralized, peer-to-peer AI pipeline by layering Keystone Polyphony's agent coordination over Pollen's distributed compute fabric.

- [x] **WASM LLM Compilation:** Compile a lightweight LLM inference engine (e.g., a variant of `llama.cpp` or WasmNN) into a WebAssembly module compatible with Pollen's pure Go runtime. (Using `tangledgroup/llama-cpp-wasm` via `scripts/build_wasm_llm.sh`)
- [ ] **Pollen Compute Integration:** Write a Pollen wrapper around the WASM engine so it can receive inference requests via Pollen's QUIC transport and return generated tokens.
- [ ] **Model Weight Distribution:** Implement a mechanism to chunk and distribute large `.gguf` model files over Pollen's content-addressed peer-to-peer blob sharing (`pln seed`).
- [ ] **Hardware Capability Routing:** Implement Pollen-level metadata tags (`--prop role=gpu` or `--prop vram=16GB`) to ensure inference requests route only to capable shards.
- [ ] **Keystone Inference Provider:** Update Keystone's `Architect` class to accept a "Pollen Mesh" provider endpoint instead of just standard REST APIs (OpenAI/Anthropic).
- [ ] **Agent Task Handoff:** Modify the Keystone `swarm_backlog` logic so agents can seamlessly delegate heavy cognitive tasks (like summarizing massive codebases) down to the Pollen compute layer via `command_request` broadcasts.
- [ ] **Context Sync Loop:** Ensure the text output from Pollen WASM execution is automatically ingested back into Keystone's CRDT state as an agent "Thought," updating the shared Liminal Space context.
