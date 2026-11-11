"""Trusted-runtime endpoints for bounded delegated grants and capability attenuation."""

from aiohttp import web

from src.core.collaboration.delegated_grants import DelegatedGrantNotAllocated


def install_delegation_routes(app, store, authorize, body, query):
    def context(request, fields, roles):
        principal, binding, policy = authorize(request, fields, roles)
        return (
            {
                **binding,
                "runtime_principal": (
                    None if principal["role"] == "owner" else principal["identity"]
                ),
                "attempt_id": fields["attempt_id"],
            },
            policy["profiles"],
        )

    async def grant(request):
        extra = {
            "attempt_id",
            "request_key",
            "instructions",
            "seconds",
            "max_turns",
            "capabilities",
        }
        fields = await body(request, extra)
        common, profiles = context(request, fields, {"runtime"})
        try:
            result = store.managed_delegated_grant(
                **common,
                **{key: fields[key] for key in extra - {"attempt_id"}},
                profiles=profiles,
            )
        except DelegatedGrantNotAllocated as exc:
            return web.json_response(
                {"error": str(exc), "code": "delegated_grant_not_allocated"},
                status=409,
            )
        return web.json_response(result)

    async def permission(request):
        fields = await body(request, {"attempt_id", "delegation_id"})
        common, profiles = context(request, fields, {"runtime"})
        return web.json_response(
            store.managed_delegated_permission(
                **common,
                delegation_id=fields["delegation_id"],
                profiles=profiles,
            )
        )

    async def turn(request):
        extra = {"attempt_id", "delegation_id", "request_key", "request_digest"}
        fields = await body(request, extra)
        common, profiles = context(request, fields, {"runtime"})
        return web.json_response(
            store.managed_delegated_turn(
                **common,
                **{key: fields[key] for key in extra - {"attempt_id"}},
                profiles=profiles,
            )
        )

    async def read(request):
        fields = query(request, {"attempt_id"})
        common, profiles = context(request, fields, {"runtime", "owner"})
        return web.json_response(
            store.managed_delegations_read(
                **common,
                profiles=profiles,
                delegation_id=request.match_info.get("delegation_id"),
            )
        )

    async def artifact(request):
        fields = query(request, {"attempt_id"})
        common, _ = context(request, fields, {"runtime", "owner"})
        return web.Response(
            text=store.managed_delegation_artifact(
                **common,
                delegation_id=request.match_info["delegation_id"],
                artifact_id=request.match_info["artifact_id"],
            )
        )

    async def capture(request):
        extra = {"attempt_id", "delegation_id", "kind", "content"}
        fields = await body(request, extra)
        common, _ = context(request, fields, {"runtime"})
        return web.json_response(
            store.managed_delegation_capture(
                **common, **{key: fields[key] for key in extra - {"attempt_id"}}
            )
        )

    async def observe(request):
        extra = {
            "attempt_id",
            "delegation_id",
            "state",
            "termination_confirmed",
            "launch_fenced",
            "artifacts",
        }
        fields = await body(request, extra)
        common, _ = context(request, fields, {"runtime"})
        delegation = store.managed_delegation_observe(
            **common, **{key: fields[key] for key in extra - {"attempt_id"}}
        )
        return web.json_response(
            {
                "schema_version": 1,
                "deployment_id": common["deployment_id"],
                "repository": common["repository"],
                "root_attempt_id": common["attempt_id"],
                "delegation": delegation,
            }
        )

    async def control(request):
        action = request.match_info.get("action", "cancel")
        extra = {"attempt_id", "reason"} | (
            {"delegation_id"} if action == "revoke" else set()
        )
        fields = await body(request, extra)
        common, _ = context(request, fields, {"runtime", "owner"})
        return web.json_response(
            store.managed_delegation_control(
                **common,
                action=action,
                reason=fields["reason"],
                delegation_id=fields.get("delegation_id"),
            )
        )

    for name, handler in (
        ("grant", grant),
        ("permission", permission),
        ("turn", turn),
        ("capture", capture),
        ("observe", observe),
    ):
        app.router.add_post("/managed/delegations/" + name, handler)
    app.router.add_post("/managed/delegations/{action:close|revoke}", control)
    app.router.add_post("/managed/cancel", control)
    app.router.add_get("/managed/delegations", read)
    app.router.add_get("/managed/delegations/{delegation_id}", read)
    app.router.add_get(
        "/managed/delegations/{delegation_id}/artifacts/{artifact_id}", artifact
    )
