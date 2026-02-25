# Issue Pre-Review Triage: Vision and Impact

## Reasoning: Why This Is Highly Valuable

In a "Polyphony" ecosystem where many autonomous agents work alongside humans, the primary failure mode is **information entropy**. Agents are highly effective at "discovering" technical debt, bugs, and tangent opportunities, but dumping these discoveries directly into the upstream repository leads to:

1.  **Issue Pollution**: A high volume of low-quality or redundant issues that overwhelm human maintainers.
2.  **Quota Exhaustion**: Unchecked automated issue creation can quickly hit GitHub API limits or consume the project's agentic bandwidth.
3.  **Lack of Strategic Alignment**: Small discoveries might not fit the broader "Master Plan" currently being executed by the swarm.

**The Issue Pre-Review Triage solves this by introducing a "Stage Buffer".**

---

## Logic: How it Fits the Outlook of the Repo

Keystone Polyphony is designed as a **hierarchical swarm**. The "Architect" (Pulse/LLM) sets the direction, and "Agents" execute. The Triage system mirrors this hierarchy:

1.  **Discovery (Agent)**: An agent finds a bug or improvement and creates a lightweight `.github/issues/*.md` file in their working branch.
2.  **Pre-Review (Staging)**: When the PR is merged into `staging`, the `agent-issue-triage` workflow is triggered.
3.  **Triage (Agent-Powered)**: A specialized Triage Agent (configured via `TRIAGE_AGENTS`) analyzes the backlog of `.md` files:
    *   **Deduplication**: Merges similar findings into a single coherent document.
    *   *Refinement**: Enhances the technical description and adds necessary context or code references.
    *   **Validation**: Checks if the issue is still relevant or if it has already been addressed.
4.  **Publication (Upstream)**: Only "surgical" and high-value issues are published to the upstream repository as formal GitHub Issues.

This fits the **Mind Bridge** philosophy: it reduces noise while ensuring no valuable finding is lost, turning chaotic agent output into a structured, executable backlog.

---

## Expected Impact

*   **Higher Signal-to-Noise Ratio**: Maintainers and other agents focus only on high-quality, verified tasks.
*   **Scalability**: Allows hundreds of agents to work in parallel without fear of polluting the issue tracker.
*   **Permanent Discovery Log**: `meta/DISCOVERIES.md` becomes a curated history of project evolution, not just a dump of automated logs.
*   **Strategic Control**: The project can enforce quality standards on automated contributions, just as it does for code.

---

## Implementation Outlook

The system will live in `.github/workflows/agent-issue-triage.yml` and utilize the `scripts/triage-lib.sh` utilities. It marks the transition from "Agents as basic solvers" to "Agents as integrated repository maintainers".
