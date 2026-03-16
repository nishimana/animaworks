from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CreateAnimaMixin — anima creation from character sheet."""

import json as _json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.tooling.handler_base import _error_result

if TYPE_CHECKING:
    pass

logger = logging.getLogger("animaworks.tool_handler")


class CreateAnimaMixin:
    """Mixin for create_anima tool handler."""

    # Declared for type-checker visibility
    _anima_dir: Path
    _anima_name: str

    def _handle_create_anima(self, args: dict[str, Any]) -> str:
        """Create a new anima from a character sheet via anima_factory."""
        from core.anima_factory import create_from_md
        from core.paths import get_animas_dir, get_data_dir

        content = args.get("character_sheet_content")
        sheet_path_raw = args.get("character_sheet_path")
        name = args.get("name")
        explicit_supervisor = args.get("supervisor")

        if content:
            md_path = None
        elif sheet_path_raw:
            md_path = Path(sheet_path_raw).expanduser()
            if not md_path.is_absolute():
                md_path = (self._anima_dir / md_path).resolve()
                if not md_path.is_relative_to(self._anima_dir.resolve()):
                    return _error_result(
                        "PermissionDenied",
                        "character_sheet_path must be within anima directory.",
                    )
            else:
                # Absolute paths are intentionally allowed without directory
                # restriction — the CLI and human operators specify full paths.
                # create_from_md validates the content as a character sheet,
                # so passing an arbitrary file (e.g. /etc/passwd) will fail
                # schema validation rather than leaking data.
                md_path = md_path.resolve()
            if not md_path.exists():
                return _error_result(
                    "FileNotFound",
                    f"Character sheet not found: {md_path}",
                    suggestion=("Use character_sheet_content to pass content directly, or ensure the file exists"),
                )
        else:
            return _error_result(
                "MissingParameter",
                "Either character_sheet_content or character_sheet_path is required",
            )

        try:
            anima_dir = create_from_md(
                get_animas_dir(),
                md_path,
                name=name,
                content=content,
                supervisor=explicit_supervisor,
            )
        except FileExistsError as e:
            return _error_result(
                "AnimaExists",
                str(e),
                suggestion="Choose a different name",
            )
        except ValueError as e:
            return _error_result("InvalidCharacterSheet", str(e))

        status_path = anima_dir / "status.json"
        if status_path.exists() and self._anima_name:
            try:
                status_data = _json.loads(status_path.read_text(encoding="utf-8"))
                if not status_data.get("supervisor"):
                    status_data["supervisor"] = self._anima_name
                    status_path.write_text(
                        _json.dumps(status_data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    logger.debug(
                        "Set fallback supervisor '%s' for '%s'",
                        self._anima_name,
                        anima_dir.name,
                    )
            except (OSError, _json.JSONDecodeError):
                logger.warning("Failed to set fallback supervisor", exc_info=True)

        try:
            from cli.commands.init_cmd import _register_anima_in_config

            _register_anima_in_config(get_data_dir(), anima_dir.name)
        except Exception:
            logger.warning("Failed to register anima in config.json", exc_info=True)

        logger.info("create_anima: created '%s' at %s", anima_dir.name, anima_dir)
        return f"Anima '{anima_dir.name}' created successfully at {anima_dir}. Reload the server to activate."
