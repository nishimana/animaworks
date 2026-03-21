# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for compression fallback features:

1. Cooldown mechanism -- suppress retry after compression failure
2. Simple truncation fallback -- remove old turns when LLM fails
3. Empty turn removal -- strip turns with blank content
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.memory.conversation_models import (
    _MAX_DISPLAY_TURNS,
    ConversationState,
    ConversationTurn,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    anima_name: str = "alice",
    n_turns: int = 0,
    compressed_summary: str = "",
    compressed_turn_count: int = 0,
    last_finalized_turn_index: int = 0,
) -> ConversationState:
    """Create a ConversationState populated with *n_turns* simple turns."""
    turns = [
        ConversationTurn(
            role="human" if i % 2 == 0 else "assistant",
            content=f"turn-{i}",
            timestamp=f"2026-01-15T10:{i:02d}:00",
        )
        for i in range(n_turns)
    ]
    return ConversationState(
        anima_name=anima_name,
        turns=turns,
        compressed_summary=compressed_summary,
        compressed_turn_count=compressed_turn_count,
        last_finalized_turn_index=last_finalized_turn_index,
    )


def _make_state_with_empty_turns(
    anima_name: str = "alice",
    contents: list[str] | None = None,
) -> ConversationState:
    """Create a ConversationState with specific content strings per turn.

    Allows mixing of normal, empty (""), and whitespace-only ("  ") turns.
    """
    if contents is None:
        contents = []
    turns = [
        ConversationTurn(
            role="human" if i % 2 == 0 else "assistant",
            content=c,
            timestamp=f"2026-01-15T10:{i:02d}:00",
        )
        for i, c in enumerate(contents)
    ]
    return ConversationState(anima_name=anima_name, turns=turns)


def _dummy_model_config():
    """Return a minimal mock that satisfies model_config usage in compression."""
    mc = MagicMock()
    mc.model = "claude-sonnet-4-6"
    mc.conversation_history_threshold = 0.30
    return mc


def _dummy_load_overrides():
    """Return a callable that returns None (no context window overrides)."""
    return lambda: None


def _clear_cooldowns():
    """Reset the module-level cooldown dict to ensure test isolation."""
    import core.memory.conversation_compression as mod

    mod._compression_cooldowns.clear()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_cooldowns():
    """Clear cooldown state before and after every test."""
    _clear_cooldowns()
    yield
    _clear_cooldowns()


# ===================================================================
# 1. Cooldown mechanism
# ===================================================================


class TestCooldownMechanism:
    """Verify that compression is suppressed for a cooldown period after failure."""

    async def test_圧縮失敗後_needs_compressionがFalseを返す(self):
        """After compression failure, needs_compression returns False during cooldown."""
        import core.memory.conversation_compression as mod

        state = _make_state(anima_name="alice", n_turns=60)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        # Trigger a compression failure to set cooldown
        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("LLM unavailable")
            await mod._compress(state, model_config, save_fn, "alice")

        # Now needs_compression should return False because of cooldown
        # Even though there are enough turns, cooldown should block it
        result = mod.needs_compression(state, model_config, _dummy_load_overrides())
        assert result is False

    async def test_クールダウン期間経過後_needs_compressionがTrueに戻る(self):
        """After cooldown period expires, needs_compression returns True again."""
        import core.memory.conversation_compression as mod

        state = _make_state(anima_name="alice", n_turns=60)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        # Trigger a compression failure
        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("LLM unavailable")
            await mod._compress(state, model_config, save_fn, "alice")

        # Simulate cooldown expiry by backdating the timestamp
        mod._compression_cooldowns["alice"] = time.monotonic() - mod._COMPRESSION_COOLDOWN_SECONDS - 1

        # needs_compression should now evaluate normally
        # With 60 turns > _MAX_TURNS_BEFORE_COMPRESS(50), should return True
        # (state.turns may have been truncated by fallback; rebuild state)
        state2 = _make_state(anima_name="alice", n_turns=60)
        result = mod.needs_compression(state2, model_config, _dummy_load_overrides())
        assert result is True

    async def test_異なるanima_nameは独立したクールダウンを持つ(self):
        """Cooldown for one anima does not affect another."""
        import core.memory.conversation_compression as mod

        model_config = _dummy_model_config()
        save_fn = MagicMock()

        # Trigger cooldown for "alice"
        state_alice = _make_state(anima_name="alice", n_turns=60)
        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("LLM unavailable")
            await mod._compress(state_alice, model_config, save_fn, "alice")

        # "bob" should NOT be in cooldown
        state_bob = _make_state(anima_name="bob", n_turns=60)
        result = mod.needs_compression(state_bob, model_config, _dummy_load_overrides())
        assert result is True

        # "alice" should still be in cooldown
        state_alice2 = _make_state(anima_name="alice", n_turns=60)
        result = mod.needs_compression(state_alice2, model_config, _dummy_load_overrides())
        assert result is False

    async def test_圧縮成功時はクールダウンが設定されない(self):
        """Successful compression should NOT set a cooldown."""
        import core.memory.conversation_compression as mod

        state = _make_state(anima_name="alice", n_turns=30)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Compressed summary of older turns"
            await mod._compress(state, model_config, save_fn, "alice")

        # No cooldown should be set
        assert "alice" not in mod._compression_cooldowns

    async def test_クールダウン期限切れ後にエントリが削除される(self):
        """After cooldown expires, the entry should be removed from the dict."""
        import core.memory.conversation_compression as mod

        # Manually set an expired cooldown
        mod._compression_cooldowns["alice"] = time.monotonic() - mod._COMPRESSION_COOLDOWN_SECONDS - 1

        state = _make_state(anima_name="alice", n_turns=60)
        model_config = _dummy_model_config()
        mod.needs_compression(state, model_config, _dummy_load_overrides())

        # The expired entry should have been cleaned up
        assert "alice" not in mod._compression_cooldowns


# ===================================================================
# 2. Simple truncation fallback
# ===================================================================


class TestSimpleTruncationFallback:
    """Verify that LLM failure triggers truncation of old turns."""

    async def test_LLM失敗時に古いターンが切り捨てられる(self):
        """When LLM fails, old turns are truncated (not kept as before)."""
        import core.memory.conversation_compression as mod

        state = _make_state(anima_name="alice", n_turns=30)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        original_turn_count = len(state.turns)
        keep_count = min(_MAX_DISPLAY_TURNS, original_turn_count - 1)

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API error")
            await mod._compress(state, model_config, save_fn, "alice")

        # Turns should be truncated to keep_count, not preserved
        assert len(state.turns) == keep_count
        # The kept turns should be the most recent ones
        assert state.turns[-1].content == f"turn-{original_turn_count - 1}"

    async def test_切り捨て後にsave_fnが呼ばれる(self):
        """save_fn is called after fallback truncation."""
        import core.memory.conversation_compression as mod

        state = _make_state(anima_name="alice", n_turns=30)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API error")
            await mod._compress(state, model_config, save_fn, "alice")

        save_fn.assert_called()

    async def test_compressed_summaryは変更されない(self):
        """Existing compressed_summary is preserved during fallback truncation."""
        import core.memory.conversation_compression as mod

        existing_summary = "Previous conversation discussed project planning."
        state = _make_state(
            anima_name="alice",
            n_turns=30,
            compressed_summary=existing_summary,
        )
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API error")
            await mod._compress(state, model_config, save_fn, "alice")

        assert state.compressed_summary == existing_summary

    async def test_compressed_turn_countが正しく更新される(self):
        """compressed_turn_count is incremented by the number of removed turns."""
        import core.memory.conversation_compression as mod

        initial_compressed_count = 5
        n_turns = 30
        state = _make_state(
            anima_name="alice",
            n_turns=n_turns,
            compressed_turn_count=initial_compressed_count,
        )
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        keep_count = min(_MAX_DISPLAY_TURNS, n_turns - 1)
        expected_removed = n_turns - keep_count

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API error")
            await mod._compress(state, model_config, save_fn, "alice")

        assert state.compressed_turn_count == initial_compressed_count + expected_removed

    async def test_last_finalized_turn_indexが正しく調整される(self):
        """last_finalized_turn_index is shifted down by the number of removed turns."""
        import core.memory.conversation_compression as mod

        n_turns = 30
        keep_count = min(_MAX_DISPLAY_TURNS, n_turns - 1)
        removed_count = n_turns - keep_count
        initial_finalized_index = 20

        state = _make_state(
            anima_name="alice",
            n_turns=n_turns,
            last_finalized_turn_index=initial_finalized_index,
        )
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API error")
            await mod._compress(state, model_config, save_fn, "alice")

        expected_index = max(0, initial_finalized_index - removed_count)
        assert state.last_finalized_turn_index == expected_index

    async def test_last_finalized_turn_indexが0以下にならない(self):
        """last_finalized_turn_index does not go below 0."""
        import core.memory.conversation_compression as mod

        n_turns = 30
        state = _make_state(
            anima_name="alice",
            n_turns=n_turns,
            last_finalized_turn_index=3,  # smaller than removed count
        )
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API error")
            await mod._compress(state, model_config, save_fn, "alice")

        assert state.last_finalized_turn_index == 0

    async def test_last_finalized_turn_indexが0の場合は変更されない(self):
        """last_finalized_turn_index of 0 stays at 0 after fallback."""
        import core.memory.conversation_compression as mod

        state = _make_state(
            anima_name="alice",
            n_turns=30,
            last_finalized_turn_index=0,
        )
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API error")
            await mod._compress(state, model_config, save_fn, "alice")

        assert state.last_finalized_turn_index == 0

    async def test_フォールバック後にクールダウンが設定される(self):
        """Cooldown timestamp is recorded after fallback truncation."""
        import core.memory.conversation_compression as mod

        state = _make_state(anima_name="alice", n_turns=30)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API error")
            await mod._compress(state, model_config, save_fn, "alice")

        assert "alice" in mod._compression_cooldowns

    async def test_compressed_summaryが空の場合も保持される(self):
        """When compressed_summary is empty, fallback does not set it."""
        import core.memory.conversation_compression as mod

        state = _make_state(anima_name="alice", n_turns=30, compressed_summary="")
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API error")
            await mod._compress(state, model_config, save_fn, "alice")

        assert state.compressed_summary == ""


# ===================================================================
# 3. Empty turn removal
# ===================================================================


class TestEmptyTurnRemoval:
    """Verify that turns with empty/blank content are removed before compression."""

    async def test_空contentのターンが除去される(self):
        """Turns with empty string content are removed."""
        import core.memory.conversation_compression as mod

        contents = ["hello", "", "world", "", "foo", "bar", "baz", "qux"]
        state = _make_state_with_empty_turns(anima_name="alice", contents=contents)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Summary"
            await mod._compress(state, model_config, save_fn, "alice")

        # No turn with empty content should remain
        for turn in state.turns:
            assert turn.content.strip() != ""

    async def test_空ターン除去後にsave_fnが呼ばれる(self):
        """save_fn is called when empty turns are removed."""
        import core.memory.conversation_compression as mod

        # 6 normal + 2 empty = 8 total. After removal -> 6 turns.
        contents = ["a", "", "b", "c", "d", "", "e", "f"]
        state = _make_state_with_empty_turns(anima_name="alice", contents=contents)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Summary"
            await mod._compress(state, model_config, save_fn, "alice")

        # save_fn should be called at least once for empty turn removal
        assert save_fn.call_count >= 1

    async def test_空ターン除去のみで圧縮閾値を下回った場合_LLM圧縮はスキップ(self):
        """When empty turn removal reduces turns below 4, LLM compression is skipped."""
        import core.memory.conversation_compression as mod

        # 5 turns total, 3 are empty -> only 2 real turns remain (< 4)
        contents = ["hello", "", "", "world", ""]
        state = _make_state_with_empty_turns(anima_name="alice", contents=contents)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            await mod._compress(state, model_config, save_fn, "alice")

        # LLM should NOT have been called because only 2 turns remain
        mock_llm.assert_not_called()
        # But save_fn should have been called to persist the empty turn removal
        save_fn.assert_called()
        # Only non-empty turns should remain
        assert len(state.turns) == 2
        assert state.turns[0].content == "hello"
        assert state.turns[1].content == "world"

    async def test_空白のみのcontentも除去対象(self):
        """Whitespace-only content (spaces, newlines, tabs) is also removed."""
        import core.memory.conversation_compression as mod

        contents = ["hello", "  ", "world", "\n", "\t", "foo", "bar", "baz"]
        state = _make_state_with_empty_turns(anima_name="alice", contents=contents)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Summary"
            await mod._compress(state, model_config, save_fn, "alice")

        # No turn with whitespace-only content should remain
        for turn in state.turns:
            assert turn.content.strip() != ""

    async def test_正常なcontentのターンは影響を受けない(self):
        """Turns with non-empty content are not affected by empty turn removal."""
        import core.memory.conversation_compression as mod

        contents = ["alpha", "beta", "gamma", "delta", "epsilon"]
        state = _make_state_with_empty_turns(anima_name="alice", contents=contents)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        original_contents = [t.content for t in state.turns]

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Summary"
            await mod._compress(state, model_config, save_fn, "alice")

        # All original non-empty turns should still be present (though some may
        # have been compressed away by the LLM step; the point is none were
        # incorrectly removed by the empty-turn filter)
        remaining_contents = [t.content for t in state.turns]
        for c in remaining_contents:
            assert c in original_contents

    async def test_空ターンが存在しない場合_save_fnは空ターン除去では呼ばれない(self):
        """When there are no empty turns, save_fn is not called for empty turn removal.

        (It may still be called by the LLM compression step.)
        """
        import core.memory.conversation_compression as mod

        contents = ["a", "b", "c", "d", "e", "f", "g", "h"]
        state = _make_state_with_empty_turns(anima_name="alice", contents=contents)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Summary"
            await mod._compress(state, model_config, save_fn, "alice")

        # save_fn is called once for the LLM compression result.
        # It should NOT have an extra call from empty turn removal.
        assert save_fn.call_count == 1

    async def test_全ターンが空の場合_LLM圧縮はスキップ(self):
        """When all turns are empty, after removal 0 turns remain; LLM is skipped."""
        import core.memory.conversation_compression as mod

        contents = ["", "  ", "\n", "\t\n"]
        state = _make_state_with_empty_turns(anima_name="alice", contents=contents)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            await mod._compress(state, model_config, save_fn, "alice")

        mock_llm.assert_not_called()
        assert len(state.turns) == 0
        save_fn.assert_called()


# ===================================================================
# 4. Integration: empty turn removal + fallback
# ===================================================================


class TestEmptyTurnRemovalWithFallback:
    """Combined scenarios: empty turn removal happens before LLM call,
    and if LLM fails, fallback truncation acts on the cleaned turns."""

    async def test_空ターン除去後にLLM失敗_フォールバック切り捨てが動作する(self):
        """Empty turns are removed first, then LLM fails, then fallback truncates."""
        import core.memory.conversation_compression as mod

        # 25 normal turns + 5 empty turns = 30 total
        contents = []
        for i in range(30):
            if i % 6 == 5:
                contents.append("")
            else:
                contents.append(f"content-{i}")

        state = _make_state_with_empty_turns(anima_name="alice", contents=contents)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        non_empty_count = sum(1 for c in contents if c.strip())

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("LLM down")
            await mod._compress(state, model_config, save_fn, "alice")

        # After empty removal and fallback truncation, no empty turns should exist
        for turn in state.turns:
            assert turn.content.strip() != ""

        # Turns should be truncated to keep_count based on non-empty count
        keep_count = min(_MAX_DISPLAY_TURNS, non_empty_count - 1)
        assert len(state.turns) == keep_count

    async def test_空ターン除去後にLLM成功_正常圧縮が動作する(self):
        """Empty turns removed, then LLM succeeds with normal compression."""
        import core.memory.conversation_compression as mod

        # 20 normal turns + 4 empty = 24 total
        contents = []
        for i in range(24):
            if i % 6 == 0 and i > 0:
                contents.append("")
            else:
                contents.append(f"msg-{i}")

        state = _make_state_with_empty_turns(anima_name="alice", contents=contents)
        model_config = _dummy_model_config()
        save_fn = MagicMock()

        with patch.object(mod, "_call_compression_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Compressed summary"
            await mod._compress(state, model_config, save_fn, "alice")

        # compressed_summary should be updated (LLM succeeded)
        assert state.compressed_summary == "Compressed summary"
        # No empty turns in the result
        for turn in state.turns:
            assert turn.content.strip() != ""
