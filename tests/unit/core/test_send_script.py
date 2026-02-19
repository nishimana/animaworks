"""Unit tests for the send wrapper script in anima templates."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from core.anima_factory import BLANK_TEMPLATE_DIR


class TestSendScript:
    def test_send_script_exists_in_blank_template(self):
        """The send script must exist in the blank template directory."""
        send_path = BLANK_TEMPLATE_DIR / "send"
        assert send_path.exists(), f"Missing send script: {send_path}"

    def test_send_script_has_shebang(self):
        """The send script must have a proper shebang line."""
        content = (BLANK_TEMPLATE_DIR / "send").read_text(encoding="utf-8")
        assert content.startswith("#!/")

    def test_send_script_uses_animaworks_anima_dir(self):
        """The send script should derive anima name from ANIMAWORKS_ANIMA_DIR env var."""
        content = (BLANK_TEMPLATE_DIR / "send").read_text(encoding="utf-8")
        assert "ANIMAWORKS_ANIMA_DIR" in content
        # Should fallback to pwd when env var is not set
        assert "$(pwd)" in content

    def test_send_script_cwd_independent(self):
        """The SELF variable should NOT depend solely on cwd."""
        content = (BLANK_TEMPLATE_DIR / "send").read_text(encoding="utf-8")
        # The old bug: SELF="$(basename "$(pwd)")"
        # This should NOT be present
        assert 'SELF="$(basename "$(pwd)")"' not in content

    def test_send_script_calls_main_py_send(self):
        """The send script must invoke main.py send subcommand."""
        content = (BLANK_TEMPLATE_DIR / "send").read_text(encoding="utf-8")
        assert "send" in content
        assert "main.py" in content or "$MAIN" in content
