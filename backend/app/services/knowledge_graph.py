"""
Knowledge Graph Service — Graphiti + Kuzu backend

Replaces the previous Zep Cloud dependency with a fully embedded, self-hosted
graph store.  The public surface mirrors what the rest of MiroFish expects
(graph creation, episode ingestion, node/edge listing, search, memory updates)
while delegating to graphiti-core with a Kuzu graph driver underneath.

Key concepts mapping (Zep -> Graphiti):
  - graph_id         -> group_id   (partition key)
  - episode          -> episode    (text chunk ingested into the graph)
  - node / entity    -> EntityNode
  - edge / fact      -> EntityEdge (with temporal validity fields)
  - semantic search  -> Graphiti.search() (hybrid vector + text)
"""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.knowledge_graph')

# ---------------------------------------------------------------------------
# Lazy singleton — the Graphiti instance is heavy (holds the Kuzu DB open),
# so we create it once and share across the process.
# ---------------------------------------------------------------------------

_graphiti_instance = None
_graphiti_lock = threading.Lock()


def _get_db_path() -> str:
    """Return the on-disk path for the Kuzu database."""
    return getattr(Config, 'KUZU_DB_PATH', None) or os.path.join(
        os.path.dirname(__file__), '../../../data/kuzu_graph'
    )


def _run_async(coro):
    """Run an async coroutine from synchronous code, safely."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # We're inside an existing event loop (e.g. Jupyter, nested async).
        # Use a new thread to avoid "cannot call run_until_complete" errors.
        result = [None]
        exc = [None]

        def _target():
            new_loop = asyncio.new_event_loop()
            try:
                result[0] = new_loop.run_until_complete(coro)
            except Exception as e:
                exc[0] = e
            finally:
                new_loop.close()

        t = threading.Thread(target=_target)
        t.start()
        t.join()
        if exc[0] is not None:
            raise exc[0]
        return result[0]
    else:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _define_patched_kuzu_driver():
    """Define and return PatchedKuzuDriver (deferred to avoid top-level import)."""
    from graphiti_core.driver.kuzu_driver import KuzuDriver

    class PatchedKuzuDriver(KuzuDriver):
        """
        KuzuDriver subclass fixing graphiti-core 0.28.2 Kuzu driver bugs.

        Remove when graphiti-core > 0.28.2 ships fixes for:
        - KuzuDriver.__init__ not setting _database (used by Graphiti.add_episode)
        - build_indices_and_constraints() being a no-op (FTS indices never created)
        """

        def __init__(self, db: str = ':memory:', max_concurrent_queries: int = 1):
            super().__init__(db=db, max_concurrent_queries=max_concurrent_queries)
            # Bug #1: Base GraphDriver declares _database but KuzuDriver never sets it.
            # Graphiti.add_episode() reads driver._database for group_id comparison.
            if not hasattr(self, '_database'):
                self._database = ''

        async def build_indices_and_constraints(self, delete_existing: bool = False):
            """Create FTS indices that KuzuDriver's no-op method skips."""
            await super().build_indices_and_constraints(delete_existing=delete_existing)
            import kuzu as _kuzu
            _conn = _kuzu.Connection(self.db)
            for stmt in [
                "CALL CREATE_FTS_INDEX('Episodic', 'episode_content', ['content', 'source', 'source_description']);",
                "CALL CREATE_FTS_INDEX('Entity', 'node_name_and_summary', ['name', 'summary']);",
                "CALL CREATE_FTS_INDEX('Community', 'community_name', ['name']);",
                "CALL CREATE_FTS_INDEX('RelatesToNode_', 'edge_name_and_fact', ['name', 'fact']);",
            ]:
                try:
                    _conn.execute(stmt)
                except RuntimeError as e:
                    if 'already exists' not in str(e):
                        logger.warning(f"FTS index creation warning: {e}")
            _conn.close()

    # Version guard: warn if graphiti-core has been upgraded past the patched version.
    import graphiti_core as _gc
    if hasattr(_gc, '__version__') and _gc.__version__ > '0.28.2':
        logger.warning(
            f"graphiti-core {_gc.__version__} detected (patches target 0.28.2). "
            "Test PatchedKuzuDriver — upstream may have fixed these issues."
        )

    return PatchedKuzuDriver


def get_graphiti():
    """Return the process-wide Graphiti instance, creating it on first call."""
    global _graphiti_instance
    if _graphiti_instance is not None:
        return _graphiti_instance

    with _graphiti_lock:
        if _graphiti_instance is not None:
            return _graphiti_instance

        from graphiti_core import Graphiti
        from graphiti_core.llm_client.anthropic_client import AnthropicClient
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

        PatchedKuzuDriver = _define_patched_kuzu_driver()

        db_path = _get_db_path()
        # Ensure parent directory exists (Kuzu creates the DB file/dir itself)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # If the path is an empty directory (e.g. from mkdir), remove it so Kuzu can create its DB file
        if os.path.isdir(db_path) and not os.listdir(db_path):
            os.rmdir(db_path)
        logger.info(f"Initializing Kuzu graph database at {db_path}")

        kuzu_driver = PatchedKuzuDriver(db=db_path)

        # --- LLM client (Anthropic via proxy or direct) ---
        anthropic_api_key = Config.ANTHROPIC_API_KEY or os.getenv('ANTHROPIC_API_KEY', '')
        anthropic_base_url = Config.ANTHROPIC_BASE_URL or os.getenv('ANTHROPIC_BASE_URL')
        llm_model = Config.LLM_ORCHESTRATION_MODEL or 'claude-haiku-4-5-20251001'

        # The native Anthropic SDK adds /v1 itself, so strip trailing /v1 from
        # proxy URLs to avoid double-pathing (e.g. http://host:8317/v1/v1/messages).
        # The .env keeps /v1 because other code paths use the OpenAI SDK which needs it.
        anthropic_sdk_base_url = anthropic_base_url
        if anthropic_sdk_base_url and anthropic_sdk_base_url.rstrip('/').endswith('/v1'):
            anthropic_sdk_base_url = anthropic_sdk_base_url.rstrip('/')[:-3].rstrip('/')

        llm_config = LLMConfig(
            api_key=anthropic_api_key,
            model=llm_model,
            base_url=anthropic_sdk_base_url if anthropic_sdk_base_url else None,
        )

        from anthropic import AsyncAnthropic
        anthropic_client_kwargs: Dict[str, Any] = {'api_key': anthropic_api_key, 'max_retries': 2}
        if anthropic_sdk_base_url:
            anthropic_client_kwargs['base_url'] = anthropic_sdk_base_url
        async_anthropic = AsyncAnthropic(**anthropic_client_kwargs)

        llm_client = AnthropicClient(config=llm_config, client=async_anthropic)

        # --- Embedder (OpenAI-compatible endpoint required for vector search) ---
        # Graphiti needs an embedding model. Use OpenAI-compatible endpoint if available,
        # otherwise fall back to a no-op embedder.
        embedder = None
        openai_api_key = os.getenv('OPENAI_API_KEY') or os.getenv('LLM_API_KEY')
        openai_base_url = os.getenv('OPENAI_BASE_URL') or os.getenv('LLM_BASE_URL')

        if openai_api_key:
            embedder_config = OpenAIEmbedderConfig(
                api_key=openai_api_key,
                base_url=openai_base_url if openai_base_url else None,
            )
            embedder = OpenAIEmbedder(embedder_config)
            logger.info("Using OpenAI-compatible embedder for vector search")
        else:
            # Create a no-op embedder that returns zero vectors.
            # Graphiti requires an embedder instance — if we pass None it creates
            # a default OpenAIEmbedder which fails without OPENAI_API_KEY.
            from graphiti_core.embedder.client import EmbedderClient

            class NoOpEmbedder(EmbedderClient):
                """Embedder stub that returns zero vectors when no embedding API is available."""
                async def create(self, input_data) -> list[float]:
                    # create() must return a single flat vector (list[float])
                    return [0.0] * 1536

                async def create_batch(self, input_data_list) -> list[list[float]]:
                    return [[0.0] * 1536 for _ in input_data_list]

            embedder = NoOpEmbedder()
            logger.warning(
                "No OPENAI_API_KEY set — using no-op embedder. "
                "Graph will work but semantic search quality will be reduced."
            )

        # Cross-encoder (reranker) — provide a no-op if no OpenAI key
        cross_encoder = None
        if not openai_api_key:
            from graphiti_core.cross_encoder.client import CrossEncoderClient

            class NoOpCrossEncoder(CrossEncoderClient):
                """Cross-encoder stub — returns original order with neutral scores."""
                async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
                    return [(p, 1.0 / (i + 1)) for i, p in enumerate(passages)]

            cross_encoder = NoOpCrossEncoder()

        _graphiti_instance = Graphiti(
            graph_driver=kuzu_driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
            store_raw_episode_content=True,
        )

        # Build indices (idempotent) — PatchedKuzuDriver.build_indices_and_constraints
        # now creates the FTS indices that the base KuzuDriver skips.
        _run_async(_graphiti_instance.build_indices_and_constraints())

        logger.info("Graphiti + Kuzu knowledge graph initialized successfully")
        return _graphiti_instance


def close_graphiti():
    """Shut down the Graphiti instance (call at app teardown)."""
    global _graphiti_instance
    if _graphiti_instance is not None:
        try:
            _run_async(_graphiti_instance.close())
        except Exception as e:
            logger.warning(f"Error closing Graphiti: {e}")
        _graphiti_instance = None
        logger.info("Graphiti + Kuzu knowledge graph closed")


# ---------------------------------------------------------------------------
# Graph CRUD helpers  (create / delete / info)
# ---------------------------------------------------------------------------

def create_graph(name: str) -> str:
    """Create a new graph partition and return its group_id."""
    graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"
    logger.info(f"Created graph group_id={graph_id} name={name}")
    # Graphiti doesn't require explicit graph creation — group_id is used
    # as a partition key on episodes/nodes/edges. We just return the id.
    return graph_id


def delete_graph(graph_id: str):
    """Delete all data associated with *graph_id* (group_id)."""
    g = get_graphiti()
    driver = g.driver if hasattr(g, 'driver') else g._driver if hasattr(g, '_driver') else None
    if driver is None:
        # Try accessing the internal reference
        for attr in ('driver', '_driver', 'graph_driver', '_graph_driver'):
            driver = getattr(g, attr, None)
            if driver is not None:
                break

    if driver is not None:
        try:
            async def _delete():
                await driver.entity_node_ops.delete_by_group_id(driver, graph_id)
            _run_async(_delete())
            logger.info(f"Deleted graph group_id={graph_id}")
        except Exception as e:
            logger.warning(f"Partial delete for graph {graph_id}: {e}")
    else:
        logger.warning("Cannot access graph driver for deletion — skipping")


# ---------------------------------------------------------------------------
# Episode ingestion
# ---------------------------------------------------------------------------

def add_episode(
    graph_id: str,
    text: str,
    source: str = "text",
    name: str = "",
    reference_time: Optional[datetime] = None,
) -> str:
    """
    Add an episode (text chunk) to the graph.

    Returns the episode UUID.
    """
    from graphiti_core.nodes import EpisodeType

    g = get_graphiti()
    episode_type = {
        'text': EpisodeType.text,
        'json': EpisodeType.json,
        'message': EpisodeType.message,
    }.get(source, EpisodeType.text)

    ref_time = reference_time or datetime.now(timezone.utc)
    episode_name = name or f"episode_{uuid.uuid4().hex[:8]}"

    result = _run_async(
        g.add_episode(
            name=episode_name,
            episode_body=text,
            source_description=f"MiroFish ingest ({graph_id})",
            reference_time=ref_time,
            source=episode_type,
            group_id=graph_id,
        )
    )

    episode_uuid = result.episode.uuid if result and result.episode else ""
    logger.debug(f"Added episode to graph {graph_id}: {episode_uuid}")
    return episode_uuid


def add_episodes_batch(
    graph_id: str,
    texts: List[str],
    source: str = "text",
    progress_callback=None,
) -> List[str]:
    """
    Add multiple text chunks as episodes.  Returns list of episode UUIDs.
    """
    episode_uuids: List[str] = []
    total = len(texts)

    for i, text in enumerate(texts):
        try:
            ep_uuid = add_episode(graph_id, text, source=source, name=f"chunk_{i}")
            episode_uuids.append(ep_uuid)
        except Exception as e:
            logger.warning(f"Failed to add episode chunk {i}: {e}")
            episode_uuids.append("")

        if progress_callback:
            progress_callback(
                f"Processed chunk {i + 1}/{total}",
                (i + 1) / total,
            )

    return episode_uuids


# ---------------------------------------------------------------------------
# Node / Edge retrieval
# ---------------------------------------------------------------------------

def get_all_nodes(graph_id: str) -> List[Dict[str, Any]]:
    """Return all entity nodes for *graph_id* as plain dicts."""
    g = get_graphiti()
    driver = _get_driver(g)

    async def _fetch():
        # The KuzuDriver itself implements QueryExecutor
        nodes = await driver.entity_node_ops.get_by_group_ids(driver, [graph_id])
        return nodes

    nodes = _run_async(_fetch())

    result = []
    for n in nodes:
        result.append({
            'uuid': n.uuid,
            'name': n.name,
            'labels': n.labels if hasattr(n, 'labels') else [],
            'summary': n.summary if hasattr(n, 'summary') else '',
            'attributes': n.attributes if hasattr(n, 'attributes') else {},
            'created_at': str(n.created_at) if hasattr(n, 'created_at') and n.created_at else None,
        })

    return result


def get_all_edges(graph_id: str) -> List[Dict[str, Any]]:
    """Return all entity edges for *graph_id* as plain dicts."""
    g = get_graphiti()
    driver = _get_driver(g)

    async def _fetch():
        edges = await driver.entity_edge_ops.get_by_group_ids(driver, [graph_id])
        return edges

    edges = _run_async(_fetch())

    result = []
    for e in edges:
        result.append({
            'uuid': e.uuid,
            'name': e.name,
            'fact': e.fact if hasattr(e, 'fact') else '',
            'source_node_uuid': e.source_node_uuid,
            'target_node_uuid': e.target_node_uuid,
            'attributes': e.attributes if hasattr(e, 'attributes') else {},
            'created_at': str(e.created_at) if hasattr(e, 'created_at') and e.created_at else None,
            'valid_at': str(e.valid_at) if hasattr(e, 'valid_at') and e.valid_at else None,
            'invalid_at': str(e.invalid_at) if hasattr(e, 'invalid_at') and e.invalid_at else None,
            'expired_at': str(e.expired_at) if hasattr(e, 'expired_at') and e.expired_at else None,
            'episodes': e.episodes if hasattr(e, 'episodes') else [],
        })

    return result


def get_node_by_uuid(node_uuid: str) -> Optional[Dict[str, Any]]:
    """Return a single entity node by UUID."""
    g = get_graphiti()
    driver = _get_driver(g)

    async def _fetch():
        return await driver.entity_node_ops.get_by_uuid(driver, node_uuid)

    try:
        n = _run_async(_fetch())
        return {
            'uuid': n.uuid,
            'name': n.name,
            'labels': n.labels if hasattr(n, 'labels') else [],
            'summary': n.summary if hasattr(n, 'summary') else '',
            'attributes': n.attributes if hasattr(n, 'attributes') else {},
            'created_at': str(n.created_at) if hasattr(n, 'created_at') and n.created_at else None,
        }
    except Exception as e:
        logger.warning(f"Node {node_uuid} not found: {e}")
        return None


def get_edges_by_node(node_uuid: str) -> List[Dict[str, Any]]:
    """Return all edges connected to *node_uuid*."""
    g = get_graphiti()
    driver = _get_driver(g)

    async def _fetch():
        return await driver.entity_edge_ops.get_by_node_uuid(driver, node_uuid)

    try:
        edges = _run_async(_fetch())
    except Exception:
        return []

    result = []
    for e in edges:
        result.append({
            'uuid': e.uuid,
            'name': e.name,
            'fact': e.fact if hasattr(e, 'fact') else '',
            'source_node_uuid': e.source_node_uuid,
            'target_node_uuid': e.target_node_uuid,
            'attributes': e.attributes if hasattr(e, 'attributes') else {},
            'valid_at': str(e.valid_at) if hasattr(e, 'valid_at') and e.valid_at else None,
            'invalid_at': str(e.invalid_at) if hasattr(e, 'invalid_at') and e.invalid_at else None,
            'expired_at': str(e.expired_at) if hasattr(e, 'expired_at') and e.expired_at else None,
        })
    return result


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_graph(
    graph_id: str,
    query: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Hybrid search over the graph.  Returns a list of edge dicts sorted by
    relevance.
    """
    g = get_graphiti()

    try:
        edges = _run_async(
            g.search(
                query=query,
                group_ids=[graph_id],
                num_results=limit,
            )
        )
    except Exception as e:
        logger.warning(f"Graphiti search failed, returning empty: {e}")
        return []

    result = []
    for e in edges:
        result.append({
            'uuid': e.uuid,
            'name': e.name,
            'fact': e.fact if hasattr(e, 'fact') else '',
            'source_node_uuid': e.source_node_uuid,
            'target_node_uuid': e.target_node_uuid,
            'valid_at': str(e.valid_at) if hasattr(e, 'valid_at') and e.valid_at else None,
            'invalid_at': str(e.invalid_at) if hasattr(e, 'invalid_at') and e.invalid_at else None,
            'expired_at': str(e.expired_at) if hasattr(e, 'expired_at') and e.expired_at else None,
        })

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_driver(g):
    """Extract the graph driver from a Graphiti instance."""
    # Graphiti stores the driver as self.driver
    d = getattr(g, 'driver', None)
    if d is not None:
        return d
    raise RuntimeError("Cannot access Graphiti graph driver")
