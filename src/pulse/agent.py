"""Pulse agent — resident infrastructure observer.

Wires k8s and mem0 tools into fastharness with DeepAgentsRuntimeFactory.
"""

from __future__ import annotations

from fastharness import FastHarness, Skill
from fastharness.runtime.deepagents import DeepAgentsRuntimeFactory

from pulse.prompt import SYSTEM_PROMPT
from pulse.tools_k8s import get_k8s_tools
from pulse.tools_mem0 import get_mem0_tools

harness = FastHarness(
    name="pulse",
    description="Resident infrastructure agent — observes k8s, remembers, reports",
    runtime_factory=DeepAgentsRuntimeFactory(ttl_minutes=30),
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
    model="claude-sonnet-4-5-20250929",
    custom_tools=get_k8s_tools() + get_mem0_tools(),
    setting_sources=[],
)

app = harness.app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
