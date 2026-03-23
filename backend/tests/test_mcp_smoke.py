"""
Task 5a — MCP server smoke tests
Verify tools are importable, callable, and return correct shapes without live API calls.
"""
import sys, os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestMCPImport:
    def test_mcp_module_imports(self):
        """mirofish_mcp.py should import without errors (no network calls at import time)."""
        # Patch heavy dependencies before import
        with patch.dict('sys.modules', {
            'graphiti_core': MagicMock(),
            'graphiti_core.driver.kuzu_driver': MagicMock(),
            'graphiti_core.llm_client.anthropic_client': MagicMock(),
            'graphiti_core.llm_client.config': MagicMock(),
            'graphiti_core.embedder.openai': MagicMock(),
        }):
            import importlib
            import mirofish_mcp  # noqa: F401


class TestCreateSimulation:
    def test_returns_valid_simconfig(self):
        from app.models.sim_config import SimConfig
        with patch('mirofish_mcp.SimConfig', SimConfig):
            from mirofish_mcp import create_simulation
            result = create_simulation(
                seed_topic="AI regulation",
                platform="twitter",
                max_rounds=5,
                num_agents=10,
            )
        assert result["seed_topic"] == "AI regulation"
        assert result["platform"] == "twitter"
        assert result["max_rounds"] == 5

    def test_invalid_platform_propagates(self):
        from pydantic import ValidationError
        from app.models.sim_config import SimConfig
        with patch('mirofish_mcp.SimConfig', SimConfig):
            from mirofish_mcp import create_simulation
            with pytest.raises(ValidationError):
                create_simulation(seed_topic="x", platform="snapchat")


class TestRunSimulation:
    def test_bad_config_returns_failed(self):
        from mirofish_mcp import run_simulation
        result = run_simulation({"seed_topic": "x", "platform": "invalid_platform"})
        assert result["status"] == "failed"
        assert result["error"]

    def test_good_config_calls_headless_runner(self):
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "graph_id": "g1", "sim_dir": "/tmp/s", "report_path": None,
            "status": "completed", "error": None, "node_count": 5,
            "edge_count": 10, "agent_count": 10, "rounds_completed": 5,
        }
        with patch('mirofish_mcp.HeadlessRunner') as MockRunner:
            MockRunner.return_value.run.return_value = mock_result
            from mirofish_mcp import run_simulation
            result = run_simulation({
                "seed_topic": "test",
                "platform": "twitter",
                "max_rounds": 5,
                "num_agents": 10,
            })
        assert result["status"] == "completed"
        assert "report_text" in result


class TestGetSimulationStatus:
    def test_not_found(self):
        with patch('mirofish_mcp.SimulationRunner') as MockRunner:
            MockRunner.get_run_state.return_value = None
            from mirofish_mcp import get_simulation_status
            result = get_simulation_status("/tmp/nonexistent_sim")
        assert result["runner_status"] == "not_found"

    def test_running_state(self):
        mock_state = MagicMock()
        mock_state.runner_status.value = "running"
        mock_state.current_round = 3
        mock_state.total_rounds = 10
        mock_state.twitter_actions_count = 42
        mock_state.reddit_actions_count = 18
        mock_state.started_at = "2026-03-22T10:00:00"
        mock_state.completed_at = None
        mock_state.error = None

        with patch('mirofish_mcp.SimulationRunner') as MockRunner:
            MockRunner.get_run_state.return_value = mock_state
            from mirofish_mcp import get_simulation_status
            result = get_simulation_status("/tmp/sim/running_sim")
        assert result["runner_status"] == "running"
        assert result["current_round"] == 3


class TestSearchGraph:
    def test_empty_graph_id(self):
        from mirofish_mcp import search_graph
        result = search_graph(graph_id="", query="test")
        assert len(result) == 1
        assert "error" in result[0]

    def test_returns_results(self):
        mock_facts = [
            {"uuid": "e1", "fact": "Agent A influenced Agent B", "name": "INFLUENCED"},
        ]
        with patch('mirofish_mcp.kg') as mock_kg:
            mock_kg.search_graph.return_value = mock_facts
            from mirofish_mcp import search_graph
            result = search_graph(graph_id="g123", query="influence")
        assert len(result) == 1
        assert result[0]["fact"] == "Agent A influenced Agent B"


class TestGetGraphStats:
    def test_empty_graph_id(self):
        from mirofish_mcp import get_graph_stats
        result = get_graph_stats(graph_id="")
        assert "error" in result
        assert result["node_count"] == 0

    def test_returns_stats(self):
        mock_nodes = [{"uuid": "n1", "labels": ["Person"]}, {"uuid": "n2", "labels": ["Organization"]}]
        mock_edges = [{"uuid": "e1"}]
        with patch('mirofish_mcp.kg') as mock_kg:
            mock_kg.get_all_nodes.return_value = mock_nodes
            mock_kg.get_all_edges.return_value = mock_edges
            from mirofish_mcp import get_graph_stats
            result = get_graph_stats(graph_id="g123")
        assert result["node_count"] == 2
        assert result["edge_count"] == 1
        assert "Person" in result["entity_types"]


import pytest  # noqa: E402 (needs to be after test classes for raises usage)
