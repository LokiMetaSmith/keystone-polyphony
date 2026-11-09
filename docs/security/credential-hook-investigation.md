# Historical root npm install-hook investigation

## Scope

This document records the repository-level follow-up for #88. The security
review is separate from the reliability and transport fixes in the same PR.

## Verified repository evidence

- Commit `befedc3bbf68875e9c32a10fd6f78af84b49b0ab` added a
  root `package.json` on 2026-06-16. That manifest included a
  `preinstall` hook that attempted to read environment and GitHub
  authentication data, encode it, and transmit it through repository automation.
  This is credential-capture behavior and is not legitimate build configuration.
- Commit `0319076de9f9873fa6ecf444230aa9e0b3d89288` removed the
  root manifest on 2026-11-08. No root `package.json` is present
  in the current repository tree.
- Review of the workflows and Dockerfile present at the introducing commit
  found Node installation for global agent CLIs and the nested sidecar, but
  did not identify a scripted root-level `npm install` there.
  This evidence does **not** rule out historical CI jobs or developer commands
  that used a root install at another point in time.

No suspicious hook was executed during this investigation. Do not restore or
run the historical root manifest to reproduce the behavior.

## Preventive control

The repository has no required root Node package. The lint and required CI
checks now reject a root `package.json` entirely, even when
it contains an innocent script or is a dangling symlink. Nested manifests
used by the sidecar, dashboard, and setup scripts are not blocked.

A future legitimate root package must receive a new security design review
before relaxing this rule. Local Git hooks are bypassable; repository CI is the
enforcement point. A direct push or an unreviewed privileged workflow could
still circumvent these checks, so repository permissions remain necessary.

## Historical exposure remains unknown

Git history and repository code do not prove whether the hook ran in a
developer's shell, a previous CI revision, or a local clone, and do not prove
that no secret was accessed or transmitted. This investigation has no
authorization to inspect developer machines, private credential stores,
or administrative audit logs. There is no defensible claim of zero exposure.

The repository owner must review available GitHub audit/action logs,
unexpected PR comments, and the lifetime of tokens that existed between
2026-06-16 and 2026-11-08. Revoke and replace any credential that could have
been exposed. Keep the review private when it involves secret values.
If evidence of actual exposure appears, use a separate incident response
process. Closing the code-level defect does not certify completion of
credential rotation or a historical security audit.
