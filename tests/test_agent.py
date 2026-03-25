"""Tests for agent wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestAgentWiring:
    def test_harness_creates_app(self):
        """Verify the harness wires up and produces a FastAPI app."""
        # Mock k8s config loading so it doesn't fail without a cluster
        with (
            patch("pulse.tools_k8s.config") as mock_config,
            patch("pulse.tools_k8s.client"),
        ):
            mock_config.ConfigException = Exception
            mock_config.load_incluster_config.side_effect = Exception
            from pulse.agent import harness

            assert harness.name == "pulse"
            assert len(harness._agents) == 1

            agent = harness._agents["pulse-observer"]
            assert agent.config.model == "claude-sonnet-4-5-20250929"
            assert len(agent.config.custom_tools) == 12  # 9 k8s + 3 mem0
            assert agent.config.system_prompt is not None
            assert "OBSERVE" in agent.config.system_prompt

    def test_system_prompt_contains_key_directives(self):
        from pulse.prompt import SYSTEM_PROMPT

        assert "never" in SYSTEM_PROMPT.lower()
        assert "observe" in SYSTEM_PROMPT.lower()
        assert "memory" in SYSTEM_PROMPT.lower()
        assert "store_observation" not in SYSTEM_PROMPT  # not leaking tool names
