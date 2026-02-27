# Sensory Architecture Diagram

## 1. Overview
This diagram represents the sensory modalities and their operational ranges for the Keystone Polyphony worker node.

```mermaid
graph TD
    subgraph Macro [Macro-Level: >5m]
        M1[Gossip Protocol]
        M2[Hyperswarm DHT]
        M3[5G / Wi-Fi]
    end

    subgraph Meso [Meso-Level: 1m - 5m]
        S1[UWB Mesh]
        S2[LiDAR SLAM]
        S3[Radar mmWave]
    end

    subgraph Micro [Micro-Level: 0.1m - 1m]
        V1[Visual Fiducials ArUco/QR]
        V2[LED Status Matrix]
        V3[BLE Beacons]
    end

    subgraph Nano [Nano-Level: <0.1m]
        F1[Force-Torque Sensors]
        F2[Haptic Feedback]
        F3[IR Proximity Array]
    end

    Node[Worker Node Daemon] --> Macro
    Node --> Meso
    Node --> Micro
    Node --> Nano

    style Macro fill:#f9f,stroke:#333,stroke-width:2px
    style Meso fill:#bbf,stroke:#333,stroke-width:2px
    style Micro fill:#bfb,stroke:#333,stroke-width:2px
    style Nano fill:#fbb,stroke:#333,stroke-width:2px
```

## 2. Attenuation Logic
- **Default State:** Global sync via Macro-level Gossip.
- **Proximity Trigger:** Activate UWB/LiDAR when peers are within 5m.
- **Precision Trigger:** Activate Visual tracking for tandem alignment under 1m.
- **Safety Trigger:** Activate IR Proximity for collision avoidance.
