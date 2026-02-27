# Specification: Formalize Swarm Discovery & Communication (ENG-SWARM-002)

## Overview
Design, document, and implement a **Multi-Granular Discovery and Communication Architecture** for the autonomous swarm machinery. This track standardizes the node bootstrapping process to ensure zero-touch activation and grid-attachment.

## Functional Requirements
1. **Standardized Bootstrapping Hooks:**
   - `install.sh`: Idempotent provisioning script. Installs all dependencies (OS-level, sensor drivers, communication libraries, AI models).
   - `./keystone-polyphony.sh`: Activation script. Bootstraps the daemon for discovery, gossip, task-announcing, task-picking, and tandem action.
2. **Multi-Granular Discovery:**
   - Implement logic for Macro (Global), Meso (Proximity), Micro (Passive Intent), and Nano (Tandem Sync) modalities.
   - Support Contextual Attenuation to aggressively filter data based on distance and urgency.
3. **Swarm Behaviors:**
   - **Gossip:** Sync global state via epidemic routing.
   - **Task-Announcing:** Advertise capabilities and readiness.
   - **Task-Picking:** Autonomously select tasks based on stigmergic markers or digital twin.
   - **Task-Helping / Tandem Action:** Physical assistance of peers using Micro/Nano modes.
4. **Environmental Stigmergy:**
   - Implement markers for progress tracking by other workers.
5. **Fallback & Redundancy:**
   - Define and implement degradation paths (e.g., local UWB/visual fallback if central broker is offline).

## Non-Functional Requirements
- **Idempotency:** `install.sh` must be safe to run multiple times.
- **Low Latency:** High-frequency synchronization for tandem actions.
- **Bandwidth Efficiency:** Prioritize passive/environmental communication.
- **Test Coverage:** >80% for all new logic.

## Acceptance Criteria
- [ ] `install.sh` successfully provisions a new node.
- [ ] `./keystone-polyphony.sh` successfully attaches a node to the swarm.
- [ ] Discovery works across at least two modalities (e.g., Macro/Gossip and Meso/UWB).
- [ ] Nodes can pick and announce tasks without central intervention.
- [ ] Automated tests verify the fallback degradation paths.
