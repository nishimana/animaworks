# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core/memory/_llm_utils.py."""

from __future__ import annotations

import inspect
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import core.memory._llm_utils as llm_utils

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_credentials_exported() -> None:
    """Reset _credentials_exported between tests so ensure_credentials_in_env runs."""
    yield
    llm_utils._credentials_exported = False


def _make_cred(api_key: str = "") -> MagicMock:
    """Create a CredentialConfig-like mock with api_key attribute."""
    cred = MagicMock()
    cred.api_key = api_key
    return cred


def _make_config(
    llm_model: str = "anthropic/claude-sonnet-4-6",
    credentials: dict[str, MagicMock] | None = None,
) -> MagicMock:
    """Create a config mock with consolidation and credentials."""
    cfg = MagicMock()
    cfg.consolidation.llm_model = llm_model
    cfg.credentials = credentials or {}
    return cfg


# ── get_consolidation_llm_kwargs ──────────────────────────────────────────────


class TestGetConsolidationLlmKwargs:
    """Tests for get_consolidation_llm_kwargs()."""

    def test_returns_model_from_config(self) -> None:
        """get_consolidation_llm_kwargs returns dict with 'model' key from config."""
        cfg = _make_config(llm_model="anthropic/claude-sonnet-4-6")
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["model"] == "anthropic/claude-sonnet-4-6"

    def test_includes_api_key_when_credential_exists(self) -> None:
        """get_consolidation_llm_kwargs includes api_key when credential exists."""
        cred = _make_cred(api_key="sk-test-key")
        cfg = _make_config(
            llm_model="anthropic/claude-sonnet-4-6",
            credentials={"anthropic": cred},
        )
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["model"] == "anthropic/claude-sonnet-4-6"
        assert result["api_key"] == "sk-test-key"

    def test_works_without_api_key_model_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_consolidation_llm_kwargs works without api_key (model only)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cfg = _make_config(
            llm_model="anthropic/claude-sonnet-4-6",
            credentials={"anthropic": _make_cred(api_key="")},
        )
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["model"] == "anthropic/claude-sonnet-4-6"
        assert "api_key" not in result


# ── ensure_credentials_in_env ─────────────────────────────────────────────────


class TestEnsureCredentialsInEnv:
    """Tests for ensure_credentials_in_env()."""

    def test_exports_credentials_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ensure_credentials_in_env exports credentials to environment."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cred = _make_cred(api_key="sk-exported")
        cfg = _make_config(credentials={"anthropic": cred})
        with patch("core.config.load_config", return_value=cfg):
            llm_utils.ensure_credentials_in_env()
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-exported"

    def test_does_not_overwrite_existing_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ensure_credentials_in_env does not overwrite existing env vars."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "existing-key")
        cred = _make_cred(api_key="sk-from-config")
        cfg = _make_config(credentials={"anthropic": cred})
        with patch("core.config.load_config", return_value=cfg):
            llm_utils.ensure_credentials_in_env()
        assert os.environ.get("ANTHROPIC_API_KEY") == "existing-key"

    def test_runs_only_once_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ensure_credentials_in_env runs only once (idempotent)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cred = _make_cred(api_key="sk-first")
        cfg = _make_config(credentials={"anthropic": cred})
        with patch("core.config.load_config", return_value=cfg) as mock_load:
            llm_utils.ensure_credentials_in_env()
            llm_utils.ensure_credentials_in_env()
            llm_utils.ensure_credentials_in_env()
        # load_config called once in ensure_credentials_in_env (first run only)
        assert mock_load.call_count == 1
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-first"

    def test_silently_returns_on_config_load_failure(self) -> None:
        """ensure_credentials_in_env silently returns on config load failure."""
        with patch("core.config.load_config", side_effect=RuntimeError("config error")):
            llm_utils.ensure_credentials_in_env()
        # No exception raised; function returns normally


# ── one_shot_completion and helpers ──────────────────────────────────────────


class TestOneShotCompletion:
    """Tests for one_shot_completion() and its fallback behavior."""

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.get_consolidation_llm_kwargs")
    @patch("core.memory._llm_utils._try_agent_sdk")
    @patch("core.memory._llm_utils._try_litellm")
    async def test_litellm_success(
        self,
        mock_try_litellm: MagicMock,
        mock_try_agent_sdk: MagicMock,
        mock_get_kwargs: MagicMock,
    ) -> None:
        """Mock litellm to succeed; verify function returns text and Agent SDK is NOT called."""
        mock_get_kwargs.return_value = {"model": "anthropic/claude-sonnet-4-6"}
        mock_try_litellm.return_value = "LLM response text"

        result = await llm_utils.one_shot_completion("Hello")

        assert result == "LLM response text"
        mock_try_litellm.assert_called_once()
        mock_try_agent_sdk.assert_not_called()

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.get_consolidation_llm_kwargs")
    @patch("core.memory._llm_utils._try_agent_sdk")
    @patch("core.memory._llm_utils._try_litellm")
    async def test_litellm_fails_sdk_success(
        self,
        mock_try_litellm: MagicMock,
        mock_try_agent_sdk: MagicMock,
        mock_get_kwargs: MagicMock,
    ) -> None:
        """LiteLLM raises; Agent SDK succeeds; verify fallback returns text."""
        mock_get_kwargs.return_value = {"model": "anthropic/claude-sonnet-4-6"}
        mock_try_litellm.side_effect = RuntimeError("LiteLLM failed")
        mock_try_agent_sdk.return_value = "SDK fallback text"

        result = await llm_utils.one_shot_completion("Hello")

        assert result == "SDK fallback text"
        mock_try_litellm.assert_called_once()
        mock_try_agent_sdk.assert_called_once()

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.get_consolidation_llm_kwargs")
    @patch("core.memory._llm_utils._try_agent_sdk")
    @patch("core.memory._llm_utils._try_litellm")
    async def test_both_fail_returns_none(
        self,
        mock_try_litellm: MagicMock,
        mock_try_agent_sdk: MagicMock,
        mock_get_kwargs: MagicMock,
    ) -> None:
        """Both LiteLLM and Agent SDK fail; verify function returns None."""
        mock_get_kwargs.return_value = {"model": "anthropic/claude-sonnet-4-6"}
        mock_try_litellm.side_effect = RuntimeError("LiteLLM failed")
        mock_try_agent_sdk.return_value = None

        result = await llm_utils.one_shot_completion("Hello")

        assert result is None
        mock_try_litellm.assert_called_once()
        mock_try_agent_sdk.assert_called_once()

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.litellm", create=True)
    async def test_system_prompt_passed_to_litellm(
        self,
        mock_litellm: MagicMock,
    ) -> None:
        """Verify system_prompt is included as system message in LiteLLM call."""
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "ok"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        with patch("core.memory._llm_utils.litellm", mock_litellm):
            # Import litellm inside _try_litellm; patch at module level
            pass
        # Patch where litellm is used - it's imported inside _try_litellm
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_resp
            result = await llm_utils._try_litellm(
                "user prompt",
                system_prompt="You are a helpful assistant.",
                model="anthropic/claude-sonnet-4-6",
                max_tokens=1024,
                llm_kwargs={},
            )
        assert result == "ok"
        call_kwargs = mock_acompletion.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        assert messages is not None
        assert messages[0] == {"role": "system", "content": "You are a helpful assistant."}
        assert messages[1] == {"role": "user", "content": "user prompt"}

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.get_consolidation_llm_kwargs")
    @patch("core.memory._llm_utils._try_agent_sdk")
    @patch("core.memory._llm_utils._try_litellm")
    async def test_default_model_from_config(
        self,
        mock_try_litellm: MagicMock,
        mock_try_agent_sdk: MagicMock,
        mock_get_kwargs: MagicMock,
    ) -> None:
        """When model='' (default), model is resolved from get_consolidation_llm_kwargs()."""
        mock_get_kwargs.return_value = {"model": "anthropic/claude-sonnet-4-6"}
        mock_try_litellm.return_value = "ok"

        await llm_utils.one_shot_completion("Hi", model="")

        mock_get_kwargs.assert_called()
        mock_try_litellm.assert_called_once()
        call_kwargs = mock_try_litellm.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-sonnet-4-6"

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.get_consolidation_llm_kwargs")
    @patch("core.memory._llm_utils._try_agent_sdk")
    @patch("core.memory._llm_utils._try_litellm")
    async def test_non_anthropic_model_skips_sdk(
        self,
        mock_try_litellm: MagicMock,
        mock_try_agent_sdk: MagicMock,
        mock_get_kwargs: MagicMock,
    ) -> None:
        """Non-Anthropic model (e.g. openai/gpt-4.1): LiteLLM failure returns None without SDK."""
        mock_get_kwargs.return_value = {"model": "openai/gpt-4.1"}
        mock_try_litellm.side_effect = RuntimeError("LiteLLM failed")

        result = await llm_utils.one_shot_completion("Hi", model="openai/gpt-4.1")

        assert result is None
        mock_try_litellm.assert_called_once()
        mock_try_agent_sdk.assert_not_called()


class TestIsAnthropicModel:
    """Tests for _is_anthropic_model() helper."""

    def test_is_anthropic_model_true(self) -> None:
        """Various Anthropic model patterns return True."""
        assert llm_utils._is_anthropic_model("anthropic/claude-sonnet-4-6") is True
        assert llm_utils._is_anthropic_model("bedrock/claude-sonnet-4-6") is True
        assert llm_utils._is_anthropic_model("vertex_ai/claude-sonnet-4-6") is True
        assert llm_utils._is_anthropic_model("claude-sonnet-4-6") is True

    def test_is_anthropic_model_false(self) -> None:
        """Non-Anthropic models return False."""
        assert llm_utils._is_anthropic_model("openai/gpt-4.1") is False
        assert llm_utils._is_anthropic_model("ollama/gemma3") is False
        assert llm_utils._is_anthropic_model("google/gemini-2.0") is False


class TestStripProviderPrefix:
    """Tests for _strip_provider_prefix() helper."""

    def test_strip_provider_prefix(self) -> None:
        """Provider prefix is stripped for Agent SDK model name."""
        assert (
            llm_utils._strip_provider_prefix("anthropic/claude-sonnet-4-6")
            == "claude-sonnet-4-6"
        )
        assert (
            llm_utils._strip_provider_prefix("bedrock/jp.anthropic.claude-sonnet-4-6")
            == "claude-sonnet-4-6"
        )
        assert (
            llm_utils._strip_provider_prefix("vertex_ai/claude-sonnet-4-6")
            == "claude-sonnet-4-6"
        )


# ── Helpers for provider-specific parameter tests ────────────────────────────


def _make_cred_with_keys(
    api_key: str = "",
    keys: dict[str, str] | None = None,
    base_url: str | None = None,
) -> MagicMock:
    """Create a CredentialConfig-like mock with api_key, keys, and base_url."""
    cred = MagicMock()
    cred.api_key = api_key
    cred.keys = keys or {}
    cred.base_url = base_url
    return cred


# ── Azure provider parameter resolution ──────────────────────────────────────


class TestAzureProviderParams:
    """Tests for Azure provider-specific parameter resolution in get_consolidation_llm_kwargs()."""

    def test_api_version_from_config_keys(self) -> None:
        """api_version is resolved from credentials.azure.keys.api_version."""
        cred = _make_cred_with_keys(
            api_key="azure-key",
            keys={"api_version": "2024-12-01-preview"},
        )
        cfg = _make_config(
            llm_model="azure/gpt-4.1-mini",
            credentials={"azure": cred},
        )
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["api_version"] == "2024-12-01-preview"
        assert result["model"] == "azure/gpt-4.1-mini"
        assert result["api_key"] == "azure-key"

    def test_api_version_from_env_fallback(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """api_version falls back to AZURE_API_VERSION env var when not in config."""
        cred = _make_cred_with_keys(api_key="azure-key", keys={})
        cfg = _make_config(
            llm_model="azure/gpt-4.1-mini",
            credentials={"azure": cred},
        )
        monkeypatch.setenv("AZURE_API_VERSION", "2025-01-01")
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["api_version"] == "2025-01-01"

    def test_config_keys_take_priority_over_env(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config keys.api_version takes priority over AZURE_API_VERSION env var."""
        cred = _make_cred_with_keys(
            api_key="azure-key",
            keys={"api_version": "from-config"},
        )
        cfg = _make_config(
            llm_model="azure/gpt-4.1-mini",
            credentials={"azure": cred},
        )
        monkeypatch.setenv("AZURE_API_VERSION", "from-env")
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["api_version"] == "from-config"

    def test_no_api_version_when_absent(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """api_version is not included when neither config nor env provides it."""
        cred = _make_cred_with_keys(api_key="azure-key", keys={})
        cfg = _make_config(
            llm_model="azure/gpt-4.1-mini",
            credentials={"azure": cred},
        )
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert "api_version" not in result


# ── Vertex AI provider parameter resolution ──────────────────────────────────


class TestVertexAIProviderParams:
    """Tests for Vertex AI provider-specific parameter resolution in get_consolidation_llm_kwargs()."""

    def test_vertex_params_from_config_keys(self) -> None:
        """vertex_project, vertex_location, vertex_credentials are resolved from config keys."""
        cred = _make_cred_with_keys(
            keys={
                "vertex_project": "my-project",
                "vertex_location": "us-central1",
                "vertex_credentials": "/path/to/sa.json",
            },
        )
        cfg = _make_config(
            llm_model="vertex_ai/claude-sonnet-4-6",
            credentials={"vertex_ai": cred},
        )
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["vertex_project"] == "my-project"
        assert result["vertex_location"] == "us-central1"
        assert result["vertex_credentials"] == "/path/to/sa.json"

    def test_vertex_params_from_env_fallback(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Vertex AI params fall back to environment variables when not in config."""
        cred = _make_cred_with_keys(keys={})
        cfg = _make_config(
            llm_model="vertex_ai/claude-sonnet-4-6",
            credentials={"vertex_ai": cred},
        )
        monkeypatch.setenv("VERTEX_PROJECT", "env-project")
        monkeypatch.setenv("VERTEX_LOCATION", "europe-west1")
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["vertex_project"] == "env-project"
        assert result["vertex_location"] == "europe-west1"
        assert "vertex_credentials" not in result

    def test_vertex_config_keys_take_priority_over_env(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config keys take priority over environment variables for Vertex AI params."""
        cred = _make_cred_with_keys(
            keys={"vertex_project": "from-config"},
        )
        cfg = _make_config(
            llm_model="vertex_ai/claude-sonnet-4-6",
            credentials={"vertex_ai": cred},
        )
        monkeypatch.setenv("VERTEX_PROJECT", "from-env")
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["vertex_project"] == "from-config"

    def test_no_vertex_params_when_absent(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Vertex AI params are not included when neither config nor env provides them."""
        cred = _make_cred_with_keys(keys={})
        cfg = _make_config(
            llm_model="vertex_ai/claude-sonnet-4-6",
            credentials={"vertex_ai": cred},
        )
        monkeypatch.delenv("VERTEX_PROJECT", raising=False)
        monkeypatch.delenv("VERTEX_LOCATION", raising=False)
        monkeypatch.delenv("VERTEX_CREDENTIALS", raising=False)
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert "vertex_project" not in result
        assert "vertex_location" not in result
        assert "vertex_credentials" not in result


# ── Bedrock provider parameter resolution ─────────────────────────────────────


class TestBedrockProviderParams:
    """Tests for Bedrock provider-specific parameter resolution in get_consolidation_llm_kwargs()."""

    def test_bedrock_params_from_config_keys(self) -> None:
        """aws_access_key_id, aws_secret_access_key, aws_region_name are resolved from config keys."""
        cred = _make_cred_with_keys(
            keys={
                "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
                "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "aws_region_name": "us-east-1",
            },
        )
        cfg = _make_config(
            llm_model="bedrock/claude-sonnet-4-6",
            credentials={"bedrock": cred},
        )
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["aws_access_key_id"] == "AKIAIOSFODNN7EXAMPLE"
        assert result["aws_secret_access_key"] == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert result["aws_region_name"] == "us-east-1"

    def test_bedrock_params_from_env_fallback(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bedrock params fall back to environment variables when not in config."""
        cred = _make_cred_with_keys(keys={})
        cfg = _make_config(
            llm_model="bedrock/claude-sonnet-4-6",
            credentials={"bedrock": cred},
        )
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "env-access-key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-secret-key")
        monkeypatch.setenv("AWS_REGION_NAME", "ap-northeast-1")
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["aws_access_key_id"] == "env-access-key"
        assert result["aws_secret_access_key"] == "env-secret-key"
        assert result["aws_region_name"] == "ap-northeast-1"

    def test_bedrock_config_keys_take_priority_over_env(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config keys take priority over environment variables for Bedrock params."""
        cred = _make_cred_with_keys(
            keys={
                "aws_access_key_id": "from-config",
                "aws_secret_access_key": "config-secret",
                "aws_region_name": "us-west-2",
            },
        )
        cfg = _make_config(
            llm_model="bedrock/claude-sonnet-4-6",
            credentials={"bedrock": cred},
        )
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "from-env")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-secret")
        monkeypatch.setenv("AWS_REGION_NAME", "eu-west-1")
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["aws_access_key_id"] == "from-config"
        assert result["aws_secret_access_key"] == "config-secret"
        assert result["aws_region_name"] == "us-west-2"

    def test_no_bedrock_params_when_absent(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bedrock params are not included when neither config nor env provides them."""
        cred = _make_cred_with_keys(keys={})
        cfg = _make_config(
            llm_model="bedrock/claude-sonnet-4-6",
            credentials={"bedrock": cred},
        )
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("AWS_REGION_NAME", raising=False)
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert "aws_access_key_id" not in result
        assert "aws_secret_access_key" not in result
        assert "aws_region_name" not in result


# ── Local LLM (ollama) configuration ─────────────────────────────────────────


class TestOllamaProviderParams:
    """Tests for local LLM (ollama) configuration in get_consolidation_llm_kwargs()."""

    def test_api_base_from_credentials_base_url(self) -> None:
        """api_base is resolved from credentials.ollama.base_url."""
        cred = _make_cred_with_keys(
            api_key="",
            base_url="http://localhost:11434",
        )
        cfg = _make_config(
            llm_model="ollama/gemma3:8b",
            credentials={"ollama": cred},
        )
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["api_base"] == "http://localhost:11434"
        assert result["model"] == "ollama/gemma3:8b"

    def test_no_api_key_for_ollama(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """api_key is not included for ollama provider (no API key needed)."""
        cred = _make_cred_with_keys(
            api_key="",
            base_url="http://localhost:11434",
        )
        cfg = _make_config(
            llm_model="ollama/gemma3:8b",
            credentials={"ollama": cred},
        )
        # Ensure no env-based fallback either
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert "api_key" not in result

    def test_ollama_with_custom_port(self) -> None:
        """api_base works with a custom port for ollama."""
        cred = _make_cred_with_keys(
            api_key="",
            base_url="http://192.168.1.100:8080",
        )
        cfg = _make_config(
            llm_model="ollama/llama3:latest",
            credentials={"ollama": cred},
        )
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["api_base"] == "http://192.168.1.100:8080"
        assert "api_key" not in result

    def test_ollama_no_credentials_section(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ollama model works even without a credentials section (model-only)."""
        cfg = _make_config(
            llm_model="ollama/gemma3:8b",
            credentials={},
        )
        with patch("core.config.load_config", return_value=cfg):
            result = llm_utils.get_consolidation_llm_kwargs()
        assert result["model"] == "ollama/gemma3:8b"
        assert "api_key" not in result
        assert "api_base" not in result


# ── Authentication error guidance log ─────────────────────────────────────────


class TestAuthErrorGuidanceLog:
    """Tests for authentication error guidance log in one_shot_completion()."""

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.get_consolidation_llm_kwargs")
    @patch("core.memory._llm_utils._try_agent_sdk")
    @patch("core.memory._llm_utils._try_litellm")
    async def test_auth_error_logs_guidance(
        self,
        mock_try_litellm: MagicMock,
        mock_try_agent_sdk: MagicMock,
        mock_get_kwargs: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """AuthenticationError triggers guidance log with model name and config advice."""
        mock_get_kwargs.return_value = {"model": "anthropic/claude-sonnet-4-6"}
        mock_try_litellm.side_effect = Exception("AuthenticationError: invalid API key")
        mock_try_agent_sdk.return_value = None

        with caplog.at_level(logging.WARNING, logger="core.memory._llm_utils"):
            await llm_utils.one_shot_completion("Hello")

        # Check that the guidance message is in the log
        guidance_messages = [
            r.message for r in caplog.records
            if "authentication failed" in r.message.lower()
            and "anthropic/claude-sonnet-4-6" in r.message
        ]
        assert len(guidance_messages) >= 1, (
            f"Expected guidance log with model name, got: {[r.message for r in caplog.records]}"
        )
        guidance = guidance_messages[0]
        assert "config.json" in guidance.lower() or "credentials" in guidance.lower()
        assert "ollama" in guidance.lower() or "local model" in guidance.lower()

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.get_consolidation_llm_kwargs")
    @patch("core.memory._llm_utils._try_agent_sdk")
    @patch("core.memory._llm_utils._try_litellm")
    async def test_401_error_logs_guidance(
        self,
        mock_try_litellm: MagicMock,
        mock_try_agent_sdk: MagicMock,
        mock_get_kwargs: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """HTTP 401 error triggers guidance log."""
        mock_get_kwargs.return_value = {"model": "anthropic/claude-sonnet-4-6"}
        mock_try_litellm.side_effect = Exception("HTTP 401 Unauthorized")
        mock_try_agent_sdk.return_value = None

        with caplog.at_level(logging.WARNING, logger="core.memory._llm_utils"):
            await llm_utils.one_shot_completion("Hello")

        guidance_messages = [
            r.message for r in caplog.records
            if "authentication failed" in r.message.lower()
        ]
        assert len(guidance_messages) >= 1

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.get_consolidation_llm_kwargs")
    @patch("core.memory._llm_utils._try_agent_sdk")
    @patch("core.memory._llm_utils._try_litellm")
    async def test_403_error_logs_guidance(
        self,
        mock_try_litellm: MagicMock,
        mock_try_agent_sdk: MagicMock,
        mock_get_kwargs: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """HTTP 403 error triggers guidance log."""
        mock_get_kwargs.return_value = {"model": "openai/gpt-4.1"}
        mock_try_litellm.side_effect = Exception("HTTP 403 Forbidden")

        with caplog.at_level(logging.WARNING, logger="core.memory._llm_utils"):
            await llm_utils.one_shot_completion("Hello", model="openai/gpt-4.1")

        guidance_messages = [
            r.message for r in caplog.records
            if "authentication failed" in r.message.lower()
        ]
        assert len(guidance_messages) >= 1

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.get_consolidation_llm_kwargs")
    @patch("core.memory._llm_utils._try_agent_sdk")
    @patch("core.memory._llm_utils._try_litellm")
    async def test_api_key_error_logs_guidance(
        self,
        mock_try_litellm: MagicMock,
        mock_try_agent_sdk: MagicMock,
        mock_get_kwargs: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """'api key' error message triggers guidance log."""
        mock_get_kwargs.return_value = {"model": "anthropic/claude-sonnet-4-6"}
        mock_try_litellm.side_effect = Exception("No API key provided")
        mock_try_agent_sdk.return_value = None

        with caplog.at_level(logging.WARNING, logger="core.memory._llm_utils"):
            await llm_utils.one_shot_completion("Hello")

        guidance_messages = [
            r.message for r in caplog.records
            if "authentication failed" in r.message.lower()
        ]
        assert len(guidance_messages) >= 1

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.get_consolidation_llm_kwargs")
    @patch("core.memory._llm_utils._try_agent_sdk")
    @patch("core.memory._llm_utils._try_litellm")
    async def test_non_auth_error_no_guidance(
        self,
        mock_try_litellm: MagicMock,
        mock_try_agent_sdk: MagicMock,
        mock_get_kwargs: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Non-authentication errors (e.g. timeout) do NOT trigger guidance log."""
        mock_get_kwargs.return_value = {"model": "anthropic/claude-sonnet-4-6"}
        mock_try_litellm.side_effect = Exception("Connection timeout after 30s")
        mock_try_agent_sdk.return_value = None

        with caplog.at_level(logging.WARNING, logger="core.memory._llm_utils"):
            await llm_utils.one_shot_completion("Hello")

        guidance_messages = [
            r.message for r in caplog.records
            if "authentication failed" in r.message.lower()
        ]
        assert len(guidance_messages) == 0


# ── Dead code removal verification ────────────────────────────────────────────


class TestDeadCodeRemoval:
    """Verify that dead code _apply_provider_kwargs has been removed from conversation_compression.py."""

    def test_apply_provider_kwargs_not_in_conversation_compression(self) -> None:
        """conversation_compression module must not contain _apply_provider_kwargs."""
        import core.memory.conversation_compression as cc

        assert not hasattr(cc, "_apply_provider_kwargs"), (
            "_apply_provider_kwargs should be removed from conversation_compression.py "
            "(dead code removal per design doc)"
        )

    def test_apply_provider_kwargs_not_in_source(self) -> None:
        """_apply_provider_kwargs must not appear in conversation_compression.py source code."""
        import core.memory.conversation_compression as cc

        source = inspect.getsource(cc)
        assert "_apply_provider_kwargs" not in source, (
            "_apply_provider_kwargs definition or reference found in conversation_compression.py source; "
            "it should have been removed as dead code"
        )
