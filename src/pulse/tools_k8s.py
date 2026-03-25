"""Read-only Kubernetes tools for cluster observation.

All tools are strictly read-only — no apply, delete, patch, or scale operations.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import Tool

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
except ImportError as e:
    raise ImportError("kubernetes is required: pip install kubernetes") from e

# ---------------------------------------------------------------------------
# Kubernetes client helpers
# ---------------------------------------------------------------------------

_core: client.CoreV1Api | None = None
_apps: client.AppsV1Api | None = None
_custom: client.CustomObjectsApi | None = None


def _ensure_clients() -> tuple[client.CoreV1Api, client.AppsV1Api, client.CustomObjectsApi]:
    global _core, _apps, _custom
    if _core is None:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        _core = client.CoreV1Api()
        _apps = client.AppsV1Api()
        _custom = client.CustomObjectsApi()
    return _core, _apps, _custom


def _serialize(obj: Any) -> str:
    """Serialize k8s API objects to compact JSON."""
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    return json.dumps(obj, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def list_pods(namespace: str = "default", label_selector: str = "") -> str:
    """List pods in a namespace. Optionally filter by label selector."""
    core, _, _ = _ensure_clients()
    pods = core.list_namespaced_pod(namespace, label_selector=label_selector or None)
    rows = []
    for p in pods.items:
        status = p.status.phase
        restarts = sum(
            (cs.restart_count for cs in (p.status.container_statuses or [])),
            0,
        )
        rows.append(
            {
                "name": p.metadata.name,
                "namespace": p.metadata.namespace,
                "status": status,
                "restarts": restarts,
                "node": p.spec.node_name,
                "age": str(p.metadata.creation_timestamp),
            }
        )
    return json.dumps(rows, indent=2)


async def list_deployments(namespace: str = "default") -> str:
    """List deployments in a namespace with replica counts."""
    _, apps, _ = _ensure_clients()
    deps = apps.list_namespaced_deployment(namespace)
    rows = []
    for d in deps.items:
        rows.append(
            {
                "name": d.metadata.name,
                "replicas": d.spec.replicas,
                "ready": d.status.ready_replicas or 0,
                "available": d.status.available_replicas or 0,
                "age": str(d.metadata.creation_timestamp),
            }
        )
    return json.dumps(rows, indent=2)


async def list_services(namespace: str = "default") -> str:
    """List services in a namespace."""
    core, _, _ = _ensure_clients()
    svcs = core.list_namespaced_service(namespace)
    rows = []
    for s in svcs.items:
        rows.append(
            {
                "name": s.metadata.name,
                "type": s.spec.type,
                "cluster_ip": s.spec.cluster_ip,
                "ports": [
                    {"port": p.port, "target_port": str(p.target_port), "protocol": p.protocol}
                    for p in (s.spec.ports or [])
                ],
            }
        )
    return json.dumps(rows, indent=2)


async def list_namespaces() -> str:
    """List all namespaces in the cluster."""
    core, _, _ = _ensure_clients()
    ns_list = core.list_namespace()
    return json.dumps(
        [{"name": ns.metadata.name, "status": ns.status.phase} for ns in ns_list.items],
        indent=2,
    )


async def get_pod_logs(
    pod_name: str, namespace: str = "default", container: str = "", tail_lines: int = 100
) -> str:
    """Read tail of pod logs. Read-only, tail only (max 200 lines)."""
    core, _, _ = _ensure_clients()
    tail_lines = min(tail_lines, 200)
    kwargs: dict[str, Any] = {"tail_lines": tail_lines}
    if container:
        kwargs["container"] = container
    try:
        return core.read_namespaced_pod_log(pod_name, namespace, **kwargs)
    except ApiException as e:
        return f"Error reading logs: {e.reason} ({e.status})"


async def get_events(namespace: str = "default", limit: int = 50) -> str:
    """Get recent events in a namespace. Useful for spotting warnings/errors."""
    core, _, _ = _ensure_clients()
    events = core.list_namespaced_event(namespace, limit=min(limit, 100))
    rows = []
    for e in events.items:
        rows.append(
            {
                "type": e.type,
                "reason": e.reason,
                "message": e.message,
                "object": f"{e.involved_object.kind}/{e.involved_object.name}",
                "count": e.count,
                "last_seen": str(e.last_timestamp),
            }
        )
    return json.dumps(rows, indent=2)


async def get_node_metrics() -> str:
    """Read node-level CPU/memory metrics from metrics-server.

    Requires metrics-server to be installed in the cluster.
    """
    _, _, custom = _ensure_clients()
    try:
        metrics = custom.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
        rows = []
        for node in metrics.get("items", []):
            rows.append(
                {
                    "name": node["metadata"]["name"],
                    "cpu": node["usage"]["cpu"],
                    "memory": node["usage"]["memory"],
                }
            )
        return json.dumps(rows, indent=2)
    except ApiException as e:
        return f"Metrics unavailable: {e.reason} ({e.status}). Is metrics-server installed?"


async def get_pod_metrics(namespace: str = "default") -> str:
    """Read pod-level CPU/memory metrics from metrics-server."""
    _, _, custom = _ensure_clients()
    try:
        metrics = custom.list_namespaced_custom_object(
            "metrics.k8s.io", "v1beta1", namespace, "pods"
        )
        rows = []
        for pod in metrics.get("items", []):
            containers = [
                {"name": c["name"], "cpu": c["usage"]["cpu"], "memory": c["usage"]["memory"]}
                for c in pod.get("containers", [])
            ]
            rows.append({"name": pod["metadata"]["name"], "containers": containers})
        return json.dumps(rows, indent=2)
    except ApiException as e:
        return f"Metrics unavailable: {e.reason} ({e.status}). Is metrics-server installed?"


async def kubectl_get(resource: str, namespace: str = "", name: str = "") -> str:
    """Generic read-only kubectl get. Supports: pods, deployments, services, configmaps, nodes, ingresses, jobs, cronjobs, daemonsets, statefulsets, replicasets, hpa.

    Never executes apply, delete, patch, or scale.
    """
    core, apps, custom = _ensure_clients()

    ALLOWED = {
        "pods",
        "deployments",
        "services",
        "configmaps",
        "secrets",
        "nodes",
        "ingresses",
        "jobs",
        "cronjobs",
        "daemonsets",
        "statefulsets",
        "replicasets",
        "hpa",
        "namespaces",
        "events",
        "persistentvolumeclaims",
        "persistentvolumes",
    }
    resource = resource.lower().strip()
    if resource not in ALLOWED:
        return f"Resource '{resource}' not in allowed list: {sorted(ALLOWED)}"

    try:
        # Core v1 resources
        if resource == "pods":
            if name:
                obj = core.read_namespaced_pod(name, namespace or "default")
            else:
                obj = core.list_namespaced_pod(namespace or "default")
        elif resource == "services":
            if name:
                obj = core.read_namespaced_service(name, namespace or "default")
            else:
                obj = core.list_namespaced_service(namespace or "default")
        elif resource == "configmaps":
            if name:
                obj = core.read_namespaced_config_map(name, namespace or "default")
            else:
                obj = core.list_namespaced_config_map(namespace or "default")
        elif resource == "secrets":
            # Return metadata only, never secret data
            if name:
                s = core.read_namespaced_secret(name, namespace or "default")
                return json.dumps(
                    {
                        "name": s.metadata.name,
                        "type": s.type,
                        "keys": list((s.data or {}).keys()),
                    },
                    indent=2,
                )
            else:
                secrets = core.list_namespaced_secret(namespace or "default")
                return json.dumps(
                    [
                        {
                            "name": s.metadata.name,
                            "type": s.type,
                            "keys": list((s.data or {}).keys()),
                        }
                        for s in secrets.items
                    ],
                    indent=2,
                )
        elif resource == "nodes":
            if name:
                obj = core.read_node(name)
            else:
                obj = core.list_node()
        elif resource == "namespaces":
            obj = core.list_namespace()
        elif resource == "events":
            obj = core.list_namespaced_event(namespace or "default")
        elif resource == "persistentvolumeclaims":
            obj = core.list_namespaced_persistent_volume_claim(namespace or "default")
        elif resource == "persistentvolumes":
            obj = core.list_persistent_volume()
        # Apps v1 resources
        elif resource == "deployments":
            if name:
                obj = apps.read_namespaced_deployment(name, namespace or "default")
            else:
                obj = apps.list_namespaced_deployment(namespace or "default")
        elif resource == "daemonsets":
            if name:
                obj = apps.read_namespaced_daemon_set(name, namespace or "default")
            else:
                obj = apps.list_namespaced_daemon_set(namespace or "default")
        elif resource == "statefulsets":
            if name:
                obj = apps.read_namespaced_stateful_set(name, namespace or "default")
            else:
                obj = apps.list_namespaced_stateful_set(namespace or "default")
        elif resource == "replicasets":
            if name:
                obj = apps.read_namespaced_replica_set(name, namespace or "default")
            else:
                obj = apps.list_namespaced_replica_set(namespace or "default")
        # Batch / autoscaling / networking
        elif resource == "jobs":
            batch = client.BatchV1Api()
            if name:
                obj = batch.read_namespaced_job(name, namespace or "default")
            else:
                obj = batch.list_namespaced_job(namespace or "default")
        elif resource == "cronjobs":
            batch = client.BatchV1Api()
            if name:
                obj = batch.read_namespaced_cron_job(name, namespace or "default")
            else:
                obj = batch.list_namespaced_cron_job(namespace or "default")
        elif resource == "hpa":
            autoscaling = client.AutoscalingV2Api()
            if name:
                obj = autoscaling.read_namespaced_horizontal_pod_autoscaler(
                    name, namespace or "default"
                )
            else:
                obj = autoscaling.list_namespaced_horizontal_pod_autoscaler(
                    namespace or "default"
                )
        elif resource == "ingresses":
            networking = client.NetworkingV1Api()
            if name:
                obj = networking.read_namespaced_ingress(name, namespace or "default")
            else:
                obj = networking.list_namespaced_ingress(namespace or "default")
        else:
            return f"Resource '{resource}' handler not implemented"

        return _serialize(obj)
    except ApiException as e:
        return f"Error: {e.reason} ({e.status})"


# ---------------------------------------------------------------------------
# Export as pydantic-ai Tools
# ---------------------------------------------------------------------------


def get_k8s_tools() -> list[Tool]:
    """Return all k8s read-only tools as pydantic-ai Tool objects."""
    return [
        Tool(list_pods),
        Tool(list_deployments),
        Tool(list_services),
        Tool(list_namespaces),
        Tool(get_pod_logs),
        Tool(get_events),
        Tool(get_node_metrics),
        Tool(get_pod_metrics),
        Tool(kubectl_get),
    ]
