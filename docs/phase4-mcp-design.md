# Phase 4: MCP Server Wrapper — Design

_Authored by Hal, 2026-03-22_

## Goal

Expose MiroFish as a set of MCP tools so Claude Code, OpenClaw, and any other MCP-capable client
can run simulations, build knowledge graphs, query results, and generate reports without touching
the Flask web UI or CLI directly.

---

## Decision: Custom Thin Wrapper (not Graphiti's built-in MCP server)

Graphiti ships an `mcp_server/` module, but it:
- Requires **FalkorDB** (Redis-backed), not Kuzu — incompatible with our embedded graph setup
- Is a **standalone process** (Docker Compose) separate from the MiroFish runtime
- Exposes raw graph primitives (`add_episode`, `search_facts`), not MiroFish-level tools

**Conclusion:** Build a thin `backend/mirofish_mcp.py` using the `mcp` Python SDK that wraps
`HeadlessRunner` and `knowledge_graph` directly. Zero extra infrastructure.

---

## Tool Surface

### Tier 1 — Simulation Lifecycle (required for Phase 4 launch)

| Tool | Inputs | Returns |
|------|--------|---------|
| `create_simulation` | `platform`, `max_rounds`, `num_agents`, `seed_topic`, `graph_id?`, `output_dir?`, `report?` | `config_json` (validated SimConfig) |
| `run_simulation` | `config_json` | `sim_result` (status, sim_dir, report_path, counts) |
| `get_simulation_status` | `sim_dir` | `runner_status`, `completed_rounds`, `total_rounds` |

### Tier 2 — Knowledge Graph (required for Phase 4 launch)

| Tool | Inputs | Returns |
|------|--------|---------|
| `build_knowledge_graph` | `document_paths[]`, `graph_name?` | `graph_id` |
| `search_graph` | `graph_id`, `query`, `limit?` | `facts[]` (edge summaries + source) |
| `get_graph_stats` | `graph_id` | `node_count`, `edge_count` |

### Tier 3 — Reports (stretch / Phase 4b)

| Tool | Inputs | Returns |
|------|--------|---------|
| `generate_report` | `sim_dir`, `graph_id`, `requirement?` | `report_path`, `report_text` |

---

## Implementation Plan

### File: `backend/mirofish_mcp.py`

```python
#!/usr/bin/env python3
"""MiroFish MCP Server (Phase 4) — wraps HeadlessRunner as MCP tools."""

from mcp.server.fastmcp import FastMCP
from backend.app.services.headless_runner import HeadlessRunner
from backend.app.models.sim_config import SimConfig
from backend.app.services import knowledge_graph as kg

mcp = FastMCP("MiroFish")

@mcp.tool()
def create_simulation(platform: str, max_rounds: int, num_agents: int,
                       seed_topic: str, graph_id: str = "", ...) -> dict:
    config = SimConfig(platform=platform, ...)
    return config.model_dump()

@mcp.tool()
def run_simulation(config_json: dict) -> dict:
    config = SimConfig(**config_json)
    result = HeadlessRunner().run(config)
    return result.model_dump()

@mcp.tool()
def search_graph(graph_id: str, query: str, limit: int = 10) -> list[dict]:
    results = kg.search_graph(graph_id, query, limit=limit)
    return results

# ... etc.

if __name__ == "__main__":
    mcp.run()  # stdio transport by default
```

### Dependencies to add

```
mcp[cli]>=1.0.0        # MCP Python SDK (fastmcp)
```

Add to `backend/requirements.txt`.

### Entry point (`pyproject.toml`)

```toml
[project.scripts]
mirofish     = "mirofish_cli:main"
mirofish-mcp = "mirofish_mcp:main"
```

### Transport

- **stdio** (default) — works with Claude Desktop, Claude Code, and OpenClaw out of the box
- **HTTP** (optional) — add `--http` flag using `mcp.run(transport="http", port=8080)` if remote access needed

---

## Claude Desktop / OpenClaw Config

```json
{
  "mcpServers": {
    "mirofish": {
      "command": "python",
      "args": ["backend/mirofish_mcp.py"],
      "cwd": "/path/to/MiroFish"
    }
  }
}
```

---

## Phase 4 Task Breakdown for CC

### Task 4a — `backend/mirofish_mcp.py`
- Implement Tier 1 + Tier 2 tools using FastMCP
- Flask app context is required for service imports — wrap tool handlers in `with app.app_context()`
- Import pattern: same as `mirofish_cli.py` (`_load_app()` helper)
- Use `asyncio.run()` for async knowledge_graph calls if needed (check if kg module is sync or async)
- File must be runnable standalone: `python backend/mirofish_mcp.py`

### Task 4b — `backend/requirements.txt`
- Add `mcp[cli]>=1.0.0`

### Task 4c — `pyproject.toml`
- Add `mirofish-mcp` entry point

### Task 4d — `docs/MCP_USAGE.md`
- Write usage guide: how to connect Claude Desktop, OpenClaw, and test with `mcp dev`
- Include tool reference table (inputs, outputs, example calls)

---

## Open Questions (resolve before or during 4a)

1. **Is `knowledge_graph.py` async or sync?** If `search_graph` uses `await`, Task 4a needs
   `asyncio.run()` wrappers or FastMCP's native async support.
2. **Flask context requirement:** Check if `SimulationRunner.get_run_state()` needs app context
   or reads from disk directly. If disk-only, no Flask context needed for status tools.
3. **Kuzu thread safety:** Kuzu embedded DB may not support concurrent writers. MCP tools that
   write to the graph should serialize (asyncio.Lock or process-level lock).

---

## Acceptance Criteria

- `python backend/mirofish_mcp.py` starts an MCP server with no errors
- `mcp dev backend/mirofish_mcp.py` shows all tools in the MCP inspector
- `run_simulation` tool executes a short (2-round, 5-agent) Twitter sim end-to-end
- `search_graph` returns results for a populated graph
- Claude Desktop (or OpenClaw) can invoke `create_simulation` + `run_simulation` in sequence
- No Flask web server required at runtime
