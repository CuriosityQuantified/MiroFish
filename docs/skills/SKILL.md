---
name: mirofish
description: MiroFish MCP tools — run multi-agent social simulations, build temporal knowledge graphs from documents, and generate prediction reports. Use when a user wants to simulate how the world reacts to an event, ingest documents into a graph, search extracted facts, or poll simulation progress. Tools: create_simulation, run_simulation, get_simulation_status, build_knowledge_graph, search_graph, get_graph_stats, read_report.
---

# MiroFish MCP Skill

MiroFish is a swarm intelligence simulation engine. AI agent swarms simulate social platform reactions to any seed topic; a temporal knowledge graph optionally grounds agent memory in real documents.

## Tool Map

| Tier | Tool | One-liner |
|------|------|-----------|
| 1 | `create_simulation` | Validate params → return SimConfig dict |
| 1 | `run_simulation` | Execute full pipeline → SimResult + inline report text |
| 1 | `get_simulation_status` | Poll progress for a running sim |
| 2 | `build_knowledge_graph` | Ingest docs (PDF/MD/TXT) → graph_id |
| 2 | `search_graph` | Hybrid semantic + keyword search over graph facts |
| 2 | `get_graph_stats` | Node/edge counts + entity type breakdown |
| 3 | `read_report` | Read a saved report.md from disk |

## Typical Workflows

### Quick simulation (no docs)
```
create_simulation(seed_topic="...", platform="twitter", max_rounds=10, num_agents=20)
→ run_simulation(config=<result>)
→ report_text inline in SimResult
```

### Simulation with document memory
```
build_knowledge_graph(document_paths=[...])          → graph_id
create_simulation(..., graph_id=<graph_id>)          → config
run_simulation(config=<config>)                       → SimResult + report
search_graph(graph_id=<graph_id>, query="...")        → facts
```

### Graph-only (no simulation)
```
build_knowledge_graph(document_paths=[...])           → graph_id
search_graph(graph_id=..., query="...")               → facts
get_graph_stats(graph_id=...)                         → counts
```

## When to Read Reference Files

- **First-time setup / install errors** → [`references/setup.md`](references/setup.md)
- **Tuning simulation parameters / OASIS errors** → [`references/simulation.md`](references/simulation.md)
- **Graph ingestion, embeddings, search quality** → [`references/knowledge-graph.md`](references/knowledge-graph.md)
- **Any error or unexpected behaviour** → [`references/troubleshooting.md`](references/troubleshooting.md)

## Quick Rules

- Always call `create_simulation` first — it validates params before any LLM spend.
- `run_simulation` is **blocking** (up to 30 min). For long runs, call it in a background job and poll with `get_simulation_status`.
- `build_knowledge_graph` is also blocking (up to 10 min for large docs). Pass file paths, not content.
- `graph_id` and `document_paths` in `create_simulation` are mutually exclusive — if both given, `graph_id` wins.
- Social simulation (`run_simulation`, `get_simulation_status`) requires the optional `requirements-simulation.txt` install. Knowledge graph tools work without it.
