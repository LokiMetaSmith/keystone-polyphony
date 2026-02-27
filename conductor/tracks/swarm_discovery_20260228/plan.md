# Implementation Plan: Formalize Swarm Discovery & Communication

## Phase 1: Environmental & Constraints Analysis [checkpoint: f13ffe1]
- [x] Task: Define physical and digital realities (Visibility, Acoustics, RF, Bandwidth)
    - [x] Research current constraints
    - [x] Document in `docs/swarm-discovery/analysis.md`
- [x] Task: Create Modality Mapping Matrix (Swarm Action vs. Modality)
    - [x] Define mappings for Passive/Active Discovery, Tandem Action, Stigmergy
    - [x] Document in `docs/swarm-discovery/modality-matrix.md`
- [x] Task: Conductor - User Manual Verification 'Phase 1: Environmental & Constraints Analysis' (Protocol in workflow.md)

## Phase 2: Core Bootstrapping Hooks [checkpoint: 523bb17]
- [x] Task: Implement `install.sh`
    - [x] Write Tests: Verify idempotency and dependency checks
    - [x] Implement: Provisioning logic (OS config, drivers, libs)
- [x] Task: Implement `keystone-polyphony.sh`
    - [x] Write Tests: Verify daemon startup and swarm attachment
    - [x] Implement: Activation logic (Discovery, Gossip, Task loops)
- [x] Task: Conductor - User Manual Verification 'Phase 2: Core Bootstrapping Hooks' (Protocol in workflow.md)

## Phase 3: Multi-Granular Discovery Implementation [checkpoint: 9fe5ab1]
- [x] Task: Implement Contextual Attenuation
    - [x] Write Tests: Verify data filtering based on distance/urgency
    - [x] Implement: Filtering logic in `LiminalMesh`
- [x] Task: Implement Task-Announcing and Task-Picking
    - [x] Write Tests: Verify autonomous task selection
    - [x] Implement: Stigmergic/Digital Twin task logic
- [x] Task: Conductor - User Manual Verification 'Phase 3: Multi-Granular Discovery Implementation' (Protocol in workflow.md)

## Phase 4: Stigmergy and Tandem Action [checkpoint: a735283]
- [x] Task: Implement Environmental Stigmergy markers
    - [x] Write Tests: Verify marker persistence and readability
    - [x] Implement: Marker system (Digital/Physical placeholders)
- [x] Task: Implement Tandem Action (Micro/Nano Sync)
    - [x] Write Tests: Verify real-time sync for physical assistance
    - [x] Implement: Haptic/Force feedback or proximity sync logic
- [x] Task: Conductor - User Manual Verification 'Phase 4: Stigmergy and Tandem Action' (Protocol in workflow.md)

## Phase 5: Redundancy & Redefinition [checkpoint: 0830783]
- [x] Task: Implement Fallback & Redundancy paths
    - [x] Write Tests: Verify degradation to local mesh when broker is offline
    - [x] Implement: Fallback switching logic
- [x] Task: Final Documentation and BOM
    - [x] Generate Sensory Architecture Diagram
    - [x] Finalize Hardware BOM
- [x] Task: Conductor - User Manual Verification 'Phase 5: Redundancy & Redefinition' (Protocol in workflow.md)
