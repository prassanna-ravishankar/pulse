"""Tests for k8s read-only tools."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pulse import tools_k8s


@pytest.fixture(autouse=True)
def _reset_clients():
    """Reset global k8s clients between tests."""
    tools_k8s._core = None
    tools_k8s._apps = None
    tools_k8s._custom = None


def _pod(name: str, phase: str = "Running", restarts: int = 0, node: str = "node-1"):
    cs = SimpleNamespace(restart_count=restarts)
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name, namespace="default", creation_timestamp=datetime(2025, 1, 1)
        ),
        status=SimpleNamespace(phase=phase, container_statuses=[cs]),
        spec=SimpleNamespace(node_name=node),
    )


def _deployment(name: str, replicas: int = 2, ready: int = 2, available: int = 2):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, creation_timestamp=datetime(2025, 1, 1)),
        spec=SimpleNamespace(replicas=replicas),
        status=SimpleNamespace(ready_replicas=ready, available_replicas=available),
    )


def _service(name: str, svc_type: str = "ClusterIP"):
    port = SimpleNamespace(port=80, target_port=8080, protocol="TCP")
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        spec=SimpleNamespace(type=svc_type, cluster_ip="10.0.0.1", ports=[port]),
    )


def _event(reason: str, message: str, kind: str = "Pod", obj_name: str = "test-pod"):
    return SimpleNamespace(
        type="Warning",
        reason=reason,
        message=message,
        involved_object=SimpleNamespace(kind=kind, name=obj_name),
        count=1,
        last_timestamp=datetime(2025, 1, 1),
    )


@pytest.fixture
def mock_k8s():
    core = MagicMock()
    apps = MagicMock()
    custom = MagicMock()
    with patch.object(tools_k8s, "_ensure_clients", return_value=(core, apps, custom)):
        yield core, apps, custom


class TestListPods:
    @pytest.mark.asyncio
    async def test_returns_pod_info(self, mock_k8s):
        core, _, _ = mock_k8s
        core.list_namespaced_pod.return_value = SimpleNamespace(
            items=[_pod("web-1"), _pod("web-2", restarts=3)]
        )
        result = json.loads(await tools_k8s.list_pods())
        assert len(result) == 2
        assert result[0]["name"] == "web-1"
        assert result[1]["restarts"] == 3

    @pytest.mark.asyncio
    async def test_passes_label_selector(self, mock_k8s):
        core, _, _ = mock_k8s
        core.list_namespaced_pod.return_value = SimpleNamespace(items=[])
        await tools_k8s.list_pods(namespace="kube-system", label_selector="app=dns")
        core.list_namespaced_pod.assert_called_once_with("kube-system", label_selector="app=dns")


class TestListDeployments:
    @pytest.mark.asyncio
    async def test_returns_deployment_info(self, mock_k8s):
        _, apps, _ = mock_k8s
        apps.list_namespaced_deployment.return_value = SimpleNamespace(
            items=[_deployment("api", replicas=3, ready=2)]
        )
        result = json.loads(await tools_k8s.list_deployments())
        assert result[0]["name"] == "api"
        assert result[0]["ready"] == 2


class TestListServices:
    @pytest.mark.asyncio
    async def test_returns_service_info(self, mock_k8s):
        core, _, _ = mock_k8s
        core.list_namespaced_service.return_value = SimpleNamespace(
            items=[_service("frontend")]
        )
        result = json.loads(await tools_k8s.list_services())
        assert result[0]["name"] == "frontend"
        assert result[0]["ports"][0]["port"] == 80


class TestGetPodLogs:
    @pytest.mark.asyncio
    async def test_returns_logs(self, mock_k8s):
        core, _, _ = mock_k8s
        core.read_namespaced_pod_log.return_value = "line1\nline2"
        result = await tools_k8s.get_pod_logs("web-1")
        assert result == "line1\nline2"

    @pytest.mark.asyncio
    async def test_caps_tail_lines(self, mock_k8s):
        core, _, _ = mock_k8s
        core.read_namespaced_pod_log.return_value = ""
        await tools_k8s.get_pod_logs("web-1", tail_lines=999)
        _, kwargs = core.read_namespaced_pod_log.call_args
        assert kwargs["tail_lines"] == 200


class TestGetEvents:
    @pytest.mark.asyncio
    async def test_returns_events(self, mock_k8s):
        core, _, _ = mock_k8s
        core.list_namespaced_event.return_value = SimpleNamespace(
            items=[_event("OOMKilled", "Container killed")]
        )
        result = json.loads(await tools_k8s.get_events())
        assert result[0]["reason"] == "OOMKilled"


class TestGetNodeMetrics:
    @pytest.mark.asyncio
    async def test_returns_metrics(self, mock_k8s):
        _, _, custom = mock_k8s
        custom.list_cluster_custom_object.return_value = {
            "items": [
                {"metadata": {"name": "node-1"}, "usage": {"cpu": "500m", "memory": "2Gi"}}
            ]
        }
        result = json.loads(await tools_k8s.get_node_metrics())
        assert result[0]["cpu"] == "500m"


class TestKubectlGet:
    @pytest.mark.asyncio
    async def test_rejects_disallowed_resource(self, mock_k8s):
        result = await tools_k8s.kubectl_get("networkpolicies")
        assert "not in allowed list" in result

    @pytest.mark.asyncio
    async def test_gets_pods(self, mock_k8s):
        core, _, _ = mock_k8s
        pod = _pod("web-1")
        core.list_namespaced_pod.return_value = SimpleNamespace(items=[pod])
        result = await tools_k8s.kubectl_get("pods")
        assert "web-1" in result

    @pytest.mark.asyncio
    async def test_secrets_redacted(self, mock_k8s):
        core, _, _ = mock_k8s
        core.list_namespaced_secret.return_value = SimpleNamespace(
            items=[
                SimpleNamespace(
                    metadata=SimpleNamespace(name="db-creds"),
                    type="Opaque",
                    data={"password": "c2VjcmV0"},
                )
            ]
        )
        result = json.loads(await tools_k8s.kubectl_get("secrets"))
        assert result[0]["keys"] == ["password"]
        assert "c2VjcmV0" not in json.dumps(result)


class TestGetK8sTools:
    def test_returns_tools(self):
        tools = tools_k8s.get_k8s_tools()
        assert len(tools) == 9
        names = {t.name for t in tools}
        assert "list_pods" in names
        assert "kubectl_get" in names
