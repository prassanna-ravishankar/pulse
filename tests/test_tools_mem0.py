"""Tests for mem0 memory tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pulse import tools_mem0


@pytest.fixture(autouse=True)
def _reset_client():
    tools_mem0._client = None


@pytest.fixture
def mock_mem0():
    mock_client = MagicMock()
    with patch.object(tools_mem0, "_ensure_client", return_value=mock_client):
        yield mock_client


class TestStoreObservation:
    @pytest.mark.asyncio
    async def test_stores_with_timestamp(self, mock_mem0):
        mock_mem0.add.return_value = {"id": "abc123"}
        result = await tools_mem0.store_observation("pod web-1 restarted")
        assert "Stored observation" in result
        call_args = mock_mem0.add.call_args
        assert "pod web-1 restarted" in call_args[0][0]
        assert call_args[1]["agent_id"] == "pulse"

    @pytest.mark.asyncio
    async def test_stores_with_tags(self, mock_mem0):
        mock_mem0.add.return_value = {"id": "abc123"}
        await tools_mem0.store_observation("OOM event", metadata_tags="oom,warning")
        msg = mock_mem0.add.call_args[0][0]
        assert "oom,warning" in msg


class TestRecallObservations:
    @pytest.mark.asyncio
    async def test_returns_matches(self, mock_mem0):
        mock_mem0.search.return_value = {
            "results": [{"memory": "pod X restarted 3 times"}]
        }
        result = await tools_mem0.recall_observations("restarts")
        assert "pod X restarted" in result

    @pytest.mark.asyncio
    async def test_returns_empty(self, mock_mem0):
        mock_mem0.search.return_value = {"results": []}
        result = await tools_mem0.recall_observations("nothing")
        assert "No matching" in result


class TestListAllObservations:
    @pytest.mark.asyncio
    async def test_returns_all(self, mock_mem0):
        mock_mem0.get_all.return_value = {
            "results": [{"memory": "obs1"}, {"memory": "obs2"}]
        }
        result = await tools_mem0.list_all_observations()
        assert "obs1" in result
        assert "obs2" in result

    @pytest.mark.asyncio
    async def test_returns_empty(self, mock_mem0):
        mock_mem0.get_all.return_value = {"results": []}
        result = await tools_mem0.list_all_observations()
        assert "No observations" in result


class TestGetMem0Tools:
    def test_returns_tools(self):
        tools = tools_mem0.get_mem0_tools()
        assert len(tools) == 3
        names = {t.name for t in tools}
        assert "store_observation" in names
        assert "recall_observations" in names
