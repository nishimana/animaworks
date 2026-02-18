from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.


"""Tests for procedural memory auto-distillation (Issue 4).

Covers:
  - Pattern detection and classification
  - Section splitting
  - LLM distillation (mocked)
  - Procedure saving with frontmatter
  - Weekly pattern distillation (mocked)
  - Pipeline integration with consolidation
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an isolated anima directory with required subdirectories."""
    d = tmp_path / "animas" / "test-anima"
    for sub in (
        "episodes", "knowledge", "procedures", "skills", "state",
        "shortterm",
    ):
        (d / sub).mkdir(parents=True)

    # Set ANIMAWORKS_DATA_DIR so MemoryManager finds shared dirs
    data_dir = d.parent.parent
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(data_dir))
    for shared in ("company", "common_skills", "common_knowledge"):
        (data_dir / shared).mkdir(parents=True, exist_ok=True)
    (data_dir / "shared" / "users").mkdir(parents=True, exist_ok=True)

    return d


@pytest.fixture
def distiller(anima_dir: Path):
    """Create a ProceduralDistiller instance."""
    from core.memory.distillation import ProceduralDistiller

    return ProceduralDistiller(anima_dir=anima_dir, anima_name="test-anima")


@pytest.fixture
def consolidation_engine(anima_dir: Path):
    """Create a ConsolidationEngine instance."""
    from core.memory.consolidation import ConsolidationEngine

    return ConsolidationEngine(anima_dir=anima_dir, anima_name="test-anima")


# ── Pattern Detection ─────────────────────────────────────────


class TestIsProceduralDetection:
    """Test the _is_procedural() pattern matcher."""

    def test_procedural_with_steps(self, distiller) -> None:
        text = (
            "## デプロイ手順\n"
            "まずコマンドを実行した。次にデプロイを確認した。"
        )
        assert distiller._is_procedural(text) is True

    def test_procedural_with_arrow_chains(self, distiller) -> None:
        text = "ビルド → テスト → デプロイ → 確認。コマンドを実行した。"
        assert distiller._is_procedural(text) is True

    def test_procedural_with_ascii_arrows(self, distiller) -> None:
        text = "build -> test -> deploy。設定した後インストールを行った。"
        assert distiller._is_procedural(text) is True

    def test_procedural_with_install_and_command(self, distiller) -> None:
        text = "サーバーにインストールし、コマンドで確認した。"
        assert distiller._is_procedural(text) is True

    def test_not_procedural_plain_chat(self, distiller) -> None:
        text = "今日はいい天気でした。ミーティングで進捗を共有しました。"
        assert distiller._is_procedural(text) is False

    def test_not_procedural_single_match(self, distiller) -> None:
        """A single pattern hit should not meet the threshold (2)."""
        text = "新しいツールをインストールしたいと思います。"
        assert distiller._is_procedural(text) is False

    def test_threshold_exactly_met(self, distiller) -> None:
        """Exactly 2 pattern matches should be classified as procedural."""
        text = "手順に従って操作した。"
        assert distiller._is_procedural(text) is True

    def test_step_numbering(self, distiller) -> None:
        text = "step 1: 準備。step 2: 実行した。コマンドを打った。"
        assert distiller._is_procedural(text) is True

    def test_sequential_ordering(self, distiller) -> None:
        text = "最初にファイルを作成し、その後コマンドで確認した。"
        assert distiller._is_procedural(text) is True


# ── Section Splitting ─────────────────────────────────────────


class TestSplitIntoSections:
    """Test the Markdown section splitter."""

    def test_split_by_h2_headers(self, distiller) -> None:
        text = (
            "## Section A\nContent A\n\n"
            "## Section B\nContent B"
        )
        sections = distiller._split_into_sections(text)
        assert len(sections) == 2
        assert sections[0].startswith("## Section A")
        assert sections[1].startswith("## Section B")

    def test_no_headers(self, distiller) -> None:
        text = "Just plain text without headers."
        sections = distiller._split_into_sections(text)
        assert len(sections) == 1
        assert sections[0] == text

    def test_empty_text(self, distiller) -> None:
        sections = distiller._split_into_sections("")
        assert sections == []

    def test_strips_blank_sections(self, distiller) -> None:
        text = "\n\n## Header\nContent\n\n\n"
        sections = distiller._split_into_sections(text)
        assert len(sections) == 1


# ── Episode Classification ────────────────────────────────────


class TestClassifyEpisodeSections:
    """Test classify_episode_sections() routing."""

    def test_mixed_episodes(self, distiller) -> None:
        text = (
            "## 09:00 — ミーティング\n"
            "プロジェクト進捗を共有しました。\n\n"
            "## 10:00 — デプロイ作業\n"
            "手順に従って操作した。コマンドを実行した。デプロイを確認した。"
        )
        semantic, procedural = distiller.classify_episode_sections(text)

        assert "ミーティング" in semantic
        assert "デプロイ作業" in procedural
        assert "デプロイ作業" not in semantic
        assert "ミーティング" not in procedural

    def test_all_semantic(self, distiller) -> None:
        text = (
            "## 09:00 — 雑談\n今日はいい天気でした。\n\n"
            "## 10:00 — 報告\n進捗を報告しました。"
        )
        semantic, procedural = distiller.classify_episode_sections(text)
        assert semantic.strip() != ""
        assert procedural.strip() == ""

    def test_all_procedural(self, distiller) -> None:
        text = (
            "## 09:00 — 環境構築\n"
            "まずインストールを行い、次にコマンドで設定した。\n\n"
            "## 10:00 — デプロイ\n"
            "手順に従って操作した。デプロイを実行した。"
        )
        semantic, procedural = distiller.classify_episode_sections(text)
        assert semantic.strip() == ""
        assert procedural.strip() != ""

    def test_empty_input(self, distiller) -> None:
        semantic, procedural = distiller.classify_episode_sections("")
        assert semantic == ""
        assert procedural == ""


# ── LLM Distillation (Mocked) ─────────────────────────────────


class TestDistillProcedures:
    """Test distill_procedures() with mocked LLM."""

    @pytest.mark.asyncio
    async def test_distill_returns_procedures(self, distiller) -> None:
        llm_response = json.dumps([
            {
                "title": "deploy_to_production",
                "description": "Production deployment procedure",
                "tags": ["deploy", "ops"],
                "content": "# Deploy to Production\n\n## Steps\n1. Pull latest\n2. Run tests\n3. Deploy",
            },
        ])

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = llm_response
            mock_llm.return_value = mock_resp

            result = await distiller.distill_procedures(
                "手順に従って操作した。コマンドを実行した。デプロイした。",
                model="test-model",
            )

        assert len(result) == 1
        assert result[0]["title"] == "deploy_to_production"
        assert "Deploy to Production" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_distill_empty_input(self, distiller) -> None:
        result = await distiller.distill_procedures("")
        assert result == []

    @pytest.mark.asyncio
    async def test_distill_no_procedures_found(self, distiller) -> None:
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = "[]"
            mock_llm.return_value = mock_resp

            result = await distiller.distill_procedures(
                "手順に従って操作した。コマンドを実行した。",
                model="test-model",
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_distill_with_code_fence(self, distiller) -> None:
        """LLM output wrapped in code fences should still parse."""
        llm_response = (
            "```json\n"
            + json.dumps([
                {
                    "title": "setup_env",
                    "description": "Environment setup",
                    "tags": ["setup"],
                    "content": "# Setup\n\n1. Install deps",
                },
            ])
            + "\n```"
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = llm_response
            mock_llm.return_value = mock_resp

            result = await distiller.distill_procedures(
                "インストールを行いコマンドで設定した。",
                model="test-model",
            )

        assert len(result) == 1
        assert result[0]["title"] == "setup_env"

    @pytest.mark.asyncio
    async def test_distill_malformed_json(self, distiller) -> None:
        """Malformed JSON should return empty list without error."""
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = "not valid json at all"
            mock_llm.return_value = mock_resp

            result = await distiller.distill_procedures(
                "手順に従ってコマンドを操作した。",
                model="test-model",
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_distill_filters_incomplete_items(self, distiller) -> None:
        """Items missing 'title' or 'content' should be filtered out."""
        llm_response = json.dumps([
            {"title": "valid", "content": "# Valid"},
            {"title": "no_content"},  # missing content
            {"content": "# No Title"},  # missing title
            {"description": "neither"},  # missing both
        ])

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = llm_response
            mock_llm.return_value = mock_resp

            result = await distiller.distill_procedures(
                "手順に従ってコマンドを操作した。",
                model="test-model",
            )

        assert len(result) == 1
        assert result[0]["title"] == "valid"

    @pytest.mark.asyncio
    async def test_distill_llm_error(self, distiller) -> None:
        """LLM call failure should return empty list."""
        with patch(
            "litellm.acompletion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API down"),
        ):
            result = await distiller.distill_procedures(
                "手順に従ってコマンドを操作した。",
                model="test-model",
            )

        assert result == []


# ── Procedure Saving ──────────────────────────────────────────


class TestSaveProcedure:
    """Test save_procedure() file I/O and frontmatter."""

    def test_saves_with_frontmatter(self, distiller, anima_dir: Path) -> None:
        item = {
            "title": "deploy_app",
            "description": "Application deploy procedure",
            "tags": ["deploy", "ops"],
            "content": "# Deploy App\n\n1. Pull\n2. Build\n3. Deploy",
        }

        path = distiller.save_procedure(item)

        assert path.exists()
        assert path.name == "deploy_app.md"
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert "auto_distilled: true" in text
        assert "confidence: 0.5" in text
        assert "description: Application deploy procedure" in text
        assert "# Deploy App" in text

    def test_title_sanitization(self, distiller) -> None:
        item = {
            "title": "my procedure/with special chars!",
            "content": "# Sanitized",
        }

        path = distiller.save_procedure(item)
        assert path.exists()
        # Special chars should be replaced with underscores
        assert "/" not in path.name
        assert "!" not in path.name

    def test_saves_to_procedures_dir(self, distiller, anima_dir: Path) -> None:
        item = {"title": "test_proc", "content": "# Test"}
        path = distiller.save_procedure(item)
        assert path.parent == anima_dir / "procedures"

    def test_metadata_fields(self, distiller, anima_dir: Path) -> None:
        item = {
            "title": "check_meta",
            "description": "Test metadata fields",
            "tags": ["test"],
            "content": "# Check Metadata",
        }
        path = distiller.save_procedure(item)

        from core.memory.manager import MemoryManager

        mm = MemoryManager(anima_dir)
        meta = mm.read_procedure_metadata(path)

        assert meta["description"] == "Test metadata fields"
        assert meta["tags"] == ["test"]
        assert meta["success_count"] == 0
        assert meta["failure_count"] == 0
        assert meta["confidence"] == 0.5
        assert meta["version"] == 1
        assert meta["auto_distilled"] is True
        assert meta["last_used"] is None
        assert "created_at" in meta


# ── Existing Procedures Summary ───────────────────────────────


class TestLoadExistingProcedures:
    """Test _load_existing_procedures() summary generation."""

    def test_no_procedures(self, distiller) -> None:
        summary = distiller._load_existing_procedures()
        assert summary == "(なし)"

    def test_with_procedures(self, distiller, anima_dir: Path) -> None:
        proc_dir = anima_dir / "procedures"
        (proc_dir / "deploy.md").write_text(
            "---\ndescription: Deploy the app\n---\n\n# Deploy",
            encoding="utf-8",
        )
        (proc_dir / "backup.md").write_text(
            "---\ndescription: Backup database\n---\n\n# Backup",
            encoding="utf-8",
        )

        summary = distiller._load_existing_procedures()
        assert "deploy: Deploy the app" in summary
        assert "backup: Backup database" in summary

    def test_procedure_without_frontmatter(self, distiller, anima_dir: Path) -> None:
        proc_dir = anima_dir / "procedures"
        (proc_dir / "legacy.md").write_text(
            "# Legacy Procedure\n\nNo frontmatter",
            encoding="utf-8",
        )

        summary = distiller._load_existing_procedures()
        # Falls back to filename stem as description
        assert "legacy: legacy" in summary


# ── Weekly Pattern Distillation ───────────────────────────────


class TestWeeklyPatternDistill:
    """Test weekly_pattern_distill() with mocked LLM."""

    @pytest.mark.asyncio
    async def test_weekly_distill_creates_procedures(
        self, distiller, anima_dir: Path,
    ) -> None:
        # Create episode files for the last 3 days
        for offset in range(3):
            target_date = datetime.now().date() - timedelta(days=offset)
            episode = anima_dir / "episodes" / f"{target_date}.md"
            episode.write_text(
                f"## 09:00 — Daily deploy\n"
                f"手順に従ってコマンドを実行した。デプロイを確認した。\n",
                encoding="utf-8",
            )

        llm_response = json.dumps([
            {
                "title": "daily_deploy",
                "description": "Daily deployment pattern",
                "tags": ["deploy", "daily"],
                "content": "# Daily Deploy\n\n1. Run deploy\n2. Verify",
            },
        ])

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = llm_response
            mock_llm.return_value = mock_resp

            result = await distiller.weekly_pattern_distill(model="test-model")

        assert result["patterns_detected"] == 1
        assert len(result["procedures_created"]) == 1
        # Verify the file was actually saved
        proc_path = Path(result["procedures_created"][0])
        assert proc_path.exists()

    @pytest.mark.asyncio
    async def test_weekly_distill_no_episodes(self, distiller) -> None:
        result = await distiller.weekly_pattern_distill(model="test-model")
        assert result["patterns_detected"] == 0
        assert result["procedures_created"] == []

    @pytest.mark.asyncio
    async def test_weekly_distill_no_patterns(
        self, distiller, anima_dir: Path,
    ) -> None:
        # Create a simple episode
        today = datetime.now().date()
        episode = anima_dir / "episodes" / f"{today}.md"
        episode.write_text(
            "## 09:00 — Chat\nJust a regular conversation.\n",
            encoding="utf-8",
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = "[]"
            mock_llm.return_value = mock_resp

            result = await distiller.weekly_pattern_distill(model="test-model")

        assert result["patterns_detected"] == 0
        assert result["procedures_created"] == []

    @pytest.mark.asyncio
    async def test_weekly_distill_llm_error(
        self, distiller, anima_dir: Path,
    ) -> None:
        today = datetime.now().date()
        episode = anima_dir / "episodes" / f"{today}.md"
        episode.write_text("## 09:00 — Work\nDid stuff.\n", encoding="utf-8")

        with patch(
            "litellm.acompletion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API down"),
        ):
            result = await distiller.weekly_pattern_distill(model="test-model")

        assert result["patterns_detected"] == 0
        assert result["procedures_created"] == []


# ── Episode Collection ────────────────────────────────────────


class TestCollectRecentEpisodes:
    """Test _collect_recent_episodes() file discovery."""

    def test_collects_within_window(self, distiller, anima_dir: Path) -> None:
        today = datetime.now().date()
        episode = anima_dir / "episodes" / f"{today}.md"
        episode.write_text("Today's episodes", encoding="utf-8")

        text = distiller._collect_recent_episodes(
            anima_dir / "episodes", days=7,
        )
        assert "Today's episodes" in text

    def test_collects_multiple_days(self, distiller, anima_dir: Path) -> None:
        for offset in range(3):
            d = datetime.now().date() - timedelta(days=offset)
            ep = anima_dir / "episodes" / f"{d}.md"
            ep.write_text(f"Episode for {d}", encoding="utf-8")

        text = distiller._collect_recent_episodes(
            anima_dir / "episodes", days=7,
        )
        for offset in range(3):
            d = datetime.now().date() - timedelta(days=offset)
            assert f"Episode for {d}" in text

    def test_ignores_old_files(self, distiller, anima_dir: Path) -> None:
        old_date = datetime.now().date() - timedelta(days=10)
        ep = anima_dir / "episodes" / f"{old_date}.md"
        ep.write_text("Old episode", encoding="utf-8")

        text = distiller._collect_recent_episodes(
            anima_dir / "episodes", days=7,
        )
        assert "Old episode" not in text

    def test_empty_directory(self, distiller, anima_dir: Path) -> None:
        text = distiller._collect_recent_episodes(
            anima_dir / "episodes", days=7,
        )
        assert text == ""

    def test_collects_suffixed_files(self, distiller, anima_dir: Path) -> None:
        today = datetime.now().date()
        ep = anima_dir / "episodes" / f"{today}_heartbeat.md"
        ep.write_text("Heartbeat episode", encoding="utf-8")

        text = distiller._collect_recent_episodes(
            anima_dir / "episodes", days=7,
        )
        assert "Heartbeat episode" in text


# ── Pipeline Integration ──────────────────────────────────────


class TestDailyConsolidationIntegration:
    """Test that daily_consolidate() integrates procedural distillation."""

    @pytest.mark.asyncio
    async def test_daily_consolidate_includes_distillation(
        self, consolidation_engine, anima_dir: Path,
    ) -> None:
        """daily_consolidate() should include distillation results."""
        today = datetime.now().date()
        episode_file = anima_dir / "episodes" / f"{today}.md"
        episode_file.write_text(
            "## 09:00 — ミーティング\n"
            "進捗を共有しました。\n\n"
            "## 10:00 — デプロイ作業\n"
            "手順に従って操作した。コマンドを実行した。デプロイを確認した。\n",
            encoding="utf-8",
        )

        # Mock both the knowledge consolidation and distillation LLM calls
        knowledge_response = (
            "## 既存ファイル更新\n(なし)\n\n"
            "## 新規ファイル作成\n"
            "- ファイル名: knowledge/meeting-notes.md\n"
            "  内容: # ミーティングノート\n\n進捗共有の記録"
        )

        distill_response = json.dumps([
            {
                "title": "deploy_procedure",
                "description": "Deploy procedure",
                "tags": ["deploy"],
                "content": "# Deploy\n\n1. Run deploy\n2. Verify",
            },
        ])

        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            # First call is distillation, subsequent calls are consolidation
            if call_count == 1:
                mock_resp.choices[0].message.content = distill_response
            else:
                mock_resp.choices[0].message.content = knowledge_response
            return mock_resp

        with patch("litellm.acompletion", side_effect=mock_acompletion):
            result = await consolidation_engine.daily_consolidate(
                min_episodes=1,
                model="test-model",
            )

        assert result["skipped"] is False
        assert "distillation" in result
        # The distillation result should be present
        distill = result["distillation"]
        assert "procedures_created" in distill

    @pytest.mark.asyncio
    async def test_daily_consolidate_distillation_failure_is_non_fatal(
        self, consolidation_engine, anima_dir: Path,
    ) -> None:
        """Distillation failure should not prevent knowledge consolidation."""
        today = datetime.now().date()
        episode_file = anima_dir / "episodes" / f"{today}.md"
        episode_file.write_text(
            "## 09:00 — テスト\n"
            "テスト内容です。\n",
            encoding="utf-8",
        )

        knowledge_response = (
            "## 既存ファイル更新\n(なし)\n\n"
            "## 新規ファイル作成\n"
            "- ファイル名: knowledge/test.md\n"
            "  内容: # Test Knowledge\n\nLearned something."
        )

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = knowledge_response
            mock_llm.return_value = mock_resp

            # Make distiller classification raise an error
            with patch(
                "core.memory.distillation.ProceduralDistiller"
                ".classify_episode_sections",
                side_effect=RuntimeError("Classification exploded"),
            ):
                result = await consolidation_engine.daily_consolidate(
                    min_episodes=1,
                    model="test-model",
                )

        # Should still succeed with knowledge consolidation
        assert result["skipped"] is False
        assert result["episodes_processed"] >= 1


class TestWeeklyIntegrationWithDistillation:
    """Test that weekly_integrate() includes pattern distillation."""

    @pytest.mark.asyncio
    async def test_weekly_integrate_includes_distillation(
        self, consolidation_engine, anima_dir: Path,
    ) -> None:
        """weekly_integrate() should include weekly distillation step."""
        # Create episode data for distillation
        today = datetime.now().date()
        episode = anima_dir / "episodes" / f"{today}.md"
        episode.write_text(
            "## 09:00 — Repeated work\n"
            "手順に従ってコマンドを実行した。\n",
            encoding="utf-8",
        )

        distill_response = json.dumps([])

        with patch.object(
            consolidation_engine, "_detect_duplicates", return_value=[],
        ):
            with patch.object(
                consolidation_engine, "_compress_old_episodes", return_value=0,
            ):
                with patch.object(
                    consolidation_engine, "_rebuild_rag_index",
                ):
                    with patch(
                        "litellm.acompletion", new_callable=AsyncMock,
                    ) as mock_llm:
                        mock_resp = MagicMock()
                        mock_resp.choices = [MagicMock()]
                        mock_resp.choices[0].message.content = distill_response
                        mock_llm.return_value = mock_resp

                        result = await consolidation_engine.weekly_integrate(
                            model="test-model",
                        )

        assert "weekly_distillation" in result
        assert result["weekly_distillation"]["patterns_detected"] == 0


# ── _filter_entries_by_text ───────────────────────────────────


class TestFilterEntriesByText:
    """Test the static _filter_entries_by_text helper on ConsolidationEngine."""

    def test_keeps_matching_entries(self) -> None:
        from core.memory.consolidation import ConsolidationEngine

        entries = [
            {"date": "2026-01-01", "time": "09:00", "content": "Alpha content here"},
            {"date": "2026-01-01", "time": "10:00", "content": "Beta content here"},
        ]
        filtered_text = "Alpha content here is included"

        result = ConsolidationEngine._filter_entries_by_text(entries, filtered_text)
        assert len(result) == 1
        assert result[0]["content"] == "Alpha content here"

    def test_returns_all_when_no_match(self) -> None:
        from core.memory.consolidation import ConsolidationEngine

        entries = [
            {"date": "2026-01-01", "time": "09:00", "content": "Something"},
        ]
        # No prefix match
        result = ConsolidationEngine._filter_entries_by_text(entries, "Completely different")
        # Falls back to returning all entries
        assert len(result) == 1

    def test_empty_filtered_text(self) -> None:
        from core.memory.consolidation import ConsolidationEngine

        entries = [
            {"date": "2026-01-01", "time": "09:00", "content": "Content"},
        ]
        result = ConsolidationEngine._filter_entries_by_text(entries, "")
        assert len(result) == 1  # falls back to all


# ── _parse_procedures ─────────────────────────────────────────


class TestParseProcedures:
    """Test the JSON parser for LLM procedure output."""

    def test_valid_json_array(self, distiller) -> None:
        text = json.dumps([
            {"title": "a", "content": "# A"},
            {"title": "b", "content": "# B"},
        ])
        result = distiller._parse_procedures(text)
        assert len(result) == 2

    def test_code_fenced_json(self, distiller) -> None:
        inner = json.dumps([{"title": "x", "content": "# X"}])
        text = f"```json\n{inner}\n```"
        result = distiller._parse_procedures(text)
        assert len(result) == 1

    def test_invalid_json(self, distiller) -> None:
        result = distiller._parse_procedures("not json")
        assert result == []

    def test_non_array_json(self, distiller) -> None:
        result = distiller._parse_procedures('{"title": "x", "content": "y"}')
        assert result == []

    def test_filters_incomplete_items(self, distiller) -> None:
        text = json.dumps([
            {"title": "ok", "content": "# OK"},
            {"title": "missing_content"},
        ])
        result = distiller._parse_procedures(text)
        assert len(result) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
