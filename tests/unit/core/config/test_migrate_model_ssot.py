"""Unit tests for core/config/migrate.py — Model Config SSoT migration.

Tests migrate_model_config_to_status.
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from core.config.migrate import migrate_model_config_to_status


# ── migrate_model_config_to_status ────────────────────────


class TestMigrateModelConfigToStatus:
    def test_migrates_model_from_config_to_status(self, tmp_path: Path) -> None:
        """config.json has model in animas, status.json empty → model copied to status.json."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        animas_dir = data_dir / "animas"
        alice_dir = animas_dir / "alice"
        alice_dir.mkdir(parents=True)

        config_data = {
            "version": 1,
            "credentials": {"anthropic": {"api_key": ""}},
            "anima_defaults": {"model": "claude-sonnet-4-6"},
            "animas": {
                "alice": {"model": "openai/gpt-4o", "supervisor": "bob"},
            },
        }
        config_path = data_dir / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        (alice_dir / "status.json").write_text(
            json.dumps({"enabled": True}),
            encoding="utf-8",
        )

        result = migrate_model_config_to_status(data_dir)

        assert result == {"alice": ["model"]}
        status_data = json.loads((alice_dir / "status.json").read_text(encoding="utf-8"))
        assert status_data["model"] == "openai/gpt-4o"
        assert status_data["enabled"] is True

    def test_status_json_wins_on_conflict(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Both have model with different values → status.json kept, warning logged."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        animas_dir = data_dir / "animas"
        alice_dir = animas_dir / "alice"
        alice_dir.mkdir(parents=True)

        config_data = {
            "version": 1,
            "credentials": {"anthropic": {"api_key": ""}},
            "animas": {"alice": {"model": "config-model"}},
        }
        config_path = data_dir / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        (alice_dir / "status.json").write_text(
            json.dumps({"model": "status-model"}),
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING):
            result = migrate_model_config_to_status(data_dir)

        assert result == {"alice": []}
        status_data = json.loads((alice_dir / "status.json").read_text(encoding="utf-8"))
        assert status_data["model"] == "status-model"
        assert "Conflict" in caplog.text or "conflict" in caplog.text.lower()

    def test_cleans_config_json_animas(self, tmp_path: Path) -> None:
        """After migration, config.json animas entry only has supervisor/speciality."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        animas_dir = data_dir / "animas"
        alice_dir = animas_dir / "alice"
        alice_dir.mkdir(parents=True)

        config_data = {
            "version": 1,
            "credentials": {"anthropic": {"api_key": ""}},
            "animas": {
                "alice": {
                    "model": "openai/gpt-4o",
                    "credential": "anthropic",
                    "supervisor": "bob",
                    "speciality": "engineer",
                },
            },
        }
        config_path = data_dir / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        (alice_dir / "status.json").write_text(json.dumps({}), encoding="utf-8")

        migrate_model_config_to_status(data_dir)

        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["animas"]["alice"] == {"supervisor": "bob", "speciality": "engineer"}

    def test_dry_run_no_changes(self, tmp_path: Path) -> None:
        """dry_run=True → no files written."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        animas_dir = data_dir / "animas"
        alice_dir = animas_dir / "alice"
        alice_dir.mkdir(parents=True)

        config_data = {
            "version": 1,
            "credentials": {"anthropic": {"api_key": ""}},
            "animas": {"alice": {"model": "openai/gpt-4o"}},
        }
        config_path = data_dir / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        original_status = {"enabled": True}
        status_path = alice_dir / "status.json"
        status_path.write_text(json.dumps(original_status), encoding="utf-8")

        result = migrate_model_config_to_status(data_dir, dry_run=True)

        assert result == {"alice": ["model"]}
        assert json.loads(status_path.read_text(encoding="utf-8")) == original_status
        config_after = json.loads(config_path.read_text(encoding="utf-8"))
        assert config_after["animas"]["alice"].get("model") == "openai/gpt-4o"

    def test_no_config_json(self, tmp_path: Path) -> None:
        """Missing config.json → empty result."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        result = migrate_model_config_to_status(data_dir)
        assert result == {}

    def test_multiple_animas(self, tmp_path: Path) -> None:
        """Multiple animas migrated."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        animas_dir = data_dir / "animas"
        alice_dir = animas_dir / "alice"
        bob_dir = animas_dir / "bob"
        alice_dir.mkdir(parents=True)
        bob_dir.mkdir(parents=True)

        config_data = {
            "version": 1,
            "credentials": {"anthropic": {"api_key": ""}},
            "animas": {
                "alice": {"model": "claude-sonnet"},
                "bob": {"model": "openai/gpt-4o", "credential": "anthropic"},
            },
        }
        config_path = data_dir / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        (alice_dir / "status.json").write_text(json.dumps({}), encoding="utf-8")
        (bob_dir / "status.json").write_text(json.dumps({}), encoding="utf-8")

        result = migrate_model_config_to_status(data_dir)

        assert set(result.keys()) == {"alice", "bob"}
        assert "model" in result["alice"]
        assert "model" in result["bob"]
        assert "credential" in result["bob"]

        alice_status = json.loads((alice_dir / "status.json").read_text(encoding="utf-8"))
        bob_status = json.loads((bob_dir / "status.json").read_text(encoding="utf-8"))
        assert alice_status["model"] == "claude-sonnet"
        assert bob_status["model"] == "openai/gpt-4o"
        assert bob_status["credential"] == "anthropic"
