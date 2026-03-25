# Pulse

Resident infrastructure agent for Kubernetes clusters. Built on fastharness + Pydantic DeepAgents.

## Architecture

- `src/pulse/agent.py` — FastHarness wiring, entrypoint (`uvicorn pulse.agent:app`)
- `src/pulse/tools_k8s.py` — Read-only k8s tools (pods, deployments, events, logs, metrics)
- `src/pulse/tools_mem0.py` — Mem0 memory tools (store/recall observations)
- `src/pulse/prompt.py` — System prompt

## Critical Constraint

**Observation-only. No kubectl apply/delete/patch/scale. All k8s tools are read-only.**

## Stack

- **fastharness** with `DeepAgentsRuntimeFactory` — A2A server + pydantic-ai runtime
- **kubernetes** Python client — cluster reads
- **mem0ai** — cross-session memory for observations
- Custom tools passed via `custom_tools=` on `harness.agent()` (requires fastharness with custom_tools support)

## Running

```bash
uv pip install -e ".[dev]"
uvicorn pulse.agent:app --port 8000
```

Requires `ANTHROPIC_API_KEY` and `MEM0_API_KEY` in `.env`.

## Testing

```bash
uv run pytest tests/ -x -q
```

Tests mock k8s and mem0 clients — no cluster or API keys needed.
