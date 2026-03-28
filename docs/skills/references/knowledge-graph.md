# Knowledge Graph Reference

## Contents
1. [build_knowledge_graph — usage & limits](#1-build_knowledge_graph--usage--limits)
2. [search_graph — query strategies](#2-search_graph--query-strategies)
3. [get_graph_stats — interpreting output](#3-get_graph_stats--interpreting-output)
4. [Embedding modes](#4-embedding-modes)
5. [Upstream graphiti-core patches](#5-upstream-graphiti-core-patches)

---

## 1. build_knowledge_graph — usage & limits

```python
build_knowledge_graph(
    document_paths=["/path/to/policy.pdf", "/path/to/article.md"],
    graph_name="EU AI Act"          # human-readable label, optional
)
```

Returns:
```json
{
  "graph_id": "mirofish_abc123...",
  "node_count": 47,
  "edge_count": 132,
  "error": null
}
```

**Supported file types:** PDF, Markdown (`.md`), plain text (`.txt`).

**Blocking call** — polls until complete (up to 10 minutes for large documents). For very large corpora (>50 documents), split into batches and merge `graph_id`s manually.

**graph_id reuse:** The `graph_id` returned persists in `data/kuzu_graph/`. You can pass it to `create_simulation(graph_id=...)` in future sessions without rebuilding.

### What gets extracted

Graphiti-core uses an LLM to extract:
- **EntityNodes** — named entities (people, organisations, concepts, policies, events)
- **EntityEdges** — typed relationships between entities with temporal validity (`valid_at` / `invalid_at`)

Entity extraction quality depends on `ANTHROPIC_MODEL` (or `LLM_ORCHESTRATION_MODEL`). More capable models extract richer graphs.

---

## 2. search_graph — query strategies

```python
search_graph(
    graph_id="mirofish_abc123...",
    query="Which stakeholders opposed the AI Act?",
    limit=10
)
```

Returns a list of edge dicts:
```json
[
  {
    "fact": "MEP Brando Benifei opposed Article 5 of the AI Act",
    "name": "OPPOSED",
    "source_node_uuid": "...",
    "target_node_uuid": "...",
    "valid_at": "2024-03-12T00:00:00",
    "invalid_at": null
  }
]
```

### Query tips

- **Ask as a question** — Graphiti's hybrid retrieval handles natural-language questions well.
- **Use entity names** — including known entity names (people, orgs, policies) improves FTS recall.
- **Temporal queries** — the `valid_at` / `invalid_at` fields let you reason about time: a fact with `invalid_at` set was true only until that date.
- **Increase `limit`** — default is 10; use 20-50 for exploratory queries.
- **Empty results** — if results are unexpectedly empty, check `get_graph_stats` first to confirm the graph was populated.

---

## 3. get_graph_stats — interpreting output

```python
get_graph_stats(graph_id="mirofish_abc123...")
```

Returns:
```json
{
  "graph_id": "mirofish_abc123...",
  "node_count": 47,
  "edge_count": 132,
  "entity_types": {
    "Person": 12,
    "Organization": 8,
    "Policy": 5,
    "Event": 6
  },
  "error": null
}
```

**0 nodes after build_knowledge_graph:** Entity extraction failed — most likely an invalid `ANTHROPIC_API_KEY` or quota exhaustion. Check server logs at `backend/logs/`.

**Low node count for large documents:** Normal for short documents. Entity extraction runs per text chunk; dense, well-structured documents produce richer graphs.

---

## 4. Embedding modes

| Mode | Config | Search quality |
|------|--------|---------------|
| **No embeddings (default)** | `OPENAI_API_KEY` not set | FTS only — exact/near-exact keyword match |
| **Hybrid** | `OPENAI_API_KEY` set | Semantic + keyword — finds conceptually related facts even without exact keyword match |
| **Local embeddings** | `OPENAI_API_KEY` + `OPENAI_BASE_URL=http://localhost:11434/v1` | Any OpenAI-compatible embedding endpoint (e.g. Ollama, LiteLLM) |

For open-source / privacy-sensitive deployments, point `OPENAI_BASE_URL` at a local Ollama instance running `nomic-embed-text` or similar.

---

## 5. Upstream graphiti-core patches

MiroFish ships with 5 patches to `graphiti-core==0.28.2` applied in `backend/app/services/knowledge_graph.py`. These are transparent to users — no action needed unless you upgrade graphiti-core.

| # | Issue | Symptom | Fix |
|---|-------|---------|-----|
| 1 | `KuzuDriver` missing `_database` attribute | `AttributeError` on episode ingestion | Attribute injected at init |
| 2 | Anthropic SDK base URL double `/v1` | `404 page not found` on LLM calls | Strips trailing `/v1` before passing to SDK |
| 3 | Kuzu FTS indices never created | `Binder exception: no index node_name_and_summary` | 4 FTS indices created manually at startup |
| 4 | `NoOpEmbedder` missing `create_batch()` | `NotImplementedError` during edge resolution | Method added to `NoOpEmbedder` |
| 5 | `NoOpEmbedder` wrong return type | `Unsupported casting LIST...FLOAT[1]` | Returns flat `list[float]` instead of nested list |

If you upgrade graphiti-core, re-run `pytest tests/test_knowledge_graph.py` to verify these patches are no longer needed. Remove any that pass without patching.
