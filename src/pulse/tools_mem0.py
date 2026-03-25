"""Mem0 memory tools for accumulating observations over time."""

from __future__ import annotations

import os
from datetime import UTC, datetime

from pydantic_ai import Tool

try:
    from mem0 import MemoryClient
except ImportError as e:
    raise ImportError("mem0ai is required: pip install mem0ai") from e

# ---------------------------------------------------------------------------
# Mem0 client
# ---------------------------------------------------------------------------

_client: MemoryClient | None = None
AGENT_ID = "pulse"


def _ensure_client() -> MemoryClient:
    global _client
    if _client is None:
        api_key = os.environ.get("MEM0_API_KEY")
        if not api_key:
            raise RuntimeError("MEM0_API_KEY not set")
        _client = MemoryClient(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def store_observation(observation: str, metadata_tags: str = "") -> str:
    """Store a cluster observation in long-term memory.

    Args:
        observation: What was observed (e.g. "pod X restarted 3 times in 1 hour").
        metadata_tags: Comma-separated tags for categorization (e.g. "restart,warning,namespace:kube-system").
    """
    mem = _ensure_client()
    timestamp = datetime.now(UTC).isoformat()
    tagged = f"[{timestamp}] {observation}"
    if metadata_tags:
        tagged += f" (tags: {metadata_tags})"
    result = mem.add(tagged, agent_id=AGENT_ID)
    return f"Stored observation: {result}"


async def recall_observations(query: str, limit: int = 10) -> str:
    """Search memory for past observations matching a query.

    Args:
        query: Natural language search (e.g. "pod restarts", "memory issues").
        limit: Max results to return.
    """
    mem = _ensure_client()
    results = mem.search(query, agent_id=AGENT_ID, limit=min(limit, 50))
    entries = results.get("results", results) if isinstance(results, dict) else results
    if not entries:
        return "No matching observations found."
    lines = []
    for r in entries:
        memory = r.get("memory", r) if isinstance(r, dict) else str(r)
        lines.append(f"- {memory}")
    return "\n".join(lines)


async def list_all_observations(limit: int = 20) -> str:
    """List recent observations from memory.

    Args:
        limit: Max observations to return.
    """
    mem = _ensure_client()
    memories = mem.get_all(agent_id=AGENT_ID, limit=min(limit, 100))
    results = memories.get("results", memories) if isinstance(memories, dict) else memories
    if not results:
        return "No observations stored yet."
    lines = []
    for m in results:
        memory = m.get("memory", m) if isinstance(m, dict) else str(m)
        lines.append(f"- {memory}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Export as pydantic-ai Tools
# ---------------------------------------------------------------------------


def get_mem0_tools() -> list[Tool]:
    """Return all mem0 tools as pydantic-ai Tool objects."""
    return [
        Tool(store_observation),
        Tool(recall_observations),
        Tool(list_all_observations),
    ]
