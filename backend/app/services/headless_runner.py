"""
HeadlessRunner — MiroFish Phase 3

Orchestrates a full simulation run without the Flask frontend:
  1. Optionally build a knowledge graph from documents
  2. Prepare simulation_config.json in the run-state directory
  3. Launch SimulationRunner and poll until complete (or timeout)
  4. Optionally generate a report and copy it to {sim_dir}/report.md
  5. Return a structured SimResult

Usage::

    from backend.app.models.sim_config import SimConfig
    from backend.app.services.headless_runner import HeadlessRunner

    config = SimConfig(
        platform="twitter",
        max_rounds=5,
        num_agents=10,
        seed_topic="AI regulation",
        report=True,
    )
    result = HeadlessRunner().run(config)
    print(result.status, result.report_path)
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from typing import Optional

from ..config import Config
from ..models.sim_config import SimConfig, SimResult
from ..services import knowledge_graph as kg
from ..services.graph_builder import GraphBuilderService
from ..services.simulation_runner import RunnerStatus, SimulationRunner
from ..utils.logger import get_logger

logger = get_logger("mirofish.headless_runner")

# How often to poll simulation status (seconds)
_POLL_INTERVAL = 5

# Default timeout: 30 minutes
_DEFAULT_TIMEOUT = 30 * 60


class HeadlessRunner:
    """
    Orchestrate a complete MiroFish simulation run headlessly.

    Parameters
    ----------
    timeout : int
        Maximum seconds to wait for the simulation to finish.
    poll_interval : int
        Seconds between status-poll iterations.
    """

    def __init__(
        self,
        timeout: int = _DEFAULT_TIMEOUT,
        poll_interval: int = _POLL_INTERVAL,
    ):
        self.timeout = timeout
        self.poll_interval = poll_interval

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, config: SimConfig) -> SimResult:
        """
        Run a full simulation and return a SimResult.

        All failures are caught and returned as SimResult(status="failed").
        """
        # Check OASIS availability before starting simulation
        try:
            import camel  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "Social simulation requires camel-oasis. "
                "Install with: pip install -r backend/requirements-simulation.txt"
            )

        sim_id = f"headless_{uuid.uuid4().hex[:12]}"
        logger.info(f"HeadlessRunner starting: sim_id={sim_id}, config={config.model_dump()}")

        try:
            # 1. Build / resolve knowledge graph
            graph_id = self._resolve_graph(config, sim_id)

            # 2. Write simulation_config.json to run-state directory
            sim_dir = self._prepare_sim_dir(config, sim_id, graph_id)

            # 3. Launch simulation
            self._start_simulation(config, sim_id, graph_id)

            # 4. Poll until done or timeout
            final_state = self._poll_until_done(sim_id)

            if final_state is None:
                return SimResult(
                    graph_id=graph_id or "",
                    sim_dir=sim_dir,
                    status="failed",
                    error=f"Simulation timed out after {self.timeout}s",
                )

            if final_state.runner_status == RunnerStatus.FAILED:
                return SimResult(
                    graph_id=graph_id or "",
                    sim_dir=sim_dir,
                    status="failed",
                    error="SimulationRunner reported FAILED status",
                )

            # 5. Optionally generate report
            report_path: Optional[str] = None
            if config.report and graph_id:
                report_path = self._generate_report(sim_id, graph_id, config, sim_dir)

            # 6. Collect counts
            node_count, edge_count = self._count_graph(graph_id)

            return SimResult(
                graph_id=graph_id or "",
                sim_dir=sim_dir,
                report_path=report_path,
                node_count=node_count,
                edge_count=edge_count,
                agent_count=config.num_agents,
                rounds_completed=final_state.completed_rounds,
                status="completed",
            )

        except Exception as exc:  # pylint: disable=broad-except
            logger.exception(f"HeadlessRunner error for sim_id={sim_id}: {exc}")
            return SimResult(
                graph_id=config.graph_id or "",
                sim_dir=os.path.join(SimulationRunner.RUN_STATE_DIR, sim_id),
                status="failed",
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Step 1: knowledge graph
    # ------------------------------------------------------------------

    def _resolve_graph(self, config: SimConfig, sim_id: str) -> Optional[str]:
        """
        Return the graph_id to use.

        - If config.graph_id is set, use it directly.
        - If config.documents are provided, build a new graph from them.
        - Otherwise return None (simulation runs without graph memory).
        """
        if config.graph_id:
            logger.info(f"Using existing graph_id={config.graph_id}")
            return config.graph_id

        if not config.documents:
            logger.info("No documents and no graph_id — running without knowledge graph")
            return None

        logger.info(f"Building knowledge graph from {len(config.documents)} document(s)")
        text = self._load_documents(config.documents)

        # Build graph synchronously via GraphBuilderService's async task + poll
        svc = GraphBuilderService()
        ontology: dict = {}  # Default empty ontology; Graphiti infers structure
        task_id = svc.build_graph_async(
            text=text,
            ontology=ontology,
            graph_name=f"mirofish-{sim_id}",
        )

        # Poll the task until done
        graph_id = self._wait_for_graph_task(svc, task_id)
        logger.info(f"Graph built: graph_id={graph_id}")
        return graph_id

    def _load_documents(self, paths: list[str]) -> str:
        """Load and concatenate text from a list of file paths."""
        parts: list[str] = []
        for path in paths:
            if not os.path.exists(path):
                logger.warning(f"Document not found, skipping: {path}")
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    parts.append(fh.read())
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(f"Could not read {path}: {exc}")
        return "\n\n".join(parts)

    def _wait_for_graph_task(self, svc: GraphBuilderService, task_id: str) -> str:
        """
        Poll GraphBuilderService's TaskManager until the build task completes.

        Returns the graph_id from the task result.
        Raises RuntimeError on failure or timeout.
        """
        from ..models.task import TaskStatus  # local import to avoid circular

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            task = svc.task_manager.get_task(task_id)
            if task is None:
                raise RuntimeError(f"Graph build task {task_id} not found")
            if task.status == TaskStatus.COMPLETED:
                graph_id = (task.result or {}).get("graph_id")
                if not graph_id:
                    raise RuntimeError(f"Graph build task {task_id} completed but returned no graph_id")
                return graph_id
            if task.status == TaskStatus.FAILED:
                raise RuntimeError(f"Graph build task {task_id} failed: {task.error}")
            time.sleep(self.poll_interval)

        raise RuntimeError(f"Graph build task {task_id} timed out after {self.timeout}s")

    # ------------------------------------------------------------------
    # Step 2: prepare simulation directory + config
    # ------------------------------------------------------------------

    def _prepare_sim_dir(
        self, config: SimConfig, sim_id: str, graph_id: Optional[str]
    ) -> str:
        """
        Create the run-state directory and write simulation_config.json.

        SimulationRunner expects simulation_config.json at
        {RUN_STATE_DIR}/{sim_id}/simulation_config.json.

        We write a minimal config that the existing scripts can parse.
        """
        sim_dir = os.path.join(SimulationRunner.RUN_STATE_DIR, sim_id)
        os.makedirs(sim_dir, exist_ok=True)

        # Resolve output dir (used for final artefacts)
        output_dir = os.path.abspath(config.output_dir)
        os.makedirs(output_dir, exist_ok=True)

        # Build the simulation_config.json structure expected by the runner scripts.
        # The scripts read fields like platform, max_rounds, num_agents, seed_topic,
        # and graph_id from this file (same structure used by the /prepare API).
        sim_config_payload: dict = {
            "simulation_id": sim_id,
            "platform": config.platform,
            "max_rounds": config.max_rounds,
            "num_agents": config.num_agents,
            "seed_topic": config.seed_topic,
            "graph_id": graph_id,
            "output_dir": output_dir,
            "headless": True,
            # Time config expected by SimulationRunner
            "time_config": {
                "total_simulation_hours": config.max_rounds,  # 1 round ≈ 1 hour
                "minutes_per_round": 60,
            },
        }

        config_path = os.path.join(sim_dir, "simulation_config.json")
        with open(config_path, "w", encoding="utf-8") as fh:
            json.dump(sim_config_payload, fh, indent=2)

        logger.info(f"Simulation config written to {config_path}")
        return sim_dir

    # ------------------------------------------------------------------
    # Step 3: launch simulation
    # ------------------------------------------------------------------

    def _start_simulation(
        self, config: SimConfig, sim_id: str, graph_id: Optional[str]
    ) -> None:
        """Call SimulationRunner.start_simulation() to kick off the subprocess."""
        platform = config.platform if config.platform != "both" else "parallel"
        enable_graph = bool(graph_id)

        logger.info(
            f"Starting simulation: sim_id={sim_id}, platform={platform}, "
            f"max_rounds={config.max_rounds}, graph_memory={enable_graph}"
        )

        SimulationRunner.start_simulation(
            simulation_id=sim_id,
            platform=platform,
            max_rounds=config.max_rounds,
            enable_graph_memory_update=enable_graph,
            graph_id=graph_id,
        )

    # ------------------------------------------------------------------
    # Step 4: poll until done
    # ------------------------------------------------------------------

    def _poll_until_done(self, sim_id: str):
        """
        Poll SimulationRunner.get_run_state() until the runner reaches a
        terminal status (COMPLETED, FAILED, STOPPED) or the timeout expires.

        Returns the final SimulationRunState, or None on timeout.
        """
        terminal = {RunnerStatus.COMPLETED, RunnerStatus.FAILED, RunnerStatus.STOPPED}
        deadline = time.time() + self.timeout

        while time.time() < deadline:
            state = SimulationRunner.get_run_state(sim_id)
            if state is None:
                logger.warning(f"No run state found for {sim_id}, retrying…")
            else:
                logger.debug(
                    f"Poll {sim_id}: status={state.runner_status}, "
                    f"rounds={state.completed_rounds}/{state.total_rounds}"
                )
                if state.runner_status in terminal:
                    return state

            time.sleep(self.poll_interval)

        logger.error(f"Simulation {sim_id} timed out after {self.timeout}s")
        return None

    # ------------------------------------------------------------------
    # Step 5: report generation
    # ------------------------------------------------------------------

    def _generate_report(
        self,
        sim_id: str,
        graph_id: str,
        config: SimConfig,
        sim_dir: str,
    ) -> Optional[str]:
        """
        Run ReportAgent and copy full_report.md to {sim_dir}/report.md.

        Returns the destination path, or None if generation fails.
        """
        from ..services.report_agent import ReportAgent, ReportManager  # local import

        try:
            requirement = (
                f"Analyze the {config.platform} simulation about '{config.seed_topic}'. "
                f"Summarise agent behaviour, emergent patterns, and key outcomes."
            )
            agent = ReportAgent(
                graph_id=graph_id,
                simulation_id=sim_id,
                simulation_requirement=requirement,
            )
            report = agent.generate_report()

            # ReportManager writes full_report.md to uploads/reports/{report_id}/
            src = ReportManager._get_report_markdown_path(report.report_id)
            dst = os.path.join(sim_dir, "report.md")

            if os.path.exists(src):
                shutil.copy2(src, dst)
                logger.info(f"Report copied to {dst}")
                return dst
            else:
                logger.warning(f"full_report.md not found at {src}")
                return None

        except Exception as exc:  # pylint: disable=broad-except
            logger.error(f"Report generation failed for sim_id={sim_id}: {exc}")
            return None

    # ------------------------------------------------------------------
    # Step 6: graph stats
    # ------------------------------------------------------------------

    def _count_graph(self, graph_id: Optional[str]) -> tuple[int, int]:
        """Return (node_count, edge_count) for the given graph_id, or (0, 0)."""
        if not graph_id:
            return 0, 0
        try:
            nodes = kg.get_all_nodes(graph_id)
            edges = kg.get_all_edges(graph_id)
            return len(nodes), len(edges)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(f"Could not count graph nodes/edges: {exc}")
            return 0, 0
