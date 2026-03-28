# Troubleshooting Reference

## Contents
1. [Environment & startup](#1-environment--startup)
2. [MCP client issues](#2-mcp-client-issues)
3. [Knowledge graph issues](#3-knowledge-graph-issues)
4. [Simulation issues](#4-simulation-issues)
5. [Dependency compatibility](#5-dependency-compatibility)

---

## 1. Environment & startup

**`ANTHROPIC_API_KEY is not configured`**
- Check `.env` exists in the repo root (not in `backend/`)
- Verify `ANTHROPIC_API_KEY=your_key_here` is set and not the literal string `placeholder`
- Run `python backend/mirofish_mcp.py --health-check` to diagnose

**Server exits immediately with no output**
- Check for Python import errors: `python -c "import mirofish_mcp"` from repo root
- Missing dependency — run `pip install -r backend/requirements.txt`

**`ModuleNotFoundError: No module named 'graphiti_core'`**
```bash
pip install -r backend/requirements.txt
```

**`ModuleNotFoundError: No module named 'camel'`** (or similar OASIS import)
```bash
pip install -r backend/requirements-simulation.txt
```

---

## 2. MCP client issues

### Tools not showing in Claude Desktop
1. Config file location (macOS): `~/Library/Application Support/Claude/claude_desktop_config.json`
2. Validate JSON syntax — no trailing commas, all paths quoted
3. Use **absolute paths** for `cwd` and `command`
4. **Fully quit and relaunch** Claude Desktop — a tab reload is not enough

### Tools not showing in Claude Code
1. Config file: `.mcp.json` in the repo root
2. Validate JSON syntax
3. **Restart the Claude Code session** — tools are loaded at session start, not on reload
4. Test manually: `python backend/mirofish_mcp.py --health-check`

### Server starts but tools return errors
- Check stderr from the MCP server process — FastMCP surfaces Python tracebacks there
- Run `--health-check` to verify all dependencies and API connectivity
- Try a minimal call: `create_simulation(seed_topic="test", max_rounds=1, num_agents=2)` — this makes no LLM calls and should return instantly

---

## 3. Knowledge graph issues

**`build_knowledge_graph` returns `node_count: 0`**
- Entity extraction uses LLM calls — verify `ANTHROPIC_API_KEY` is valid and has quota
- Check `backend/logs/` for extraction errors
- Very short documents (< 200 words) may yield 0 entities — this is normal

**`search_graph` returns empty list**
- Confirm `get_graph_stats(graph_id=...)` shows `node_count > 0` — if 0, the build failed silently
- Without `OPENAI_API_KEY`, only FTS search runs. Try more specific keyword-rich queries
- `graph_id` must match exactly what `build_knowledge_graph` returned — UUIDs are case-sensitive

**`search_graph` returns fewer results than expected**
- Set `OPENAI_API_KEY` to enable semantic (vector) search — greatly improves recall
- Increase `limit` parameter (default 10)
- Try rephrasing the query using entity names present in the documents

**`Binder exception: no index node_name_and_summary`**
- This is a known graphiti-core 0.28.2 bug, patched in MiroFish
- If you see it, the patch didn't apply — check you're running from the correct repo and haven't modified `backend/app/services/knowledge_graph.py`

**`AttributeError: 'KuzuDriver' object has no attribute '_database'`**
- Same as above — known upstream bug, patched in MiroFish
- Indicates the patch in `knowledge_graph.py` is not active

---

## 4. Simulation issues

**`Social simulation requires camel-oasis (not installed)`**
```bash
pip install -r backend/requirements-simulation.txt
```
Knowledge graph tools (`build_knowledge_graph`, `search_graph`, `get_graph_stats`) still work without this.

**Simulation times out (30-minute limit)**
- Reduce `max_rounds` or `num_agents` — each round × agent = 1 LLM call
- Start with `max_rounds=5, num_agents=10` to verify the pipeline works

**`run_simulation` returns `status: "failed"` with no clear error**
- Check `result["error"]` field
- Check `backend/logs/` for stack traces
- Try `create_simulation` first and verify the config looks correct

**`get_simulation_status` returns `runner_status: "not_found"`**
- The `sim_dir` must be the exact absolute path from `run_simulation`'s `sim_dir` field
- Run state is in-memory — restarting the server clears it. Use `sim_dir` path to read outputs directly after a server restart.

**Report not generated / `report_text` is null**
- Verify `generate_report=True` in config
- Check `report_path` in SimResult — if set, the file exists; read it with `read_report(report_path=...)`
- If `report_path` is null, report generation failed — check `backend/logs/`

---

## 5. Dependency compatibility

### pydantic + mcp compatibility

MiroFish pins `pydantic>=2.11.0,<2.12` in `pyproject.toml`. **Do not upgrade pydantic past 2.11.x** — pydantic 2.12.x introduced a regression in `RootModel` generic serialization that breaks `mcp 1.24.0`.

If you see:
```
KeyError: 'pydantic.root_model'
```
Run: `pip install "pydantic>=2.11.0,<2.12"`

### Python version

Tested on Python 3.12. Python 3.10+ required (uses `match` statements and modern `asyncio` patterns).

### asyncio warnings

If you see `DeprecationWarning: There is no current event loop` — this is fixed in the current codebase. If it reappears, it means code elsewhere is calling `asyncio.get_event_loop()` — replace with `asyncio.new_event_loop()` + `try/finally loop.close()`.
