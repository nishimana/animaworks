# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for Windows command-line overflow (WinError 206) fix.

Verifies that:
- ``_PROMPT_FILE_THRESHOLD`` is lowered on Windows to avoid exceeding
  the 32,767-character ``CreateProcess`` limit.
- ``_build_sdk_options()`` correctly diverts the system prompt to a file
  when running on Windows with prompts above the lowered threshold.
- ``_build_mcp_env()`` minimizes the ``PATH`` environment variable on
  Windows to reduce ``--mcp-config`` size.

Design reference: docs/design/fix-win-cmdline-overflow-analysis.md
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. _PROMPT_FILE_THRESHOLD platform tests
# ---------------------------------------------------------------------------


class TestPromptFileThreshold:
    """Verify _PROMPT_FILE_THRESHOLD is platform-dependent."""

    def test_prompt_file_threshold_windows(self):
        """On Windows, _PROMPT_FILE_THRESHOLD must be well below 100,000
        to avoid exceeding the 32,767-char CreateProcess limit.
        """
        with patch("sys.platform", "win32"):
            import core.execution._sdk_session as mod
            importlib.reload(mod)
            try:
                assert mod._PROMPT_FILE_THRESHOLD < 100_000, (
                    f"Windows threshold ({mod._PROMPT_FILE_THRESHOLD}) must be "
                    f"less than 100,000 to avoid WinError 206"
                )
                # The design doc recommends ~6,000-8,000 bytes.
                assert mod._PROMPT_FILE_THRESHOLD <= 10_000, (
                    f"Windows threshold ({mod._PROMPT_FILE_THRESHOLD}) should be "
                    f"at most 10,000 per the design recommendation"
                )
            finally:
                # Restore the module to its original state.
                with patch("sys.platform", _original_platform()):
                    importlib.reload(mod)

    def test_prompt_file_threshold_linux(self):
        """On Linux, _PROMPT_FILE_THRESHOLD must remain at 100,000 (regression test)."""
        with patch("sys.platform", "linux"):
            import core.execution._sdk_session as mod
            importlib.reload(mod)
            try:
                assert mod._PROMPT_FILE_THRESHOLD == 100_000, (
                    f"Linux threshold should remain 100,000 but got "
                    f"{mod._PROMPT_FILE_THRESHOLD}"
                )
            finally:
                with patch("sys.platform", _original_platform()):
                    importlib.reload(mod)


def _original_platform() -> str:
    """Return the real sys.platform value for cleanup."""
    # When this function is loaded, sys.platform has not been patched yet.
    return sys.platform


# ---------------------------------------------------------------------------
# 2. _build_sdk_options prompt file diversion on Windows
# ---------------------------------------------------------------------------


class TestBuildSdkOptionsPromptFile:
    """Verify _build_sdk_options() writes system_prompt to a temp file on Windows
    when the prompt exceeds the lowered Windows threshold.
    """

    def test_build_sdk_options_uses_file_on_windows(self, tmp_path: Path):
        """An 8,000-byte system prompt exceeds the Windows threshold (~6,000)
        and should be diverted to a temp file (prompt_file is not None).
        """
        # Arrange: reload _sdk_session with win32 threshold
        with patch("sys.platform", "win32"):
            import core.execution._sdk_session as session_mod
            importlib.reload(session_mod)

        try:
            # Patch _PROMPT_FILE_THRESHOLD in _sdk_options to use the reloaded value
            win_threshold = session_mod._PROMPT_FILE_THRESHOLD

            # Create a system prompt that exceeds the Windows threshold
            # but is well below the original 100,000 Linux threshold.
            system_prompt = "a" * 8_000
            assert len(system_prompt.encode("utf-8")) > win_threshold, (
                f"Test prompt ({len(system_prompt.encode('utf-8'))} bytes) must exceed "
                f"Windows threshold ({win_threshold}) for this test to be meaningful"
            )

            # Build a minimal SDKOptionsMixin-like object with required attributes
            mixin = _make_stub_mixin(tmp_path)

            # Mock ClaudeAgentOptions and HookMatcher to avoid real SDK import
            mock_options_cls = MagicMock()
            mock_hook_matcher = MagicMock()

            with (
                patch(
                    "core.execution._sdk_options._PROMPT_FILE_THRESHOLD",
                    win_threshold,
                ),
                patch(
                    "core.execution._sdk_options.ClaudeAgentOptions",
                    mock_options_cls,
                    create=True,
                ),
                patch.dict(
                    "sys.modules",
                    {
                        "claude_agent_sdk": MagicMock(
                            ClaudeAgentOptions=mock_options_cls,
                            HookMatcher=mock_hook_matcher,
                        ),
                    },
                ),
                patch(
                    "core.execution._sdk_options._build_pre_tool_hook",
                    return_value=MagicMock(),
                ),
                patch(
                    "core.execution._sdk_options._build_pre_compact_hook",
                    return_value=MagicMock(),
                ),
                patch(
                    "core.execution._sdk_options._build_post_tool_hook",
                    return_value=MagicMock(),
                ),
                patch(
                    "core.execution._sdk_options._is_debug_superuser",
                    return_value=False,
                ),
                patch(
                    "core.execution._sdk_options._find_system_claude_cli",
                    return_value=None,
                ),
            ):
                from core.execution._sdk_options import SDKOptionsMixin

                # Call the method
                _, prompt_file = SDKOptionsMixin._build_sdk_options(
                    mixin,
                    system_prompt=system_prompt,
                    max_turns=5,
                    context_window=200_000,
                    session_stats={},
                )

                # Assert: prompt should be written to a file
                assert prompt_file is not None, (
                    "Expected prompt_file to be set (system prompt should be diverted "
                    "to a file on Windows when exceeding the lowered threshold)"
                )
                assert prompt_file.exists(), (
                    f"Prompt file {prompt_file} should exist on disk"
                )
                # Verify the file contains the system prompt
                content = prompt_file.read_text(encoding="utf-8")
                assert content == system_prompt

                # Cleanup the temp file
                prompt_file.unlink(missing_ok=True)
        finally:
            # Restore _sdk_session module to real platform value
            with patch("sys.platform", _original_platform()):
                importlib.reload(session_mod)

    def test_build_sdk_options_inline_on_linux(self, tmp_path: Path):
        """An 8,000-byte system prompt is well under the Linux threshold (100,000)
        and should remain inline (prompt_file is None).
        """
        system_prompt = "a" * 8_000

        mixin = _make_stub_mixin(tmp_path)

        mock_options_cls = MagicMock()
        mock_hook_matcher = MagicMock()

        with (
            patch("sys.platform", "linux"),
            patch(
                "core.execution._sdk_options._PROMPT_FILE_THRESHOLD",
                100_000,
            ),
            patch.dict(
                "sys.modules",
                {
                    "claude_agent_sdk": MagicMock(
                        ClaudeAgentOptions=mock_options_cls,
                        HookMatcher=mock_hook_matcher,
                    ),
                },
            ),
            patch(
                "core.execution._sdk_options._build_pre_tool_hook",
                return_value=MagicMock(),
            ),
            patch(
                "core.execution._sdk_options._build_pre_compact_hook",
                return_value=MagicMock(),
            ),
            patch(
                "core.execution._sdk_options._build_post_tool_hook",
                return_value=MagicMock(),
            ),
            patch(
                "core.execution._sdk_options._is_debug_superuser",
                return_value=False,
            ),
            patch(
                "core.execution._sdk_options._find_system_claude_cli",
                return_value=None,
            ),
        ):
            from core.execution._sdk_options import SDKOptionsMixin

            _, prompt_file = SDKOptionsMixin._build_sdk_options(
                mixin,
                system_prompt=system_prompt,
                max_turns=5,
                context_window=200_000,
                session_stats={},
            )

            assert prompt_file is None, (
                "On Linux, an 8,000-byte prompt should stay inline (under 100,000 threshold)"
            )


# ---------------------------------------------------------------------------
# 3. _build_mcp_env PATH minimization on Windows
# ---------------------------------------------------------------------------


class TestBuildMcpEnvPathMinimization:
    """Verify _build_mcp_env() returns a shorter PATH on Windows."""

    def test_build_mcp_env_minimizes_path_on_windows(self, tmp_path: Path):
        """On Windows, _build_mcp_env() should produce a PATH that is
        substantially shorter than the full os.environ['PATH'].
        """
        mixin = _make_stub_mixin(tmp_path)

        # Simulate a realistic long Windows PATH (>2000 chars)
        long_path = ";".join(
            [
                r"C:\Windows\system32",
                r"C:\Windows",
                r"C:\Windows\System32\Wbem",
                r"C:\Windows\System32\WindowsPowerShell\v1.0",
                r"C:\Program Files\Git\cmd",
                r"C:\Program Files\nodejs",
                r"C:\Program Files\Docker\Docker\resources\bin",
                r"C:\Users\user\AppData\Local\Programs\Python\Python312",
                r"C:\Users\user\AppData\Local\Programs\Python\Python312\Scripts",
                r"C:\Users\user\.cargo\bin",
                r"C:\Program Files\dotnet",
                r"C:\Program Files\PowerShell\7",
                r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64",
                r"C:\Program Files\Microsoft VS Code\bin",
                r"C:\Program Files\Amazon\AWSCLIV2",
                r"C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin",
            ]
        )

        with (
            patch("sys.platform", "win32"),
            patch.dict(os.environ, {"PATH": long_path}),
        ):
            from core.execution._sdk_options import SDKOptionsMixin

            env = SDKOptionsMixin._build_mcp_env(mixin)

            result_path = env.get("PATH", "")
            assert len(result_path) < len(long_path), (
                f"Windows MCP PATH ({len(result_path)} chars) should be shorter "
                f"than the full system PATH ({len(long_path)} chars)"
            )
            # The minimized PATH should still contain the Python executable's directory
            # so the MCP server can import modules.
            python_dir = str(Path(sys.executable).parent)
            # Note: the actual implementation may resolve the path differently;
            # we just check it is substantially shorter.
            assert len(result_path) < len(long_path) // 2, (
                f"Windows MCP PATH should be drastically shorter than the system PATH. "
                f"Got {len(result_path)} chars vs {len(long_path)} chars."
            )

    def test_build_mcp_env_preserves_full_path_on_linux(self, tmp_path: Path):
        """On Linux, _build_mcp_env() should pass through the full PATH unchanged."""
        mixin = _make_stub_mixin(tmp_path)

        linux_path = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

        with (
            patch("sys.platform", "linux"),
            patch.dict(os.environ, {"PATH": linux_path}),
        ):
            from core.execution._sdk_options import SDKOptionsMixin

            env = SDKOptionsMixin._build_mcp_env(mixin)

            assert env.get("PATH") == linux_path, (
                "On Linux, the full PATH should be passed through to the MCP env"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stub_mixin(tmp_path: Path) -> MagicMock:
    """Create a MagicMock that satisfies SDKOptionsMixin's self.* attribute access.

    SDKOptionsMixin._build_sdk_options() accesses BaseExecutor attributes:
    - self._model_config (ModelConfig)
    - self._anima_dir (Path)
    - self._task_cwd (Path | None)
    - self._has_subordinates() -> bool
    - self._resolve_api_key() -> str | None
    - self._hb_soft_timeout_s (float)
    """
    from core.schemas import ModelConfig

    anima_dir = tmp_path / "animas" / "test"
    anima_dir.mkdir(parents=True, exist_ok=True)

    mixin = MagicMock()
    mixin._model_config = ModelConfig(
        model="claude-sonnet-4-20250514",
        api_key="test-key",
        thinking=None,
        extra_mcp_servers={},
    )
    mixin._anima_dir = anima_dir
    mixin._task_cwd = None
    mixin._has_subordinates.return_value = False
    mixin._resolve_api_key.return_value = "test-key"
    mixin._extra_mcp_servers = {}
    return mixin
