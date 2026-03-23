"""
Task 5d — Graphiti + Kuzu integration smoke test
Uses a temp dir for the DB — no API calls (mocks Anthropic LLM + embedder).
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(autouse=True)
def reset_graphiti_singleton():
    """Reset the module-level singleton between tests."""
    import app.services.knowledge_graph as kg_mod
    kg_mod._graphiti_instance = None
    yield
    kg_mod._graphiti_instance = None


@pytest.fixture
def mock_graphiti(tmp_path):
    """
    Patch get_graphiti() to return a mock Graphiti instance backed by a
    temp Kuzu DB path. Avoids real LLM / embedding calls.
    """
    mock_g = MagicMock()

    # search() returns empty list by default
    mock_g.search = AsyncMock(return_value=[])

    # add_episode returns a mock result with an episode UUID
    mock_ep = MagicMock()
    mock_ep.episode.uuid = "test-uuid-001"
    mock_g.add_episode = AsyncMock(return_value=mock_ep)

    # build_indices_and_constraints is a no-op
    mock_g.build_indices_and_constraints = AsyncMock(return_value=None)

    # Driver with node/edge ops
    mock_driver = MagicMock()
    mock_driver.entity_node_ops.get_by_group_ids = AsyncMock(return_value=[])
    mock_driver.entity_edge_ops.get_by_group_ids = AsyncMock(return_value=[])
    mock_driver.entity_node_ops.get_by_uuid = AsyncMock(return_value=None)
    mock_driver.entity_edge_ops.get_by_node_uuid = AsyncMock(return_value=[])
    mock_g.driver = mock_driver

    with patch('app.services.knowledge_graph.get_graphiti', return_value=mock_g):
        yield mock_g


class TestCreateAndDeleteGraph:
    def test_create_graph_returns_id(self, mock_graphiti):
        from app.services.knowledge_graph import create_graph
        gid = create_graph("test graph")
        assert gid.startswith("mirofish_")
        assert len(gid) > 10

    def test_delete_graph_does_not_raise(self, mock_graphiti):
        from app.services.knowledge_graph import create_graph, delete_graph
        gid = create_graph("to delete")
        # Should not raise even if driver ops are mocked
        delete_graph(gid)


class TestAddEpisode:
    def test_add_episode_returns_uuid(self, mock_graphiti):
        from app.services.knowledge_graph import add_episode
        ep_uuid = add_episode("g_test", "Some seed text about AI policy")
        assert ep_uuid == "test-uuid-001"
        mock_graphiti.add_episode.assert_called_once()


class TestGetNodes:
    def test_get_all_nodes_empty(self, mock_graphiti):
        from app.services.knowledge_graph import get_all_nodes
        nodes = get_all_nodes("g_test")
        assert nodes == []

    def test_get_all_nodes_with_data(self, mock_graphiti):
        mock_node = MagicMock()
        mock_node.uuid = "n1"
        mock_node.name = "EU AI Act"
        mock_node.labels = ["Policy", "Entity"]
        mock_node.summary = "Landmark regulation"
        mock_node.attributes = {}
        mock_node.created_at = None
        mock_graphiti.driver.entity_node_ops.get_by_group_ids = AsyncMock(
            return_value=[mock_node]
        )
        from app.services.knowledge_graph import get_all_nodes
        nodes = get_all_nodes("g_test")
        assert len(nodes) == 1
        assert nodes[0]["name"] == "EU AI Act"
        assert "Policy" in nodes[0]["labels"]


class TestSearchGraph:
    def test_search_returns_empty_list(self, mock_graphiti):
        from app.services.knowledge_graph import search_graph
        results = search_graph("g_test", "AI regulation")
        assert results == []

    def test_search_returns_edges(self, mock_graphiti):
        mock_edge = MagicMock()
        mock_edge.uuid = "e1"
        mock_edge.name = "INFLUENCED"
        mock_edge.fact = "The EU AI Act influenced public opinion"
        mock_edge.source_node_uuid = "n1"
        mock_edge.target_node_uuid = "n2"
        mock_edge.valid_at = None
        mock_edge.invalid_at = None
        mock_edge.expired_at = None
        mock_graphiti.search = AsyncMock(return_value=[mock_edge])

        from app.services.knowledge_graph import search_graph
        results = search_graph("g_test", "EU AI Act")
        assert len(results) == 1
        assert "INFLUENCED" in results[0]["name"]
        assert "EU AI Act" in results[0]["fact"]
