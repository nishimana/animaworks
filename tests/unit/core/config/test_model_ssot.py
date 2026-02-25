"""Unit tests for core/config/models.py — Model Config SSoT helpers.

Tests update_injection_model and update_status_model.
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config.models import update_injection_model, update_status_model


# ── update_injection_model ─────────────────────────────────


class TestUpdateInjectionModel:
    def test_updates_model_line(self, tmp_path: Path) -> None:
        """Create injection.md with model line, call update_injection_model, verify change."""
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        injection_path = anima_dir / "injection.md"
        injection_path.write_text(
            "- **モデル**: Old Model\n- **役割**: engineer\n",
            encoding="utf-8",
        )
        result = update_injection_model(anima_dir, "New Model")
        assert result is True
        content = injection_path.read_text(encoding="utf-8")
        assert "- **モデル**: New Model" in content
        assert "- **役割**: engineer" in content

    def test_no_matching_line_returns_false(self, tmp_path: Path) -> None:
        """injection.md without model line → returns False, file unchanged."""
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        original = "- **役割**: engineer\n- **上司**: bob\n"
        injection_path = anima_dir / "injection.md"
        injection_path.write_text(original, encoding="utf-8")
        result = update_injection_model(anima_dir, "New Model")
        assert result is False
        assert injection_path.read_text(encoding="utf-8") == original

    def test_no_injection_file_returns_false(self, tmp_path: Path) -> None:
        """No injection.md → returns False."""
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        result = update_injection_model(anima_dir, "New Model")
        assert result is False

    def test_preserves_other_content(self, tmp_path: Path) -> None:
        """Other lines remain intact after update."""
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        injection_path = anima_dir / "injection.md"
        injection_path.write_text(
            "# 役割\n\n- **モデル**: claude-sonnet\n"
            "- **役割**: manager\n"
            "- **上司**: bob\n",
            encoding="utf-8",
        )
        result = update_injection_model(anima_dir, "openai/gpt-4o")
        assert result is True
        content = injection_path.read_text(encoding="utf-8")
        assert "- **モデル**: openai/gpt-4o" in content
        assert "- **役割**: manager" in content
        assert "- **上司**: bob" in content


# ── update_status_model ────────────────────────────────────


class TestUpdateStatusModel:
    def test_updates_model_in_status_json(self, tmp_path: Path) -> None:
        """Create status.json with model field, update model, verify."""
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        status_path = anima_dir / "status.json"
        status_path.write_text(
            json.dumps({"model": "claude-sonnet", "enabled": True}),
            encoding="utf-8",
        )
        update_status_model(anima_dir, model="openai/gpt-4o")
        data = json.loads(status_path.read_text(encoding="utf-8"))
        assert data["model"] == "openai/gpt-4o"
        assert data["enabled"] is True

    def test_updates_credential(self, tmp_path: Path) -> None:
        """Update credential only."""
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        status_path = anima_dir / "status.json"
        status_path.write_text(
            json.dumps({"model": "claude-sonnet", "credential": "anthropic"}),
            encoding="utf-8",
        )
        update_status_model(anima_dir, credential="openai")
        data = json.loads(status_path.read_text(encoding="utf-8"))
        assert data["model"] == "claude-sonnet"
        assert data["credential"] == "openai"

    def test_updates_both(self, tmp_path: Path) -> None:
        """Update both model and credential."""
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        status_path = anima_dir / "status.json"
        status_path.write_text(
            json.dumps({"model": "old", "credential": "old_cred"}),
            encoding="utf-8",
        )
        update_status_model(anima_dir, model="new-model", credential="new_cred")
        data = json.loads(status_path.read_text(encoding="utf-8"))
        assert data["model"] == "new-model"
        assert data["credential"] == "new_cred"

    def test_no_status_json_raises(self, tmp_path: Path) -> None:
        """FileNotFoundError when no status.json."""
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="status.json not found"):
            update_status_model(anima_dir, model="new-model")

    def test_preserves_other_fields(self, tmp_path: Path) -> None:
        """Other fields (enabled, role, etc.) remain intact."""
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        status_path = anima_dir / "status.json"
        status_path.write_text(
            json.dumps({
                "model": "old-model",
                "enabled": True,
                "role": "engineer",
                "supervisor": "bob",
            }),
            encoding="utf-8",
        )
        update_status_model(anima_dir, model="new-model")
        data = json.loads(status_path.read_text(encoding="utf-8"))
        assert data["model"] == "new-model"
        assert data["enabled"] is True
        assert data["role"] == "engineer"
        assert data["supervisor"] == "bob"
