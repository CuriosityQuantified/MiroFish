"""
Simulation Configuration Models (Pydantic v2)

Defines the config schema for headless simulation runs and the
structured result returned after completion.

JSON schema exported to backend/mirofish-config.schema.json for
IDE support and MCP validation.
"""

from pydantic import BaseModel, Field
from typing import Literal


class SimConfig(BaseModel):
    """Configuration for a headless simulation run."""

    graph_id: str | None = None
    documents: list[str] = Field(default_factory=list)
    platform: Literal["twitter", "reddit", "both"] = "both"
    max_rounds: int = 10
    num_agents: int = 10
    seed_topic: str = ""
    output_dir: str = "data/sim_output"
    report: bool = True


class SimResult(BaseModel):
    """Structured result of a headless simulation run."""

    graph_id: str
    sim_dir: str
    report_path: str | None = None
    node_count: int = 0
    edge_count: int = 0
    agent_count: int = 0
    rounds_completed: int = 0
    status: Literal["completed", "failed", "partial"] = "completed"
    error: str | None = None


def export_json_schema(path: str | None = None) -> str:
    """Export the SimConfig JSON schema to a file and return the JSON string."""
    import json
    import os

    schema = SimConfig.model_json_schema()
    schema_json = json.dumps(schema, indent=2)

    if path is None:
        path = os.path.join(
            os.path.dirname(__file__), "../../mirofish-config.schema.json"
        )

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(schema_json + "\n")

    return schema_json


if __name__ == "__main__":
    export_json_schema()
    print("Schema exported to backend/mirofish-config.schema.json")
