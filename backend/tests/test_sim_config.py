"""
Task 5b — SimConfig pydantic validation tests
"""
import json
import pytest
from pydantic import ValidationError

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.models.sim_config import SimConfig, SimResult


class TestSimConfig:
    def test_defaults(self):
        config = SimConfig(seed_topic="test")
        assert config.platform == "both"
        assert config.max_rounds == 10
        assert config.num_agents == 10
        assert config.report is True
        assert config.documents == []
        assert config.graph_id is None

    def test_platform_values(self):
        for p in ("twitter", "reddit", "both"):
            c = SimConfig(seed_topic="x", platform=p)
            assert c.platform == p

    def test_invalid_platform(self):
        with pytest.raises(ValidationError):
            SimConfig(seed_topic="x", platform="facebook")

    def test_graph_id_optional(self):
        c = SimConfig(seed_topic="x", graph_id="mirofish_abc123")
        assert c.graph_id == "mirofish_abc123"

    def test_documents_list(self):
        c = SimConfig(seed_topic="x", documents=["/tmp/a.pdf", "/tmp/b.md"])
        assert len(c.documents) == 2

    def test_serialisation_roundtrip(self):
        c = SimConfig(seed_topic="AI regulation", platform="twitter", max_rounds=5)
        d = c.model_dump()
        c2 = SimConfig(**d)
        assert c == c2

    def test_json_schema_export(self):
        from app.models.sim_config import export_json_schema
        schema_json = export_json_schema(path=None)
        schema = json.loads(schema_json)
        assert schema["title"] == "SimConfig"
        assert "seed_topic" in schema["properties"]
        assert "platform" in schema["properties"]


class TestSimResult:
    def test_completed(self):
        r = SimResult(graph_id="g1", sim_dir="/tmp/sim", status="completed")
        assert r.status == "completed"
        assert r.error is None

    def test_failed_with_error(self):
        r = SimResult(graph_id="", sim_dir="", status="failed", error="timeout")
        assert r.status == "failed"
        assert r.error == "timeout"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            SimResult(graph_id="", sim_dir="", status="unknown")
