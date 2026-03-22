# Phase 3: Headless Mode — Design

_Authored by Hal, 2026-03-22_

## Goal

Decouple MiroFish from the Vue frontend so simulations can be driven entirely from:
1. **CLI** — `python -m mirofish run --config sim.json`
2. **Python API** — `import mirofish; mirofish.run(config)`
3. **MCP tools** (Phase 4, depends on this)

The Flask web server should remain functional but become optional infrastructure, not a requirement.

---

## Current Architecture

```
Vue Frontend
    ↓ HTTP
Flask API (backend/app/api/)
    ↓
Services: graph_builder, simulation_runner, report_agent
    ↓
Scripts: run_parallel_simulation.py (subprocess)
```

The scripts are already somewhat standalone (they accept `--config simulation_config.json`). The gap is:
- No single entry point that coordinates graph build + simulation + report without HTTP
- Config schema is undocumented outside the Vue forms
- Output is written to disk but not returned in a structured way suitable for piping/MCP

---

## Proposed Headless Architecture

### 1. `backend/mirofish_cli.py` — Top-Level Entry Point

```python
# python -m mirofish  OR  mirofish (with pip entry_points)
commands:
  run       --config FILE [--output DIR] [--twitter-only|--reddit-only] [--no-report]
  build     --input FILE [--graph-id NAME]
  report    --sim-dir DIR [--graph-id ID]
  status    --sim-dir DIR
```

### 2. `backend/app/services/headless_runner.py` — Orchestrator

Wraps the existing service layer into a single synchronous call chain:

```python
class HeadlessRunner:
    def run(config: SimConfig) -> SimResult:
        graph = GraphBuilderService().build(config.documents)
        sim   = SimulationRunner().run(graph.graph_id, config)
        report = ReportAgent().generate(sim.sim_dir, graph.graph_id)
        return SimResult(graph=graph, simulation=sim, report=report)
```

`SimResult` serializes to JSON + Markdown.

### 3. Config Schema (`SimConfig`)

Pydantic model covering everything currently scattered across Vue form state:

```python
class SimConfig(BaseModel):
    graph_id: str | None = None          # auto-generated if omitted
    documents: list[str] = []            # paths to PDF/MD/TXT files
    platform: Literal["twitter", "reddit", "both"] = "both"
    max_rounds: int = 10
    num_agents: int = 10
    seed_topic: str = ""
    output_dir: str = "data/sim_output"
    report: bool = True
```

JSON schema exported as `mirofish-config.schema.json` for IDE support / MCP validation.

### 4. Output Structure

```
data/sim_output/sim_{id}/
├── config.json          ← copy of input config
├── graph_summary.json   ← node/edge counts, entity types
├── twitter/
│   └── actions.jsonl
├── reddit/
│   └── actions.jsonl
├── simulation.log
├── run_state.json
└── report.md            ← final Markdown report (MCP-ready)
```

`report.md` is the primary artifact for Phase 4 MCP integration.

---

## Implementation Plan for CC

### Task 3a — Fix remaining Chinese comments in scripts (quick, parallel-able now)

Files still needing translation:
- `backend/scripts/run_parallel_simulation.py` — 615 Chinese instances
- `backend/scripts/run_twitter_simulation.py` — 245 instances
- `backend/scripts/run_reddit_simulation.py` — 218 instances
- `backend/scripts/action_logger.py` — 46 instances
- `backend/app/api/simulation.py` — 825 instances (docstrings/comments only)

### Task 3b — `SimConfig` Pydantic model

Create `backend/app/models/sim_config.py` with the schema above. Export JSON schema.

### Task 3c — `HeadlessRunner` service

Create `backend/app/services/headless_runner.py`. Wire up existing services in sequence. Handle async/sync bridge (same pattern as `knowledge_graph.py`).

### Task 3d — CLI entry point

Create `backend/mirofish_cli.py` with argparse. Hook `run`, `build`, `report`, `status` subcommands.

Add to `backend/setup.py` or `pyproject.toml`:
```toml
[project.scripts]
mirofish = "mirofish_cli:main"
```

### Task 3e — Structured Markdown report output

Ensure `report_agent.py` writes final output to `{sim_dir}/report.md` in addition to whatever it currently does.

---

## Dependencies

No new pip dependencies needed — everything uses the existing stack.

---

## What This Unlocks for Phase 4

Once headless mode is working:
- MCP `run_simulation` tool calls `HeadlessRunner.run(config)` and returns `report.md` content
- MCP `query_graph` tool calls `knowledge_graph.search_graph()`
- No HTTP server needed in the MCP use case

---

## Acceptance Criteria

- [ ] `python backend/mirofish_cli.py run --config test_config.json` completes without Flask running
- [ ] `report.md` written to output dir
- [ ] `SimConfig` validates cleanly with `pydantic v2`
- [ ] All script files have English-only comments/docstrings
