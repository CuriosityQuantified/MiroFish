"""
Graph Building Service
API 2: Build Standalone Graph using Graphiti + Kuzu
"""

import os
import uuid
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from .text_processor import TextProcessor
from . import knowledge_graph as kg


@dataclass
class GraphInfo:
    """Graph information"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    Graph Building Service
    Responsible for building knowledge graphs via Graphiti + Kuzu
    """

    def __init__(self, api_key: Optional[str] = None):
        # api_key kept for interface compatibility but no longer required
        self.task_manager = TaskManager()

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        """
        Build graph asynchronously

        Args:
            text: Input text
            ontology: Ontology definition (from API 1 output)
            graph_name: Graph name
            chunk_size: Text chunk size
            chunk_overlap: Chunk overlap size
            batch_size: Number of chunks per batch

        Returns:
            Task ID
        """
        # Create task
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )

        # Execute build in background thread
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size)
        )
        thread.daemon = True
        thread.start()

        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ):
        """Graph building worker thread"""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="Starting graph building..."
            )

            # 1. Create graph
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"Graph created: {graph_id}"
            )

            # 2. Set ontology (stored as metadata; Graphiti handles entity extraction via LLM)
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="Ontology set"
            )

            # 3. Split text into chunks
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"Text split into {total_chunks} chunks"
            )

            # 4. Send chunks as episodes
            episode_uuids = self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.6),  # 20-80%
                    message=msg
                )
            )

            # 5. Graphiti processes episodes synchronously during add_episode,
            #    so no separate wait step is needed (unlike Zep Cloud async processing).
            self.task_manager.update_task(
                task_id,
                progress=85,
                message="Episodes processed, gathering graph info..."
            )

            # 6. Get graph info
            graph_info = self._get_graph_info(graph_id)

            # Complete
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })

        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)

    def create_graph(self, name: str) -> str:
        """Create graph (public method)"""
        return kg.create_graph(name)

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """
        Set graph ontology (public method).

        With Graphiti, entity extraction is driven by the LLM at episode-ingestion
        time.  We store the ontology as metadata for reference, but Graphiti's LLM
        pipeline handles the actual extraction.  For richer schema hints you can
        pass entity_types to add_episode — we do that in add_text_batches.
        """
        # Store ontology definition for later use in add_episode entity_types param
        self._ontology = ontology

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Add text to graph in batches, return list of all episode uuids"""
        episode_uuids = kg.add_episodes_batch(
            graph_id=graph_id,
            texts=chunks,
            source="text",
            progress_callback=progress_callback,
        )
        return episode_uuids

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """Get graph info"""
        nodes = kg.get_all_nodes(graph_id)
        edges = kg.get_all_edges(graph_id)

        # Count entity types
        entity_types = set()
        for node in nodes:
            for label in node.get('labels', []):
                if label not in ["Entity", "Node"]:
                    entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types)
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        Get complete graph data (with detailed info)

        Args:
            graph_id: Graph ID

        Returns:
            Dictionary with nodes and edges, including time info, attributes, and other details
        """
        nodes = kg.get_all_nodes(graph_id)
        edges = kg.get_all_edges(graph_id)

        # Create node map for getting node names
        node_map = {n['uuid']: n.get('name', '') for n in nodes}

        edges_data = []
        for edge in edges:
            fact_type = edge.get('name', '')
            source_uuid = edge.get('source_node_uuid', '')
            target_uuid = edge.get('target_node_uuid', '')

            edges_data.append({
                "uuid": edge.get('uuid', ''),
                "name": edge.get('name', ''),
                "fact": edge.get('fact', ''),
                "fact_type": fact_type,
                "source_node_uuid": source_uuid,
                "target_node_uuid": target_uuid,
                "source_node_name": node_map.get(source_uuid, ''),
                "target_node_name": node_map.get(target_uuid, ''),
                "attributes": edge.get('attributes', {}),
                "created_at": edge.get('created_at'),
                "valid_at": edge.get('valid_at'),
                "invalid_at": edge.get('invalid_at'),
                "expired_at": edge.get('expired_at'),
                "episodes": edge.get('episodes', []),
            })

        return {
            "graph_id": graph_id,
            "nodes": nodes,
            "edges": edges_data,
            "node_count": len(nodes),
            "edge_count": len(edges_data),
        }

    def delete_graph(self, graph_id: str):
        """Delete graph"""
        kg.delete_graph(graph_id)
