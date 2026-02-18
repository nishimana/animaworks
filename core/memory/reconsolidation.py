from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.


"""Prediction-error-based memory reconsolidation engine.

When new episodes contradict existing knowledge or procedures, the
system detects a "prediction error" and reconsolidates (updates) the
existing memory.  This mirrors the reconsolidation process observed
in biological memory systems, where reactivated memories become
labile and susceptible to modification.

Pipeline:
  1. RAG search for related existing knowledge/procedures
  2. NLI contradiction check (fast, local)
  3. LLM detailed analysis of prediction errors
  4. Version-controlled update of existing memories
"""

import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("animaworks.reconsolidation")


# ── Data Structures ────────────────────────────────────────────


@dataclass
class PredictionError:
    """A detected contradiction between new episodes and existing memory.

    Attributes:
        source_file: Path to the contradicted knowledge/procedure file.
        memory_type: Type of memory ("knowledge" or "procedures").
        error_type: Category of prediction error.
        description: Human-readable description of the contradiction.
        original_content: Original content of the memory file.
        updated_content: LLM-proposed updated content, or None if no update.
        confidence: Confidence score of the prediction error detection (0-1).
    """

    source_file: Path
    memory_type: str  # "knowledge" | "procedures"
    error_type: str  # "factual_update" | "procedure_change" | "context_shift"
    description: str
    original_content: str
    updated_content: str | None
    confidence: float


# ── ReconsolidationEngine ──────────────────────────────────────


class ReconsolidationEngine:
    """Prediction-error-based memory reconsolidation engine.

    Detects when new episodes contradict existing knowledge or procedures
    ("prediction errors") and updates the affected memories through a
    version-controlled reconsolidation process.
    """

    PREDICTION_ERROR_NLI_THRESHOLD = 0.6

    def __init__(self, anima_dir: Path, anima_name: str) -> None:
        """Initialize the reconsolidation engine.

        Args:
            anima_dir: Path to anima's directory (~/.animaworks/animas/{name}).
            anima_name: Name of the anima for logging and RAG queries.
        """
        self.anima_dir = anima_dir
        self.anima_name = anima_name
        self.knowledge_dir = anima_dir / "knowledge"
        self.procedures_dir = anima_dir / "procedures"

    # ── Prediction Error Detection ─────────────────────────────

    async def detect_prediction_errors(
        self,
        new_episodes: str,
        model: str = "anthropic/claude-sonnet-4-20250514",
    ) -> list[PredictionError]:
        """Detect prediction errors between new episodes and existing memories.

        Pipeline:
          1. RAG search for related existing knowledge/procedures
          2. NLI contradiction check per related memory
          3. LLM detailed analysis for confirmed contradictions

        Args:
            new_episodes: Text of new episodes to check against existing memory.
            model: LLM model identifier (LiteLLM format) for detailed analysis.

        Returns:
            List of detected prediction errors with proposed updates.
        """
        errors: list[PredictionError] = []
        related = self._find_related_memories(new_episodes)

        if not related:
            logger.debug(
                "No related memories found for reconsolidation check, "
                "anima=%s",
                self.anima_name,
            )
            return errors

        logger.info(
            "Checking %d related memories for prediction errors, anima=%s",
            len(related), self.anima_name,
        )

        for mem in related:
            # NLI contradiction check
            is_contradiction, nli_score = await self._nli_contradiction_check(
                new_episodes[:2000], mem["content"][:2000],
            )
            if not is_contradiction:
                continue

            logger.info(
                "NLI contradiction detected (score=%.2f) for %s, "
                "running LLM analysis",
                nli_score, mem["file"],
            )

            # LLM detailed analysis
            analysis = await self._analyze_prediction_error(
                new_episodes, mem, model,
            )
            if analysis:
                errors.append(analysis)

        logger.info(
            "Prediction error detection complete for anima=%s: %d errors found",
            self.anima_name, len(errors),
        )
        return errors

    def _find_related_memories(self, episodes: str) -> list[dict[str, Any]]:
        """Find existing knowledge/procedures related to the new episodes.

        Uses RAG vector search to find semantically similar memories.

        Args:
            episodes: New episode text to search against.

        Returns:
            List of dicts with "file", "content", "memory_type" keys.
        """
        related: list[dict[str, Any]] = []

        try:
            from core.memory.rag.retriever import MemoryRetriever
            from core.memory.rag.singleton import get_vector_store

            from core.memory.rag import MemoryIndexer

            vector_store = get_vector_store()
            indexer = MemoryIndexer(
                vector_store, self.anima_name, self.anima_dir,
            )

            # Search knowledge
            retriever = MemoryRetriever(
                vector_store, indexer, self.knowledge_dir,
            )

            for memory_type, mem_dir in [
                ("knowledge", self.knowledge_dir),
                ("procedures", self.procedures_dir),
            ]:
                try:
                    results = retriever.search(
                        query=episodes[:500],
                        anima_name=self.anima_name,
                        memory_type=memory_type,
                        top_k=5,
                    )
                    for r in results:
                        source_file = r.metadata.get("source_file", "")
                        if source_file:
                            file_path = mem_dir / Path(source_file).name
                        else:
                            file_path = mem_dir / f"{r.doc_id}.md"

                        # Read full file content if available
                        if file_path.exists():
                            content = file_path.read_text(encoding="utf-8")
                        else:
                            content = r.content

                        related.append({
                            "file": str(file_path),
                            "content": content,
                            "memory_type": memory_type,
                            "path": file_path,
                        })
                except Exception as e:
                    logger.debug(
                        "RAG search failed for %s: %s", memory_type, e,
                    )

        except ImportError:
            logger.debug("RAG not available, skipping related memory search")
        except Exception as e:
            logger.warning("Failed to find related memories: %s", e)

        return related

    async def _nli_contradiction_check(
        self, new_text: str, existing_text: str,
    ) -> tuple[bool, float]:
        """Check if new text contradicts existing text using NLI.

        Reuses the KnowledgeValidator's NLI pipeline for consistency.

        Args:
            new_text: New episode text (truncated to fit NLI input).
            existing_text: Existing memory text (truncated to fit NLI input).

        Returns:
            Tuple of (is_contradiction, nli_score).
        """
        try:
            from core.memory.validation import KnowledgeValidator

            validator = KnowledgeValidator()
            label, score = validator._nli_check(new_text, existing_text)

            is_contradiction = (
                label == "contradiction"
                and score >= self.PREDICTION_ERROR_NLI_THRESHOLD
            )
            return (is_contradiction, score)

        except ImportError:
            logger.debug("Validation module not available for NLI check")
            return (False, 0.0)
        except Exception as e:
            logger.warning("NLI contradiction check failed: %s", e)
            return (False, 0.0)

    async def _analyze_prediction_error(
        self,
        episodes: str,
        memory: dict[str, Any],
        model: str,
    ) -> PredictionError | None:
        """Use LLM to analyze a potential prediction error in detail.

        Args:
            episodes: Full new episode text.
            memory: Dict with "file", "content", "memory_type", "path" keys.
            model: LLM model identifier (LiteLLM format).

        Returns:
            PredictionError if confirmed, None otherwise.
        """
        prompt = f"""以下の新しいエピソード（行動記録）と既存の知識/手順を比較してください。

【新しいエピソード】
{episodes[:3000]}

【既存の知識/手順】
ファイル: {memory['file']}
{memory['content'][:2000]}

質問:
1. 新しいエピソードは既存の知識/手順と矛盾していますか？
2. 矛盾している場合、既存の知識は更新すべきですか？
3. どのように更新すべきですか？

回答はJSON形式で:
{{"is_error": true, "error_type": "factual_update", "description": "予測誤差の説明", "updated_content": "更新後の知識/手順テキスト（更新不要なら null）"}}

error_type は以下のいずれか:
- "factual_update": 事実関係の変更（APIエンドポイント、設定値、バージョン等）
- "procedure_change": 手順・ワークフローの変更
- "context_shift": 状況・コンテキストの変化（チーム構成、方針転換等）
- "none": 矛盾なし

is_error が false の場合、error_type は "none" にしてください。"""

        try:
            import litellm

            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )

            text = response.choices[0].message.content or ""

            # Sanitize LLM output
            from core.memory.consolidation import ConsolidationEngine
            text = ConsolidationEngine._sanitize_llm_output(text)

            # Extract JSON from response
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if not json_match:
                logger.warning(
                    "No JSON found in LLM prediction error analysis for %s",
                    memory["file"],
                )
                return None

            result = json.loads(json_match.group())

            if not result.get("is_error", False):
                logger.debug(
                    "LLM judged no prediction error for %s",
                    memory["file"],
                )
                return None

            error_type = result.get("error_type", "factual_update")
            if error_type == "none":
                return None

            return PredictionError(
                source_file=memory["path"],
                memory_type=memory["memory_type"],
                error_type=error_type,
                description=result.get("description", "")[:500],
                original_content=memory["content"],
                updated_content=result.get("updated_content"),
                confidence=0.7,
            )

        except Exception as e:
            logger.warning(
                "LLM prediction error analysis failed for %s: %s",
                memory["file"], e,
            )
            return None

    # ── Reconsolidation Application ────────────────────────────

    async def apply_reconsolidation(
        self, errors: list[PredictionError],
    ) -> dict[str, int]:
        """Apply prediction errors to update existing memories.

        For each error with updated content:
          1. Archive the current version of the file
          2. Update metadata (version, reconsolidation info)
          3. Write the updated content

        Args:
            errors: List of prediction errors to apply.

        Returns:
            Dict with counts: "updated", "skipped", "errors".
        """
        results: dict[str, int] = {"updated": 0, "skipped": 0, "errors": 0}

        for error in errors:
            if not error.updated_content:
                results["skipped"] += 1
                logger.debug(
                    "Skipping reconsolidation (no updated content) for %s",
                    error.source_file,
                )
                continue

            try:
                # Archive the current version before overwriting
                self._archive_version(error.source_file)

                # Read and update metadata
                meta = self._read_metadata(error.source_file)
                meta["version"] = meta.get("version", 1) + 1
                meta["updated_at"] = datetime.now().isoformat()
                meta["reconsolidated_from"] = error.error_type
                meta["reconsolidation_reason"] = error.description[:200]

                # Write updated content with metadata
                from core.memory.manager import MemoryManager
                mm = MemoryManager(self.anima_dir)

                if error.memory_type == "knowledge":
                    mm.write_knowledge_with_meta(
                        error.source_file, error.updated_content, meta,
                    )
                elif error.memory_type == "procedures":
                    mm.write_procedure_with_meta(
                        error.source_file, error.updated_content, meta,
                    )

                results["updated"] += 1
                logger.info(
                    "Reconsolidated %s: type=%s reason=%s",
                    error.source_file.name,
                    error.error_type,
                    error.description[:100],
                )

            except Exception as e:
                logger.warning(
                    "Reconsolidation failed for %s: %s",
                    error.source_file, e,
                )
                results["errors"] += 1

        logger.info(
            "Reconsolidation complete for anima=%s: "
            "updated=%d skipped=%d errors=%d",
            self.anima_name,
            results["updated"],
            results["skipped"],
            results["errors"],
        )
        return results

    # ── Version Management ─────────────────────────────────────

    def _archive_version(self, file_path: Path) -> None:
        """Archive the current version of a file before reconsolidation.

        Saves a timestamped copy to archive/versions/ for audit trail.

        Args:
            file_path: Path to the file to archive.
        """
        if not file_path.exists():
            return

        archive_dir = self.anima_dir / "archive" / "versions"
        archive_dir.mkdir(parents=True, exist_ok=True)

        meta = self._read_metadata(file_path)
        version = meta.get("version", 1)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        dest = archive_dir / f"{file_path.stem}_v{version}_{timestamp}{file_path.suffix}"
        shutil.copy2(str(file_path), str(dest))

        logger.debug(
            "Archived version %d of %s to %s",
            version, file_path.name, dest.name,
        )

    def _read_metadata(self, file_path: Path) -> dict[str, Any]:
        """Read YAML frontmatter metadata from a memory file.

        Supports both knowledge and procedure files.

        Args:
            file_path: Path to the memory file.

        Returns:
            Metadata dict, or empty dict if no frontmatter.
        """
        from core.memory.manager import MemoryManager
        mm = MemoryManager(self.anima_dir)

        # Determine memory type by parent directory
        if self.knowledge_dir in file_path.parents or file_path.parent == self.knowledge_dir:
            return mm.read_knowledge_metadata(file_path)
        elif self.procedures_dir in file_path.parents or file_path.parent == self.procedures_dir:
            return mm.read_procedure_metadata(file_path)
        else:
            return mm.read_knowledge_metadata(file_path)
