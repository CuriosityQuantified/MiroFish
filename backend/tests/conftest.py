"""
conftest.py — shared pytest fixtures and session-level configuration.

Module isolation for MCP smoke tests
--------------------------------------
test_mcp_smoke.py::TestMCPImport uses patch.dict('sys.modules', ...) to stub
out heavy dependencies, then imports mirofish_mcp inside that context. When
the context manager exits it removes ALL modules that were added during the
block — including pydantic.root_model, which mcp.types loads as a side-effect.

After the context exits, pydantic.root_model is no longer in sys.modules.
When the next test tries to construct a RootModel generic subclass, pydantic's
internal _generics.create_generic_submodel calls:
    sys.modules[created_model.__module__].__dict__
with __module__ == 'pydantic.root_model' — and gets a KeyError.

Fix: pre-import pydantic.root_model (and related submodules) at session start
so they are already in sys.modules before any patch.dict context can evict
them. We then re-pin them after each test to survive any further evictions.
"""
import sys
import pytest

# Pre-load pydantic submodules that must persist across patch.dict contexts.
import pydantic.root_model  # noqa: F401 — side-effect import to warm sys.modules
import pydantic.main        # noqa: F401

# Snapshot the modules we need to keep alive
_PYDANTIC_MODULES_TO_PRESERVE = {
    k: v for k, v in sys.modules.items()
    if k.startswith("pydantic")
}

MCP_MODULE_PREFIXES = ("mcp", "mirofish_mcp")


@pytest.fixture(autouse=True)
def isolate_mcp_modules():
    """
    Before and after each test:
    1. Purge mcp / mirofish_mcp from sys.modules so imports start fresh.
    2. Re-inject any pydantic submodules that were evicted by patch.dict.

    This prevents TestMCPImport's patch.dict context from poisoning subsequent
    tests that need to import mirofish_mcp (and transitively mcp.types).
    """
    _purge_mcp_modules()
    _restore_pydantic_modules()
    yield
    _purge_mcp_modules()
    _restore_pydantic_modules()


def _purge_mcp_modules():
    to_delete = [
        k for k in sys.modules
        if any(k == p or k.startswith(p + ".") for p in MCP_MODULE_PREFIXES)
    ]
    for key in to_delete:
        del sys.modules[key]


def _restore_pydantic_modules():
    for key, mod in _PYDANTIC_MODULES_TO_PRESERVE.items():
        if key not in sys.modules:
            sys.modules[key] = mod
