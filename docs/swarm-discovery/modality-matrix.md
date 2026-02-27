# Modality Mapping Matrix

## 1. Overview
This matrix maps swarm actions to the appropriate communication and discovery modalities across the four granular levels: Macro, Meso, Micro, and Nano.

## 2. Action vs. Modality Matrix

| Swarm Action | Macro (Global/Zone) | Meso (Proximity) | Micro (Passive Intent) | Nano (Tandem Sync) |
|---|---|---|---|---|
| **Passive Discovery** | Gossip (Epidemic Routing) | UWB Beaconing | LED Status / BLE | N/A |
| **Active Discovery** | Hyperswarm DHT | LiDAR / Radar Scan | ArUco/QR Detection | IR Proximity Array |
| **Tandem Action** | Digital Twin Sync | UWB Range/AoA | BLE RSSI | Force-Torque / Haptic |
| **Stigmergy** | Global Task Board | LiDAR Occupancy | RFID / Physical Tags | Mechanical Coupling |

## 3. Modality Definitions

### 3.1 Macro-Level (Global/Zone)
- **Wi-Fi / 5G:** Primary transport for high-bandwidth telemetry.
- **Hyperswarm:** P2P discovery and DHT-based routing.
- **Gossip:** Low-bandwidth broadcast of state changes (e.g., baton acquisition).

### 3.2 Meso-Level (Proximity)
- **Ultra-Wideband (UWB):** High-precision ranging and Angle-of-Arrival (AoA) for relative positioning.
- **LiDAR:** Simultaneous Localization and Mapping (SLAM) and obstacle detection.

### 3.3 Micro-Level (Passive Intent)
- **Visual Fiducials (ArUco/QR):** Identification and 6-DOF pose estimation at short range.
- **LED Status Matrices:** Human-and-machine readable broadcast of current node intent/mode.

### 3.4 Nano-Level (Tandem Sync)
- **Force-Torque Sensors:** Real-time physical feedback for collaborative lifting/moving.
- **IR Proximity:** Ultra-short range collision avoidance and alignment.

## 4. Execution Logic
- **Default:** Nodes use Macro-level Gossip for global awareness.
- **Attenuation:** When nodes are within 5m, they activate Meso-level UWB.
- **Precision:** Within 1m, Micro-level visual tracking is prioritized to save RF bandwidth.
- **Contact:** Physical interaction triggers Nano-level force feedback loops.
