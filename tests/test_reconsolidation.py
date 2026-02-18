from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.


"""Tests for prediction-error-based memory reconsolidation.

All NLI, LLM, and RAG dependencies are mocked to ensure unit test
isolation without requiring API keys or model downloads.
"""

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.memory.reconsolidation import PredictionError, ReconsolidationEngine


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    """Create a minimal anima directory structure for testing."""
    anima = tmp_path / "animas" / "test-anima"
    (anima / "knowledge").mkdir(parents=True)
    (anima / "procedures").mkdir(parents=True)
    (anima / "episodes").mkdir(parents=True)
    (anima / "skills").mkdir(parents=True)
    (anima / "state").mkdir(parents=True)
    return anima


@pytest.fixture
def engine(anima_dir: Path) -> ReconsolidationEngine:
    """Create a ReconsolidationEngine for the test anima."""
    return ReconsolidationEngine(anima_dir, "test-anima")


@pytest.fixture
def knowledge_file(anima_dir: Path) -> Path:
    """Create a sample knowledge file with YAML frontmatter."""
    path = anima_dir / "knowledge" / "api-config.md"
    path.write_text(
        "---\n"
        "created_at: '2026-01-01T00:00:00'\n"
        "confidence: 0.8\n"
        "version: 1\n"
        "---\n\n"
        "# API Configuration\n\n"
        "The server runs on port 8080.\n"
        "Database connection string: postgresql://localhost:5432/mydb\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def procedure_file(anima_dir: Path) -> Path:
    """Create a sample procedure file with YAML frontmatter."""
    path = anima_dir / "procedures" / "deploy-process.md"
    path.write_text(
        "---\n"
        "description: deployment procedure\n"
        "tags: [deploy]\n"
        "version: 1\n"
        "confidence: 0.9\n"
        "created_at: '2026-01-01T00:00:00'\n"
        "---\n\n"
        "# Deployment Process\n\n"
        "1. Run tests\n"
        "2. Build Docker image\n"
        "3. Push to ECR\n"
        "4. Deploy to ECS\n",
        encoding="utf-8",
    )
    return path


def _make_prediction_error(
    anima_dir: Path,
    *,
    memory_type: str = "knowledge",
    error_type: str = "factual_update",
    updated_content: str | None = "Updated content",
    filename: str = "api-config.md",
) -> PredictionError:
    """Helper to create a PredictionError for testing."""
    if memory_type == "knowledge":
        source = anima_dir / "knowledge" / filename
    else:
        source = anima_dir / "procedures" / filename
    return PredictionError(
        source_file=source,
        memory_type=memory_type,
        error_type=error_type,
        description="Port changed from 8080 to 3000",
        original_content="The server runs on port 8080.",
        updated_content=updated_content,
        confidence=0.7,
    )


# ── NLI Contradiction Check Tests ──────────────────────────


class TestNLIContradictionCheck:
    """Test the NLI-based contradiction detection stage."""

    @pytest.mark.asyncio
    async def test_contradiction_detected(self, engine: ReconsolidationEngine) -> None:
        """NLI contradiction above threshold returns True."""
        with patch(
            "core.memory.validation.KnowledgeValidator",
        ) as MockValidator:
            mock_v = MockValidator.return_value
            mock_v._nli_check.return_value = ("contradiction", 0.85)

            is_contradiction, score = await engine._nli_contradiction_check(
                "Server now runs on port 3000",
                "Server runs on port 8080",
            )

        assert is_contradiction is True
        assert score == 0.85

    @pytest.mark.asyncio
    async def test_no_contradiction(self, engine: ReconsolidationEngine) -> None:
        """NLI entailment returns False."""
        with patch(
            "core.memory.validation.KnowledgeValidator",
        ) as MockValidator:
            mock_v = MockValidator.return_value
            mock_v._nli_check.return_value = ("entailment", 0.90)

            is_contradiction, score = await engine._nli_contradiction_check(
                "Server runs on port 8080",
                "Server runs on port 8080",
            )

        assert is_contradiction is False

    @pytest.mark.asyncio
    async def test_contradiction_below_threshold(
        self, engine: ReconsolidationEngine,
    ) -> None:
        """NLI contradiction below threshold returns False."""
        with patch(
            "core.memory.validation.KnowledgeValidator",
        ) as MockValidator:
            mock_v = MockValidator.return_value
            mock_v._nli_check.return_value = ("contradiction", 0.4)

            is_contradiction, score = await engine._nli_contradiction_check(
                "Something slightly different",
                "Original text",
            )

        assert is_contradiction is False

    @pytest.mark.asyncio
    async def test_nli_import_error(self, engine: ReconsolidationEngine) -> None:
        """ImportError in NLI returns (False, 0.0) gracefully."""
        with patch.dict("sys.modules", {"core.memory.validation": None}):
            is_contradiction, score = await engine._nli_contradiction_check(
                "new text", "old text",
            )

        assert is_contradiction is False
        assert score == 0.0


# ── LLM Prediction Error Analysis Tests ────────────────────


class TestAnalyzePredictionError:
    """Test the LLM-based prediction error analysis."""

    @pytest.mark.asyncio
    async def test_error_detected(self, engine: ReconsolidationEngine) -> None:
        """LLM confirms a prediction error and provides updated content."""
        llm_response = MagicMock()
        llm_response.choices = [MagicMock()]
        llm_response.choices[0].message.content = (
            '{"is_error": true, "error_type": "factual_update", '
            '"description": "Port changed to 3000", '
            '"updated_content": "# API Config\\nServer runs on port 3000."}'
        )

        memory = {
            "file": "/test/knowledge/api-config.md",
            "content": "Server runs on port 8080.",
            "memory_type": "knowledge",
            "path": Path("/test/knowledge/api-config.md"),
        }

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = llm_response
            result = await engine._analyze_prediction_error(
                "Today we changed the server to port 3000",
                memory,
                "test-model",
            )

        assert result is not None
        assert result.error_type == "factual_update"
        assert result.description == "Port changed to 3000"
        assert result.updated_content is not None
        assert "3000" in result.updated_content

    @pytest.mark.asyncio
    async def test_no_error(self, engine: ReconsolidationEngine) -> None:
        """LLM determines no prediction error exists."""
        llm_response = MagicMock()
        llm_response.choices = [MagicMock()]
        llm_response.choices[0].message.content = (
            '{"is_error": false, "error_type": "none", '
            '"description": "No contradiction", "updated_content": null}'
        )

        memory = {
            "file": "/test/knowledge/api-config.md",
            "content": "Server runs on port 8080.",
            "memory_type": "knowledge",
            "path": Path("/test/knowledge/api-config.md"),
        }

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = llm_response
            result = await engine._analyze_prediction_error(
                "Server port 8080 is working fine",
                memory,
                "test-model",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_llm_failure(self, engine: ReconsolidationEngine) -> None:
        """LLM call failure returns None gracefully."""
        memory = {
            "file": "/test/knowledge/api-config.md",
            "content": "Server runs on port 8080.",
            "memory_type": "knowledge",
            "path": Path("/test/knowledge/api-config.md"),
        }

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API error")
            result = await engine._analyze_prediction_error(
                "new episodes", memory, "test-model",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_unparseable_json(self, engine: ReconsolidationEngine) -> None:
        """Unparseable LLM response returns None."""
        llm_response = MagicMock()
        llm_response.choices = [MagicMock()]
        llm_response.choices[0].message.content = "I cannot determine this."

        memory = {
            "file": "/test/knowledge/api-config.md",
            "content": "Server runs on port 8080.",
            "memory_type": "knowledge",
            "path": Path("/test/knowledge/api-config.md"),
        }

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = llm_response
            result = await engine._analyze_prediction_error(
                "new text", memory, "test-model",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_procedure_change(self, engine: ReconsolidationEngine) -> None:
        """LLM detects a procedure_change type error."""
        llm_response = MagicMock()
        llm_response.choices = [MagicMock()]
        llm_response.choices[0].message.content = (
            '{"is_error": true, "error_type": "procedure_change", '
            '"description": "Deployment now uses GitHub Actions", '
            '"updated_content": "# Deploy\\n1. Push to main\\n2. GitHub Actions deploys"}'
        )

        memory = {
            "file": "/test/procedures/deploy.md",
            "content": "1. Run tests\n2. Manual deploy via SSH",
            "memory_type": "procedures",
            "path": Path("/test/procedures/deploy.md"),
        }

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = llm_response
            result = await engine._analyze_prediction_error(
                "We migrated to GitHub Actions for deployment",
                memory,
                "test-model",
            )

        assert result is not None
        assert result.error_type == "procedure_change"
        assert result.memory_type == "procedures"


# ── Version Archive Tests ──────────────────────────────────


class TestArchiveVersion:
    """Test version archiving before reconsolidation."""

    def test_archive_creates_copy(
        self, engine: ReconsolidationEngine, knowledge_file: Path,
    ) -> None:
        """Archiving creates a timestamped copy in archive/versions/."""
        engine._archive_version(knowledge_file)

        archive_dir = engine.anima_dir / "archive" / "versions"
        assert archive_dir.exists()
        archived_files = list(archive_dir.glob("api-config_v1_*"))
        assert len(archived_files) == 1

        # Verify content is preserved
        archived_content = archived_files[0].read_text(encoding="utf-8")
        original_content = knowledge_file.read_text(encoding="utf-8")
        assert archived_content == original_content

    def test_archive_nonexistent_file(
        self, engine: ReconsolidationEngine,
    ) -> None:
        """Archiving a nonexistent file is a no-op."""
        fake_path = engine.knowledge_dir / "nonexistent.md"
        engine._archive_version(fake_path)

        archive_dir = engine.anima_dir / "archive" / "versions"
        # Archive dir should not be created for nonexistent files
        assert not archive_dir.exists()

    def test_archive_uses_version_from_metadata(
        self, engine: ReconsolidationEngine, anima_dir: Path,
    ) -> None:
        """Archive filename includes the version number from metadata."""
        path = anima_dir / "knowledge" / "versioned.md"
        path.write_text(
            "---\n"
            "version: 3\n"
            "---\n\n"
            "Content at version 3\n",
            encoding="utf-8",
        )

        engine._archive_version(path)

        archive_dir = anima_dir / "archive" / "versions"
        archived_files = list(archive_dir.glob("versioned_v3_*"))
        assert len(archived_files) == 1


# ── Apply Reconsolidation Tests ────────────────────────────


class TestApplyReconsolidation:
    """Test applying prediction errors to update memories."""

    @pytest.mark.asyncio
    async def test_knowledge_update(
        self, engine: ReconsolidationEngine, knowledge_file: Path,
    ) -> None:
        """Successfully update a knowledge file with reconsolidated content."""
        error = _make_prediction_error(
            engine.anima_dir,
            memory_type="knowledge",
            updated_content="# API Configuration\n\nThe server runs on port 3000.\n",
            filename="api-config.md",
        )

        result = await engine.apply_reconsolidation([error])

        assert result["updated"] == 1
        assert result["skipped"] == 0
        assert result["errors"] == 0

        # Verify the file was updated
        content = knowledge_file.read_text(encoding="utf-8")
        assert "port 3000" in content

        # Verify metadata was updated
        from core.memory.manager import MemoryManager
        mm = MemoryManager(engine.anima_dir)
        meta = mm.read_knowledge_metadata(knowledge_file)
        assert meta["version"] == 2
        assert meta["reconsolidated_from"] == "factual_update"
        assert "reconsolidation_reason" in meta

    @pytest.mark.asyncio
    async def test_procedure_update(
        self, engine: ReconsolidationEngine, procedure_file: Path,
    ) -> None:
        """Successfully update a procedure file with reconsolidated content."""
        error = _make_prediction_error(
            engine.anima_dir,
            memory_type="procedures",
            error_type="procedure_change",
            updated_content="# Deploy\n\n1. Push to main\n2. GitHub Actions deploys\n",
            filename="deploy-process.md",
        )

        result = await engine.apply_reconsolidation([error])

        assert result["updated"] == 1

        # Verify metadata updated
        from core.memory.manager import MemoryManager
        mm = MemoryManager(engine.anima_dir)
        meta = mm.read_procedure_metadata(procedure_file)
        assert meta["version"] == 2
        assert meta["reconsolidated_from"] == "procedure_change"

    @pytest.mark.asyncio
    async def test_skip_no_updated_content(
        self, engine: ReconsolidationEngine, knowledge_file: Path,
    ) -> None:
        """Errors without updated_content are skipped."""
        error = _make_prediction_error(
            engine.anima_dir,
            updated_content=None,
        )

        result = await engine.apply_reconsolidation([error])

        assert result["updated"] == 0
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_archive_before_update(
        self, engine: ReconsolidationEngine, knowledge_file: Path,
    ) -> None:
        """The old version is archived before applying the update."""
        original_content = knowledge_file.read_text(encoding="utf-8")

        error = _make_prediction_error(
            engine.anima_dir,
            updated_content="Completely new content",
        )

        await engine.apply_reconsolidation([error])

        # Verify archive exists
        archive_dir = engine.anima_dir / "archive" / "versions"
        archived_files = list(archive_dir.glob("api-config_v1_*"))
        assert len(archived_files) == 1
        assert archived_files[0].read_text(encoding="utf-8") == original_content

    @pytest.mark.asyncio
    async def test_multiple_errors(
        self, engine: ReconsolidationEngine, knowledge_file: Path, procedure_file: Path,
    ) -> None:
        """Multiple prediction errors are applied independently."""
        errors = [
            _make_prediction_error(
                engine.anima_dir,
                memory_type="knowledge",
                updated_content="Updated knowledge",
                filename="api-config.md",
            ),
            _make_prediction_error(
                engine.anima_dir,
                memory_type="procedures",
                error_type="procedure_change",
                updated_content="Updated procedure",
                filename="deploy-process.md",
            ),
            _make_prediction_error(
                engine.anima_dir,
                updated_content=None,  # This one should be skipped
                filename="api-config.md",
            ),
        ]

        result = await engine.apply_reconsolidation(errors)

        assert result["updated"] == 2
        assert result["skipped"] == 1
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_error_handling(
        self, engine: ReconsolidationEngine,
    ) -> None:
        """Errors during apply are counted, not raised."""
        error = _make_prediction_error(
            engine.anima_dir,
            updated_content="Updated content",
            filename="nonexistent.md",
        )
        # The file doesn't exist, so _archive_version will be no-op
        # but write will create it. Let's cause an actual error by
        # mocking MemoryManager to raise.

        with patch(
            "core.memory.manager.MemoryManager",
        ) as MockMM:
            mock_mm = MockMM.return_value
            mock_mm.write_knowledge_with_meta.side_effect = IOError("write failed")
            mock_mm.read_knowledge_metadata.return_value = {"version": 1}

            result = await engine.apply_reconsolidation([error])

        assert result["errors"] == 1
        assert result["updated"] == 0


# ── Detect Prediction Errors (Full Pipeline) ──────────────


class TestDetectPredictionErrors:
    """Test the full detection pipeline with all dependencies mocked."""

    @pytest.mark.asyncio
    async def test_no_related_memories(
        self, engine: ReconsolidationEngine,
    ) -> None:
        """No related memories found yields no errors."""
        with patch.object(engine, "_find_related_memories", return_value=[]):
            errors = await engine.detect_prediction_errors("new episodes")

        assert errors == []

    @pytest.mark.asyncio
    async def test_no_contradiction(
        self, engine: ReconsolidationEngine,
    ) -> None:
        """Related memories that don't contradict yield no errors."""
        related = [
            {
                "file": "knowledge/api.md",
                "content": "Server on port 8080",
                "memory_type": "knowledge",
                "path": Path("knowledge/api.md"),
            }
        ]

        with patch.object(engine, "_find_related_memories", return_value=related):
            with patch.object(
                engine, "_nli_contradiction_check",
                new_callable=AsyncMock,
                return_value=(False, 0.3),
            ):
                errors = await engine.detect_prediction_errors("port 8080 working")

        assert errors == []

    @pytest.mark.asyncio
    async def test_full_pipeline_with_error(
        self, engine: ReconsolidationEngine,
    ) -> None:
        """Full pipeline: RAG -> NLI contradiction -> LLM analysis."""
        related = [
            {
                "file": "knowledge/api.md",
                "content": "Server on port 8080",
                "memory_type": "knowledge",
                "path": Path("knowledge/api.md"),
            }
        ]

        mock_error = PredictionError(
            source_file=Path("knowledge/api.md"),
            memory_type="knowledge",
            error_type="factual_update",
            description="Port changed",
            original_content="Server on port 8080",
            updated_content="Server on port 3000",
            confidence=0.7,
        )

        with patch.object(engine, "_find_related_memories", return_value=related):
            with patch.object(
                engine, "_nli_contradiction_check",
                new_callable=AsyncMock,
                return_value=(True, 0.85),
            ):
                with patch.object(
                    engine, "_analyze_prediction_error",
                    new_callable=AsyncMock,
                    return_value=mock_error,
                ):
                    errors = await engine.detect_prediction_errors("port changed to 3000")

        assert len(errors) == 1
        assert errors[0].error_type == "factual_update"

    @pytest.mark.asyncio
    async def test_llm_rejects_after_nli(
        self, engine: ReconsolidationEngine,
    ) -> None:
        """NLI detects contradiction but LLM analysis returns None."""
        related = [
            {
                "file": "knowledge/api.md",
                "content": "Server on port 8080",
                "memory_type": "knowledge",
                "path": Path("knowledge/api.md"),
            }
        ]

        with patch.object(engine, "_find_related_memories", return_value=related):
            with patch.object(
                engine, "_nli_contradiction_check",
                new_callable=AsyncMock,
                return_value=(True, 0.75),
            ):
                with patch.object(
                    engine, "_analyze_prediction_error",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    errors = await engine.detect_prediction_errors("some new info")

        assert errors == []


# ── Consolidation Pipeline Integration Tests ───────────────


class TestConsolidationIntegration:
    """Test integration with the ConsolidationEngine pipeline."""

    @pytest.mark.asyncio
    async def test_run_reconsolidation_method_exists(
        self, anima_dir: Path,
    ) -> None:
        """ConsolidationEngine._run_reconsolidation is callable."""
        from core.memory.consolidation import ConsolidationEngine
        engine = ConsolidationEngine(anima_dir, "test-anima")
        assert hasattr(engine, "_run_reconsolidation")
        assert callable(engine._run_reconsolidation)

    @pytest.mark.asyncio
    async def test_run_reconsolidation_no_errors(
        self, anima_dir: Path,
    ) -> None:
        """_run_reconsolidation with no errors returns zero counts."""
        from core.memory.consolidation import ConsolidationEngine

        engine = ConsolidationEngine(anima_dir, "test-anima")

        with patch(
            "core.memory.reconsolidation.ReconsolidationEngine.detect_prediction_errors",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await engine._run_reconsolidation(
                "some episodes text", "test-model",
            )

        assert result["errors_detected"] == 0
        assert result["updated"] == 0

    @pytest.mark.asyncio
    async def test_run_reconsolidation_with_errors(
        self, anima_dir: Path, knowledge_file: Path,
    ) -> None:
        """_run_reconsolidation detects and applies prediction errors."""
        from core.memory.consolidation import ConsolidationEngine

        engine = ConsolidationEngine(anima_dir, "test-anima")

        mock_error = PredictionError(
            source_file=knowledge_file,
            memory_type="knowledge",
            error_type="factual_update",
            description="Port changed",
            original_content="Server on port 8080",
            updated_content="Server on port 3000",
            confidence=0.7,
        )

        with patch(
            "core.memory.reconsolidation.ReconsolidationEngine.detect_prediction_errors",
            new_callable=AsyncMock,
            return_value=[mock_error],
        ):
            with patch(
                "core.memory.reconsolidation.ReconsolidationEngine.apply_reconsolidation",
                new_callable=AsyncMock,
                return_value={"updated": 1, "skipped": 0, "errors": 0},
            ):
                with patch.object(engine, "_update_rag_index"):
                    result = await engine._run_reconsolidation(
                        "port changed episodes", "test-model",
                    )

        assert result["errors_detected"] == 1
        assert result["updated"] == 1

    @pytest.mark.asyncio
    async def test_daily_consolidate_includes_reconsolidation_key(
        self, anima_dir: Path,
    ) -> None:
        """daily_consolidate result dict includes 'reconsolidation' key."""
        from core.memory.consolidation import ConsolidationEngine

        engine = ConsolidationEngine(anima_dir, "test-anima")

        # Create a minimal episode file
        from datetime import datetime
        today = datetime.now().date()
        episode_path = anima_dir / "episodes" / f"{today}.md"
        episode_path.write_text(
            f"# {today} Log\n\n"
            f"## {datetime.now().strftime('%H:%M')} --- Test Episode\n"
            f"Some test content here.\n",
            encoding="utf-8",
        )

        # Mock all external dependencies
        with patch.object(engine, "_summarize_episodes", new_callable=AsyncMock, return_value=""):
            with patch.object(engine, "_validate_consolidation", new_callable=AsyncMock, return_value=""):
                with patch.object(engine, "_run_reconsolidation", new_callable=AsyncMock, return_value={"errors_detected": 0}):
                    with patch("core.memory.forgetting.ForgettingEngine", side_effect=ImportError):
                        with patch("core.memory.distillation.ProceduralDistiller", side_effect=ImportError):
                            result = await engine.daily_consolidate(
                                model="test-model",
                                min_episodes=1,
                            )

        assert "reconsolidation" in result


# ── Read Metadata Tests ────────────────────────────────────


class TestReadMetadata:
    """Test the _read_metadata helper."""

    def test_read_knowledge_metadata(
        self, engine: ReconsolidationEngine, knowledge_file: Path,
    ) -> None:
        """Read metadata from a knowledge file."""
        meta = engine._read_metadata(knowledge_file)
        assert meta["confidence"] == 0.8
        assert meta["version"] == 1

    def test_read_procedure_metadata(
        self, engine: ReconsolidationEngine, procedure_file: Path,
    ) -> None:
        """Read metadata from a procedure file."""
        meta = engine._read_metadata(procedure_file)
        assert meta["confidence"] == 0.9
        assert meta["version"] == 1
        assert "deploy" in meta.get("tags", [])

    def test_read_metadata_no_frontmatter(
        self, engine: ReconsolidationEngine, anima_dir: Path,
    ) -> None:
        """Files without frontmatter return empty dict."""
        path = anima_dir / "knowledge" / "plain.md"
        path.write_text("# Just content\n\nNo frontmatter here.\n", encoding="utf-8")

        meta = engine._read_metadata(path)
        assert meta == {}


# ── PredictionError Dataclass Tests ────────────────────────


class TestPredictionError:
    """Test the PredictionError dataclass."""

    def test_creation(self) -> None:
        """PredictionError is created with all fields."""
        error = PredictionError(
            source_file=Path("/test/knowledge/api.md"),
            memory_type="knowledge",
            error_type="factual_update",
            description="Port changed",
            original_content="old content",
            updated_content="new content",
            confidence=0.8,
        )

        assert error.memory_type == "knowledge"
        assert error.error_type == "factual_update"
        assert error.confidence == 0.8

    def test_none_updated_content(self) -> None:
        """PredictionError can have None updated_content."""
        error = PredictionError(
            source_file=Path("/test/knowledge/api.md"),
            memory_type="knowledge",
            error_type="context_shift",
            description="Context changed",
            original_content="old content",
            updated_content=None,
            confidence=0.5,
        )

        assert error.updated_content is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
