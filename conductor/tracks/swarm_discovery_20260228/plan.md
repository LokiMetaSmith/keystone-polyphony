# Implementation Plan: Formalize Swarm Discovery & Communication

## Phase 1: Environmental & Constraints Analysis [checkpoint: f13ffe1]
- [x] Task: Define physical and digital realities (Visibility, Acoustics, RF, Bandwidth)
    - [x] Research current constraints
    - [x] Document in `docs/swarm-discovery/analysis.md`
- [x] Task: Create Modality Mapping Matrix (Swarm Action vs. Modality)
    - [x] Define mappings for Passive/Active Discovery, Tandem Action, Stigmergy
    - [x] Document in `docs/swarm-discovery/modality-matrix.md`
- [x] Task: Conductor - User Manual Verification 'Phase 1: Environmental & Constraints Analysis' (Protocol in workflow.md)

## Phase 2: Core Bootstrapping Hooks
- [ ] Task: Implement `install.sh`
    - [ ] Write Tests: Verify idempotency and dependency checks
    - [ ] Implement: Provisioning logic (OS config, drivers, libs)
- [ ] Task: Implement `keystone-polyphony.sh`
    - [ ] Write Tests: Verify daemon startup and swarm attachment
    - [ ] Implement: Activation logic (Discovery, Gossip, Task loops)
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Core Bootstrapping Hooks' (Protocol in workflow.md)

## Phase 3: Multi-Granular Discovery Implementation
- [ ] Task: Implement Contextual Attenuation
    - [ ] Write Tests: Verify data filtering based on distance/urgency
    - [ ] Implement: Filtering logic in `LiminalMesh`
- [ ] Task: Implement Task-Announcing and Task-Picking
    - [ ] Write Tests: Verify autonomous task selection
    - [ ] Implement: Stigmergic/Digital Twin task logic
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Multi-Granular Discovery Implementation' (Protocol in workflow.md)

## Phase 4: Stigmergy and Tandem Action
- [ ] Task: Implement Environmental Stigmergy markers
    - [ ] Write Tests: Verify marker persistence and readability
    - [ ] Implement: Marker system (Digital/Physical placeholders)
- [ ] Task: Implement Tandem Action (Micro/Nano Sync)
    - [ ] Write Tests: Verify real-time sync for physical assistance
    - [ ] Implement: Haptic/Force feedback or proximity sync logic
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Stigmergy and Tandem Action' (Protocol in workflow.md)

## Phase 5: Redundancy & Redefinition
- [ ] Task: Implement Fallback & Redundancy paths
    - [ ] Write Tests: Verify degradation to local mesh when broker is offline
    - [ ] Implement: Fallback switching logic
- [ ] Task: Final Documentation and BOM
    - [ ] Generate Sensory Architecture Diagram
    - [ ] Finalize Hardware BOM
- [ ] Task: Conductor - User Manual Verification 'Phase 5: Redundancy & Redefinition' (Protocol in workflow.md)
