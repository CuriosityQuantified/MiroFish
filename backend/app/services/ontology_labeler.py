"""
Ontology Labeler — Post-process graph nodes to assign entity type labels.

Problem: Graphiti extracts entities but stores them all with labels=['Entity'].
The simulation entity filter requires custom labels (e.g. 'AIResearcher', 'AILab')
to identify simulatable agents. This service bridges that gap.

Approach:
1. Read all nodes from the graph (names + summaries)
2. Read the project ontology (entity_types from ontology generation)
3. Use LLM (batch) to classify each node against the ontology
4. Persist labels in a sidecar file: data/kuzu_graph/.labels/{graph_id}.json
5. Patch ZepEntityReader.get_all_nodes() to merge sidecar labels at read time

The sidecar approach avoids modifying the Kuzu DB schema (which is managed by
graphiti-core) and is idempotent — re-running updates labels in place.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger("mirofish.ontology_labeler")

# Where label sidecars are stored — sibling to kuzu_graph file, not inside it
_LABELS_DIR = os.path.join(
    os.path.dirname(__file__), "../../../data/graph_labels"
)


def _labels_path(graph_id: str) -> str:
    return os.path.join(_LABELS_DIR, f"{graph_id}.json")


def load_labels(graph_id: str) -> Dict[str, List[str]]:
    """
    Load persisted labels for a graph.  Returns {node_uuid: [label, ...]} dict.
    Returns empty dict if no sidecar exists yet.
    """
    path = _labels_path(graph_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning(f"Could not load labels for {graph_id}: {exc}")
        return {}


def save_labels(graph_id: str, labels: Dict[str, List[str]]) -> None:
    """Persist labels sidecar."""
    os.makedirs(_LABELS_DIR, exist_ok=True)
    path = _labels_path(graph_id)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(labels, fh, ensure_ascii=False, indent=2)
    logger.info(f"Saved labels for {graph_id}: {len(labels)} nodes labelled")


def merge_labels_into_nodes(
    nodes: List[Dict[str, Any]], graph_id: str
) -> List[Dict[str, Any]]:
    """
    Merge sidecar labels into a list of raw node dicts (in-place update).
    Called by ZepEntityReader.get_all_nodes() transparently.
    """
    sidecar = load_labels(graph_id)
    if not sidecar:
        return nodes
    for node in nodes:
        extra = sidecar.get(node.get("uuid", ""), [])
        if extra:
            existing = node.get("labels", [])
            merged = list(dict.fromkeys(existing + extra))  # dedup, preserve order
            node["labels"] = merged
    return nodes


# ---------------------------------------------------------------------------
# Core labelling logic
# ---------------------------------------------------------------------------

_BATCH_SIZE = 15  # nodes per LLM call


def label_graph_nodes(
    graph_id: str,
    entity_types: List[Dict[str, Any]],
    nodes: Optional[List[Dict[str, Any]]] = None,
    force: bool = False,
) -> Dict[str, List[str]]:
    """
    Classify each node in the graph against the provided ontology entity types.

    Args:
        graph_id: Graph to label.
        entity_types: List of entity type dicts from the ontology generator,
                      e.g. [{"name": "AIResearcher", "description": "..."}, ...]
        nodes: Pre-fetched node list (optional — fetched from graph if omitted).
        force: Re-label even if a sidecar already exists.

    Returns:
        {node_uuid: [entity_type_name, "Entity"]} mapping (also persisted to disk).
    """
    existing = load_labels(graph_id)
    if existing and not force:
        logger.info(
            f"Sidecar already exists for {graph_id} ({len(existing)} nodes). "
            "Pass force=True to re-label."
        )
        return existing

    if not entity_types:
        logger.warning("No entity types provided — skipping labelling")
        return {}

    # Fetch nodes from graph if not provided
    if nodes is None:
        from . import knowledge_graph as kg
        nodes = kg.get_all_nodes(graph_id)

    if not nodes:
        logger.warning(f"No nodes found in graph {graph_id}")
        return {}

    logger.info(
        f"Labelling {len(nodes)} nodes for graph {graph_id} "
        f"using {len(entity_types)} entity types"
    )

    # Build the type reference string once
    types_desc = "\n".join(
        f'- "{et["name"]}": {et.get("description", "")}'
        for et in entity_types
    )

    llm = LLMClient()
    labels: Dict[str, List[str]] = {}

    # Process in batches
    for batch_start in range(0, len(nodes), _BATCH_SIZE):
        batch = nodes[batch_start : batch_start + _BATCH_SIZE]
        batch_labels = _classify_batch(llm, batch, entity_types, types_desc)
        labels.update(batch_labels)
        logger.info(
            f"  Labelled batch {batch_start // _BATCH_SIZE + 1}"
            f"/{(len(nodes) - 1) // _BATCH_SIZE + 1}"
        )

    save_labels(graph_id, labels)
    return labels


def _classify_batch(
    llm: LLMClient,
    nodes: List[Dict[str, Any]],
    entity_types: List[Dict[str, Any]],
    types_desc: str,
) -> Dict[str, List[str]]:
    """
    Ask the LLM to classify a batch of nodes and return {uuid: [label]} mapping.
    Falls back to heuristic matching if LLM call fails.
    """
    type_names = [et["name"] for et in entity_types]
    # Include "Other" as an explicit option so the model has a clean escape hatch
    all_types = type_names + ["Other"]

    node_lines = "\n".join(
        f'{i+1}. uuid="{n["uuid"]}" name="{n.get("name","")}" '
        f'summary="{(n.get("summary") or "")[:120]}"'
        for i, n in enumerate(nodes)
    )

    system = (
        "You are an entity classifier for a social simulation engine. "
        "You will be given a list of entities extracted from a document and a set of "
        "entity types. Classify each entity to exactly one type. "
        "Respond ONLY with valid JSON: a list of objects, one per entity, in the same order. "
        'Each object: {"uuid": "<uuid>", "type": "<TypeName>"}. '
        f"Valid types: {all_types}. "
        "Use 'Other' only if no type fits at all — prefer a real type."
    )

    user = (
        f"Entity types available:\n{types_desc}\n\n"
        f"Entities to classify:\n{node_lines}\n\n"
        f"Return a JSON array of {len(nodes)} objects."
    )

    try:
        result = llm.chat_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        # Result may be a list directly or wrapped in a key
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict):
            # Find the first list value
            items = next(
                (v for v in result.values() if isinstance(v, list)), []
            )
        else:
            items = []

        labels: Dict[str, List[str]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            uuid = item.get("uuid", "")
            etype = item.get("type", "Other")
            if not uuid:
                continue
            if etype and etype != "Other":
                labels[uuid] = [etype, "Entity"]
            else:
                labels[uuid] = ["Entity"]
        return labels

    except Exception as exc:
        logger.warning(f"LLM classification failed ({exc}), using heuristic fallback")
        return _heuristic_classify(nodes, entity_types)


def _heuristic_classify(
    nodes: List[Dict[str, Any]],
    entity_types: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """
    Simple keyword-based fallback when the LLM call fails.
    Matches entity type names/descriptions against node names and summaries.
    """
    labels: Dict[str, List[str]] = {}
    for node in nodes:
        text = (
            (node.get("name") or "") + " " + (node.get("summary") or "")
        ).lower()
        best_type = None
        for et in entity_types:
            name_lc = et["name"].lower()
            desc_lc = (et.get("description") or "").lower()
            # Simple word overlap score
            keywords = set(name_lc.split() + desc_lc.split()) - {"a", "an", "the", "of", "in", "for"}
            score = sum(1 for kw in keywords if kw in text)
            if score > 0 and (best_type is None or score > best_type[1]):
                best_type = (et["name"], score)
        if best_type:
            labels[node["uuid"]] = [best_type[0], "Entity"]
        else:
            labels[node["uuid"]] = ["Entity"]
    return labels
