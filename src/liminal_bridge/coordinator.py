"""Single-host durable authority. Mesh state and model output are never authority.

All public methods are for the trusted service process. Remote callers must use
coordinator_service, which binds identities and restricts roles before dispatch.
"""

import hashlib
import json
import math
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import contextmanager


class Conflict(ValueError):
    """A precondition failed; retry only after observing new state."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def positive(value):
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError("expected a positive finite limit")
    return value


def managed_task(task):
    """Fail closed even when the authority service is unavailable."""
    return (
        str(task.get("id", "")).startswith("task_v2_")
        or task.get("schema_version", 1) >= 2
    )


class Coordinator:
    def __init__(self, path, clock=time.time):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self.clock = clock
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
            return result

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
            return self._save(db, "task", task_id, task)

    def start_attempt(self, task_id, worker, capabilities, seconds, request_key):
        """Worker chooses task_id; intent does not authorize any shared write."""
        positive(seconds)
        with self.transaction() as db:
            key = digest([worker, request_key])
            payload = {
                "task": task_id,
                "seconds": seconds,
                "capabilities": capabilities,
            }
            prior = db.execute(
                "SELECT body FROM records WHERE kind='start' AND id=?", (key,)
            ).fetchone()
            if prior:
                saved = json.loads(prior[0])
                if saved["payload"] != payload:
                    raise Conflict("retry key payload changed")
                return self._get(db, "attempt", saved["attempt"])
            task = self._get(db, "task", task_id)
            if task["status"] in {"accepted", "awaiting_review"}:
                raise Conflict("already accepted or candidate awaiting review")
            if not set(task["required"]) <= set(capabilities):
                raise Conflict("capability mismatch")
            if any(
                self._get(db, "task", d)["status"] != "accepted"
                for d in task["dependencies"]
            ):
                raise Conflict("dependencies not accepted")
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
                "started": self.clock(),
                "deadline": self.clock() + seconds,
                "state": "reserved",
                "termination_confirmed": False,
                "cost": None,
            }
            task.pop("current_candidate", None)
            task["attempts"] += 1
            task["allocated_seconds"] += seconds
            task["status"] = "in_progress"
            self._save(db, "task", task_id, task)
            self._save(db, "start", key, {"payload": payload, "attempt": aid})
            return self._save(db, "attempt", aid, attempt)

    def observe(self, attempt_id, state, termination_confirmed=False):
        """Adapter/owner only; a cancellation request is not proof of death."""
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
            if a["termination_confirmed"]:
                return a
            a.update(state=state, termination_confirmed=termination_confirmed)
            return self._save(db, "attempt", attempt_id, a)

    def _permission(self, db, attempt_id, worker):
        a = self._get(db, "attempt", attempt_id)
        if (
            a["worker"] != worker
            or a["termination_confirmed"]
            or self.clock() >= a["deadline"]
        ):
            raise Conflict("attempt permission expired")
        task = self._get(db, "task", a["task"])
        if (
            task["revision"] != a["requirements_revision"]
            or task["status"] == "accepted"
        ):
            raise Conflict("attempt requirements expired")
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
            if old["fence"] != expected_fence or old["until"] > self.clock():
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
                or self.clock() >= lease["until"]
            ):
                raise Conflict("stale fencing token")
            result = {"resource": resource, "fence": fence, "value": value}
            self._save(db, "destination", resource, result)
            self._save(db, "effect", key, {"payload": payload, "result": result})
            return result

    def save_work(self, attempt_id, worker, content):
        """Even an expired author may salvage work; this is never acceptance."""
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
        if not base:
            raise ValueError("base revision is required")
        with self.transaction() as db:
            a = self._get(db, "attempt", attempt_id)
            if a["worker"] != worker:
                raise Conflict("wrong author")
            task = self._get(db, "task", a["task"])
            if task["revision"] != a["requirements_revision"]:
                raise Conflict("requirements changed; salvage work in a new attempt")
            self._get(db, "work", digest([attempt_id, artifact_id]))
            identity = {
                "base": base,
                "patch": artifact_id,
                "requirements": task["requirements"],
                "revision": task["revision"],
                "task": task["id"],
            }
            cid = digest(identity)
            existing = db.execute(
                "SELECT body FROM records WHERE kind='candidate' AND id=?", (cid,)
            ).fetchone()
            if existing:
                return json.loads(existing[0])
            if task["status"] != "accepted" and a["number"] == task["attempts"]:
                task.update(status="awaiting_review", current_candidate=cid)
                self._save(db, "task", task["id"], task)
            return self._save(
                db,
                "candidate",
                cid,
                {
                    "id": cid,
                    **identity,
                    "author": worker,
                    "attempt": attempt_id,
                },
            )

    def evidence(self, candidate_id, reviewer, check, passed, input_revision):
        """Reviewer identity is service-authenticated, never a worker-supplied label."""
        if type(passed) is not bool:
            raise ValueError("passed must be boolean")
        with self.transaction() as db:
            candidate = self._get(db, "candidate", candidate_id)
            task = self._get(db, "task", candidate["task"])
            if (
                reviewer not in task["reviewers"]
                or reviewer == candidate["author"]
                or check not in task["checks"]
            ):
                raise Conflict("reviewer/check not authorized or not independent")
            if (
                input_revision != candidate["revision"]
                or task["revision"] != input_revision
            ):
                raise Conflict("review input revision is stale")
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
            return result

    def accept(self, candidate_id):
        with self.transaction() as db:
            c = self._get(db, "candidate", candidate_id)
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
            packet = self._get(db, "admission", candidate_id)
            task = self._get(db, "task", packet["candidate"]["task"])
            if task.get("accepted") != candidate_id:
                raise Conflict("admission superseded")
            return packet

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
            old = [a for a in self._all(db, "advice") if a["task"] == task_id]
            if old and self.clock() - max(a["time"] for a in old) < minimum_interval:
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
                    "input_revision": task["revision"],
                },
            )

    def respond(self, advice_id, worker, response, cause):
        if response not in {"follow", "decline", "defer"} or not cause:
            raise ValueError("response and cause required")
        with self.transaction() as db:
            a = self._get(db, "advice", advice_id)
            task = self._get(db, "task", a["task"])
            if self.clock() >= a["expires"] or a["input_revision"] != task["revision"]:
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
    busy = {r["id"] for r in snapshot["resource"] if r["until"] > now}
    ready = [
        t
        for t in tasks.values()
        if t["status"] not in {"accepted", "awaiting_review"}
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
