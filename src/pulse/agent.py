"""Pulse agent — resident infrastructure observer.

Wires k8s and mem0 tools into fastharness with DeepAgentsRuntimeFactory.
"""

from __future__ import annotations

import os

from fastharness import FastHarness, Skill
from fastharness.runtime.deepagents import DeepAgentsRuntimeFactory

from pulse.prompt import SYSTEM_PROMPT
from pulse.tools_k8s import get_k8s_tools
from pulse.tools_mem0 import get_mem0_tools


def _build_task_store():
    """Build task store — Redis if REDIS_URL set, Postgres if DATABASE_URL set, else in-memory."""
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        from fastharness.stores.redis import RedisTaskStore

        return RedisTaskStore(redis_url, ttl_seconds=3600)

    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        from a2a.server.tasks.database_task_store import DatabaseTaskStore
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(db_url)
        return DatabaseTaskStore(engine=engine)

    return None  # FastHarness defaults to InMemoryTaskStore


harness = FastHarness(
    name="pulse",
    description="Resident infrastructure agent — observes k8s, remembers, reports",
    runtime_factory=DeepAgentsRuntimeFactory(ttl_minutes=30),
    task_store=_build_task_store(),
)

harness.agent(
    name="pulse-observer",
    description="Kubernetes cluster observer with long-term memory",
    skills=[
        Skill(
            id="observe",
            name="Observe",
            description="Observe and report on Kubernetes cluster state",
        ),
        Skill(
            id="recall",
            name="Recall",
            description="Recall past observations and surface patterns",
        ),
    ],
    system_prompt=SYSTEM_PROMPT,
    model="anthropic:claude-sonnet-4-5-20250929",
    custom_tools=get_k8s_tools() + get_mem0_tools(),
    setting_sources=[],
)

app = harness.app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
