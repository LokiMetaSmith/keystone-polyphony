# Bug: Define delivery guarantees for mixed MQTT, BLE, and Hyperswarm swarms

The LokiMetaSmith integration at a837308 introduces alternate broadcast transports. A successful MQTT publish bypasses Hyperswarm, so DHT-only peers miss high-urgency updates in a mixed swarm. BLE discovery likewise cannot guarantee coverage of DHT peers; after a partial BLE success, failed or undiscovered recipients can miss the message.

The integration fixes BLE sending only to the first matching discovered device and switches discovery to advertisement UUIDs. It intentionally does not unconditionally publish over every transport: command-request callbacks currently lack duplicate suppression, so dual delivery can execute a command twice.

Design explicit per-peer transport capability/coverage tracking or message IDs and duplicate suppression before enabling redundant broadcasts. Test MQTT-only, DHT-only, mixed peers, partial BLE failure, and the same command arriving through multiple transports. Keep MQTT and BLE opt-in until coverage and execution semantics are documented and verified. Live broker and BLE hardware validation remain outstanding.
