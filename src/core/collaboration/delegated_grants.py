"""One-level delegated grant allocations in the canonical task and artifact journal.

Only a trusted runtime consumes these grants. Its broker must authenticate guest
contexts independently; a delegation identifier from guest JSON is never authority.
"""

import hashlib
import json
import math
import re
import secrets

from .errors import Conflict

DELEGATED_GRANT_POLICY_FIELDS = frozenset(
    {
        "max_delegated_grants",
        "max_grant_seconds",
        "max_grant_turns",
        "grant_capabilities",
    }
)
CAPTURES = frozenset({"patch", "log", "manifest"})


class DelegatedGrantNotAllocated(Conflict):
    """A new delegated grant was conclusively rejected before allocation."""


def delegated_grant_policy(profile):
    """Read defaults without inserting them into an approved profile digest."""
    if not profile or not profile.get("max_delegated_grants", 0):
        return None
    return {key: profile[key] for key in DELEGATED_GRANT_POLICY_FIELDS}


def _seconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("grant seconds must be positive and finite")


class DelegatedGrantAuthority:
    def _delegation_root(self, db, attempt_id, binding, runtime_principal):
        from .managed_runtime import bounded_text

        if runtime_principal is not None:
            return self._managed_attempt(db, attempt_id, binding, runtime_principal)
        # None is injected only by the service for an authenticated owner.
        root = self._get(db, "attempt", bounded_text(attempt_id, "attempt_id"))
        external = root.get("runtime_binding", {})
        if root.get("execution_mode") != "external" or any(
            external.get(key) != value for key, value in binding.items()
        ):
            raise Conflict("root is outside the managed scope")
        return root

    def _delegation(self, db, root, delegation_id):
        from .managed_runtime import bounded_text

        delegation = self._get(
            db, "delegation", bounded_text(delegation_id, "delegation_id")
        )
        if delegation["binding"]["root_attempt_id"] != root["id"]:
            raise Conflict("delegation is outside the authorized root lineage")
        return delegation

    def _delegations(self, db, root_id):
        return [
            delegation
            for delegation in self._all(db, "delegation")
            if delegation["binding"]["root_attempt_id"] == root_id
        ]

    def _delegation_permission(self, db, root, delegation, profile):
        current = self._managed_permission(db, root, profile)
        allowed, reason = current["launch_allowed"], current["reason"]
        if delegation["termination_confirmed"] or delegation.get("revoked"):
            allowed, reason = False, "delegation is terminated or revoked"
        elif (
            delegation["boot_id"] != self.boot_id
            or self.monotonic_clock() >= delegation["monotonic_deadline"]
        ):
            allowed, reason = False, "delegation permission expired"
        remaining = (
            max(
                0,
                min(root["monotonic_deadline"], delegation["monotonic_deadline"])
                - self.monotonic_clock(),
            )
            if allowed
            else 0
        )
        binding = delegation["binding"]
        return {
            "schema_version": 1,
            "deployment_id": binding["deployment_id"],
            "repository": binding["repository"],
            "root_attempt_id": root["id"],
            "delegation": delegation,
            "binding": binding,
            "instructions": delegation["instructions"],
            "launch_allowed": allowed,
            "remaining_seconds": remaining,
            "reason": reason,
        }

    def managed_delegated_grant(
        self,
        deployment_id,
        repository,
        runtime_principal,
        attempt_id,
        request_key,
        instructions,
        seconds,
        max_turns,
        capabilities,
        profiles,
    ):
        from .authority import digest
        from .managed_runtime import bounded_text, scope

        bounded_text(request_key, "request_key")
        bounded_text(instructions, "grant instructions", 1_000_000)
        _seconds(seconds)
        if type(max_turns) is not int or max_turns < 1:
            raise ValueError("max_turns must be a positive integer")
        if (
            not isinstance(capabilities, list)
            or len(capabilities) > 100
            or any(not isinstance(value, str) for value in capabilities)
            or len(set(capabilities)) != len(capabilities)
        ):
            raise ValueError("grant capabilities must be distinct identifiers")
        for value in capabilities:
            bounded_text(value, "capability")
        payload = {
            "instructions": instructions,
            "seconds": seconds,
            "max_turns": max_turns,
            "capabilities": sorted(capabilities),
        }
        binding = scope(deployment_id, repository)
        key = digest([runtime_principal, attempt_id, request_key])
        with self.transaction() as db:
            root = self._delegation_root(db, attempt_id, binding, runtime_principal)
            profile = profiles.get(root["runtime_binding"]["profile"])
            prior = db.execute(
                "SELECT body FROM records WHERE kind='delegation_start' AND id=?",
                (key,),
            ).fetchone()
            if prior:
                saved = json.loads(prior[0])
                if saved["payload"] != payload:
                    raise Conflict("delegation retry key payload changed")
                delegation = self._delegation(db, root, saved["delegation_id"])
                return self._delegation_permission(db, root, delegation, profile)
            policy = delegated_grant_policy(profile)
            permission = self._managed_permission(db, root, profile)
            if not permission["launch_allowed"]:
                raise DelegatedGrantNotAllocated(permission["reason"])
            if root.get("delegation_admission_closed") or policy is None:
                raise DelegatedGrantNotAllocated(
                    "delegation admission is closed or unsupported"
                )
            if len(self._delegations(db, attempt_id)) >= policy["max_delegated_grants"]:
                raise DelegatedGrantNotAllocated(
                    "root lifetime delegated grant limit exhausted"
                )
            if (
                seconds > policy["max_grant_seconds"]
                or max_turns > policy["max_grant_turns"]
                or not set(capabilities) <= set(policy["grant_capabilities"])
            ):
                raise DelegatedGrantNotAllocated(
                    "delegated grant request exceeds approved policy"
                )
            task = self._get(db, "task", root["task"])
            if task["allocated_seconds"] + seconds > task["budget_seconds"]:
                raise DelegatedGrantNotAllocated("task time allowance exhausted")
            delegation_id = "del_" + secrets.token_hex(16)
            immutable = {
                **binding,
                "delegation_id": delegation_id,
                "root_attempt_id": attempt_id,
                "parent_attempt_id": attempt_id,
                "task_id": root["task"],
                "runtime_principal": runtime_principal,
                "worker_id": root["runtime_binding"]["worker_id"],
                "profile": root["runtime_binding"]["profile"],
                "profile_digest": root["runtime_binding"]["profile_digest"],
                "requirements_revision": root["requirements_revision"],
                "base": root["runtime_binding"]["base"],
                "launch_key": "polyphony-delegation:" + delegation_id,
                "allocated_seconds": seconds,
                "deadline": min(root["deadline"], self.clock() + seconds),
                "max_turns": max_turns,
                "capabilities": sorted(capabilities),
                "instructions_digest": hashlib.sha256(
                    instructions.encode()
                ).hexdigest(),
            }
            immutable["grant_digest"] = digest(immutable)
            delegation = {
                "id": delegation_id,
                "binding": immutable,
                "instructions": instructions,
                "boot_id": self.boot_id,
                "monotonic_deadline": min(
                    root["monotonic_deadline"], self.monotonic_clock() + seconds
                ),
                "state": "unknown",
                "termination_confirmed": False,
                "turns_allocated": 0,
            }
            task["allocated_seconds"] += seconds
            self._save(db, "task", task["id"], task)
            self._save(db, "delegation", delegation_id, delegation)
            self._save(
                db,
                "delegation_start",
                key,
                {"payload": payload, "delegation_id": delegation_id},
            )
            return self._delegation_permission(db, root, delegation, profile)

    def managed_delegated_permission(
        self,
        deployment_id,
        repository,
        runtime_principal,
        attempt_id,
        delegation_id,
        profiles,
    ):
        from .managed_runtime import scope

        with self.transaction() as db:
            root = self._delegation_root(
                db, attempt_id, scope(deployment_id, repository), runtime_principal
            )
            delegation = self._delegation(db, root, delegation_id)
            profile = profiles.get(root["runtime_binding"]["profile"])
            return self._delegation_permission(db, root, delegation, profile)

    def managed_delegated_turn(
        self,
        deployment_id,
        repository,
        runtime_principal,
        attempt_id,
        delegation_id,
        request_key,
        request_digest,
        profiles,
    ):
        from .authority import digest
        from .managed_runtime import bounded_text, scope

        bounded_text(request_key, "request_key")
        if not isinstance(request_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", request_digest
        ):
            raise ValueError("request_digest must be a SHA-256 content hash")
        with self.transaction() as db:
            root = self._delegation_root(
                db, attempt_id, scope(deployment_id, repository), runtime_principal
            )
            delegation = self._delegation(db, root, delegation_id)
            profile = profiles.get(root["runtime_binding"]["profile"])
            key = digest([delegation_id, request_key])
            prior = db.execute(
                "SELECT body FROM records WHERE kind='delegation_turn' AND id=?",
                (key,),
            ).fetchone()
            current = self._delegation_permission(db, root, delegation, profile)
            if prior:
                turn = json.loads(prior[0])
                if turn["request_digest"] != request_digest:
                    raise Conflict("delegation turn retry payload changed")
                return current | {"turn": turn}
            if not current["launch_allowed"]:
                raise Conflict("delegation turn permission expired or revoked")
            if delegation["turns_allocated"] >= delegation["binding"]["max_turns"]:
                raise Conflict("delegation turn allowance exhausted")
            delegation["turns_allocated"] += 1
            self._save(db, "delegation", delegation_id, delegation)
            turn = {
                "turn_id": key,
                "delegation_id": delegation_id,
                "root_attempt_id": attempt_id,
                "number": delegation["turns_allocated"],
                "request_digest": request_digest,
            }
            self._save(db, "delegation_turn", key, turn)
            return self._delegation_permission(db, root, delegation, profile) | {
                "turn": turn
            }

    def managed_delegations_read(
        self,
        deployment_id,
        repository,
        runtime_principal,
        attempt_id,
        profiles,
        delegation_id=None,
    ):
        from .managed_runtime import scope

        with self.transaction() as db:
            root = self._delegation_root(
                db, attempt_id, scope(deployment_id, repository), runtime_principal
            )
            profile = profiles.get(root["runtime_binding"]["profile"])
            delegations = (
                [self._delegation(db, root, delegation_id)]
                if delegation_id is not None
                else self._delegations(db, attempt_id)
            )
            return {
                "schema_version": 1,
                **scope(deployment_id, repository),
                "root_attempt_id": attempt_id,
                "admission_closed": root.get("delegation_admission_closed", False),
                "delegations": [
                    self._delegation_permission(db, root, delegation, profile)
                    for delegation in delegations
                ],
            }

    def managed_delegation_control(
        self,
        deployment_id,
        repository,
        runtime_principal,
        attempt_id,
        action,
        reason,
        delegation_id=None,
    ):
        from .managed_runtime import bounded_text, scope

        bounded_text(reason, "reason", 2000)
        if action not in {"close", "cancel", "revoke"}:
            raise ValueError("invalid delegation control action")
        with self.transaction() as db:
            root = self._delegation_root(
                db, attempt_id, scope(deployment_id, repository), runtime_principal
            )
            if action == "revoke":
                delegations = [self._delegation(db, root, delegation_id)]
            else:
                delegations = (
                    self._delegations(db, attempt_id) if action == "cancel" else []
                )
                if not root.get("delegation_admission_closed"):
                    root.update(
                        delegation_admission_closed=True,
                        delegation_admission_reason=reason,
                    )
                if action == "cancel" and not root["termination_confirmed"]:
                    root.update(cancel_requested=True, state="cancel_requested")
                self._save(db, "attempt", attempt_id, root)
            for delegation in delegations:
                if not delegation["termination_confirmed"] and not delegation.get(
                    "revoked"
                ):
                    delegation.update(
                        revoked=True,
                        revocation_reason=reason,
                        state="cancel_requested",
                    )
                    self._save(db, "delegation", delegation["id"], delegation)
            return {
                "schema_version": 1,
                **scope(deployment_id, repository),
                "attempt": root,
                "action": action,
            }

    def managed_delegation_capture(
        self,
        deployment_id,
        repository,
        runtime_principal,
        attempt_id,
        delegation_id,
        kind,
        content,
    ):
        from .authority import digest
        from .managed_runtime import scope

        if kind not in CAPTURES or not isinstance(content, str):
            raise ValueError("delegation patch, log or manifest UTF-8 capture required")
        raw = content.encode()
        if len(raw) > 4_000_000:
            raise ValueError("delegation capture exceeds 4 MB limit")
        if kind == "manifest" and not isinstance(json.loads(content), dict):
            raise ValueError("delegation manifest must be a JSON object")
        artifact = hashlib.sha256(raw).hexdigest()
        with self.transaction() as db:
            root = self._delegation_root(
                db, attempt_id, scope(deployment_id, repository), runtime_principal
            )
            delegation = self._delegation(db, root, delegation_id)
            key = digest([delegation_id, kind])
            prior = db.execute(
                "SELECT body FROM records WHERE kind='delegation_capture' AND id=?",
                (key,),
            ).fetchone()
            if prior:
                saved = json.loads(prior[0])
                if saved["artifact_id"] != artifact:
                    raise Conflict(
                        "final delegation capture already has different content"
                    )
                return saved
            if delegation["termination_confirmed"]:
                raise Conflict("terminated delegation capture cannot be changed")
            db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?)", (artifact, raw))
            return self._save(
                db,
                "delegation_capture",
                key,
                {
                    "schema_version": 1,
                    **scope(deployment_id, repository),
                    "root_attempt_id": attempt_id,
                    "delegation_id": delegation_id,
                    "kind": kind,
                    "artifact_id": artifact,
                    "runtime_principal": runtime_principal,
                },
            )

    def _verify_delegation_capture(self, db, delegation):
        from .authority import digest

        artifacts = delegation.get("captured_artifacts", {})
        if set(artifacts) != CAPTURES:
            raise Conflict("delegation terminal receipt requires every capture")
        for kind, artifact in artifacts.items():
            saved = self._get(
                db, "delegation_capture", digest([delegation["id"], kind])
            )
            row = db.execute(
                "SELECT content FROM artifacts WHERE id=?", (artifact,)
            ).fetchone()
            if (
                saved["artifact_id"] != artifact
                or row is None
                or hashlib.sha256(bytes(row[0])).hexdigest() != artifact
            ):
                raise Conflict("delegation durable capture verification failed")

    def managed_delegation_observe(
        self,
        deployment_id,
        repository,
        runtime_principal,
        attempt_id,
        delegation_id,
        state,
        termination_confirmed,
        launch_fenced,
        artifacts,
    ):
        from .managed_runtime import scope

        if state not in {
            "running",
            "unknown",
            "cancel_requested",
            "exited",
            "timed_out",
        }:
            raise ValueError("invalid delegation execution state")
        if type(termination_confirmed) is not bool or type(launch_fenced) is not bool:
            raise ValueError("delegation receipt flags must be boolean")
        if not isinstance(artifacts, dict) or any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
            for value in artifacts.values()
        ):
            raise ValueError("delegation artifact hash mapping required")
        if termination_confirmed:
            if (
                state not in {"exited", "timed_out"}
                or not launch_fenced
                or set(artifacts) != CAPTURES
            ):
                raise Conflict(
                    "delegation terminal receipt requires fence and every capture"
                )
        elif artifacts or launch_fenced:
            raise ValueError(
                "nonterminal delegation cannot assert capture or launch fence"
            )
        receipt = {
            "state": state,
            "termination_confirmed": termination_confirmed,
            "launch_fenced": launch_fenced,
            "artifacts": artifacts,
        }
        with self.transaction() as db:
            root = self._delegation_root(
                db, attempt_id, scope(deployment_id, repository), runtime_principal
            )
            delegation = self._delegation(db, root, delegation_id)
            if delegation["termination_confirmed"]:
                if delegation.get("runtime_receipt") != receipt:
                    raise Conflict("delegation terminal receipt changed")
                self._verify_delegation_capture(db, delegation)
                return delegation
            if termination_confirmed:
                delegation["captured_artifacts"] = artifacts
                self._verify_delegation_capture(db, delegation)
                delegation.update(
                    termination_confirmed=True,
                    launch_fenced=True,
                    runtime_receipt=receipt,
                )
            if delegation.get("revoked") and not termination_confirmed:
                state = "cancel_requested"
            delegation["state"] = state
            if state == "cancel_requested":
                delegation["revoked"] = True
            return self._save(db, "delegation", delegation_id, delegation)

    def managed_delegation_artifact(
        self,
        deployment_id,
        repository,
        runtime_principal,
        attempt_id,
        delegation_id,
        artifact_id,
    ):
        from .managed_runtime import scope

        with self.connect() as db:
            root = self._delegation_root(
                db, attempt_id, scope(deployment_id, repository), runtime_principal
            )
            self._delegation(db, root, delegation_id)
            if not any(
                c["delegation_id"] == delegation_id and c["artifact_id"] == artifact_id
                for c in self._all(db, "delegation_capture")
            ):
                raise Conflict("artifact is outside the authorized delegation lineage")
            row = db.execute(
                "SELECT content FROM artifacts WHERE id=?", (artifact_id,)
            ).fetchone()
            if row is None or hashlib.sha256(bytes(row[0])).hexdigest() != artifact_id:
                raise Conflict("delegation durable artifact verification failed")
            return bytes(row[0]).decode()

    def _delegation_terminal_lineage(self, db, root_id):
        lineage = []
        for delegation in self._delegations(db, root_id):
            if not delegation["termination_confirmed"] or not delegation.get(
                "launch_fenced"
            ):
                raise Conflict("root has an unresolved delegation execution")
            self._verify_delegation_capture(db, delegation)
            lineage.append(
                {
                    "delegation_id": delegation["id"],
                    "grant_digest": delegation["binding"]["grant_digest"],
                    "artifacts": delegation["captured_artifacts"],
                }
            )
        return sorted(lineage, key=lambda row: row["delegation_id"])
