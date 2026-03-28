# MiroFish MCP Server — Usage Guide

MiroFish exposes its simulation and knowledge-graph capabilities as MCP tools,
usable from Claude Desktop, Claude Code, OpenClaw, and any MCP-compatible client.

---

## Setup

### 1. Install dependencies

```bash
cd MiroFish/backend
pip install -r requirements.txt              # Core (graph, search, reports)
pip install -r requirements-simulation.txt   # + Social simulation (optional)
# or, if using uv:
uv pip install -r requirements.txt
uv pip install -r requirements-simulation.txt  # optional
```

### 2. Configure `.env`

Copy `.env.example` to `.env` and fill in your API key:

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here

# Optional: OpenAI-compatible proxy (e.g. cliproxy)
# ANTHROPIC_BASE_URL=http://localhost:8317/v1

# Model overrides (defaults shown)
LLM_SWARM_MODEL=claude-haiku-4-5-20251001
LLM_ORCHESTRATION_MODEL=claude-sonnet-4-6
```

### 3. Embeddings (`OPENAI_API_KEY`) — optional but recommended

MiroFish works without an OpenAI API key, but adding one improves knowledge graph search quality:

| Mode | Key required | Graph search behaviour |
|------|-------------|------------------------|
| Keyword / FTS only | None | Works; relies on full-text search — good for exact terms |
| Hybrid (semantic + keyword) | `OPENAI_API_KEY` | Recommended; finds conceptually related nodes even without exact keyword matches |

Add to `.env`:

```env
OPENAI_API_KEY=your_openai_key_here

# Optional: point to any OpenAI-compatible embedding endpoint (e.g. local model via Ollama)
# OPENAI_BASE_URL=http://localhost:11434/v1
```

If `OPENAI_API_KEY` is not set, the graph still ingests and searches correctly — results may just be fewer or less semantically rich.

---

## Running the MCP Server

### stdio (Claude Desktop / OpenClaw — default)

```bash
python backend/mirofish_mcp.py
```

### HTTP (remote access)

```bash
python backend/mirofish_mcp.py --http --port 8080
# MCP endpoint: http://localhost:8080/mcp/
```

---

## Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

## OpenClaw Configuration

Add to your OpenClaw config:

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

## Available Tools

### Tier 1 — Simulation Lifecycle

| Tool | Description | Requires OASIS? |
|------|-------------|-----------------|
| `create_simulation` | Validate and return a SimConfig dict | No |
| `run_simulation` | Execute a full simulation end-to-end, returns SimResult + report text | **Yes** |
| `get_simulation_status` | Poll a running simulation for progress | **Yes** |

### Tier 2 — Knowledge Graph

| Tool | Description | Requires OASIS? |
|------|-------------|-----------------|
| `build_knowledge_graph` | Ingest documents into a temporal graph, returns graph_id | No |
| `search_graph` | Hybrid search over graph facts (semantic + keyword) | No |
| `get_graph_stats` | Node/edge counts and entity type breakdown | No |

### Tier 3 — Reports

| Tool | Description | Requires OASIS? |
|------|-------------|-----------------|
| `read_report` | Read a report.md from disk and return Markdown text | No |

> **Note:** Tools marked "Requires OASIS" need `pip install -r requirements-simulation.txt`. All other tools work with the core install only.

---

## Example Workflows

### Basic simulation (no documents)

```
create_simulation(
    seed_topic="AI regulation debate in the EU",
    platform="twitter",
    max_rounds=10,
    num_agents=20
)
→ returns config dict

run_simulation(config=<config dict>)
→ returns SimResult with report_text inline
```

### Simulation with knowledge graph

```
build_knowledge_graph(
    document_paths=["/path/to/policy_brief.pdf", "/path/to/news_article.md"],
    graph_name="EU AI Act"
)
→ returns { graph_id: "mirofish_abc123...", node_count: 47, edge_count: 132 }

create_simulation(
    seed_topic="Public reaction to EU AI Act vote",
    platform="both",
    max_rounds=20,
    num_agents=50,
    graph_id="mirofish_abc123..."
)
→ config dict

run_simulation(config=<config dict>)
→ SimResult with report_text

search_graph(
    graph_id="mirofish_abc123...",
    query="Which agents were most influential in shaping opinion?"
)
→ list of relevant facts from the simulation graph
```

---

## Infrastructure

MiroFish MCP requires **zero external services**:

- **Knowledge graph:** Kuzu (embedded, stored at `data/kuzu_graph/`) — no Neo4j, no Docker
- **LLM:** Anthropic API (or compatible proxy)
- **Simulation:** CAMEL-AI / OASIS (runs as local subprocesses)
- **MCP transport:** stdio (default) or HTTP

---

## Known Issues (graphiti-core 0.28.2)

The following bugs exist in the upstream `graphiti-core==0.28.2` release. All five are patched locally in `backend/app/services/knowledge_graph.py`. No action is needed unless you upgrade graphiti-core, at which point you should re-test each item.

| # | Issue | Symptom | Status |
|---|-------|---------|--------|
| 1 | `KuzuDriver` missing `_database` attribute | `AttributeError` on episode ingestion | Patched in `knowledge_graph.py` |
| 2 | Anthropic SDK base URL double `/v1` | `404 page not found` on LLM calls | Patched — strips trailing `/v1` for native SDK |
| 3 | Kuzu FTS indices never created | `Binder exception: no index node_name_and_summary` | Patched — manually creates 4 FTS indices |
| 4 | `NoOpEmbedder` missing `create_batch()` | `NotImplementedError` during edge resolution | Patched — method added |
| 5 | `NoOpEmbedder` wrong return type | `Unsupported casting LIST...FLOAT[1]` | Patched — returns flat `list[float]` |

All 5 issues are patched in `backend/app/services/knowledge_graph.py`. No action needed unless you upgrade graphiti-core.

---

## Troubleshooting

### General

**`ANTHROPIC_API_KEY is not configured`** — check your `.env` file is in the repo root and `ANTHROPIC_API_KEY` is set.

**`No run state found for sim_dir`** — the sim_dir path must match exactly what `run_simulation` returned. Use `get_simulation_status(sim_dir)` with the full path.

**Simulation times out** — reduce `max_rounds` or `num_agents`. Each round makes LLM calls for every agent. Start with `max_rounds=5, num_agents=10`.

**Graph search returns empty results** — if `OPENAI_API_KEY` is not set, the no-op embedder is used and semantic search quality is reduced. Keyword / FTS search still works. Set `OPENAI_API_KEY` (or `OPENAI_BASE_URL` for a local model) to enable full hybrid search.

### MCP-specific

**Server won't start**
- Confirm `.env` exists in the repo root and `ANTHROPIC_API_KEY` is set.
- Run a quick health check: `python backend/mirofish_mcp.py --health-check`
- Check for Python import errors by running the server manually and reading stderr.

**Tools not showing in Claude Code**
- Verify `.mcp.json` syntax is valid JSON (no trailing commas, correct paths).
- Restart the Claude Code session — tools are loaded at session start.
- Confirm the `cwd` in `.mcp.json` points to the MiroFish repo root.

**Tools not showing in Claude Desktop**
- Confirm the config is in the correct location: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS).
- Fully quit and relaunch Claude Desktop — a reload is not enough.
- Check that the `command` and `args` paths are absolute or correctly relative to `cwd`.

**Knowledge graph returns 0 nodes**
- Verify `ANTHROPIC_API_KEY` is valid and has quota — entity extraction requires LLM calls.
- Check server logs in `backend/logs/` for extraction errors.
- Ensure the documents passed to `build_knowledge_graph` exist and are readable.

**Search returns fewer results than expected**
- This is expected when `OPENAI_API_KEY` is not set. The FTS fallback requires exact or near-exact keyword matches; add `OPENAI_API_KEY` for semantic (vector) search.
- If `OPENAI_API_KEY` is set but results are still thin, the graph may have few nodes — run `get_graph_stats` to verify ingestion completed successfully.
