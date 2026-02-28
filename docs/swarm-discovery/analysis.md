# Environmental & Constraints Analysis

## 1. Overview
This document defines the physical and digital realities of the operating environment for the Keystone Polyphony swarm. These constraints inform the selection and attenuation of communication modalities.

## 2. Physical Realities

### 2.1 Operating Environment
- **Setting:** Industrial/Research spaces (e.g., factory floors, lab environments).
- **Dynamic Obstacles:** Moving personnel, machinery, and other swarm nodes.

### 2.2 Visibility
- **Line-of-Sight (LoS):** Required for Micro-level visual fiducials (ArUco/QR) and Nano-level IR proximity.
- **Occlusion:** High probability in dynamic environments. Optical modes must degrade gracefully to non-LoS modes (e.g., UWB).

### 2.3 Acoustics
- **Ambient Noise:** High in industrial settings. Acoustic sonar/communication is susceptible to interference from high-frequency machinery.

### 2.4 RF Interference
- **Spectrum Congestion:** 2.4GHz/5GHz (Wi-Fi) may be crowded.
- **Multipath:** RF signals (UWB, Wi-Fi) subject to reflections off metallic surfaces common in industrial environments.

## 3. Digital Realities

### 3.1 Bandwidth Limits
- **Macro-Level:** Wi-Fi/5G provides high bandwidth but high energy/infrastructure cost.
- **Meso/Micro-Level:** Gossip protocols and UWB mesh have limited throughput. High-frequency global state syncing must be avoided to prevent network saturation.

### 3.2 Latency
- **Variable Latency:** P2P DHT-based discovery (Hyperswarm) has non-deterministic startup latency.
- **Real-Time Requirements:** Nano-level tandem actions (physical assistance) require sub-10ms latency for haptic/force feedback.

### 3.3 Compute Budget
- **Edge Processing:** Worker nodes must process sensor data (LiDAR, Visual) locally to minimize transmission overhead.
- **Resource Contention:** Local AI model execution competes with communication stacks for CPU/Memory cycles.

## 4. Key Constraints Summary

| Reality | Constraint | Mitigation Strategy |
|---|---|---|
| Visibility | Occlusion | Fallback from optical to UWB/RF |
| RF | Interference | Frequency hopping / Contextual Attenuation |
| Bandwidth | Congestion | Aggressive filtering / Passive markers |
| Latency | Jitter | Local feedback loops for tandem action |
| Compute | Power/Heat | Event-driven processing / Sleep states |
