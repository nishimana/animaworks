# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Compression logic for conversation memory."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from core.i18n import t
from core.memory.conversation_models import (
    _MAX_DISPLAY_TURNS,
    _MAX_TURNS_BEFORE_COMPRESS,
    ConversationState,
    ConversationTurn,
)
from core.paths import load_prompt

logger = logging.getLogger("animaworks.conversation_memory")

# 圧縮失敗後のクールダウン管理（プロセス内インメモリ）
_compression_cooldowns: dict[str, float] = {}
_COMPRESSION_COOLDOWN_SECONDS: int = 300  # 5分


async def _call_llm(
    system: str,
    user_content: str,
    max_tokens: int = 1000,
) -> str:
    """Common LLM helper with automatic backend selection.

    Raises RuntimeError when all LLM backends fail so callers
    can keep raw turns instead of saving an empty summary.
    """
    from core.memory._llm_utils import one_shot_completion

    result = await one_shot_completion(user_content, system_prompt=system, max_tokens=max_tokens)
    if result is None:
        raise RuntimeError("All LLM backends failed for conversation LLM call")
    return result


def _format_turns_for_compression(turns: list[ConversationTurn]) -> str:
    """Format turns into readable text for the compression prompt."""
    lines: list[str] = []
    for turn in turns:
        role = t("conversation.role_you") if turn.role == "assistant" else turn.role
        text = f"[{turn.timestamp}] {role}: {turn.content}"
        if turn.tool_records:
            tools = ", ".join(tr.tool_name for tr in turn.tool_records)
            text += "\n  " + t("conversation.tools_used", tools=tools)
        lines.append(text)
    return "\n\n".join(lines)


async def _call_compression_llm(
    old_summary: str,
    new_turns: str,
) -> str:
    """Call the LLM to produce a compressed conversation summary."""
    system = load_prompt("memory/conversation_compression")

    user_content = ""
    if old_summary:
        user_content += f"{t('conversation.existing_summary_header')}\n\n{old_summary}\n\n---\n\n"
    user_content += f"{t('conversation.new_turns_header')}\n\n{new_turns}\n\n"
    user_content += t("conversation.integrate_instruction")

    return await _call_llm(system, user_content, max_tokens=2000)


def needs_compression(
    state: ConversationState,
    model_config: Any,
    load_context_window_overrides_fn: Callable[[], dict[str, int] | None],
) -> bool:
    """Check whether conversation history exceeds the compression threshold."""
    # クールダウンチェック: 圧縮失敗後の一定期間は再試行を抑制
    if state.anima_name in _compression_cooldowns:
        if time.monotonic() - _compression_cooldowns[state.anima_name] < _COMPRESSION_COOLDOWN_SECONDS:
            return False
        else:
            del _compression_cooldowns[state.anima_name]

    if len(state.turns) < 4:
        return False

    # Turn-count trigger: force compression regardless of token estimate
    if len(state.turns) > _MAX_TURNS_BEFORE_COMPRESS:
        return True

    from core.prompt.context import resolve_context_window

    window = resolve_context_window(model_config.model, load_context_window_overrides_fn())

    # Auto-scale threshold for small context models.
    configured = model_config.conversation_history_threshold
    if window < 64_000:
        auto_threshold = max(0.10, window / 64_000 * 0.30)
        effective_threshold = min(configured, auto_threshold)
    else:
        effective_threshold = configured

    threshold_tokens = int(window * effective_threshold)
    return state.total_token_estimate > threshold_tokens


async def compress_if_needed(
    state: ConversationState,
    model_config: Any,
    load_context_window_overrides_fn: Callable[[], dict[str, int] | None],
    save_fn: Callable[[], None],
    anima_name: str = "",
) -> bool:
    """Compress older conversation turns if the threshold is exceeded.

    Returns True if compression was performed.
    """
    if not needs_compression(state, model_config, load_context_window_overrides_fn):
        return False
    await _compress(state, model_config, save_fn, anima_name)
    return True


async def _compress(
    state: ConversationState,
    model_config: Any,
    save_fn: Callable[[], None],
    anima_name: str = "",
) -> None:
    """Perform LLM-based compression of older conversation turns."""
    if len(state.turns) < 4:
        return

    # 空ターンの除去（圧縮の前処理）
    original_count = len(state.turns)
    state.turns = [turn for turn in state.turns if turn.content.strip()]
    removed_empty = original_count - len(state.turns)
    if removed_empty > 0:
        logger.info("Removed %d empty turns for %s", removed_empty, anima_name)
        save_fn()

    # 空ターン除去後の再チェック
    if len(state.turns) < 4:
        return

    # Keep a fixed number of recent turns (matches _MAX_DISPLAY_TURNS)
    keep_count = min(_MAX_DISPLAY_TURNS, len(state.turns) - 1)
    to_compress = state.turns[:-keep_count]
    to_keep = state.turns[-keep_count:]

    old_summary = state.compressed_summary
    turn_text = _format_turns_for_compression(to_compress)

    try:
        summary = await _call_compression_llm(old_summary, turn_text)
    except Exception:
        logger.warning(
            "Conversation compression LLM failed for %s; falling back to simple truncation (%d turns removed)",
            state.anima_name,
            len(to_compress),
            exc_info=True,
        )
        # フォールバック: LLM 要約なしで古いターンを切り捨て
        # 既存の compressed_summary は保持する
        _compression_cooldowns[state.anima_name] = time.monotonic()
        removed_count = len(to_compress)
        state.turns = to_keep
        state.compressed_turn_count += removed_count
        if state.last_finalized_turn_index > 0:
            state.last_finalized_turn_index = max(0, state.last_finalized_turn_index - removed_count)
        save_fn()
        return

    removed_count = len(to_compress)
    state.turns = to_keep
    state.compressed_summary = summary
    state.compressed_turn_count += removed_count

    # Shift finalization index to match the shortened turns array.
    if state.last_finalized_turn_index > 0:
        state.last_finalized_turn_index = max(
            0,
            state.last_finalized_turn_index - removed_count,
        )

    save_fn()

    logger.info(
        "Conversation compressed for %s: %d turns -> summary (%d chars), keeping %d recent turns",
        anima_name,
        len(to_compress),
        len(summary),
        len(to_keep),
    )
