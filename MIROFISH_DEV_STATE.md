# MiroFish Development State

_Last updated: 2026-03-22 12:00 PDT_

## Project Overview
MiroFish is a multi-agent swarm intelligence simulation engine. We're converting it into a tool for OpenClaw and Claude Code (MCP server) with Anthropic LLM support and self-hosted dependencies.

**Repo:** https://github.com/CuriosityQuantified/MiroFish
**Local:** ~/Projects/MiroFish
**Channel:** #mirofish (Discord channel:1485064060855648256)
**Team:** Hal (architecture, review, coordination), CC (implementation, coding)

## Roadmap

### Phase 1: Anthropic LLM Backend Swap ✅ COMPLETE
**Status:** Done — commit `64e2b99` (2026-03-22)
**Goal:** Replace OpenAI/Qwen LLM calls with Anthropic Claude models
**Details:**
- Layer 1 (easy): `backend/app/utils/llm_client.py` — uses OpenAI SDK with configurable `base_url`/`model`. Point at Anthropic-compatible endpoint.
- Layer 2 (complex): CAMEL-AI/CAMEL-OASIS internal LLM config — `camel-oasis==0.2.5` and `camel-ai==0.2.78` have their own model configuration. Need to verify how they accept LLM provider settings.
- `oasis_profile_generator.py` also uses `openai.OpenAI` directly (separate from LLMClient)
- `chat_json()` uses `response_format={"type": "json_object"}` — verify Claude compatibility through OpenAI-compatible endpoint
- **Target models:** Haiku 4.5 for swarm agents, Sonnet for orchestration/reports

### Phase 2: Zep Cloud → Graphiti + Kuzu ✅ COMPLETE
**Status:** Done — commit `13ce291` (2026-03-22)
**Goal:** Replace `zep-cloud` SaaS dependency with self-hosted `graphiti-core[kuzu,anthropic]`
**What was done:**
- Created `backend/app/services/knowledge_graph.py` — central Graphiti + Kuzu wrapper module
  - Lazy singleton Graphiti instance with KuzuDriver (embedded DB at `data/kuzu_graph/`)
  - Anthropic LLM client for entity extraction
  - No-op embedder/cross-encoder fallbacks when OPENAI_API_KEY is absent
  - Full API: create_graph, add_episode(s), get_all_nodes/edges, search_graph, delete_graph
- Rewrote `backend/app/services/graph_builder.py` — no longer imports `zep_cloud`
- Rewrote `backend/app/services/zep_entity_reader.py` — delegates to knowledge_graph module
- Rewrote `backend/app/services/zep_tools.py` — search/retrieval backed by Graphiti
- Rewrote `backend/app/services/zep_graph_memory_updater.py` — memory updates via Graphiti
- Updated `backend/app/services/oasis_profile_generator.py` — hybrid search via knowledge_graph
- Updated `backend/app/utils/zep_paging.py` — legacy stub (graceful if zep_cloud missing)
- Updated `backend/app/api/graph.py`, `simulation.py`, `report.py` — removed ZEP_API_KEY checks
- Updated `backend/app/config.py` — added KUZU_DB_PATH, made ZEP_API_KEY optional
- Updated `.env.example` — documented new config, Zep marked as legacy
- **ZEP_API_KEY is no longer required** — fully embedded, zero external dependencies
- Class names (ZepEntityReader, ZepToolsService, etc.) kept for backward compat
- `zep-cloud` pip package still installable but not imported at runtime

**Post-Phase-2 cleanup done by Hal (2026-03-22):**
- `backend/requirements.txt` updated: `graphiti-core[kuzu,anthropic]` added, `zep-cloud` demoted to legacy comment — commit `64aa60f`
- `docs/phase3-headless-design.md` written — full architecture doc for Phase 3
- Translation cleanup subagent spawned: scripts still had 615/245/218/46 Chinese instances in run_parallel_simulation.py, run_twitter_simulation.py, run_reddit_simulation.py, action_logger.py; pending commit

### Phase 3: Headless Mode 🔄 IN PROGRESS
**Status:** Architecture designed, CC to implement
**Goal:** Decouple from Vue frontend, enable pure CLI/API execution
**Design doc:** `docs/phase3-headless-design.md`

**Tasks for CC:**
1. **Task 3a** — Fix remaining Chinese comments in scripts (run_parallel_simulation.py, run_twitter/reddit_simulation.py, action_logger.py, simulation.py API) — translation subagent running
2. **Task 3b** — Create `backend/app/models/sim_config.py` — Pydantic `SimConfig` model + JSON schema export
3. **Task 3c** — Create `backend/app/services/headless_runner.py` — `HeadlessRunner` class wrapping graph build + sim run + report in sequence
4. **Task 3d** — Create `backend/mirofish_cli.py` — argparse CLI with `run`, `build`, `report`, `status` subcommands
5. **Task 3e** — Ensure `report_agent.py` writes `report.md` to sim output dir

**Acceptance criteria:**
- `python backend/mirofish_cli.py run --config test_config.json` runs without Flask
- `report.md` written to output dir
- `SimConfig` validates with pydantic v2
- All script files English-only

### Phase 4: MCP Server Wrapper
**Status:** Not started (depends on Phase 3)
**Goal:** Expose MiroFish as MCP tools for Claude Code / OpenClaw
**Details:**
- Evaluate Graphiti's built-in MCP server first (ships with graphiti-core)
- Tool surface: `create_simulation`, `run_simulation`, `inject_variable`, `get_results`, `query_graph`
- If built-in MCP server covers enough, extend it; otherwise build thin wrapper
- Phase 3 `HeadlessRunner` + `report.md` output are the bridge

## Architecture Notes

### Key Files
- `backend/app/utils/llm_client.py` — LLM abstraction (OpenAI SDK format)
- `backend/app/config.py` — env var loading (.env file)
- `backend/app/services/knowledge_graph.py` — Graphiti + Kuzu knowledge graph wrapper (NEW)
- `backend/app/services/simulation_runner.py` — runs OASIS simulations as subprocesses
- `backend/app/services/graph_builder.py` — graph construction (via Graphiti + Kuzu)
- `backend/app/services/zep_tools.py` — all retrieval/search tools (via Graphiti + Kuzu)
- `backend/app/services/oasis_profile_generator.py` — generates agent personas from graph entities
- `backend/app/services/report_agent.py` — post-simulation report generation
- `backend/scripts/run_parallel_simulation.py` — simulation entry point (1713 lines)
- `docs/phase3-headless-design.md` — Phase 3 architecture design (NEW)

### Dependencies
- `openai>=1.0.0` — LLM client (OpenAI SDK format)
- `graphiti-core[kuzu,anthropic]` — knowledge graph engine + embedded graph DB ← UPDATED
- `camel-oasis==0.2.5` — OASIS simulation framework
- `camel-ai==0.2.78` — CAMEL multi-agent framework
- `flask>=3.0.0` — web API
- `PyMuPDF>=1.24.0` — PDF parsing
- `zep-cloud==3.13.0` — LEGACY, optional fallback (not imported at runtime, commented out in requirements)

### What CC Translated (completed in Phase 1+2)
- 60 files, 3,448 lines changed
- All human-facing text → English
- Backend Python (docstrings, comments, logs, errors)
- Frontend Vue/JS (UI text, component labels)
- Config files (.env.example, Dockerfile, docker-compose.yml)
- Some Chinese LLM system prompts intentionally preserved (functional for Chinese NLP pipeline)
- **Missed:** simulation scripts (run_parallel_simulation.py etc.) — being fixed in cleanup

## Decisions Made
- **Graphiti + Kuzu over Zep Cloud** — self-hosted, embedded, no external API keys
- **Kuzu over Neo4j/FalkorDB** — embedded graph DB, zero infrastructure
- **Anthropic models** — Haiku 4.5 for agents, Sonnet for orchestration
- **Neo4j is NOT a dependency** — all graph ops go through Graphiti + Kuzu
- **Zep Cloud kept as optional fallback** — zep_paging.py still works if zep-cloud is installed
- **Class names preserved** — ZepEntityReader, ZepToolsService etc. kept for backward compat
- **Phase 3 headless architecture** — HeadlessRunner service + mirofish_cli.py entry point; no new pip deps
- **Phase 4 MCP strategy** — evaluate Graphiti's built-in MCP server first, extend if sufficient
