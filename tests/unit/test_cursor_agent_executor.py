from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for CursorAgentExecutor (Mode D).

All tests use mocks — no cursor-agent CLI binary required.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.execution.base import ExecutionResult, ToolCallRecord
from core.execution.cursor_agent import (
    CursorAgentExecutor,
    _CURSOR_AGENT_BINARY_NAMES,
    _DEFAULT_TIMEOUT_SECONDS,
    _find_cursor_agent_binary,
    is_cursor_agent_available,
)

# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "test-cursor"
    d.mkdir(parents=True)
    (d / "shortterm" / "chat").mkdir(parents=True)
    (d / "shortterm" / "heartbeat").mkdir(parents=True)
    (d / "identity.md").write_text("# Test Cursor Anima", encoding="utf-8")
    (d / "state").mkdir()
    (d / "state" / "current_state.md").write_text("status: idle\n", encoding="utf-8")
    return d


@pytest.fixture
def model_config():
    from core.schemas import ModelConfig

    return ModelConfig(
        model="cursor/claude-4-sonnet",
        max_tokens=4096,
        max_turns=30,
        credential="cursor",
        context_threshold=0.50,
        max_chains=2,
    )


@pytest.fixture
def executor(model_config, anima_dir):
    return CursorAgentExecutor(
        model_config=model_config,
        anima_dir=anima_dir,
        tool_registry=["web_search"],
        personal_tools={},
    )


# ── Helper tests ─────────────────────────────────────────────


class TestBinaryDiscovery:
    def test_find_binary_returns_first_match(self):
        with patch("shutil.which", side_effect=lambda n: f"/usr/bin/{n}" if n == "agent" else None):
            assert _find_cursor_agent_binary() == "/usr/bin/agent"

    def test_find_binary_fallback_to_cursor_agent(self):
        def _which(name):
            return "/usr/local/bin/cursor-agent" if name == "cursor-agent" else None

        with patch("shutil.which", side_effect=_which):
            assert _find_cursor_agent_binary() == "/usr/local/bin/cursor-agent"

    def test_find_binary_returns_none_when_missing(self):
        with patch("shutil.which", return_value=None):
            assert _find_cursor_agent_binary() is None

    def test_is_available_true(self):
        with patch("core.execution.cursor_agent._find_cursor_agent_binary", return_value="/usr/bin/agent"):
            assert is_cursor_agent_available() is True

    def test_is_available_false(self):
        with patch("core.execution.cursor_agent._find_cursor_agent_binary", return_value=None):
            assert is_cursor_agent_available() is False


class TestModelResolution:
    def test_strip_cursor_prefix(self, executor):
        assert executor._resolve_cursor_model() == "claude-4-sonnet"

    def test_no_prefix(self, executor):
        executor._model_config.model = "gpt-4.1"
        assert executor._resolve_cursor_model() == "gpt-4.1"


class TestWorkspace:
    def test_ensure_workspace_creates_dirs(self, executor):
        executor._ensure_workspace()
        assert executor._workspace.is_dir()
        assert (executor._workspace / ".cursor").is_dir()

    def test_write_mcp_config(self, executor):
        executor._ensure_workspace()
        executor._write_mcp_config()
        mcp_path = executor._workspace / ".cursor" / "mcp.json"
        assert mcp_path.exists()
        config = json.loads(mcp_path.read_text())
        assert "mcpServers" in config
        assert "aw" in config["mcpServers"]
        aw_conf = config["mcpServers"]["aw"]
        assert "-m" in aw_conf["args"]
        assert "core.mcp.server" in aw_conf["args"]
        assert "ANIMAWORKS_ANIMA_DIR" in aw_conf["env"]

    def test_workspace_location(self, executor, anima_dir):
        assert executor._workspace == anima_dir / ".cursor-workspace"


class TestBuildCommand:
    def test_build_command_structure(self, executor):
        with patch.object(executor, "_find_binary", return_value="/usr/bin/agent"):
            cmd = executor._build_command("hello")
        assert cmd[0] == "/usr/bin/agent"
        assert "-p" in cmd
        assert "--force" in cmd
        assert "--trust" in cmd
        assert "--approve-mcps" in cmd
        assert "--output-format" in cmd
        idx = cmd.index("--output-format")
        assert cmd[idx + 1] == "stream-json"
        assert "--stream-partial-output" in cmd
        assert "--model" in cmd
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "claude-4-sonnet"
        assert cmd[-1] == "hello"

    def test_build_command_empty_when_no_binary(self, executor):
        with patch.object(executor, "_find_binary", return_value=None):
            assert executor._build_command("test") == []


class TestBuildEnv:
    def test_includes_path_and_home(self, executor):
        env = executor._build_env()
        assert "PATH" in env
        assert "HOME" in env

    def test_no_api_key_injected(self, executor):
        executor._model_config.api_key = "test-anthropic-key"
        env = executor._build_env()
        assert "CURSOR_API_KEY" not in env or env.get("CURSOR_API_KEY") != "test-anthropic-key"


class TestNDJSONParsing:
    def test_parse_valid_json(self, executor):
        event = executor._parse_ndjson_event('{"type": "system", "subtype": "init"}')
        assert event == {"type": "system", "subtype": "init"}

    def test_parse_empty_line(self, executor):
        assert executor._parse_ndjson_event("") is None
        assert executor._parse_ndjson_event("  ") is None

    def test_parse_invalid_json(self, executor):
        assert executor._parse_ndjson_event("not json") is None

    def test_parse_whitespace_stripped(self, executor):
        event = executor._parse_ndjson_event('  {"type": "result"}  \n')
        assert event == {"type": "result"}


class TestToolRecordExtraction:
    def test_read_tool_call(self, executor):
        tc = {"readToolCall": {"args": {"path": "/tmp/test.py"}}, "id": "call_1"}
        record = executor._extract_tool_record(tc)
        assert record is not None
        assert record.tool_name == "Read"
        assert record.tool_id == "call_1"

    def test_write_tool_call(self, executor):
        tc = {"writeToolCall": {"args": {"path": "/tmp/out.py", "content": "..."}, "result": {"success": {}}}, "id": "call_2"}
        record = executor._extract_tool_record(tc)
        assert record is not None
        assert record.tool_name == "Write"

    def test_function_tool_call(self, executor):
        tc = {"function": {"name": "web_search", "arguments": '{"query": "test"}'}, "id": "call_3"}
        record = executor._extract_tool_record(tc)
        assert record is not None
        assert record.tool_name == "web_search"

    def test_mcp_aw_prefix_stripped(self, executor):
        tc = {"function": {"name": "mcp__aw__send_message", "arguments": "{}"}, "id": "call_4"}
        record = executor._extract_tool_record(tc)
        assert record is not None
        assert record.tool_name == "send_message"

    def test_error_flag(self, executor):
        tc = {"function": {"name": "test"}, "is_error": True, "id": "call_5"}
        record = executor._extract_tool_record(tc)
        assert record is not None
        assert record.is_error is True


# ── Execute tests ─────────────────────────────────────────────


def _make_ndjson_lines(events: list[dict]) -> bytes:
    return b"".join(json.dumps(e).encode() + b"\n" for e in events)


class TestExecute:
    @pytest.mark.asyncio
    async def test_not_installed(self, executor):
        with patch.object(executor, "_find_binary", return_value=None):
            result = await executor.execute(prompt="hello")
        assert "cursor-agent" in result.text.lower() or "not found" in result.text.lower()

    @pytest.mark.asyncio
    async def test_interrupted(self, executor):
        executor._interrupt_event = asyncio.Event()
        executor._interrupt_event.set()
        result = await executor.execute(prompt="hello")
        assert "interrupted" in result.text.lower()

    @pytest.mark.asyncio
    async def test_successful_execution(self, executor):
        events = [
            {"type": "system", "subtype": "init", "model": "claude-4-sonnet"},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello, "}]}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "world!"}]}},
            {"type": "result", "subtype": "success", "result": "Hello, world!", "duration_ms": 1234},
        ]
        stdout_data = _make_ndjson_lines(events)

        mock_proc = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stderr = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.wait = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")

        lines = stdout_data.split(b"\n")
        line_iter = iter(lines)
        mock_proc.stdout.readline = AsyncMock(side_effect=lambda: next(line_iter, b""))

        with (
            patch.object(executor, "_find_binary", return_value="/usr/bin/agent"),
            patch.object(executor, "_ensure_workspace"),
            patch.object(executor, "_write_mcp_config"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            result = await executor.execute(prompt="hello", system_prompt="You are helpful")

        assert result.text == "Hello, world!"
        assert isinstance(result, ExecutionResult)

    @pytest.mark.asyncio
    async def test_system_prompt_injected_as_prefix(self, executor):
        captured_cmd = []

        async def mock_create(*args, **kwargs):
            captured_cmd.extend(args)
            mock_proc = AsyncMock()
            mock_proc.stdout = AsyncMock()
            mock_proc.stderr = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.wait = AsyncMock()
            mock_proc.stderr.read = AsyncMock(return_value=b"")
            result_line = json.dumps({"type": "result", "result": "ok"}).encode() + b"\n"
            lines = iter([result_line, b""])
            mock_proc.stdout.readline = AsyncMock(side_effect=lambda: next(lines, b""))
            return mock_proc

        with (
            patch.object(executor, "_find_binary", return_value="/usr/bin/agent"),
            patch.object(executor, "_ensure_workspace"),
            patch.object(executor, "_write_mcp_config"),
            patch("asyncio.create_subprocess_exec", side_effect=mock_create),
        ):
            await executor.execute(prompt="do something", system_prompt="You are Alice")

        prompt_arg = captured_cmd[-1]
        assert "<system_context>" in prompt_arg
        assert "You are Alice" in prompt_arg
        assert "do something" in prompt_arg

    @pytest.mark.asyncio
    async def test_tool_records_extracted(self, executor):
        events = [
            {
                "type": "tool_call",
                "subtype": "completed",
                "tool_call": {
                    "readToolCall": {"args": {"path": "/tmp/test.py"}},
                    "id": "tc_1",
                },
            },
            {
                "type": "tool_call",
                "subtype": "completed",
                "tool_call": {
                    "function": {"name": "mcp__aw__search_memory", "arguments": '{"query": "test"}'},
                    "id": "tc_2",
                },
            },
            {"type": "result", "result": "done"},
        ]
        stdout_data = _make_ndjson_lines(events)

        mock_proc = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stderr = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.wait = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        lines = iter(stdout_data.split(b"\n"))
        mock_proc.stdout.readline = AsyncMock(side_effect=lambda: next(lines, b""))

        with (
            patch.object(executor, "_find_binary", return_value="/usr/bin/agent"),
            patch.object(executor, "_ensure_workspace"),
            patch.object(executor, "_write_mcp_config"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            result = await executor.execute(prompt="test")

        assert len(result.tool_call_records) == 2
        assert result.tool_call_records[0].tool_name == "Read"
        assert result.tool_call_records[1].tool_name == "search_memory"

    @pytest.mark.asyncio
    async def test_auth_error_detected(self, executor):
        mock_proc = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stderr = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.wait = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"Error: not authenticated, please run agent login")
        mock_proc.stdout.readline = AsyncMock(return_value=b"")

        with (
            patch.object(executor, "_find_binary", return_value="/usr/bin/agent"),
            patch.object(executor, "_ensure_workspace"),
            patch.object(executor, "_write_mcp_config"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            result = await executor.execute(prompt="hello")

        assert "login" in result.text.lower() or "認証" in result.text

    @pytest.mark.asyncio
    async def test_nonzero_exit_without_auth(self, executor):
        mock_proc = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stderr = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.wait = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"Some random error")
        mock_proc.stdout.readline = AsyncMock(return_value=b"")

        with (
            patch.object(executor, "_find_binary", return_value="/usr/bin/agent"),
            patch.object(executor, "_ensure_workspace"),
            patch.object(executor, "_write_mcp_config"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            result = await executor.execute(prompt="hello")

        assert "error" in result.text.lower()


# ── Mode D resolution test ────────────────────────────────────


class TestModeDResolution:
    def test_cursor_pattern_resolves_to_d(self):
        from core.config.model_mode import DEFAULT_MODEL_MODE_PATTERNS

        assert "cursor/*" in DEFAULT_MODEL_MODE_PATTERNS
        assert DEFAULT_MODEL_MODE_PATTERNS["cursor/*"] == "D"

    def test_resolve_execution_mode_cursor(self):
        from core.config.model_mode import resolve_execution_mode
        from core.config.models import load_config

        try:
            config = load_config()
        except Exception:
            pytest.skip("config not available in test environment")
        mode = resolve_execution_mode(config, "cursor/claude-4-sonnet")
        assert mode.upper() == "D"
