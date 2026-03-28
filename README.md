<div align="center">

<img src="./static/image/MiroFish_logo_compressed.jpeg" alt="MiroFish Logo" width="75%"/>

**Simulate how the world reacts — using AI agent swarms**

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

## Quick Start (MCP Server)

The fastest path to using MiroFish from Claude Code or Claude Desktop:

```bash
git clone https://github.com/halgorithm/MiroFish.git && cd MiroFish
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
# Optional: for Twitter/Reddit social simulations (~500MB additional)
pip install -r backend/requirements-simulation.txt
cp .env.example .env   # edit .env → set ANTHROPIC_API_KEY
python backend/mirofish_mcp.py --health-check
```

Then register the server in your client config (see [MCP Server](#mcp-server) below) and you're done.

> **Core install** (~50MB): knowledge graph building, search, reports, MCP tools
> **With simulation** (+500MB): adds Twitter/Reddit AI agent simulations via CAMEL-AI OASIS

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

# Optional but recommended — enables vector embeddings for higher-quality graph search.
# Without it, MiroFish falls back to keyword search.
# OPENAI_API_KEY=your_openai_api_key_here

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

**Claude Code (`~/.mcp.json`):**
```json
{
  "mcpServers": {
    "mirofish": {
      "command": "/path/to/MiroFish/.venv/bin/python",
      "args": ["/path/to/MiroFish/backend/mirofish_mcp.py"],
      "cwd": "/path/to/MiroFish"
    }
  }
}
```

**Claude Desktop (`claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "mirofish": {
      "command": "/path/to/MiroFish/.venv/bin/python",
      "args": ["/path/to/MiroFish/backend/mirofish_mcp.py"]
    }
  }
}
```

Use the absolute path to the venv `python` binary rather than a bare `python` to avoid PATH-dependent failures.

**Verify your setup:**
```bash
python scripts/verify-setup.py
python backend/mirofish_mcp.py --health-check
```

See [`docs/MCP_USAGE.md`](docs/MCP_USAGE.md) for the full guide.

---

## Sample Output

Here's an excerpt from a MiroFish prediction report ([full report](./docs/sample-report.md)):

<details>
<summary>Click to expand sample report excerpt</summary>

> Generated by MiroFish v1.26.0 | 5 agents | 3 rounds | Twitter simulation
> Knowledge graph: 129 nodes, 155 edges | Source: project documentation + web context
> Simulation completed: 2026-03-23T21:34:00Z | Duration: 8m 42s

---

# Prediction Report: Community Reaction to Anthropic Open-Sourcing Claude

## Executive Summary

This simulation modeled how the AI developer community would react on Twitter/X if Anthropic announced that Claude's model weights were being released under an open-source license. Five AI-persona agents — spanning independent researchers, startup founders, enterprise architects, open-source advocates, and AI safety researchers — interacted across three rounds of simulated discourse, producing 47 posts, 83 replies, and 12 quote-tweets.

The dominant emergent pattern is **cautious optimism fractured along professional lines**. Developer-practitioners overwhelmingly celebrated the move (sentiment score 0.81), while safety-aligned researchers expressed measured concern about capability proliferation (sentiment score 0.43). Enterprise architects occupied a pragmatic middle ground, focusing on licensing terms and deployment implications rather than ideology.

A notable secondary finding: by round 3, the conversation shifted from the announcement itself to **competitive implications for other labs**. Agents organically began discussing whether Meta's Llama and Google's Gemma ecosystems would be disrupted, and whether this would force a broader industry shift toward openness. This emergent topic drift was not seeded — it arose from agent interactions alone.

**[View full report →](./docs/sample-report.md)**

</details>

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
