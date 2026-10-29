# Bug: Server fails to start with mcp 2.x and direct-script launch has broken imports

## Problem
1. `requirements.txt` specifies `mcp>=1.0.0`, which now resolves to mcp 2.x. In 2.x `FastMCP` was renamed to `MCPServer`, so `from mcp.server.fastmcp import FastMCP` in `src/liminal_bridge/server.py` raises `ModuleNotFoundError`.
2. `python src/liminal_bridge/server.py --mode=daemon` fails with `ImportError: attempted relative import with no known parent package` (the fallback absolute imports in `server.py` reach `mesh.py`/`storage.py`, which use relative imports). `PYTHONPATH=src python -m liminal_bridge.server` works. This is the launch path documented in `docs/getting-started.md`, so the docs are currently wrong.

## Proposed work
- Short term: pin `mcp>=1.0.0,<2` in `requirements.txt`.
- Long term: migrate to the mcp v2 API (`from mcp.server.mcpserver import MCPServer`); see https://py.sdk.modelcontextprotocol.io/v2/migration/ and lift the pin.
- Make `mesh.py`/`storage.py` imports work in both package and script modes, or update docs to use `python -m liminal_bridge.server`.

## Acceptance criteria
- Fresh `scripts/setup-ensemble.sh` followed by the documented daemon command starts cleanly.
- `--mode=mcp` serves tools to an MCP client (verified with a stdio client).
