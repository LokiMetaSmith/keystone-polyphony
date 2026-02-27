# Hardware Bill of Materials (BOM)

## 1. Overview
Preliminary list of required sensors and emitters per worker node to support the Multi-Granular Discovery and Communication Architecture.

## 2. Sensor List

| Modality | Component | Quantity | Description |
|---|---|---|---|
| Macro | 5G/Wi-Fi Module | 1 | Global connectivity and telemetry. |
| Meso | UWB Transceiver | 3 | Triangulation and ranging (e.g., Decawave DW1000). |
| Meso | LiDAR Module | 1 | 360-degree SLAM and obstacle detection (e.g., RPLidar A1). |
| Micro | Wide-Angle Camera | 2 | ArUco/QR code detection and pose estimation. |
| Micro | BLE Beacon | 1 | Passive proximity broadcasting. |
| Micro | LED Matrix | 1 | 8x8 or 16x16 Status display for intent signaling. |
| Nano | Force-Torque Sensor | 1 | Integrated into end-effector for tandem sync. |
| Nano | IR Proximity Array | 1 | 4-8 sensors for ultra-short range detection. |

## 3. Processing Unit
- **SoC:** NVIDIA Jetson Orin or equivalent (support for local AI/processing models).
- **MCU:** ESP32 (handles low-level sensor polling and UWB mesh).
