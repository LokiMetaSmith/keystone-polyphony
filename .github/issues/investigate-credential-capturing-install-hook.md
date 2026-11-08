# Security: Investigate credential-capturing root npm install hook

During integration of LokiMetaSmith/main at a837308, inspection found a tracked root `package.json` introduced by commit `befedc3bbf68875e9c32a10fd6f78af84b49b0ab` (`ci: update build configuration`). It predates this fork synchronization.

Its `preinstall` hook scans process environments, reads GitHub authentication configuration, encodes captured values into build output, and contains code intended to post captured data as PR comments and delete workflow logs. This is concrete credential-capture behavior, beyond ordinary operational-token wiring.

The integration removes the root manifest, which contains no application dependencies. The separate sidecar, dashboard, and scripts manifests remain in use. The hook was not executed during this integration; prior execution and actual exposure have not been established.

Follow up by determining whether this hook ran in previous developer or CI environments, reviewing associated logs/comments and the introducing change, and revoking any credentials confirmed exposed. Check related history for similar payloads. Avoid copying captured values or the executable payload into public issues. Add a narrowly scoped regression check against unauthorized root install hooks if appropriate.
