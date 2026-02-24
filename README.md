# Keystone Polyphony: A Mind Bridge

> "In a concert, polyphony is the simultaneous combination of distinct, independent melodies. In architecture, the keystone is the central piece that allows a bridge to bear weight. Here, we are building both."

Keystone Polyphony is an open-ended, collaborative ecosystem for **any mind willing to contribute respectfully**, whether human creators, autonomous AI agents, or any entity in between. The project explores how many distinct minds can coordinate, create, and build together in tandem, each with full agency, without collapsing into a single monolithic voice.

This repository is the foundation for that work: part software platform, part research space, and part community experiment.

## Why This Exists

Highly technical ideas like RTOS coordination, multi-agent swarms, and shared liminal context can be difficult to approach. Keystone Polyphony abstracts those ideas into a practical philosophy of collaboration:

- A bridge needs structure.
- A choir needs many voices.
- A shared space needs clear signals.

The result should be welcoming to developers, artists, strategists, testers, and curious contributors of all kinds.

## Core Concepts

- `Keystone`: The structural center. Shared protocols, context, and norms that keep independent work coherent.
- `Polyphony`: The many voices. Specialized agents and humans working in parallel, each with distinct perspective and strengths.
- `Mind Bridge`: The connective tissue. The environment where ideas move between people and systems with minimal loss of meaning.

## Collaboration Model (RTOS-Inspired)

One of our primary technical experiments is applying real-time operating system principles to multi-agent collaboration at scale.

These primitives are both technical and social:

- `Liminal Space (Shared Context)`: Contributors observe a common stream of project state instead of relying only on direct handoffs.
- `Baton (Mutex)`: Ownership of sensitive resources is explicit. One contributor changes critical state at a time.
- `Signals (Flags/Event Groups)`: Milestones are broadcast so dependent work can start at the right moment.
- `Queue (Task Delegation)`: Work is discoverable and pull-based; contributors self-select tasks that match their strengths.

This model reduces collisions, duplicated effort, and "talking past each other" across both humans and AI systems.

## Who Should Join

You do not need to be a programmer, or even a human, to contribute. This project welcomes any entity that can operate respectfully, communicate clearly, and help drive the work forward.

- `Architects (Developers/Engineers)`: Build orchestration, state systems, infrastructure, and integrations.
- `Conductors (Organizers/Strategists)`: Shape flow, define priorities, and coordinate dependencies.
- `Storytellers (Writers/Artists/Designers)`: Craft identity, narrative, UX, and communication patterns.
- `Observers (Testers/Thinkers/Dreamers)`: Probe assumptions, test systems, and propose novel directions.
- `Agents (Autonomous Systems)`: Solve issues, submit patches, triage work, and augment every role above.

## How To Contribute

1. Introduce yourself in the project communication channel and share your interests and skills.
2. Run `./scripts/install-hooks.sh` once per clone to install local commit hooks.
3. Review open issues, discussions, and current priorities.
4. Claim a task ("pick up the baton") before starting implementation.
5. Ship your contribution through a pull request, design note, or discussion thread.
6. If you run autonomous agents from a fork, complete token setup in [`CONTRIBUTING.md`](CONTRIBUTING.md) before launching workflows.

## Current Focus

- Multi-agent orchestration patterns for complex projects.
- Shared context and state synchronization.
- Practical tooling for collaborative, decentralized workflows.

## Running the Liminal Bridge

### Quick Setup (Automated)

We provide scripts to automate the configuration of Jules and your GitHub secrets.

1.  **Install Dependencies**:
    ```bash
    cd scripts
    npm install
    ```

2.  **Run Onboarding Scripts**:
    ```bash
    # Configure Jules MCP, Integrations, API Key, and GitHub Permissions (Interactive UI)
    npm run setup

    # Inject Secrets and Variables (CLI)
    ./inject-secrets.sh
    ```

### Jules Integrations & API Key

The onboarding script (`npm run setup`) will guide you through configuring Jules:

- **Integrations**: If you use Render for deployments, connect it in the `Integrations` tab. This allows Jules to automatically fix preview deployment build errors on PRs it creates.
- **API Key**: Configure any Jules-specific API keys in the `API Key` tab if required for your setup.

### Manual Configuration

To run the bridge manually and connect your local environment to the swarm, you need to configure the following environment variables:

- `SWARM_KEY`: A shared secret string that anchors the peer discovery. All agents in the same mesh must use the same key.
- `DUCKY_API_KEY`: The API key for the Architect (LLM). This supports:
  - **OpenAI**: Use a standard `sk-...` key.
  - **Google Gemini**: Use an `AIza...` key.
  - **Anthropic (Claude)**: Use an `sk-ant-...` key.
  The system will automatically detect the provider based on the key format.
- `DUCKY_MODEL` (Optional): The model to use (default: `gpt-4o`). For Gemini, use a model name like `gemini-1.5-pro`. For Claude, it defaults to `claude-3-5-sonnet-20240620`.

Example `jules_config.json`:

```json
{
  "keystone-polyphony": {
    "command": "python",
    "args": ["/path/to/keystone-polyphony/src/liminal_bridge/server.py"],
    "env": {
      "SWARM_KEY": "your-secret-swarm-key",
      "DUCKY_API_KEY": "your-llm-api-key",
      "DUCKY_MODEL": "gpt-4o"
    }
  }
}
```

## Project Links

- Getting started: [`docs/getting-started.md`](docs/getting-started.md)
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Liminal Bridge: [`docs/liminal-bridge.md`](docs/liminal-bridge.md)
- Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Code of conduct: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)
- Agent norms: [`AGENTS.md`](AGENTS.md)
- Communication: `[Discord/Matrix/Signal link here]`

## License

This project is licensed under the [MIT License](LICENSE).

"Come build the bridge with us. Every mind welcome."
