# Simulation Reference

## Contents
1. [create_simulation — parameter guide](#1-create_simulation--parameter-guide)
2. [run_simulation — execution & output](#2-run_simulation--execution--output)
3. [get_simulation_status — polling](#3-get_simulation_status--polling)
4. [Tuning for cost vs. fidelity](#4-tuning-for-cost-vs-fidelity)
5. [OASIS install & known errors](#5-oasis-install--known-errors)

---

## 1. create_simulation — parameter guide

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `seed_topic` | str | required | Topic to simulate. Be specific — "EU AI Act vote reaction on Twitter" beats "AI policy". |
| `platform` | str | `"both"` | `"twitter"` / `"reddit"` / `"both"` |
| `max_rounds` | int | `10` | Each round ≈ 1 simulated hour. Start low (5-10) to test; use 24-144 for full-day/week sims. |
| `num_agents` | int | `10` | 10 is good for testing; 50+ for richer emergence (higher LLM cost). |
| `graph_id` | str | `""` | ID from `build_knowledge_graph`. Leave blank to run without document memory. |
| `document_paths` | list[str] | `None` | Build a graph on-the-fly before running. Mutually exclusive with `graph_id` — if both given, `graph_id` wins. |
| `output_dir` | str | `"data/sim_output"` | Directory for outputs. Created if it doesn't exist. |
| `generate_report` | bool | `True` | Whether to generate a Markdown prediction report after the simulation. |

`create_simulation` is a **validation-only call** — it makes no LLM requests and returns immediately. Always call it first to catch config errors cheaply.

---

## 2. run_simulation — execution & output

`run_simulation` accepts the dict returned by `create_simulation` and executes the full pipeline:

1. (If `document_paths` provided) builds knowledge graph
2. Generates agent personas from graph entities
3. Runs OASIS social simulation
4. (If `generate_report=True`) generates Markdown prediction report

**This is a blocking call** — it will not return until the simulation completes or times out (default 30 minutes).

### SimResult fields

| Field | Description |
|-------|-------------|
| `status` | `"completed"` / `"failed"` / `"partial"` |
| `sim_dir` | Path to simulation output directory |
| `report_path` | Path to `report.md` (if generated) |
| `report_text` | Full Markdown report text inline (if generated and readable) |
| `node_count` / `edge_count` | Knowledge graph statistics |
| `agent_count` / `rounds_completed` | Simulation statistics |
| `error` | Error message if `status == "failed"` |

### Long-running simulations

For sims with `max_rounds > 20` or `num_agents > 50`, consider:
1. Call `run_simulation` in a background job / async context
2. Poll progress with `get_simulation_status(sim_dir=<sim_dir from result>)`
3. Read the report with `read_report(report_path=<report_path>)` when done

---

## 3. get_simulation_status — polling

```python
get_simulation_status(sim_dir="/absolute/path/to/data/sim_output/sim_20250328_...")
```

Returns:

| Field | Values |
|-------|--------|
| `runner_status` | `"idle"` / `"starting"` / `"running"` / `"completed"` / `"failed"` / `"stopped"` / `"not_found"` |
| `current_round` / `total_rounds` | Progress counters |
| `twitter_actions_count` / `reddit_actions_count` | Action tallies |
| `started_at` / `completed_at` | ISO timestamps |
| `error` | Set if `status == "failed"` |

`"not_found"` means `sim_dir` doesn't match any tracked run — verify the path from `run_simulation`'s `sim_dir` field.

---

## 4. Tuning for cost vs. fidelity

| Use case | Recommended settings |
|----------|---------------------|
| Quick test / prototype | `max_rounds=5, num_agents=10, platform="twitter"` |
| Standard prediction | `max_rounds=20, num_agents=30, platform="both"` |
| High-fidelity / research | `max_rounds=48-144, num_agents=50-100, platform="both"` |

**Cost drivers:**
- Every round makes one LLM call per agent
- `platform="both"` runs two separate platform simulations
- `generate_report=True` adds ~5-10 LLM calls for synthesis

**Cost estimate:** `max_rounds × num_agents` = total agent-turn LLM calls. At `max_rounds=10, num_agents=20` that's ~200 calls to `LLM_SWARM_MODEL` (haiku by default).

---

## 5. OASIS install & known errors

Social simulation (`run_simulation`, `get_simulation_status`) requires CAMEL-AI's OASIS framework:

```bash
pip install -r backend/requirements-simulation.txt
```

### Error: `camel-oasis is not installed`

```
Social simulation requires camel-oasis (not installed).
Install with: pip install -r backend/requirements-simulation.txt
```

This is a clean error — graph and report tools still work. Install the optional requirements to enable simulation.

### Error: simulation times out

Reduce `max_rounds` or `num_agents`. At high values, each round takes several minutes due to per-agent LLM calls.

### Error: `No run state found for sim_dir`

The `sim_dir` passed to `get_simulation_status` must match exactly what `run_simulation` returned. Use the full absolute path from the `sim_dir` field of the SimResult.
