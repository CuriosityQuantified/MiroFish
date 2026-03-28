#!/usr/bin/env python3
"""
MiroFish MCP Server (Phase 4)

Exposes MiroFish simulation and knowledge-graph capabilities as MCP tools
for Claude Code, OpenClaw, Claude Desktop, and any MCP-compatible client.

Run (stdio, default):
    python backend/mirofish_mcp.py

Run (HTTP, remote):
    python backend/mirofish_mcp.py --http --port 8080

Install as a command (after pip install -e .):
    mirofish-mcp

Claude Desktop / OpenClaw config:
    {
      "mcpServers": {
        "mirofish": {
          "command": "python",
          "args": ["backend/mirofish_mcp.py"],
          "cwd": "/path/to/MiroFish"
        }
      }
    }
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Ensure backend package is importable when run directly from repo root
_BACKEND_DIR = os.path.join(os.path.dirname(__file__))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)
for _p in [_BACKEND_DIR, _REPO_ROOT]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Load .env before importing anything else (Config reads env at import time)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(_REPO_ROOT, ".env"), override=False)

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app.models.sim_config import SimConfig, SimResult  # noqa: E402
from app.services import knowledge_graph as kg  # noqa: E402
from app.services.headless_runner import HeadlessRunner  # noqa: E402
from app.services.simulation_runner import SimulationRunner  # noqa: E402

mcp = FastMCP(
    "MiroFish",
    instructions=(
        "MiroFish is a multi-agent swarm intelligence simulation engine. "
        "Use these tools to: build temporal knowledge graphs from documents, "
        "run social simulations with AI agents, query simulation results, "
        "and generate prediction reports.\n\n"
        "Typical workflow:\n"
        "1. (Optional) build_knowledge_graph() with source documents\n"
        "2. create_simulation() to produce a validated config\n"
        "3. run_simulation() to execute — returns report text when done\n"
        "4. search_graph() to query specific facts from the graph"
    ),
)


# ---------------------------------------------------------------------------
# Tier 1 — Simulation Lifecycle
# ---------------------------------------------------------------------------


@mcp.tool()
def create_simulation(
    seed_topic: str,
    platform: str = "both",
    max_rounds: int = 10,
    num_agents: int = 10,
    graph_id: str = "",
    document_paths: list[str] | None = None,
    output_dir: str = "data/sim_output",
    generate_report: bool = True,
) -> dict:
    """
    Validate and return a MiroFish simulation configuration.

    Use this tool first to set up simulation parameters. Pass the returned
    config dict to run_simulation() to execute it.

    Args:
        seed_topic: Topic or scenario to simulate (e.g. "AI regulation debate",
                    "product launch reaction", "climate policy announcement").
        platform: Social platform to simulate — "twitter", "reddit", or "both".
        max_rounds: Number of simulation rounds. Each round ≈ 1 simulated hour.
                    Start with 5-10 for quick tests; up to 144 for a full week.
        num_agents: Number of AI agents to spawn. 10 is a good default;
                    50+ for richer emergence (higher cost).
        graph_id: ID of an existing knowledge graph to inject as agent memory.
                  Leave blank to run without graph memory, or provide one from
                  build_knowledge_graph().
        document_paths: Optional list of file paths (PDF, MD, TXT) to build a
                        knowledge graph from before running. Mutually exclusive
                        with graph_id — if both given, graph_id takes priority.
        output_dir: Directory where simulation outputs and report will be written.
        generate_report: Whether to generate a Markdown report after the simulation.

    Returns:
        Validated SimConfig as a dict. Pass directly to run_simulation().
    """
    config = SimConfig(
        seed_topic=seed_topic,
        platform=platform,
        max_rounds=max_rounds,
        num_agents=num_agents,
        graph_id=graph_id if graph_id else None,
        documents=document_paths or [],
        output_dir=output_dir,
        report=generate_report,
    )
    return config.model_dump()


@mcp.tool()
def run_simulation(config: dict) -> dict:
    """
    Run a MiroFish simulation end-to-end and return the result.

    Accepts the dict produced by create_simulation(). Executes the full pipeline:
    - (If documents provided) builds a knowledge graph
    - Generates agent personas from graph entities
    - Runs the OASIS social simulation (Twitter/Reddit/both)
    - (If generate_report=True) produces a Markdown prediction report

    This is a blocking call — it polls until the simulation completes or times out
    (default 30 minutes). For long simulations, consider using
    get_simulation_status() to poll manually after calling this in a background job.

    Args:
        config: SimConfig dict from create_simulation().

    Returns:
        SimResult dict with fields:
          - status: "completed" | "failed" | "partial"
          - sim_dir: path to simulation output directory
          - report_path: path to report.md (if generated)
          - report_text: full report Markdown text (if generated and file readable)
          - node_count / edge_count: knowledge graph statistics
          - agent_count / rounds_completed: simulation statistics
          - error: error message if status is "failed"
    """
    try:
        sim_config = SimConfig(**config)
    except Exception as exc:
        return SimResult(
            graph_id="",
            sim_dir="",
            status="failed",
            error=f"Invalid config: {exc}",
        ).model_dump()

    try:
        result = HeadlessRunner().run(sim_config)
    except RuntimeError as exc:
        if "camel-oasis" in str(exc):
            return {
                "status": "failed",
                "error": (
                    "Social simulation requires camel-oasis (not installed). "
                    "Install with: pip install -r backend/requirements-simulation.txt\n"
                    "Graph and report tools still work without it."
                ),
            }
        raise
    result_dict = result.model_dump()

    # Attach report text inline so the MCP client can read it without filesystem access
    if result.report_path and os.path.exists(result.report_path):
        try:
            with open(result.report_path, "r", encoding="utf-8") as fh:
                result_dict["report_text"] = fh.read()
        except Exception:
            result_dict["report_text"] = None
    else:
        result_dict["report_text"] = None

    return result_dict


@mcp.tool()
def get_simulation_status(sim_dir: str) -> dict:
    """
    Get the current status of a running or completed simulation.

    Args:
        sim_dir: Path to the simulation directory (from run_simulation result).

    Returns:
        Dict with:
          - runner_status: "idle"|"starting"|"running"|"completed"|"failed"|"stopped"
          - current_round / total_rounds: progress counters
          - twitter_actions_count / reddit_actions_count: action tallies
          - error: error message if failed
    """
    sim_id = os.path.basename(sim_dir.rstrip("/"))
    state = SimulationRunner.get_run_state(sim_id)

    if state is None:
        return {
            "runner_status": "not_found",
            "current_round": 0,
            "total_rounds": 0,
            "twitter_actions_count": 0,
            "reddit_actions_count": 0,
            "error": f"No run state found for sim_dir={sim_dir}",
        }

    return {
        "runner_status": state.runner_status.value,
        "current_round": state.current_round,
        "total_rounds": state.total_rounds,
        "twitter_actions_count": state.twitter_actions_count,
        "reddit_actions_count": state.reddit_actions_count,
        "started_at": state.started_at,
        "completed_at": state.completed_at,
        "error": state.error,
    }


# ---------------------------------------------------------------------------
# Tier 2 — Knowledge Graph
# ---------------------------------------------------------------------------


@mcp.tool()
def build_knowledge_graph(
    document_paths: list[str],
    graph_name: str = "MiroFish Graph",
) -> dict:
    """
    Build a temporal knowledge graph from documents.

    Extracts entities and relationships from the provided files using
    Graphiti + Kuzu (embedded, no external services required). The resulting
    graph_id can be passed to create_simulation() to inject this knowledge
    as agent memory.

    Supports PDF, Markdown (.md), and plain text (.txt) files.

    Args:
        document_paths: List of file paths to ingest.
        graph_name: Human-readable name for the graph.

    Returns:
        Dict with:
          - graph_id: Use this in create_simulation(graph_id=...)
          - node_count / edge_count: graph statistics
          - error: set if something went wrong (graph_id may still be valid)
    """
    if not document_paths:
        return {"graph_id": "", "node_count": 0, "edge_count": 0, "error": "No document paths provided"}

    # Verify files exist
    missing = [p for p in document_paths if not os.path.exists(p)]
    if missing:
        return {
            "graph_id": "",
            "node_count": 0,
            "edge_count": 0,
            "error": f"Files not found: {missing}",
        }

    # Read and concatenate documents
    parts: list[str] = []
    for path in document_paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                parts.append(fh.read())
        except Exception as exc:
            return {
                "graph_id": "",
                "node_count": 0,
                "edge_count": 0,
                "error": f"Could not read {path}: {exc}",
            }
    text = "\n\n".join(parts)

    # Build via GraphBuilderService (async task + poll)
    from app.services.graph_builder import GraphBuilderService

    svc = GraphBuilderService()
    task_id = svc.build_graph_async(text=text, ontology={}, graph_name=graph_name)

    # Poll (up to 10 minutes for large documents)
    import time
    from app.models.task import TaskStatus

    deadline = time.time() + 600
    graph_id = None
    while time.time() < deadline:
        task = svc.task_manager.get_task(task_id)
        if task is None:
            return {"graph_id": "", "node_count": 0, "edge_count": 0, "error": "Task disappeared"}
        if task.status == TaskStatus.COMPLETED:
            graph_id = (task.result or {}).get("graph_id")
            break
        if task.status == TaskStatus.FAILED:
            return {"graph_id": "", "node_count": 0, "edge_count": 0, "error": task.error or "Graph build failed"}
        time.sleep(5)

    if not graph_id:
        return {"graph_id": "", "node_count": 0, "edge_count": 0, "error": "Graph build timed out"}

    # Return stats
    try:
        nodes = kg.get_all_nodes(graph_id)
        edges = kg.get_all_edges(graph_id)
        return {"graph_id": graph_id, "node_count": len(nodes), "edge_count": len(edges), "error": None}
    except Exception as exc:
        return {"graph_id": graph_id, "node_count": 0, "edge_count": 0, "error": str(exc)}


@mcp.tool()
def search_graph(
    graph_id: str,
    query: str,
    limit: int = 10,
) -> list[dict]:
    """
    Search a knowledge graph for facts matching a query.

    Uses Graphiti's hybrid retrieval (semantic + keyword + graph traversal).
    Returns the most relevant edges (facts / relationships) from the graph.

    Args:
        graph_id: Graph to search (from build_knowledge_graph or run_simulation).
        query: Natural-language question or keyword query.
        limit: Maximum number of results to return (default 10).

    Returns:
        List of fact dicts, each with:
          - fact: The extracted relationship / claim as a sentence
          - name: Relationship type label
          - source_node_uuid / target_node_uuid: Entity UUIDs
          - valid_at / invalid_at: Temporal validity window (ISO timestamps or null)
    """
    if not graph_id:
        return [{"error": "graph_id is required"}]

    try:
        results = kg.search_graph(graph_id, query, limit=limit)
        return results if results else []
    except Exception as exc:
        return [{"error": str(exc)}]


@mcp.tool()
def get_graph_stats(graph_id: str) -> dict:
    """
    Get statistics for a knowledge graph.

    Args:
        graph_id: Graph ID from build_knowledge_graph or run_simulation.

    Returns:
        Dict with node_count, edge_count, and entity_types breakdown.
    """
    if not graph_id:
        return {"graph_id": "", "node_count": 0, "edge_count": 0, "entity_types": {}, "error": "graph_id required"}

    try:
        nodes = kg.get_all_nodes(graph_id)
        edges = kg.get_all_edges(graph_id)

        # Tally entity types from node labels
        entity_types: dict[str, int] = {}
        for node in nodes:
            for label in node.get("labels", []):
                if label not in ("Entity", "Node"):
                    entity_types[label] = entity_types.get(label, 0) + 1

        return {
            "graph_id": graph_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "entity_types": entity_types,
            "error": None,
        }
    except Exception as exc:
        return {"graph_id": graph_id, "node_count": 0, "edge_count": 0, "entity_types": {}, "error": str(exc)}


# ---------------------------------------------------------------------------
# Tier 3 — Reports (stretch)
# ---------------------------------------------------------------------------


@mcp.tool()
def read_report(report_path: str) -> str:
    """
    Read a simulation report from disk and return its Markdown text.

    Args:
        report_path: Path to report.md (from run_simulation result).

    Returns:
        Full Markdown report text, or an error message.
    """
    if not report_path:
        return "Error: report_path is required"
    if not os.path.exists(report_path):
        return f"Error: Report not found at {report_path}"
    try:
        with open(report_path, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception as exc:
        return f"Error reading report: {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


VERSION = "1.0.0"


def _run_health_check() -> int:
    """Run health checks and print results. Returns 0 if all pass, 1 if any fail."""
    import importlib
    import socket
    import urllib.request

    results: list[tuple[bool, str]] = []

    # 1. Check .env exists
    env_path = os.path.join(_REPO_ROOT, ".env")
    if os.path.exists(env_path):
        results.append((True, ".env found"))
    else:
        results.append((False, f".env not found (expected at {env_path})"))

    # 2. Check ANTHROPIC_API_KEY
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    proxy_localhost = "localhost" in base_url or "127.0.0.1" in base_url
    if not api_key:
        results.append((False, "ANTHROPIC_API_KEY is not set"))
    elif api_key == "placeholder" and not proxy_localhost:
        results.append((False, 'ANTHROPIC_API_KEY is "placeholder" (set a real key or configure a proxy)'))
    else:
        results.append((True, "ANTHROPIC_API_KEY configured"))

    # 3. Check Python dependencies
    missing_deps: list[str] = []
    for dep in ("graphiti_core", "mcp", "anthropic"):
        try:
            importlib.import_module(dep)
        except ImportError:
            missing_deps.append(dep)
    if missing_deps:
        results.append((False, f"Missing dependencies: {', '.join(missing_deps)}"))
    else:
        results.append((True, "Dependencies installed"))

    # 4. Check Kuzu data directory is writable
    data_dir = os.path.join(_REPO_ROOT, "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
        test_file = os.path.join(data_dir, ".write_test")
        with open(test_file, "w") as fh:
            fh.write("ok")
        os.remove(test_file)
        results.append((True, "Data directory writable"))
    except Exception as exc:
        results.append((False, f"Data directory not writable ({data_dir}): {exc}"))

    # 5. Check LLM endpoint is reachable
    model_name = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    endpoint_ok = False
    endpoint_msg = ""
    try:
        import anthropic

        # Strip trailing /v1 — the Anthropic SDK adds it automatically
        sdk_base_url = base_url
        if sdk_base_url and sdk_base_url.rstrip("/").endswith("/v1"):
            sdk_base_url = sdk_base_url.rstrip("/")[:-3].rstrip("/")

        client = anthropic.Anthropic(
            api_key=api_key or "placeholder",
            **({"base_url": sdk_base_url} if sdk_base_url else {}),
        )
        # Minimal call — one token, fast
        resp = client.messages.create(
            model=model_name,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        endpoint_ok = True
        endpoint_msg = f"LLM endpoint reachable ({model_name})"
    except Exception as exc:
        endpoint_msg = f"LLM endpoint unreachable: {exc}"

    results.append((endpoint_ok, endpoint_msg))

    # Print summary
    print("MiroFish Health Check")
    for ok, msg in results:
        mark = "\u2713" if ok else "\u2717"
        print(f"  {mark} {msg}")

    all_passed = all(ok for ok, _ in results)
    print()
    if all_passed:
        print("All checks passed. Server is ready.")
    else:
        failed = sum(1 for ok, _ in results if not ok)
        print(f"{failed} check(s) failed. Review the issues above before starting the server.")

    return 0 if all_passed else 1


def main():
    parser = argparse.ArgumentParser(
        prog="mirofish-mcp",
        description="MiroFish MCP Server",
        add_help=False,  # We supply our own --help for a cleaner message
    )
    parser.add_argument(
        "--help", "-h",
        action="store_true",
        help="Show this help message and exit",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Run environment and dependency checks, then exit",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run with HTTP transport instead of stdio",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for HTTP transport (default: 8080)",
    )
    args = parser.parse_args()

    if args.help:
        print(
            f"MiroFish MCP Server v{VERSION}\n"
            "\n"
            "Usage:\n"
            "  mirofish-mcp [OPTIONS]\n"
            "\n"
            "Options:\n"
            "  --help            Show this message and exit\n"
            "  --version         Print version and exit\n"
            "  --health-check    Run environment checks and exit (0=pass, 1=fail)\n"
            "  --http            Use HTTP transport instead of stdio\n"
            "  --port PORT       HTTP port (default: 8080)\n"
            "\n"
            "Examples:\n"
            "  mirofish-mcp                        # stdio mode (Claude Desktop / OpenClaw)\n"
            "  mirofish-mcp --http --port 8080     # HTTP mode\n"
            "  mirofish-mcp --health-check         # verify environment before starting\n"
        )
        sys.exit(0)

    if args.version:
        print(f"MiroFish MCP Server v{VERSION}")
        sys.exit(0)

    if args.health_check:
        sys.exit(_run_health_check())

    if args.http:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=args.port)
    else:
        mcp.run()  # stdio — default, works with Claude Desktop / OpenClaw


if __name__ == "__main__":
    main()
