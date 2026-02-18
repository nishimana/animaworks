from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.

"""Integration tests for Phase 3: RAG index update + success/failure tracking."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.schemas import SkillMeta


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    """Create a minimal anima directory."""
    d = tmp_path / "animas" / "test-anima"
    for sub in ("episodes", "knowledge", "procedures", "skills", "state"):
        (d / sub).mkdir(parents=True)
    return d


@pytest.fixture
def memory(anima_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a MemoryManager that skips RAG initialization."""
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(anima_dir.parent.parent))

    data_dir = anima_dir.parent.parent
    (data_dir / "company").mkdir(parents=True, exist_ok=True)
    (data_dir / "common_skills").mkdir(parents=True, exist_ok=True)
    (data_dir / "common_knowledge").mkdir(parents=True, exist_ok=True)
    (data_dir / "shared" / "users").mkdir(parents=True, exist_ok=True)

    from core.memory.manager import MemoryManager

    return MemoryManager(anima_dir)


# ── 3-1: RAG index auto-update after write_memory_file ───


class TestRAGIndexAutoUpdate:
    """Test that writing to skills/ or procedures/ triggers RAG re-indexing."""

    def test_skill_write_triggers_index(self, memory, anima_dir: Path) -> None:
        """Writing a skill file should attempt to index it."""
        # Set up a mock indexer
        mock_indexer = MagicMock()
        mock_indexer.index_file = MagicMock(return_value=1)
        memory._indexer = mock_indexer
        memory._indexer_initialized = True

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle("write_memory_file", {
            "path": "skills/test-skill.md",
            "content": "---\ndescription: test\n---\n\n# Test Skill",
        })

        assert "Written to" in result
        mock_indexer.index_file.assert_called_once()
        call_args = mock_indexer.index_file.call_args
        assert call_args[1]["memory_type"] == "skills"
        assert call_args[1]["force"] is True

    def test_procedure_write_triggers_index(self, memory, anima_dir: Path) -> None:
        """Writing a procedure file should attempt to index it."""
        mock_indexer = MagicMock()
        mock_indexer.index_file = MagicMock(return_value=1)
        memory._indexer = mock_indexer
        memory._indexer_initialized = True

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle("write_memory_file", {
            "path": "procedures/deploy.md",
            "content": "---\ndescription: deploy\n---\n\n# Deploy",
        })

        assert "Written to" in result
        mock_indexer.index_file.assert_called_once()
        call_args = mock_indexer.index_file.call_args
        assert call_args[1]["memory_type"] == "procedures"

    def test_non_skill_write_skips_index(self, memory, anima_dir: Path) -> None:
        """Writing to knowledge/ should not trigger skill/procedure indexing."""
        mock_indexer = MagicMock()
        memory._indexer = mock_indexer
        memory._indexer_initialized = True

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        handler.handle("write_memory_file", {
            "path": "knowledge/notes.md",
            "content": "# Some knowledge",
        })

        mock_indexer.index_file.assert_not_called()

    def test_index_failure_does_not_break_write(self, memory, anima_dir: Path) -> None:
        """RAG index failure should be logged but not block the write."""
        mock_indexer = MagicMock()
        mock_indexer.index_file = MagicMock(side_effect=RuntimeError("index error"))
        memory._indexer = mock_indexer
        memory._indexer_initialized = True

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle("write_memory_file", {
            "path": "procedures/failing.md",
            "content": "---\ndescription: test\n---\n\n# Test",
        })

        assert "Written to" in result  # write still succeeds


# ── 3-2: report_procedure_outcome tool ───────────────────


class TestReportProcedureOutcome:
    """Test the report_procedure_outcome tool handler."""

    def test_success_increments_count(self, memory, anima_dir: Path) -> None:
        """Reporting success should increment success_count and update confidence."""
        # Create procedure with initial metadata
        memory.write_procedure_with_meta(
            Path("deploy.md"),
            "# Deploy Steps\n\n1. Pull\n2. Build",
            {
                "description": "deploy procedure",
                "success_count": 3,
                "failure_count": 1,
                "confidence": 0.75,
                "last_used": None,
            },
        )

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle("report_procedure_outcome", {
            "path": "procedures/deploy.md",
            "success": True,
            "notes": "Deployed successfully",
        })

        assert "成功" in result
        assert "confidence: 0.80" in result

        # Verify metadata was updated
        meta = memory.read_procedure_metadata(
            anima_dir / "procedures" / "deploy.md",
        )
        assert meta["success_count"] == 4
        assert meta["failure_count"] == 1
        assert abs(meta["confidence"] - 0.8) < 0.01
        assert meta["last_used"] is not None

    def test_failure_increments_count(self, memory, anima_dir: Path) -> None:
        """Reporting failure should increment failure_count and lower confidence."""
        memory.write_procedure_with_meta(
            Path("backup.md"),
            "# Backup",
            {
                "description": "backup procedure",
                "success_count": 2,
                "failure_count": 0,
                "confidence": 1.0,
            },
        )

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle("report_procedure_outcome", {
            "path": "procedures/backup.md",
            "success": False,
            "notes": "Backup failed due to disk full",
        })

        assert "失敗" in result
        meta = memory.read_procedure_metadata(
            anima_dir / "procedures" / "backup.md",
        )
        assert meta["failure_count"] == 1
        assert abs(meta["confidence"] - 2 / 3) < 0.01

    def test_missing_file_returns_error(self, memory, anima_dir: Path) -> None:
        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle("report_procedure_outcome", {
            "path": "procedures/nonexistent.md",
            "success": True,
        })
        assert "error" in result.lower() or "not found" in result.lower()

    def test_empty_path_returns_error(self, memory, anima_dir: Path) -> None:
        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle("report_procedure_outcome", {
            "path": "",
            "success": True,
        })
        assert "error" in result.lower()

    def test_body_content_preserved(self, memory, anima_dir: Path) -> None:
        """The procedure body should be preserved when metadata is updated."""
        body_text = "# Complex Procedure\n\n1. Step one\n2. Step two\n3. Step three"
        memory.write_procedure_with_meta(
            Path("complex.md"),
            body_text,
            {"description": "complex", "success_count": 0, "failure_count": 0, "confidence": 0.5},
        )

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        handler.handle("report_procedure_outcome", {
            "path": "procedures/complex.md",
            "success": True,
        })

        # Read the file content and verify body is intact
        content = memory.read_procedure_content(
            anima_dir / "procedures" / "complex.md",
        )
        assert "Step one" in content
        assert "Step two" in content
        assert "Step three" in content


# ── 3-2: Schema registration ────────────────────────────


class TestProcedureToolSchema:
    """Test that the procedure outcome tool is registered in schemas."""

    def test_schema_in_build_tool_list(self) -> None:
        from core.tooling.schemas import build_tool_list

        tools = build_tool_list()
        names = {t["name"] for t in tools}
        assert "report_procedure_outcome" in names

    def test_schema_has_required_fields(self) -> None:
        from core.tooling.schemas import PROCEDURE_TOOLS

        schema = PROCEDURE_TOOLS[0]
        assert schema["name"] == "report_procedure_outcome"
        params = schema["parameters"]
        assert "path" in params["properties"]
        assert "success" in params["properties"]
        assert "notes" in params["properties"]
        assert set(params["required"]) == {"path", "success"}


# ── 3-3: Auto-outcome tracking in conversation.py ────────


class TestAutoOutcomeTracking:
    """Test automatic procedure outcome tracking during session finalization."""

    def test_success_auto_tracked(self, memory, anima_dir: Path) -> None:
        """Normal session completion should record success for injected procedures."""
        from core.memory.conversation import ConversationMemory, ConversationTurn
        from core.prompt.builder import _last_injected_procedures
        from core.schemas import ModelConfig

        # Create a procedure
        proc_path = anima_dir / "procedures" / "deploy.md"
        memory.write_procedure_with_meta(
            proc_path,
            "# Deploy Steps",
            {"description": "deploy", "success_count": 0, "failure_count": 0, "confidence": 0.5},
        )

        # Simulate injected procedures
        _last_injected_procedures["test-anima"] = [proc_path]

        # Create conversation memory and simulate normal turns
        conv = ConversationMemory(anima_dir, ModelConfig())
        normal_turns = [
            ConversationTurn(role="human", content="Deploy the app please"),
            ConversationTurn(role="assistant", content="I'll deploy the app now. Done, everything is running."),
        ]

        conv._auto_track_procedure_outcomes(memory, normal_turns)

        meta = memory.read_procedure_metadata(proc_path)
        assert meta["success_count"] == 1
        assert meta["failure_count"] == 0
        assert meta["confidence"] == 1.0
        assert meta["last_used"] is not None

    def test_failure_auto_tracked(self, memory, anima_dir: Path) -> None:
        """Session with errors should record failure for injected procedures."""
        from core.memory.conversation import ConversationMemory, ConversationTurn
        from core.prompt.builder import _last_injected_procedures
        from core.schemas import ModelConfig

        proc_path = anima_dir / "procedures" / "backup.md"
        memory.write_procedure_with_meta(
            proc_path,
            "# Backup Steps",
            {"description": "backup", "success_count": 2, "failure_count": 0, "confidence": 1.0},
        )

        _last_injected_procedures["test-anima"] = [proc_path]

        conv = ConversationMemory(anima_dir, ModelConfig())
        error_turns = [
            ConversationTurn(role="human", content="Run the backup"),
            ConversationTurn(role="assistant", content="I encountered an error: disk space is insufficient"),
        ]

        conv._auto_track_procedure_outcomes(memory, error_turns)

        meta = memory.read_procedure_metadata(proc_path)
        assert meta["success_count"] == 2
        assert meta["failure_count"] == 1
        assert abs(meta["confidence"] - 2 / 3) < 0.01

    def test_no_injected_procedures_noop(self, memory, anima_dir: Path) -> None:
        """When no procedures were injected, nothing should happen."""
        from core.memory.conversation import ConversationMemory, ConversationTurn
        from core.prompt.builder import _last_injected_procedures
        from core.schemas import ModelConfig

        # Ensure no injected procedures
        _last_injected_procedures.pop("test-anima", None)

        conv = ConversationMemory(anima_dir, ModelConfig())
        turns = [
            ConversationTurn(role="human", content="Hello"),
            ConversationTurn(role="assistant", content="Hi!"),
        ]

        # Should not raise
        conv._auto_track_procedure_outcomes(memory, turns)

    def test_clears_tracking_after_processing(self, memory, anima_dir: Path) -> None:
        """After processing, the tracking dict should be cleared for that anima."""
        from core.memory.conversation import ConversationMemory, ConversationTurn
        from core.prompt.builder import _last_injected_procedures
        from core.schemas import ModelConfig

        proc_path = anima_dir / "procedures" / "test.md"
        memory.write_procedure_with_meta(
            proc_path,
            "# Test",
            {"description": "test", "success_count": 0, "failure_count": 0, "confidence": 0.5},
        )

        _last_injected_procedures["test-anima"] = [proc_path]

        conv = ConversationMemory(anima_dir, ModelConfig())
        conv._auto_track_procedure_outcomes(memory, [
            ConversationTurn(role="human", content="test"),
            ConversationTurn(role="assistant", content="ok"),
        ])

        assert "test-anima" not in _last_injected_procedures

    def test_japanese_error_detected(self, memory, anima_dir: Path) -> None:
        """Japanese error keywords should also trigger failure tracking."""
        from core.memory.conversation import ConversationMemory, ConversationTurn
        from core.prompt.builder import _last_injected_procedures
        from core.schemas import ModelConfig

        proc_path = anima_dir / "procedures" / "jp-proc.md"
        memory.write_procedure_with_meta(
            proc_path,
            "# 手順",
            {"description": "japanese", "success_count": 0, "failure_count": 0, "confidence": 0.5},
        )

        _last_injected_procedures["test-anima"] = [proc_path]

        conv = ConversationMemory(anima_dir, ModelConfig())
        conv._auto_track_procedure_outcomes(memory, [
            ConversationTurn(role="human", content="実行してください"),
            ConversationTurn(role="assistant", content="処理を実行しましたが失敗しました。"),
        ])

        meta = memory.read_procedure_metadata(proc_path)
        assert meta["failure_count"] == 1
