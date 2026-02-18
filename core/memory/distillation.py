from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.


"""Procedural memory auto-distillation engine.

Classifies episodic memories as semantic or procedural, and distills
procedural episodes into reusable procedure files with YAML frontmatter.

Pipeline:
  - Daily: classify episode sections -> distill procedural episodes
  - Weekly: detect repeated action patterns -> distill into procedures
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("animaworks.distillation")


# ── ProceduralDistiller ────────────────────────────────────────


class ProceduralDistiller:
    """Engine that distills procedural knowledge from episodic memories.

    Detects procedural content via regex pattern matching, then uses an
    LLM to extract structured, reusable procedure documents from the
    matched episodes.  Saved procedures include YAML frontmatter with
    tracking metadata (confidence, success/failure counts, etc.).
    """

    # Patterns that indicate procedural (how-to / step-based) content
    PROCEDURAL_PATTERNS: list[str] = [
        r"手順[をに]",
        r"操作した",
        r"設定した",
        r"コマンド",
        r"インストール",
        r"デプロイ",
        r"実行した",
        r"step\s*\d",
        r"→.*→",           # arrow chains (workflow steps)
        r"->.*->",         # ASCII arrow chains
        r"まず.*次に",      # sequential ordering (Japanese)
        r"最初に.*その後",   # sequential ordering (Japanese)
    ]

    PROCEDURAL_THRESHOLD: int = 2  # minimum pattern hits to classify as procedural

    def __init__(self, anima_dir: Path, anima_name: str) -> None:
        """Initialize the distiller.

        Args:
            anima_dir: Path to the anima's data directory.
            anima_name: Name of the anima (for logging).
        """
        self.anima_dir = anima_dir
        self.anima_name = anima_name
        self.procedures_dir = anima_dir / "procedures"
        self.knowledge_dir = anima_dir / "knowledge"
        self.episodes_dir = anima_dir / "episodes"
        self.procedures_dir.mkdir(parents=True, exist_ok=True)

    # ── Classification ─────────────────────────────────────────

    def classify_episode_sections(
        self, episodes_text: str,
    ) -> tuple[str, str]:
        """Split episode text into semantic and procedural parts.

        Sections are delimited by ``## `` Markdown headers.  Each section
        is independently classified.

        Args:
            episodes_text: Full episode text (may contain multiple sections).

        Returns:
            Tuple of ``(semantic_episodes, procedural_episodes)``.
        """
        sections = self._split_into_sections(episodes_text)
        semantic_parts: list[str] = []
        procedural_parts: list[str] = []

        for section in sections:
            if self._is_procedural(section):
                procedural_parts.append(section)
            else:
                semantic_parts.append(section)

        return (
            "\n\n".join(semantic_parts),
            "\n\n".join(procedural_parts),
        )

    def _is_procedural(self, text: str) -> bool:
        """Determine whether *text* is procedural based on pattern hits.

        Args:
            text: A single episode section.

        Returns:
            True when the number of matching patterns meets the threshold.
        """
        count = sum(
            1 for pattern in self.PROCEDURAL_PATTERNS
            if re.search(pattern, text, re.IGNORECASE)
        )
        return count >= self.PROCEDURAL_THRESHOLD

    @staticmethod
    def _split_into_sections(text: str) -> list[str]:
        """Split *text* on ``## `` Markdown headers.

        Args:
            text: Raw Markdown text.

        Returns:
            List of non-empty section strings.
        """
        sections = re.split(r"\n(?=##\s)", text)
        return [s.strip() for s in sections if s.strip()]

    # ── Daily Distillation ─────────────────────────────────────

    async def distill_procedures(
        self,
        procedural_episodes: str,
        model: str = "anthropic/claude-sonnet-4-20250514",
    ) -> list[dict]:
        """Extract reusable procedures from procedural episode text.

        Sends the procedural episodes and a summary of existing procedures
        to an LLM, which returns a JSON array of extracted procedures.

        Args:
            procedural_episodes: Concatenated procedural episode text.
            model: LiteLLM model identifier.

        Returns:
            List of dicts, each with keys ``title``, ``description``,
            ``tags``, and ``content``.
        """
        if not procedural_episodes.strip():
            return []

        existing = self._load_existing_procedures()

        prompt = (
            "以下のエピソード（行動記録）から、再利用可能な手順書を抽出してください。\n\n"
            "【エピソード】\n"
            f"{procedural_episodes[:4000]}\n\n"
            "【既存の手順書（重複避け）】\n"
            f"{existing[:2000]}\n\n"
            "出力形式（JSON配列）:\n"
            "[\n"
            "  {\n"
            '    "title": "手順名（英語ファイル名向け）",\n'
            '    "description": "手順の概要（1-2文）",\n'
            '    "tags": ["tag1", "tag2"],\n'
            '    "content": "# 手順名\\n\\n## 概要\\n...\\n\\n## 手順\\n'
            '1. ...\\n2. ...\\n\\n## 注意点\\n..."\n'
            "  }\n"
            "]\n\n"
            "ルール:\n"
            "- 既存手順と重複する場合はスキップ\n"
            "- 汎用的で再利用価値の高い手順のみ抽出\n"
            "- 具体的な手順ステップを含めること\n"
            "- 手順が曖昧な場合は抽出しない\n"
            "- 空配列 [] を返しても構わない"
        )

        try:
            import litellm

            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
            text = response.choices[0].message.content or "[]"
            procedures = self._parse_procedures(text)

            logger.info(
                "Distilled %d procedures from episodes for anima=%s",
                len(procedures), self.anima_name,
            )
            return procedures

        except Exception:
            logger.exception(
                "Failed to distill procedures for anima=%s", self.anima_name,
            )
            return []

    # ── Weekly Pattern Distillation ────────────────────────────

    async def weekly_pattern_distill(
        self,
        model: str = "anthropic/claude-sonnet-4-20250514",
        days: int = 7,
    ) -> dict:
        """Detect repeated action patterns over recent episodes and distill.

        Collects episode files from the last *days* days, asks the LLM to
        identify repeated patterns, and saves any new procedures.

        Args:
            model: LiteLLM model identifier.
            days: Look-back window in days.

        Returns:
            Dict with ``procedures_created`` (list of file paths) and
            ``patterns_detected`` (int).
        """
        texts = self._collect_recent_episodes(self.episodes_dir, days=days)
        if not texts.strip():
            logger.info(
                "No recent episodes for weekly pattern distill, anima=%s",
                self.anima_name,
            )
            return {"procedures_created": [], "patterns_detected": 0}

        existing = self._load_existing_procedures()

        prompt = (
            "以下は7日間の行動記録です。繰り返し行われている作業パターンを"
            "特定し、手順書として蒸留してください。\n\n"
            "【行動記録】\n"
            f"{texts[:6000]}\n\n"
            "【既存手順】\n"
            f"{existing[:2000]}\n\n"
            "出力形式（JSON配列）:\n"
            "[\n"
            "  {\n"
            '    "title": "手順名（英語ファイル名向け）",\n'
            '    "description": "手順の概要（1-2文）",\n'
            '    "tags": ["tag1", "tag2"],\n'
            '    "content": "# 手順名\\n\\n## 概要\\n...\\n\\n## 手順\\n'
            '1. ...\\n2. ...\\n\\n## 注意点\\n..."\n'
            "  }\n"
            "]\n\n"
            "ルール:\n"
            "- 繰り返しパターンがない場合は空配列 [] を返してください\n"
            "- 既存手順と重複する場合はスキップ\n"
            "- 2回以上繰り返された作業のみ手順化\n"
            "- 具体的な手順ステップを含めること"
        )

        try:
            import litellm

            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
            text = response.choices[0].message.content or "[]"
            procedures = self._parse_procedures(text)

            saved_paths: list[str] = []
            for item in procedures:
                path = self.save_procedure(item)
                saved_paths.append(str(path))
                logger.info(
                    "Weekly pattern distill: saved procedure '%s' for anima=%s",
                    path.name, self.anima_name,
                )

            return {
                "procedures_created": saved_paths,
                "patterns_detected": len(procedures),
            }

        except Exception:
            logger.exception(
                "Weekly pattern distill failed for anima=%s", self.anima_name,
            )
            return {"procedures_created": [], "patterns_detected": 0}

    # ── Parsing Helpers ────────────────────────────────────────

    def _parse_procedures(self, text: str) -> list[dict]:
        """Parse an LLM JSON response into a list of procedure dicts.

        Strips code fences before parsing.  Each valid item must have
        at least ``title`` and ``content`` keys.

        Args:
            text: Raw LLM output (potentially fenced JSON).

        Returns:
            List of procedure dicts with ``title``, ``content``, and
            optionally ``description`` and ``tags``.
        """
        text = self._strip_code_fence(text)

        try:
            items = json.loads(text)
            if isinstance(items, list):
                return [
                    i for i in items
                    if isinstance(i, dict)
                    and "title" in i
                    and "content" in i
                ]
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse LLM procedure output for anima=%s",
                self.anima_name,
            )

        return []

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """Remove Markdown code fences wrapping the entire text.

        Handles any language tag (``json``, ``markdown``, etc.) and
        preserves interior content.

        Args:
            text: Raw text potentially wrapped in code fences.

        Returns:
            Text with outer code fences removed.
        """
        text = re.sub(r"^```\w*\s*\n", "", text.strip(), count=1)
        text = re.sub(r"\n```\s*$", "", text)
        return text.strip()

    # ── Procedure I/O ──────────────────────────────────────────

    def _load_existing_procedures(self) -> str:
        """Build a summary of existing procedures for duplicate avoidance.

        Returns:
            Newline-separated list of ``- filename: description`` entries,
            or ``(なし)`` when the directory is empty.
        """
        summaries: list[str] = []
        for f in sorted(self.procedures_dir.glob("*.md")):
            meta = self._read_metadata(f)
            desc = meta.get("description", f.stem)
            summaries.append(f"- {f.stem}: {desc}")
        return "\n".join(summaries) if summaries else "(なし)"

    @staticmethod
    def _read_metadata(path: Path) -> dict:
        """Read YAML frontmatter metadata from a procedure file.

        Args:
            path: Absolute path to the procedure Markdown file.

        Returns:
            Parsed metadata dict, or empty dict on failure.
        """
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                import yaml

                try:
                    return yaml.safe_load(parts[1]) or {}
                except Exception:
                    return {}
        return {}

    def save_procedure(self, item: dict) -> Path:
        """Persist a distilled procedure with YAML frontmatter.

        Uses ``MemoryManager.write_procedure_with_meta()`` for consistent
        file format across the codebase.

        Args:
            item: Dict with ``title``, ``content``, and optionally
                ``description`` and ``tags``.

        Returns:
            Path to the saved procedure file.
        """
        from core.memory.manager import MemoryManager

        title = re.sub(r"[^\w\-]", "_", item["title"])
        path = self.procedures_dir / f"{title}.md"

        metadata = {
            "description": item.get("description", ""),
            "tags": item.get("tags", []),
            "success_count": 0,
            "failure_count": 0,
            "last_used": None,
            "confidence": 0.5,
            "version": 1,
            "created_at": datetime.now().isoformat(),
            "auto_distilled": True,
        }

        mm = MemoryManager(self.anima_dir)
        mm.write_procedure_with_meta(path, item["content"], metadata)

        logger.info("Saved distilled procedure: %s", path.name)
        return path

    # ── Episode Collection ─────────────────────────────────────

    @staticmethod
    def _collect_recent_episodes(
        episodes_dir: Path, days: int = 7,
    ) -> str:
        """Collect raw episode text from the last *days* days.

        Args:
            episodes_dir: Path to the ``episodes/`` directory.
            days: Number of days to look back.

        Returns:
            Concatenated episode Markdown text.
        """
        parts: list[str] = []
        today = datetime.now().date()

        for offset in range(days):
            target_date = today - timedelta(days=offset)
            for episode_file in sorted(episodes_dir.glob(f"{target_date}*.md")):
                try:
                    parts.append(
                        episode_file.read_text(encoding="utf-8"),
                    )
                except OSError:
                    logger.warning(
                        "Failed to read episode file: %s", episode_file,
                    )

        return "\n\n".join(parts)
