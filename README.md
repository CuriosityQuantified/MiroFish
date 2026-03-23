<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="MiroFish Logo" width="75%"/>

**A Simple and Universal Swarm Intelligence Engine, Predicting Anything**

[![GitHub Stars](https://img.shields.io/github/stars/CuriosityQuantified/MiroFish?style=flat-square&color=DAA520)](https://github.com/CuriosityQuantified/MiroFish/stargazers)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=flat-square&logo=discord&logoColor=white)](http://discord.gg/ePf5aPaHnA)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/666ghj/MiroFish)

</div>

---

## What is MiroFish?

MiroFish is a multi-agent swarm intelligence simulation engine. Feed it seed data — a news article, policy draft, financial report, or narrative — and it builds a high-fidelity digital world populated by AI agents with independent personalities, long-term memory, and behavioral logic. Those agents interact, evolve, and generate emergent patterns. The result: a prediction report telling you how a scenario plays out before it happens.

**Use cases:**
- Predict public opinion shifts before a product launch or policy announcement
- Simulate how information spreads across social networks
- Stress-test strategic decisions against thousands of simulated human reactions
- Generate prediction reports for novel narrative or story scenarios

---

## Architecture

```
Documents / Seed Data
        ↓
  Knowledge Graph (Graphiti + Kuzu)     ← embedded, no external services
        ↓
  Agent Profile Generation              ← personas derived from graph entities
        ↓
  OASIS Simulation (CAMEL-AI)           ← Twitter + Reddit social platforms
        ↓
  Report Agent (Claude Sonnet)          ← structured Markdown prediction report
        ↓
  MCP Tools / CLI / Web UI              ← consume results
```

**Tech stack:**
- **LLM:** Anthropic Claude (Haiku 4.5 for swarm agents, Sonnet for orchestration)
- **Knowledge graph:** [Graphiti](https://github.com/getzep/graphiti) + [Kuzu](https://kuzudb.com/) — embedded, temporal, zero infrastructure
- **Simulation:** [CAMEL-AI OASIS](https://github.com/camel-ai/oasis) — dual-platform (Twitter + Reddit)
- **Interface:** MCP server (Claude Code / OpenClaw), CLI, Flask web API

---

## Quickstart

### 1. Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.11–3.12 | `python --version` |
| Node.js | 18+ | `node -v` |
| uv | latest | `uv --version` |

### 2. Clone and configure

```bash
git clone https://github.com/CuriosityQuantified/MiroFish.git
cd MiroFish
cp .env.example .env
```

Edit `.env`:

```env
# Required
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Optional: use a proxy (e.g. cliproxy)
# ANTHROPIC_BASE_URL=http://localhost:8317/v1

# Model tuning (defaults shown)
LLM_SWARM_MODEL=claude-haiku-4-5-20251001
LLM_ORCHESTRATION_MODEL=claude-sonnet-4-6
```

### 3. Install dependencies

```bash
# All at once
npm run setup:all

# Or step by step
npm run setup          # Node + frontend
npm run setup:backend  # Python venv + backend deps
```

### 4. Run

**Web UI (Flask + Vue):**
```bash
npm run dev
# Frontend: http://localhost:3000
# Backend API: http://localhost:5001
```

**CLI (headless, no web UI):**
```bash
python backend/mirofish_cli.py run --config my_sim.json
```

**MCP server (Claude Code / OpenClaw):**
```bash
python backend/mirofish_mcp.py
```

**Docker:**
```bash
docker compose up -d
```

---

## CLI Reference

```
python backend/mirofish_cli.py <command> [options]

Commands:
  run      Run a full simulation from a config file
  build    Build a knowledge graph from documents
  report   Generate a report for a completed simulation
  status   Check simulation progress

Options for run:
  --config FILE      SimConfig JSON file (required)
  --output DIR       Output directory (default: data/sim_output)

Options for build:
  --documents FILE [FILE ...]   Document paths (PDF, MD, TXT)
  --graph-id NAME               Name for the graph
```

**Example config file (`sim.json`):**
```json
{
  "seed_topic": "Public reaction to new AI safety regulations",
  "platform": "both",
  "max_rounds": 10,
  "num_agents": 20,
  "output_dir": "data/sim_output",
  "report": true
}
```

---

## MCP Server

MiroFish exposes 7 tools via the [Model Context Protocol](https://modelcontextprotocol.io):

| Tool | Description |
|------|-------------|
| `create_simulation` | Validate and build a SimConfig |
| `run_simulation` | Execute a full pipeline — returns report text inline |
| `get_simulation_status` | Poll a running simulation |
| `build_knowledge_graph` | Ingest documents into a temporal graph |
| `search_graph` | Hybrid semantic + keyword search over graph facts |
| `get_graph_stats` | Node/edge counts and entity type breakdown |
| `read_report` | Read a report.md from disk |

**Claude Desktop / OpenClaw config:**
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

See [`docs/MCP_USAGE.md`](docs/MCP_USAGE.md) for the full guide.

---

## Simulation Config Schema

Full schema: [`backend/mirofish-config.schema.json`](backend/mirofish-config.schema.json)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `seed_topic` | string | `""` | Topic or scenario to simulate |
| `platform` | `"twitter"` \| `"reddit"` \| `"both"` | `"both"` | Social platform |
| `max_rounds` | int | `10` | Simulation rounds (1 round ≈ 1 hour) |
| `num_agents` | int | `10` | Number of AI agents |
| `graph_id` | string \| null | `null` | Existing knowledge graph to inject as agent memory |
| `documents` | string[] | `[]` | Document paths to build a graph from |
| `output_dir` | string | `"data/sim_output"` | Output directory |
| `report` | bool | `true` | Generate Markdown report after simulation |

---

## Output Structure

```
data/sim_output/sim_{id}/
├── config.json            ← copy of input config
├── simulation_config.json ← internal runner config
├── twitter/
│   └── actions.jsonl      ← per-agent actions (Twitter platform)
├── reddit/
│   └── actions.jsonl      ← per-agent actions (Reddit platform)
├── simulation.log         ← full process log
├── run_state.json         ← live status + progress
└── report.md              ← final Markdown prediction report ← primary artifact
```

---

## Infrastructure

Zero external services required beyond an Anthropic API key:

| Component | Technology | Notes |
|-----------|-----------|-------|
| Knowledge graph | Kuzu (embedded) | Stored at `data/kuzu_graph/`, no server needed |
| LLM | Anthropic API | Or any compatible proxy |
| Simulation | CAMEL-AI OASIS | Runs as local subprocesses |
| Semantic search | Graphiti hybrid retrieval | Degrades gracefully without embeddings |

---

## Development

**Run tests:**
```bash
cd backend
pytest tests/ -v
```

**Project structure:**
```
MiroFish/
├── backend/
│   ├── app/
│   │   ├── api/           ← Flask routes
│   │   ├── models/        ← SimConfig, SimResult, task models
│   │   ├── services/      ← HeadlessRunner, GraphBuilder, SimulationRunner, knowledge_graph
│   │   └── utils/         ← LLMClient, logger, zep_paging (legacy)
│   ├── scripts/           ← OASIS simulation entry points
│   ├── mirofish_cli.py    ← CLI entry point
│   └── mirofish_mcp.py    ← MCP server
├── frontend/              ← Vue web UI (optional)
├── docs/                  ← Design docs, MCP usage guide
├── data/
│   ├── kuzu_graph/        ← Embedded Kuzu DB (auto-created)
│   └── sim_output/        ← Simulation outputs
└── .env.example
```

---

## Credits

MiroFish's simulation engine is powered by [OASIS (Open Agent Social Interaction Simulations)](https://github.com/camel-ai/oasis) from the CAMEL-AI team.

Knowledge graph powered by [Graphiti](https://github.com/getzep/graphiti) from the Zep team.

Original MiroFish engine by the [MiroFish team](https://github.com/666ghj/MiroFish) at Shanda Group.

---

## License

AGPL-3.0
