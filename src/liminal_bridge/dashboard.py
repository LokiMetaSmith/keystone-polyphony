import os
from aiohttp import web
from typing import Optional


class DashboardServer:
    def __init__(self, mesh, port: int = 8000, frontend_path: Optional[str] = None):
        self.mesh = mesh
        self.port = port
        if frontend_path is None:
            # Default to dashboard_ui/dist relative to this file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.frontend_path = os.path.join(current_dir, "dashboard_ui", "dist")
        else:
            self.frontend_path = frontend_path

        self.app = web.Application(middlewares=[self.auth_middleware])
        self._setup_routes()
        self.runner = None
        self.site = None

    def _setup_routes(self):
        # API Routes
        self.app.router.add_post("/api/login", self.handle_login)
        self.app.router.add_post("/api/logout", self.handle_logout)
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_get("/api/thoughts", self.handle_thoughts)
        self.app.router.add_post("/api/thoughts", self.handle_post_thought)
        self.app.router.add_get("/api/batons", self.handle_batons)
        self.app.router.add_post("/api/batons", self.handle_post_baton)
        self.app.router.add_get("/api/kv", self.handle_kv)
        self.app.router.add_get("/api/logs", self.handle_logs)
        self.app.router.add_get("/api/network", self.handle_network)

        # CORS (Simplified for local dev)
        # self.app.on_response_prepare.append(self.add_cors_headers)

        # Static Files
        if os.path.exists(self.frontend_path):
            # Serve index.html at root
            self.app.router.add_get("/", self.serve_index)
            # Serve other static files
            self.app.router.add_static("/", self.frontend_path)
        else:
            print(f"Warning: Frontend path {self.frontend_path} does not exist.")
            self.app.router.add_get("/", self.handle_root_fallback)

    async def add_cors_headers(self, request, response):
        response.headers["Access-Control-Allow-Origin"] = "*"

    async def serve_index(self, request):
        return web.FileResponse(os.path.join(self.frontend_path, "index.html"))

    @web.middleware
    async def auth_middleware(self, request, handler):
        # Allow static files and login endpoint
        if not request.path.startswith("/api/") or request.path in ["/api/login"]:
            return await handler(request)

        # Check cookie
        session = request.cookies.get("LIMINAL_SESSION")
        if not session or session != "authenticated":
            return web.json_response({"error": "Unauthorized"}, status=401)

        return await handler(request)

    async def handle_login(self, request):
        try:
            data = await request.json()
            password = data.get("password")

            expected_password = (
                os.getenv("DASHBOARD_PASSWORD") or os.getenv("SWARM_KEY") or "admin"
            )

            if password == expected_password:
                resp = web.json_response({"status": "ok"})
                resp.set_cookie(
                    "LIMINAL_SESSION", "authenticated", httponly=True, samesite="Strict"
                )
                return resp
            else:
                return web.json_response({"error": "Invalid password"}, status=401)
        except Exception:
            return web.json_response({"error": "Invalid request"}, status=400)

    async def handle_logout(self, request):
        resp = web.json_response({"status": "logged_out"})
        resp.del_cookie("LIMINAL_SESSION")
        return resp

    async def handle_root_fallback(self, request):
        return web.Response(
            text="Dashboard Frontend not found. API is running.",
            content_type="text/plain",
        )

    async def handle_status(self, request):
        status = {
            "node_id": self.mesh.node_id,
            "topic": self.mesh.topic,
            "peers": list(self.mesh.peers),
            "running": self.mesh.running,
        }
        return web.json_response(status)

    async def handle_thoughts(self, request):
        return web.json_response(self.mesh.thoughts)

    async def handle_post_thought(self, request):
        try:
            data = await request.json()
            thought = data.get("thought")
            if not thought:
                return web.json_response({"error": "Missing 'thought'"}, status=400)

            await self.mesh.share_thought(thought)
            return web.json_response({"status": "ok"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_batons(self, request):
        return web.json_response(self.mesh.batons)

    async def handle_post_baton(self, request):
        try:
            data = await request.json()
            resource = data.get("resource")
            action = data.get("action")

            if not resource or not action:
                return web.json_response(
                    {"error": "Missing 'resource' or 'action'"}, status=400
                )

            if action == "acquire":
                success = await self.mesh.acquire_baton(resource)
                return web.json_response({"success": success})
            elif action == "release":
                await self.mesh.release_baton(resource)
                return web.json_response({"status": "released"})
            else:
                return web.json_response({"error": "Invalid action"}, status=400)

        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_kv(self, request):
        return web.json_response(self.mesh.get_all_kv())

    async def handle_logs(self, request):
        return web.json_response(self.mesh.log_aggregator.get_logs())

    async def handle_network(self, request):
        return web.json_response(self.mesh.network_map)

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await self.site.start()
        print(f"Dashboard Server started at http://localhost:{self.port}")

    async def stop(self):
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
