# Phase 5: Integration Testing + End-to-End Validation

_Authored by Hal, 2026-03-22_

## Goal

Confirm all 4 phases work together correctly. Every piece of the new stack (Anthropic LLMs,
Graphiti+Kuzu graph, HeadlessRunner, mirofish_cli, MCP server) should have at least smoke-level
test coverage and a working CI run. Replace the outdated README with accurate documentation.

---

## Test Strategy

- **Framework:** `pytest` + `unittest.mock` — no live API calls, no real LLM/graph overhead
- **Kuzu:** use `tmp_path` fixture for ephemeral embedded graph DB per test
- **CI:** GitHub Actions, Python 3.11, cache pip deps, run on push + PR

---

## Tasks

### Task 5a — `tests/test_mcp_smoke.py`

Smoke tests for each MCP tool. Mock `HeadlessRunner.run()` and `knowledge_graph` so no
real simulation runs.

**Coverage:**
- All 6 Tier 1+2 tools importable from `mirofish_mcp`
- `create_simulation` returns a valid JSON string (round-trips through `SimConfig`)
- `get_simulation_status` handles missing `sim_dir` gracefully (returns `status: not_found`)
- `search_graph` returns empty list for unknown graph_id (no crash)
- `get_graph_stats` returns `{nodes: 0, edges: 0}` for unknown graph_id

**File:** `tests/test_mcp_smoke.py`
**Dependencies:** `pytest`, `unittest.mock`

### Task 5b — `tests/test_sim_config.py`

Pydantic v2 validation tests for `SimConfig` and `SimResult`.

**Coverage:**
- Default values are correct (platform="both", max_rounds=10, num_agents=10, report=True)
- `platform` rejects invalid values
- `SimResult` status field rejects invalid literals
- `export_json_schema()` produces valid JSON and writes a file

**File:** `tests/test_sim_config.py`

### Task 5c — `tests/test_cli.py`

CLI subcommand smoke tests using `subprocess.run` (or `click.testing.CliRunner` if applicable).

**Coverage:**
- `python backend/mirofish_cli.py --help` exits 0
- `python backend/mirofish_cli.py run --help` exits 0
- `python backend/mirofish_cli.py status --help` exits 0
- `python backend/mirofish_cli.py status --sim-dir /nonexistent` exits gracefully (no traceback)

**File:** `tests/test_cli.py`

### Task 5d — `tests/test_knowledge_graph.py`

Graphiti + Kuzu integration smoke test (real embedded DB, no LLM calls — use mock for LLM).

**Coverage:**
- `create_graph(graph_id)` succeeds (no exception)
- `add_episode(graph_id, text, source)` succeeds with mocked LLM
- `get_all_nodes(graph_id)` returns a list (may be empty without real LLM extraction)
- `search_graph(graph_id, query)` returns a list (may be empty)
- `delete_graph(graph_id)` succeeds

Use `pytest` `tmp_path` fixture for Kuzu DB path. Patch the Anthropic LLM client.

**File:** `tests/test_knowledge_graph.py`

### Task 5e — `.github/workflows/test.yml`

CI workflow that runs the test suite on every push and PR.

```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('backend/requirements.txt') }}
      - run: pip install -r backend/requirements.txt
      - run: pip install pytest
      - run: pytest tests/ -v
```

**File:** `.github/workflows/test.yml`

### Task 5f — `README.md` full rewrite

Replace the outdated Chinese-era README with a clean, accurate English document.
`README-EN.md` should also be updated (or symlinked to `README.md`).

**Sections:**
1. **What is MiroFish** — 2-3 sentences, accurate description of current state
2. **Architecture** — ASCII diagram showing: Documents → Graphiti+Kuzu → HeadlessRunner → Simulation → Report; MCP tools wrapping the stack
3. **Quickstart (5 steps):**
   ```
   git clone + cd
   cp .env.example .env  # add ANTHROPIC_API_KEY
   pip install -r backend/requirements.txt
   python backend/mirofish_cli.py run --config examples/simple_config.json
   # (optional) python backend/mirofish_mcp.py  # start MCP server
   ```
4. **Configuration** — link to `mirofish-config.schema.json`, describe key fields
5. **MCP Server** — how to add to Claude Desktop / OpenClaw (reference `docs/MCP_USAGE.md`)
6. **Development** — how to run tests, PR flow
7. **License**

**File:** `README.md` (overwrite), also update `README-EN.md`

---

## Acceptance Criteria

- `pytest tests/ -v` passes with no failures (all 5 test files)
- CI workflow runs green on push
- `README.md` no longer contains Chinese text or outdated setup instructions
- `README.md` accurately describes: Anthropic LLM setup, headless CLI, MCP server

---

## Notes

- Do NOT add live integration tests that require `ANTHROPIC_API_KEY` in CI — mock everything
- If `graphiti-core` has heavy deps that slow CI, consider `pytest --ignore=tests/test_knowledge_graph.py` as a fallback for the CI step, and note this in test.yml comments
- `tests/__init__.py` should exist (empty) to make `tests/` a proper package
