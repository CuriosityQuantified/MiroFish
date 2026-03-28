# MiroFish Setup Reference

## Contents
1. [Install dependencies](#1-install-dependencies)
2. [Configure .env](#2-configure-env)
3. [Run the server](#3-run-the-server)
4. [Client configuration](#4-client-configuration)
5. [Health check](#5-health-check)

---

## 1. Install dependencies

```bash
cd MiroFish/backend

# Core (graph, search, reports — always needed)
pip install -r requirements.txt

# Social simulation — only needed for run_simulation / get_simulation_status
pip install -r requirements-simulation.txt
```

Using `uv`:
```bash
uv pip install -r requirements.txt
uv pip install -r requirements-simulation.txt   # optional
```

> **Minimum working install:** `requirements.txt` only. Knowledge graph, search, and report tools all work. Social simulation requires the optional install.

---

## 2. Configure .env

Copy `.env.example` to `.env` in the repo root and set:

```env
# Required
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here

# Optional: OpenAI-compatible proxy (e.g. cliproxy, LiteLLM)
# ANTHROPIC_BASE_URL=http://localhost:8317/v1

# Optional: model overrides (defaults shown)
LLM_SWARM_MODEL=claude-haiku-4-5-20251001
LLM_ORCHESTRATION_MODEL=claude-sonnet-4-6

# Optional: enables semantic (vector) search in knowledge graph
OPENAI_API_KEY=your_openai_key_here
# OPENAI_BASE_URL=http://localhost:11434/v1   # any OpenAI-compatible embedding endpoint
```

### Embeddings — optional but recommended

| Mode | Key required | Search behaviour |
|------|-------------|-----------------|
| Keyword / FTS only | None | Full-text exact/near-exact match |
| Hybrid (semantic + keyword) | `OPENAI_API_KEY` | Finds conceptually related nodes, better recall |

Without `OPENAI_API_KEY` the graph ingests and searches correctly — results may just be narrower.

---

## 3. Run the server

### stdio (Claude Desktop / OpenClaw — default)
```bash
python backend/mirofish_mcp.py
```

### HTTP (remote or multi-client access)
```bash
python backend/mirofish_mcp.py --http --port 8080
# MCP endpoint: http://localhost:8080/mcp/
```

---

## 4. Client configuration

### Claude Desktop

File: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "mirofish": {
      "command": "python",
      "args": ["backend/mirofish_mcp.py"],
      "cwd": "/absolute/path/to/MiroFish"
    }
  }
}
```

After editing: **fully quit and relaunch** Claude Desktop (reload is not enough).

### Claude Code

File: `.mcp.json` in the repo root:

```json
{
  "mcpServers": {
    "mirofish": {
      "command": "python",
      "args": ["backend/mirofish_mcp.py"],
      "cwd": "."
    }
  }
}
```

After editing: restart the Claude Code session — tools are loaded at session start.

### OpenClaw

Add to your OpenClaw config (`~/.openclaw/openclaw.json`):

```json
{
  "mcpServers": {
    "mirofish": {
      "command": "python",
      "args": ["backend/mirofish_mcp.py"],
      "cwd": "/absolute/path/to/MiroFish"
    }
  }
}
```

---

## 5. Health check

Run before starting to verify environment:

```bash
python backend/mirofish_mcp.py --health-check
```

Checks:
- `.env` file exists
- `ANTHROPIC_API_KEY` is set and non-placeholder
- Python dependencies are installed
- `data/` directory is writable
- LLM endpoint is reachable (makes a 1-token call)

Returns exit code `0` if all pass, `1` if any fail.
