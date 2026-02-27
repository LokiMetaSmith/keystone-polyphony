# Technology Stack

## Languages
- **Python 3:** Primary language for server-side logic, agent orchestration, and coordination primitives.
- **JavaScript (ES6+):** Used for the Node.js P2P sidecar and the browser-resident dashboard.
- **HTML5 / CSS3:** Standard web technologies for the user interface.

## Frameworks & Libraries
### Backend & Coordination
- **aiohttp:** Asynchronous HTTP server for the Liminal Bridge.
- **pydantic:** Data validation and settings management using Python type annotations.
- **Hyperswarm:** A distributed networking stack for peer discovery and connectivity (running in a Node.js sidecar).
- **paho-mqtt:** Client library for MQTT communication (Zone-level telemetry).
- **Model Context Protocol (MCP):** For standardized interaction between agents and tools.

### Frontend
- **React 18:** Component-based UI library for the Interactive Dashboard.
- **Vite:** Next-generation frontend tooling for fast development and building.
- **react-force-graph-2d:** Visualization of the distributed network mesh.

### Security & Identity
- **cryptography (Python):** For server-side cryptographic operations and secure communication.
- **TweetNaCl (JS):** Cryptographic library for browser-side Ed25519 identity management.

## LLM Integrations
- **OpenAI / Anthropic / Google Gemini:** Supported cloud-based model providers.
- **Ollama:** Support for local model execution.

## Development & Testing
- **pytest & pytest-asyncio:** Testing frameworks for verifying core logic and asynchronous operations.
- **flake8 & black:** Linting and code formatting for Python.
- **Vite Preview:** For local verification of dashboard builds.
