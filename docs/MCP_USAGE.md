# MiroFish MCP Server — Usage Guide

MiroFish exposes its simulation and knowledge-graph capabilities as MCP tools,
usable from Claude Desktop, Claude Code, OpenClaw, and any MCP-compatible client.

---

## Setup

### 1. Install dependencies

```bash
cd MiroFish/backend
pip install -r requirements.txt
# or, if using uv:
uv pip install -r requirements.txt
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

| Tool | Description |
|------|-------------|
| `create_simulation` | Validate and return a SimConfig dict |
| `run_simulation` | Execute a full simulation end-to-end, returns SimResult + report text |
| `get_simulation_status` | Poll a running simulation for progress |

### Tier 2 — Knowledge Graph

| Tool | Description |
|------|-------------|
| `build_knowledge_graph` | Ingest documents into a temporal graph, returns graph_id |
| `search_graph` | Hybrid search over graph facts (semantic + keyword) |
| `get_graph_stats` | Node/edge counts and entity type breakdown |

### Tier 3 — Reports

| Tool | Description |
|------|-------------|
| `read_report` | Read a report.md from disk and return Markdown text |

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

## Troubleshooting

**`ANTHROPIC_API_KEY is not configured`** — check your `.env` file is in the repo root and `ANTHROPIC_API_KEY` is set.

**`No run state found for sim_dir`** — the sim_dir path must match exactly what `run_simulation` returned. Use `get_simulation_status(sim_dir)` with the full path.

**Simulation times out** — reduce `max_rounds` or `num_agents`. Each round makes LLM calls for every agent. Start with `max_rounds=5, num_agents=10`.

**Graph search returns empty results** — if no `OPENAI_API_KEY` is set, the no-op embedder is used and semantic search quality is reduced. Keyword search still works. Set an OpenAI-compatible embedding endpoint for full hybrid search.
