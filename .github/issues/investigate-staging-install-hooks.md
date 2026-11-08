# Security: Investigate credential-capturing install hooks in existing staging history

While reconciling PR #86 with staging at 55d438a, inspection found a root setup.py and a modified root package.json containing environment/token capture and encoded shell/Python payloads. The staging-only history consists of earlier "ci: update build configuration" commits. These files are unrelated to legitimate bridge packaging.

The integration merge preserves the intended root package.json deletion and excludes setup.py from the resulting tree. Neither install hook was executed during this work. Promotion's prior success-only placeholder has been replaced with a fail-closed command while real isolated tests are installed.

Investigate the staging commits, automation identity and earlier run logs to establish whether either hook ran and whether credentials were exposed. Coordinate any credential response with the repository owner based on confirmed exposure. Do not execute or copy these payloads into executable fixtures. This extends the existing investigation of the root npm preinstall hook already present in main history.
