"""Single-host durable authority. Mesh state and model output are never authority.

All public methods are for the trusted service process. Remote callers must use
coordinator_service, which binds identities and restricts roles before dispatch.
"""

import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager

from .managed_runtime import ManagedRuntimeAuthority
from .errors import Conflict


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def positive(value):
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError("expected a positive finite limit")
    return value


def immutable_revision(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value
    ):
        raise ValueError("base must be a full immutable Git object ID")
    return value


def managed_task(task):
    """Fail closed even when the authority service is unavailable."""
    return (
        str(task.get("id", "")).startswith("task_v2_")
        or task.get("schema_version", 1) >= 2
    )


class Coordinator(ManagedRuntimeAuthority):
    def __init__(self, path, clock=time.time, monotonic_clock=None, boot_id=None):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self.clock = clock
        self.monotonic_clock = monotonic_clock or (
            time.monotonic if clock is time.time else clock
        )
        if boot_id is None:
            try:
                boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            except OSError:
                # Without a stable boot identity, reopening cannot grant old
                # execution permission. Saved work/admissions remain durable.
                boot_id = secrets.token_hex(16)
        self.boot_id = boot_id
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(kind, id));
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY, content BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, time REAL NOT NULL,
                    kind TEXT NOT NULL, record_id TEXT NOT NULL);
                """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA busy_timeout=5000")
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    def _get(self, db, kind, key):
        row = db.execute(
            "SELECT body FROM records WHERE kind=? AND id=?", (kind, key)
        ).fetchone()
        if not row:
            raise Conflict(f"unknown {kind}: {key}")
        return json.loads(row[0])

    def _all(self, db, kind):
        return [
            json.loads(row[0])
            for row in db.execute(
                "SELECT body FROM records WHERE kind=? ORDER BY id", (kind,)
            )
        ]

    def _current_admission(self, db, candidate_id, trail=(), cache=None):
        cache = {} if cache is None else cache
        if candidate_id in cache:
            packet = cache[candidate_id]
            if packet["candidate"]["task"] in trail:
                raise Conflict("cyclic dependency admissions")
            return packet
        packet = self._get(db, "admission", candidate_id)
        candidate = packet["candidate"]
        try:
            immutable_revision(candidate["base"])
        except ValueError as exc:
            raise Conflict(
                "legacy candidate requires an immutable base and new review"
            ) from exc
        task = self._get(db, "task", candidate["task"])
        if task["id"] in trail:
            raise Conflict("cyclic dependency admissions")
        if (
            task["status"] != "accepted"
            or task.get("accepted") != candidate_id
            or task["revision"] != candidate["revision"]
        ):
            raise Conflict("admission superseded")
        self._check_dependencies(db, task, candidate, trail + (task["id"],), cache)
        cache[candidate_id] = packet
        return packet

    def _dependency_bindings(self, db, task, trail=(), cache=None):
        cache = {} if cache is None else cache
        bindings = {}
        for dependency_id in task["dependencies"]:
            dependency = self._get(db, "task", dependency_id)
            if dependency["status"] != "accepted" or not dependency.get("accepted"):
                raise Conflict("dependencies not accepted")
            packet = self._current_admission(db, dependency["accepted"], trail, cache)
            bindings[dependency_id] = digest(packet)
        return bindings

    def _check_dependencies(self, db, task, record, trail=(), cache=None):
        # Old dependency-free records remain usable. Old dependent records have
        # no trustworthy input provenance and require a fresh attempt/review.
        expected = record.get(
            "dependency_admissions", {} if not task["dependencies"] else None
        )
        if expected != self._dependency_bindings(db, task, trail, cache):
            raise Conflict("dependency admission changed or provenance missing")
        return expected

    def _invalidate_dependents(self, db, task_id):
        pending = [task_id]
        seen = {task_id}
        tasks = self._all(db, "task")
        while pending:
            invalid = pending.pop()
            for task in tasks:
                if invalid in task["dependencies"] and task["id"] not in seen:
                    seen.add(task["id"])
                    pending.append(task["id"])
                    task.pop("accepted", None)
                    task.update(status="needs_revision", dependency_problem=task_id)
                    self._save(db, "task", task["id"], task)

    def _save(self, db, kind, key, value):
        db.execute(
            "INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) "
            "DO UPDATE SET body=excluded.body",
            (kind, key, canonical(value)),
        )
        db.execute(
            "INSERT INTO events(time,kind,record_id) VALUES(?,?,?)",
            (self.clock(), kind, key),
        )
        return value

    def snapshot(self):
        with self.connect() as db:
            db.execute("BEGIN")
            result = {
                kind: self._all(db, kind)
                for kind in (
                    "task",
                    "attempt",
                    "resource",
                    "problem",
                    "advice",
                    "candidate",
                    "evidence",
                    "work",
                    "response",
                    "destination",
                )
            } | {
                "cursor": db.execute(
                    "SELECT COALESCE(MAX(seq),0) FROM events"
                ).fetchone()[0]
            }

            admissions = {}
            for task in result["task"]:
                task["remaining_attempts"] = task["max_attempts"] - task["attempts"]
                task["remaining_seconds"] = (
                    task["budget_seconds"] - task["allocated_seconds"]
                )
                task["unresolved_reason"] = None
                if task["status"] != "accepted":
                    if task["remaining_attempts"] <= 0:
                        task["unresolved_reason"] = (
                            "task attempt budget exhausted; preserved work awaits review or owner action"
                        )
                    elif task["remaining_seconds"] <= 0:
                        task["unresolved_reason"] = (
                            "task time budget exhausted; preserved work awaits review or owner action"
                        )
                if task["status"] == "accepted":
                    try:
                        self._current_admission(db, task["accepted"], cache=admissions)
                    except Conflict as exc:
                        task.update(
                            status="blocked",
                            admission_invalid=True,
                            unresolved_reason=str(exc),
                        )
            for attempt in result["attempt"]:
                try:
                    self._permission(db, attempt["id"], attempt["worker"])
                    attempt["permission_current"] = True
                except Conflict:
                    attempt["permission_current"] = False
            for resource in result["resource"]:
                resource["lease_current"] = self._lease_current(resource)
            return result

    def _lease_current(self, resource):
        return (
            resource.get("boot_id") == self.boot_id
            and resource.get("monotonic_until", 0) > self.monotonic_clock()
        )

    def cursor(self):
        with self.connect() as db:
            return db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]

    def enroll(
        self,
        title,
        requirements,
        checks,
        reviewers=(),
        required=(),
        dependencies=(),
        resource=None,
        max_attempts=3,
        budget_seconds=900,
        priority=1,
    ):
        positive(budget_seconds)
        if type(priority) is not int or not 0 <= priority <= 2:
            raise ValueError("priority must be 0, 1 or 2")
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if (
            not title
            or not requirements
            or not checks
            or len(set(checks)) != len(checks)
        ):
            raise ValueError(
                "title, requirements and distinct required checks are mandatory"
            )
        task_id = "task_v2_" + secrets.token_hex(12)
        with self.transaction() as db:
            for dep in dependencies:
                self._get(db, "task", dep)
            return self._save(
                db,
                "task",
                task_id,
                {
                    "id": task_id,
                    "schema_version": 2,
                    "title": title,
                    "requirements": requirements,
                    "checks": list(checks),
                    "reviewers": sorted(set(reviewers)),
                    "required": list(required),
                    "dependencies": list(dependencies),
                    "resource": resource,
                    "max_attempts": max_attempts,
                    "budget_seconds": budget_seconds,
                    "allocated_seconds": 0,
                    "attempts": 0,
                    "priority": priority,
                    "created": self.clock(),
                    "status": "todo",
                    "revision": 1,
                },
            )

    def revise(self, task_id, expected_revision, requirements, checks, reviewers):
        """Owner-only: new requirements invalidate admission, never reset budgets."""
        if not requirements or not checks or len(set(checks)) != len(checks):
            raise ValueError("requirements and distinct checks required")
        with self.transaction() as db:
            task = self._get(db, "task", task_id)
            if task["revision"] != expected_revision:
                raise Conflict("requirements revision changed")
            task.update(
                requirements=requirements,
                checks=list(checks),
                reviewers=sorted(set(reviewers)),
                revision=expected_revision + 1,
                status="todo",
            )
            task.pop("accepted", None)
            self._save(db, "task", task_id, task)
            self._invalidate_dependents(db, task_id)
            return task

    def start_attempt(self, task_id, worker, capabilities, seconds, request_key):
        """Worker chooses task_id; intent does not authorize any shared write."""
        with self.transaction() as db:
            return self._start_attempt(
                db, task_id, worker, capabilities, seconds, request_key
            )

    def _start_attempt(
        self, db, task_id, worker, capabilities, seconds, request_key, external=None
    ):
        """Common atomic budget reservation for local and managed execution."""
        positive(seconds)
        key = digest([worker, request_key])
        payload = {
            "task": task_id,
            "seconds": seconds,
            "capabilities": capabilities,
        }
        if external is not None:
            payload["external"] = external
        prior = db.execute(
            "SELECT body FROM records WHERE kind='start' AND id=?", (key,)
        ).fetchone()
        if prior:
            saved = json.loads(prior[0])
            if saved["payload"] != payload:
                raise Conflict("retry key payload changed")
            return self._get(db, "attempt", saved["attempt"])
        task = self._get(db, "task", task_id)
        if task.get("managed_scope") and external is None:
            raise Conflict("managed task requires its bound external runtime")
        if external is not None and any(
            a["worker"] == worker and not a["termination_confirmed"]
            for a in self._all(db, "attempt")
        ):
            raise Conflict("worker incarnation has an unresolved root execution")
        if task["status"] in {"accepted", "awaiting_review"}:
            raise Conflict("already accepted or candidate awaiting review")
        if not set(task["required"]) <= set(capabilities):
            raise Conflict("capability mismatch")
        dependencies = self._dependency_bindings(db, task, (task_id,))
        if any(
            a["task"] == task_id and not a["termination_confirmed"]
            for a in self._all(db, "attempt")
        ):
            raise Conflict("previous execution still reserved; termination unknown")
        if (
            task["attempts"] >= task["max_attempts"]
            or task["allocated_seconds"] + seconds > task["budget_seconds"]
        ):
            raise Conflict("task budget exhausted")
        aid = secrets.token_hex(16)
        attempt = {
            "id": aid,
            "task": task_id,
            "worker": worker,
            "number": task["attempts"] + 1,
            "requirements_revision": task["revision"],
            "dependency_admissions": dependencies,
            "started": self.clock(),
            "deadline": self.clock() + seconds,
            "monotonic_deadline": self.monotonic_clock() + seconds,
            "boot_id": self.boot_id,
            "state": "reserved",
            "termination_confirmed": False,
            "cost": None,
        }
        if external is not None:
            attempt.update(
                state="unknown",
                execution_mode="external",
                approved_requirements=task["requirements"],
                runtime_binding=external
                | {
                    "attempt_id": aid,
                    "launch_key": "polyphony:" + aid,
                    "spec_digest": digest(external),
                    "deadline": attempt["deadline"],
                    "requirements_revision": task["revision"],
                },
            )
        task.pop("current_candidate", None)
        task.pop("dependency_problem", None)
        task["attempts"] += 1
        task["allocated_seconds"] += seconds
        task["status"] = "in_progress"
        self._save(db, "task", task_id, task)
        self._save(db, "start", key, {"payload": payload, "attempt": aid})
        return self._save(db, "attempt", aid, attempt)

    def observe(self, attempt_id, state, termination_confirmed=False):
        """Adapter/owner only; a cancellation request is not proof of death."""
        if type(termination_confirmed) is not bool:
            raise ValueError("termination confirmation must be boolean")
        if state not in {
            "running",
            "unknown",
            "cancel_requested",
            "exited",
            "timed_out",
        }:
            raise ValueError("invalid execution state")
        if termination_confirmed and state not in {"exited", "timed_out"}:
            raise ValueError("termination needs adapter confirmation")
        with self.transaction() as db:
            a = self._get(db, "attempt", attempt_id)
            if a.get("execution_mode") == "external":
                raise Conflict(
                    "external receipt requires its bound runtime and capture"
                )
            if a["termination_confirmed"]:
                return a
            if a.get("cancel_requested") and not termination_confirmed:
                state = "cancel_requested"
            a.update(state=state, termination_confirmed=termination_confirmed)
            return self._save(db, "attempt", attempt_id, a)

    def request_cancel(self, attempt_id, worker):
        with self.transaction() as db:
            attempt = self._get(db, "attempt", attempt_id)
            if attempt["worker"] != worker:
                raise Conflict("wrong worker")
            if attempt["termination_confirmed"]:
                return attempt
            if attempt["state"] == "reserved":
                # Launch and cancellation contend in this same transaction.
                # No launch claim exists, so it is safe to confirm no process.
                attempt.update(state="exited", termination_confirmed=True)
            else:
                attempt["state"] = "cancel_requested"
            attempt["cancel_requested"] = True
            return self._save(db, "attempt", attempt_id, attempt)

    def authorize_launch(self, attempt_id, worker):
        with self.transaction() as db:
            attempt = self._permission(db, attempt_id, worker)
            if attempt.get("execution_mode") == "external":
                raise Conflict("attempt is bound to an external runtime")
            if attempt["state"] != "reserved":
                raise Conflict("launch outcome unknown; reconcile before retry")
            attempt["state"] = "unknown"
            attempt["execution_mode"] = "local"
            self._save(db, "attempt", attempt_id, attempt)
            task = self._get(db, "task", attempt["task"])
            return attempt, task["requirements"]

    def execution_permission(self, attempt_id, worker):
        with self.transaction() as db:
            return self._permission(db, attempt_id, worker)

    def remaining_seconds(self, attempt_id, worker):
        with self.transaction() as db:
            attempt = self._permission(db, attempt_id, worker)
            return attempt["monotonic_deadline"] - self.monotonic_clock()

    def _permission(self, db, attempt_id, worker):
        a = self._get(db, "attempt", attempt_id)
        if (
            a["worker"] != worker
            or a["termination_confirmed"]
            or a.get("cancel_requested")
            or a["state"] == "cancel_requested"
            or a.get("boot_id") != self.boot_id
            or self.monotonic_clock() >= a.get("monotonic_deadline", 0)
        ):
            raise Conflict("attempt permission expired")
        task = self._get(db, "task", a["task"])
        if (
            task["revision"] != a["requirements_revision"]
            or task["status"] == "accepted"
        ):
            raise Conflict("attempt requirements expired")
        self._check_dependencies(db, task, a, (task["id"],))
        return a

    def acquire(self, resource, attempt_id, worker, expected_fence, seconds=30):
        positive(seconds)
        with self.transaction() as db:
            # CAS revision is also this acquisition's retry identity. Never
            # acquire a second lease when the first response was lost.
            retry_id = digest([resource, attempt_id, worker, expected_fence])
            prior = db.execute(
                "SELECT body FROM records WHERE kind='acquisition' AND id=?",
                (retry_id,),
            ).fetchone()
            if prior:
                saved = json.loads(prior[0])
                if saved["seconds"] != seconds:
                    raise Conflict("retry acquisition payload changed")
                return saved["result"]
            a = self._permission(db, attempt_id, worker)
            task = self._get(db, "task", a["task"])
            if task["resource"] != resource:
                raise Conflict("resource not authorized for task")
            rows = db.execute(
                "SELECT body FROM records WHERE kind='resource' AND id=?", (resource,)
            ).fetchone()
            old = json.loads(rows[0]) if rows else {"fence": 0, "until": 0}
            if old["fence"] != expected_fence or self._lease_current(old):
                raise Conflict("resource busy or revision changed")
            result = self._save(
                db,
                "resource",
                resource,
                {
                    "id": resource,
                    "fence": old["fence"] + 1,
                    "attempt": attempt_id,
                    "until": min(self.clock() + seconds, a["deadline"]),
                    "monotonic_until": min(
                        self.monotonic_clock() + seconds, a["monotonic_deadline"]
                    ),
                    "boot_id": self.boot_id,
                },
            )

            self._save(
                db, "acquisition", retry_id, {"seconds": seconds, "result": result}
            )
            return result

    def write_resource(self, resource, attempt_id, worker, fence, retry_key, value):
        """The prototype destination is SQLite, checked in the effect transaction.

        No arbitrary external side effect callbacks: those require destination
        fencing/idempotency and reconciliation before retrying unknown outcomes.
        """
        payload = {
            "resource": resource,
            "attempt": attempt_id,
            "worker": worker,
            "fence": fence,
            "value": value,
        }
        with self.transaction() as db:
            key = digest([worker, retry_key])
            prior = db.execute(
                "SELECT body FROM records WHERE kind='effect' AND id=?", (key,)
            ).fetchone()
            if prior:
                saved = json.loads(prior[0])
                if saved["payload"] != payload:
                    raise Conflict("retry key payload changed")
                return saved["result"]
            self._permission(db, attempt_id, worker)
            lease = self._get(db, "resource", resource)
            if (
                lease["attempt"] != attempt_id
                or lease["fence"] != fence
                or not self._lease_current(lease)
            ):
                raise Conflict("stale fencing token")
            result = {"resource": resource, "fence": fence, "value": value}
            self._save(db, "destination", resource, result)
            self._save(db, "effect", key, {"payload": payload, "result": result})
            return result

    def save_work(self, attempt_id, worker, content):
        """Even an expired author may salvage work; this is never acceptance."""
        if not isinstance(content, str):
            raise ValueError("work product must be UTF-8 text")
        raw = content.encode()
        if len(raw) > 4_000_000:
            raise ValueError("work product exceeds 4 MB prototype limit")
        artifact = hashlib.sha256(raw).hexdigest()
        with self.transaction() as db:
            a = self._get(db, "attempt", attempt_id)
            if a["worker"] != worker:
                raise Conflict("wrong author")
            db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?)", (artifact, raw))
            self._save(
                db,
                "work",
                digest([attempt_id, artifact]),
                {
                    "attempt": attempt_id,
                    "artifact": artifact,
                    "saved": self.clock(),
                },
            )
        return artifact

    def artifact(self, artifact_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT content FROM artifacts WHERE id=?", (artifact_id,)
            ).fetchone()
            if not row:
                raise Conflict("missing durable artifact")
            return bytes(row[0]).decode()

    def candidate(self, attempt_id, worker, base, artifact_id):
        immutable_revision(base)
        with self.transaction() as db:
            a = self._get(db, "attempt", attempt_id)
            if a["worker"] != worker:
                raise Conflict("wrong author")
            binding = a.get("runtime_binding")
            if binding and (
                not a["termination_confirmed"]
                or not a.get("launch_fenced")
                or a.get("captured_artifacts", {}).get("patch") != artifact_id
                or binding["base"] != base
            ):
                raise Conflict("external candidate requires its verified final capture")
            task = self._get(db, "task", a["task"])
            if task["revision"] != a["requirements_revision"]:
                raise Conflict("requirements changed; salvage work in a new attempt")
            dependencies = self._check_dependencies(db, task, a, (task["id"],))
            self._get(db, "work", digest([attempt_id, artifact_id]))
            identity = {
                "base": base,
                "patch": artifact_id,
                "requirements": task["requirements"],
                "revision": task["revision"],
                "task": task["id"],
                "dependency_admissions": dependencies,
            }
            if binding:
                lineage = self._child_terminal_lineage(db, attempt_id)
                if lineage:
                    if a.get("child_lineage") != lineage:
                        raise Conflict("root terminal child lineage changed")
                    identity["child_lineage"] = lineage
            cid = digest(identity)
            existing = db.execute(
                "SELECT body FROM records WHERE kind='candidate' AND id=?", (cid,)
            ).fetchone()
            if task["status"] != "accepted" and a["number"] == task["attempts"]:
                task.update(status="awaiting_review", current_candidate=cid)
                self._save(db, "task", task["id"], task)
            if existing:
                return json.loads(existing[0])
            return self._save(
                db,
                "candidate",
                cid,
                {
                    "id": cid,
                    **identity,
                    "author": worker,
                    "attempt": attempt_id,
                    **(
                        {"author_principal": binding["runtime_principal"]}
                        if binding
                        else {}
                    ),
                },
            )

    def evidence(
        self, candidate_id, reviewer, check, passed, input_revision, request_key=None
    ):
        """Reviewer identity is service-authenticated, never a worker-supplied label."""
        if type(passed) is not bool:
            raise ValueError("passed must be boolean")
        with self.transaction() as db:
            payload = {
                "candidate": candidate_id,
                "reviewer": reviewer,
                "check": check,
                "passed": passed,
                "input_revision": input_revision,
            }
            retry_id = (
                digest([reviewer, request_key]) if request_key is not None else None
            )
            if retry_id is not None:
                prior = db.execute(
                    "SELECT body FROM records WHERE kind='review_retry' AND id=?",
                    (retry_id,),
                ).fetchone()
                if prior:
                    saved = json.loads(prior[0])
                    if saved["payload"] != payload:
                        raise Conflict("review retry payload changed")
                    return saved["result"]
            candidate = self._get(db, "candidate", candidate_id)
            task = self._get(db, "task", candidate["task"])
            if (
                reviewer not in task["reviewers"]
                or reviewer == candidate["author"]
                or reviewer == candidate.get("author_principal")
                or check not in task["checks"]
            ):
                raise Conflict("reviewer/check not authorized or not independent")
            if (
                input_revision != candidate["revision"]
                or task["revision"] != input_revision
            ):
                raise Conflict("review input revision is stale")
            self._check_dependencies(db, task, candidate, (task["id"],))
            previous = [
                e
                for e in self._all(db, "evidence")
                if e["candidate"] == candidate_id
                and e["reviewer"] == reviewer
                and e["check"] == check
            ]
            latest = max(
                previous, key=lambda e: e["observation_revision"], default=None
            )
            if latest and latest["passed"] == passed:
                if retry_id is not None:
                    self._save(
                        db,
                        "review_retry",
                        retry_id,
                        {"payload": payload, "result": latest},
                    )
                return latest
            if latest and retry_id is None:
                raise Conflict("review changes require an explicit request_key")
            result = self._save(
                db,
                "evidence",
                secrets.token_hex(16),
                {
                    "observation_revision": 1
                    + max(
                        (
                            e["observation_revision"]
                            for e in self._all(db, "evidence")
                            if e["candidate"] == candidate_id
                            and e["reviewer"] == reviewer
                            and e["check"] == check
                        ),
                        default=0,
                    ),
                    "candidate": candidate_id,
                    "reviewer": reviewer,
                    "check": check,
                    "passed": passed,
                    "source": reviewer,
                    "time": self.clock(),
                    "input_revision": input_revision,
                },
            )

            if task.get("current_candidate") == candidate_id:
                latest = {}
                for e in self._all(db, "evidence"):
                    if e["candidate"] == candidate_id:
                        key = (e["reviewer"], e["check"])
                        if (
                            key not in latest
                            or e["observation_revision"]
                            > latest[key]["observation_revision"]
                        ):
                            latest[key] = e
                task.pop("accepted", None)
                task["status"] = (
                    "needs_revision"
                    if any(not e["passed"] for e in latest.values())
                    else "awaiting_review"
                )
                self._save(db, "task", task["id"], task)
                self._invalidate_dependents(db, task["id"])
            if retry_id is not None:
                self._save(
                    db, "review_retry", retry_id, {"payload": payload, "result": result}
                )
            return result

    def accept(self, candidate_id):
        with self.transaction() as db:
            c = self._get(db, "candidate", candidate_id)
            try:
                immutable_revision(c["base"])
            except ValueError as exc:
                raise Conflict(
                    "candidate requires an immutable base and new review"
                ) from exc
            task = self._get(db, "task", c["task"])
            if (
                task["revision"] != c["revision"]
                or task["requirements"] != c["requirements"]
            ):
                raise Conflict("candidate requirements expired")
            if task.get("accepted") not in (None, candidate_id):
                raise Conflict("another candidate already accepted")
            if task.get("current_candidate") != candidate_id:
                raise Conflict("candidate superseded by newer work")
            self._check_dependencies(db, task, c, (task["id"],))
            evidence = [
                e
                for e in self._all(db, "evidence")
                if e["candidate"] == candidate_id
                and e["input_revision"] == task["revision"]
            ]
            latest = {}
            for observation in evidence:
                key = (observation["reviewer"], observation["check"])
                if (
                    key not in latest
                    or observation["observation_revision"]
                    > latest[key]["observation_revision"]
                ):
                    latest[key] = observation
            evidence = list(latest.values())
            for check in task["checks"]:
                applicable = [
                    e
                    for e in evidence
                    if e["check"] == check
                    and e["reviewer"] in task["reviewers"]
                    and e["reviewer"] != c["author"]
                    and e["reviewer"] != c.get("author_principal")
                ]
                if not applicable or not all(e["passed"] for e in applicable):
                    raise Conflict(f"missing or failed required check: {check}")
            self._get(db, "work", digest([c["attempt"], c["patch"]]))
            if task.get("accepted") == candidate_id:
                return self._get(db, "admission", candidate_id)
            task.update(status="accepted", accepted=candidate_id)
            self._save(db, "task", task["id"], task)
            # Revisions bind the packet; a later requirements change holds export.
            return self._save(
                db,
                "admission",
                candidate_id,
                {
                    "candidate": c,
                    "evidence": evidence,
                    "accepted_at": self.clock(),
                    "release_authorized": False,
                },
            )

    def admission(self, candidate_id):
        with self.connect() as db:
            db.execute("BEGIN")
            return self._current_admission(db, candidate_id)

    def problem(self, attempt_id, worker, cause):
        with self.transaction() as db:
            a = self._get(db, "attempt", attempt_id)
            if a["worker"] != worker:
                raise Conflict("wrong worker")
            return self._save(
                db,
                "problem",
                secrets.token_hex(12),
                {
                    "attempt": attempt_id,
                    "task": a["task"],
                    "source": worker,
                    "time": self.clock(),
                    "input_revision": a["requirements_revision"],
                    "cause": cause,
                },
            )

    def advise(self, task_id, source, message, ttl=300, minimum_interval=60):
        positive(ttl)
        positive(minimum_interval)
        with self.transaction() as db:
            task = self._get(db, "task", task_id)
            old = [
                a
                for a in self._all(db, "advice")
                if a["task"] == task_id and a.get("boot_id") == self.boot_id
            ]
            if (
                old
                and self.monotonic_clock() - max(a["monotonic_time"] for a in old)
                < minimum_interval
            ):
                raise Conflict("advice rate limited")
            aid = secrets.token_hex(12)
            return self._save(
                db,
                "advice",
                aid,
                {
                    "id": aid,
                    "task": task_id,
                    "source": source,
                    "message": message,
                    "time": self.clock(),
                    "expires": self.clock() + min(ttl, 3600),
                    "monotonic_time": self.monotonic_clock(),
                    "monotonic_expires": self.monotonic_clock() + min(ttl, 3600),
                    "boot_id": self.boot_id,
                    "input_revision": task["revision"],
                },
            )

    def respond(self, advice_id, worker, response, cause):
        if response not in {"follow", "decline", "defer"} or not cause:
            raise ValueError("response and cause required")
        with self.transaction() as db:
            a = self._get(db, "advice", advice_id)
            task = self._get(db, "task", a["task"])
            if (
                a.get("boot_id") != self.boot_id
                or self.monotonic_clock() >= a.get("monotonic_expires", 0)
                or a["input_revision"] != task["revision"]
            ):
                raise Conflict("advice expired")
            return self._save(
                db,
                "response",
                digest([advice_id, worker]),
                {
                    "advice": advice_id,
                    "worker": worker,
                    "response": response,
                    "cause": cause,
                    "time": self.clock(),
                    "input_revision": task["revision"],
                },
            )


def select_task(snapshot, capabilities, seconds, now=None):
    """Worker-side choice. Aging caps priority advantage at two minutes.

    Busy protected tasks are skipped before allocating an attempt/model call.
    Unknown termination reserves that task, without blocking independent tasks.
    """
    now = time.time() if now is None else now
    tasks = {t["id"]: t for t in snapshot["task"]}
    active = {a["task"] for a in snapshot["attempt"] if not a["termination_confirmed"]}
    busy = {
        r["id"]
        for r in snapshot["resource"]
        if r.get("lease_current", r["until"] > now)
    }
    ready = [
        t
        for t in tasks.values()
        if t["status"] not in {"accepted", "awaiting_review", "blocked"}
        and t["id"] not in active
        and t["resource"] not in busy
        and set(t["required"]) <= set(capabilities)
        and all(tasks[d]["status"] == "accepted" for d in t["dependencies"])
        and t["attempts"] < t["max_attempts"]
        and t["allocated_seconds"] + seconds <= t["budget_seconds"]
    ]
    return min(
        ready,
        key=lambda t: (t["created"] - 60 * max(0, min(2, t["priority"])), t["id"]),
        default=None,
    )
