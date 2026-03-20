"""Unit tests for _kill_zombie_runners Windows compatibility."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from core.supervisor.manager import ProcessSupervisor


@pytest.fixture
def supervisor(tmp_path: Path) -> ProcessSupervisor:
    """Create a minimal ProcessSupervisor with run dir."""
    return ProcessSupervisor(
        animas_dir=tmp_path / "animas",
        shared_dir=tmp_path / "shared",
        run_dir=tmp_path / "run",
        log_dir=tmp_path / "logs",
    )


class TestKillZombieRunnersWindows:
    """Tests for _kill_zombie_runners on Windows (os.kill(pid, 0) compat)."""

    def test_stale_pidfile_cleaned_up(self, supervisor: ProcessSupervisor):
        """Stale PID files (dead process) should be cleaned up without error."""
        pid_dir = supervisor.run_dir / "animas"
        pid_dir.mkdir(parents=True)
        (pid_dir / "test-anima.pid").write_text("999999999", encoding="utf-8")

        # Should not raise on any platform
        supervisor._kill_zombie_runners(["test-anima"])

        # PID file should be cleaned up
        assert not (pid_dir / "test-anima.pid").exists()

    def test_current_process_detected_alive(self, supervisor: ProcessSupervisor):
        """A PID file pointing to a live process should trigger kill and cleanup."""
        pid_dir = supervisor.run_dir / "animas"
        pid_dir.mkdir(parents=True)
        (pid_dir / "test-anima.pid").write_text(str(os.getpid()), encoding="utf-8")

        # Mock the kill to avoid killing the test process itself
        with patch("core.supervisor.manager.subprocess.run") as mock_run, \
             patch("os.kill"):
            mock_run.return_value = type("Result", (), {"returncode": 0})()
            supervisor._kill_zombie_runners(["test-anima"])

        # PID file should be cleaned up after killing
        assert not (pid_dir / "test-anima.pid").exists()

    def test_no_pidfiles(self, supervisor: ProcessSupervisor):
        """No crash when pid directory is empty or missing."""
        # Missing directory
        supervisor._kill_zombie_runners(["test-anima"])

        # Empty directory
        pid_dir = supervisor.run_dir / "animas"
        pid_dir.mkdir(parents=True)
        supervisor._kill_zombie_runners(["test-anima"])

    def test_lock_files_cleaned(self, supervisor: ProcessSupervisor):
        """Stale lock files should be removed."""
        pid_dir = supervisor.run_dir / "animas"
        pid_dir.mkdir(parents=True)
        (pid_dir / "test-anima.lock").write_text("", encoding="utf-8")

        supervisor._kill_zombie_runners(["test-anima"])

        assert not (pid_dir / "test-anima.lock").exists()
