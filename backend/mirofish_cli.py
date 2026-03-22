#!/usr/bin/env python3
"""
mirofish_cli.py — MiroFish headless CLI (Phase 3d)

Subcommands
-----------
  run     Run a full simulation from a JSON config file
  build   Build a knowledge graph from one or more document files
  report  Generate a report for an existing simulation directory
  status  Query the status of a simulation directory

Examples
--------
  python backend/mirofish_cli.py run --config my_config.json
  python backend/mirofish_cli.py run --config my_config.json --output data/results
  python backend/mirofish_cli.py build --documents paper1.pdf paper2.txt --graph-id my-graph
  python backend/mirofish_cli.py report --sim-dir data/sim_output/headless_abc123 --graph-id g_xyz
  python backend/mirofish_cli.py status --sim-dir data/sim_output/headless_abc123

Entry point (pyproject.toml)
----------------------------
  [project.scripts]
  mirofish = "mirofish_cli:main"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

# Ensure the project root is on the path regardless of how the CLI is invoked.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_app():
    """Bootstrap a minimal Flask app context so service imports work."""
    from backend.app import create_app  # type: ignore
    app = create_app()
    return app


def _json_out(data: dict, indent: int = 2) -> None:
    print(json.dumps(data, indent=indent, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    """
    Load a SimConfig JSON file and run a full headless simulation.
    """
    config_path = os.path.abspath(args.config)
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        return 1

    with open(config_path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    # Override output_dir if --output was supplied on the CLI
    if args.output:
        raw["output_dir"] = os.path.abspath(args.output)

    app = _load_app()
    with app.app_context():
        from backend.app.models.sim_config import SimConfig  # type: ignore
        from backend.app.services.headless_runner import HeadlessRunner  # type: ignore

        try:
            config = SimConfig(**raw)
        except Exception as exc:
            print(f"ERROR: Invalid config — {exc}", file=sys.stderr)
            return 1

        print(f"Starting simulation…  platform={config.platform}, "
              f"max_rounds={config.max_rounds}, agents={config.num_agents}")

        runner = HeadlessRunner()
        result = runner.run(config)

    _json_out(result.model_dump())

    if result.status == "completed":
        print(f"\n✓ Simulation complete. Output: {result.sim_dir}")
        if result.report_path:
            print(f"  Report: {result.report_path}")
        return 0
    else:
        print(f"\n✗ Simulation failed: {result.error}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Subcommand: build
# ---------------------------------------------------------------------------

def cmd_build(args: argparse.Namespace) -> int:
    """
    Build a knowledge graph from one or more document files.
    Prints the resulting graph_id on success.
    """
    docs = [os.path.abspath(d) for d in args.documents]
    missing = [d for d in docs if not os.path.exists(d)]
    if missing:
        print(f"ERROR: Document(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 1

    app = _load_app()
    with app.app_context():
        from backend.app.services.graph_builder import GraphBuilderService  # type: ignore
        from backend.app.models.task import TaskStatus  # type: ignore

        # Load and concatenate document text
        parts: list[str] = []
        for path in docs:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                parts.append(fh.read())
        text = "\n\n".join(parts)

        graph_name = args.graph_id or f"mirofish-build-{int(time.time())}"
        svc = GraphBuilderService()
        task_id = svc.build_graph_async(text=text, ontology={}, graph_name=graph_name)

        print(f"Building graph '{graph_name}' (task_id={task_id})…")

        deadline = time.time() + 30 * 60  # 30 min timeout
        while time.time() < deadline:
            task = svc.task_manager.get_task(task_id)
            if task is None:
                print("ERROR: Task disappeared.", file=sys.stderr)
                return 1
            if task.status == TaskStatus.COMPLETED:
                graph_id = (task.result or {}).get("graph_id", "")
                print(f"✓ Graph built: graph_id={graph_id}")
                _json_out({"graph_id": graph_id, "task_id": task_id})
                return 0
            if task.status == TaskStatus.FAILED:
                print(f"✗ Graph build failed: {task.error}", file=sys.stderr)
                return 1
            progress = getattr(task, "progress", "?")
            print(f"  [{task.status}] progress={progress}%", end="\r")
            time.sleep(5)

        print("ERROR: Graph build timed out.", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Subcommand: report
# ---------------------------------------------------------------------------

def cmd_report(args: argparse.Namespace) -> int:
    """
    Generate a report for a simulation that has already completed.
    Copies full_report.md to {sim_dir}/report.md.
    """
    sim_dir = os.path.abspath(args.sim_dir)
    if not os.path.isdir(sim_dir):
        print(f"ERROR: sim-dir not found: {sim_dir}", file=sys.stderr)
        return 1

    sim_id = os.path.basename(sim_dir.rstrip("/"))
    graph_id = args.graph_id

    if not graph_id:
        # Try to read graph_id from simulation_config.json
        cfg_path = os.path.join(sim_dir, "simulation_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path) as fh:
                cfg = json.load(fh)
            graph_id = cfg.get("graph_id")

    if not graph_id:
        print("ERROR: --graph-id is required (or must be present in simulation_config.json).",
              file=sys.stderr)
        return 1

    app = _load_app()
    with app.app_context():
        from backend.app.services.report_agent import ReportAgent, ReportManager  # type: ignore
        import shutil

        requirement = args.requirement or (
            f"Analyse the simulation '{sim_id}' and summarise key findings."
        )
        agent = ReportAgent(
            graph_id=graph_id,
            simulation_id=sim_id,
            simulation_requirement=requirement,
        )
        print(f"Generating report for sim_id={sim_id}…")
        report = agent.generate_report()

        src = ReportManager._get_report_markdown_path(report.report_id)
        dst = os.path.join(sim_dir, "report.md")
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"✓ Report written to {dst}")
            return 0
        else:
            print(f"✗ full_report.md not found at {src}", file=sys.stderr)
            return 1


# ---------------------------------------------------------------------------
# Subcommand: status
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    """
    Print the current run-state for a simulation directory.
    """
    sim_dir = os.path.abspath(args.sim_dir)
    sim_id = os.path.basename(sim_dir.rstrip("/"))

    app = _load_app()
    with app.app_context():
        from backend.app.services.simulation_runner import SimulationRunner  # type: ignore

        state = SimulationRunner.get_run_state(sim_id)
        if state is None:
            print(f"No run state found for sim_id={sim_id}")
            return 1

        _json_out(state.to_dict())
        return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mirofish",
        description="MiroFish headless CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- run ---
    p_run = sub.add_parser("run", help="Run a full simulation from a config file")
    p_run.add_argument(
        "--config", required=True,
        help="Path to a SimConfig JSON file (matches mirofish-config.schema.json)",
    )
    p_run.add_argument(
        "--output", default=None,
        help="Override output directory (default: value from config)",
    )

    # --- build ---
    p_build = sub.add_parser("build", help="Build a knowledge graph from documents")
    p_build.add_argument(
        "--documents", nargs="+", required=True,
        help="One or more document file paths",
    )
    p_build.add_argument(
        "--graph-id", default=None,
        help="Optional name/ID for the new graph (auto-generated if omitted)",
    )

    # --- report ---
    p_report = sub.add_parser("report", help="Generate a report for an existing simulation")
    p_report.add_argument(
        "--sim-dir", required=True,
        help="Path to the simulation run-state directory",
    )
    p_report.add_argument(
        "--graph-id", default=None,
        help="Knowledge graph ID (reads from simulation_config.json if not specified)",
    )
    p_report.add_argument(
        "--requirement", default=None,
        help="Custom report requirement string",
    )

    # --- status ---
    p_status = sub.add_parser("status", help="Query simulation status")
    p_status.add_argument(
        "--sim-dir", required=True,
        help="Path to the simulation run-state directory",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "run": cmd_run,
        "build": cmd_build,
        "report": cmd_report,
        "status": cmd_status,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
