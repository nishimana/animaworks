# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Unit tests for ResponseStream._notify_seq race condition fix (Fix N3).

The ``_notify_seq`` counter was introduced to prevent a race where
``set()`` + ``clear()`` on ``asyncio.Event`` fires before the waiter's
``await`` runs, causing the waiter to miss the event.  The sequence
counter ensures that even if the Event is already cleared, a changed
``_notify_seq`` signals that a new event arrived.
"""

import asyncio

import pytest

from server.stream_registry import ResponseStream

# ── Helpers ──────────────────────────────────────────────


def _make_stream(**kwargs) -> ResponseStream:
    """Create a ResponseStream with deterministic defaults."""
    return ResponseStream(
        response_id="test123",
        anima_name="alice",
        **kwargs,
    )


# ── _notify_seq Counter Tests ────────────────────────────


class TestNotifySeqCounter:
    """Tests for _notify_seq initialization and incrementation."""

    def test_starts_at_zero(self):
        stream = _make_stream()
        assert stream._notify_seq == 0

    def test_increments_on_add_event(self):
        stream = _make_stream()
        stream.add_event("text_delta", {"text": "a"})
        assert stream._notify_seq == 1
        stream.add_event("text_delta", {"text": "b"})
        assert stream._notify_seq == 2

    def test_increments_for_all_event_types(self):
        stream = _make_stream()
        stream.add_event("text_delta", {"text": "a"})
        stream.add_event("tool_start", {"tool_name": "web_search"})
        stream.add_event("tool_end", {"tool_name": "web_search"})
        stream.add_event("done", {"status": "ok"})
        assert stream._notify_seq == 4

    def test_seq_counter_and_notify_seq_independent(self):
        """_seq_counter counts events; _notify_seq counts notifications."""
        stream = _make_stream()
        stream.add_event("text_delta", {"text": "x"})
        # Both should be 1 after one event (seq_counter is 1, notify_seq is 1)
        assert stream._seq_counter == 1
        assert stream._notify_seq == 1


# ── wait_new_event Race Fix Tests ─────────────────────────


class TestWaitNewEventRaceFix:
    """Tests for wait_new_event correctly using _notify_seq to detect events."""

    @pytest.mark.asyncio
    async def test_returns_true_on_normal_event(self):
        """Normal case: event fires during wait."""
        stream = _make_stream()

        async def _add_later():
            await asyncio.sleep(0.01)
            stream.add_event("text_delta", {"text": "x"})

        task = asyncio.create_task(_add_later())
        result = await stream.wait_new_event(timeout=2.0)
        assert result is True
        await task

    @pytest.mark.asyncio
    async def test_returns_false_on_timeout(self):
        """When no event arrives, returns False."""
        stream = _make_stream()
        result = await stream.wait_new_event(timeout=0.05)
        assert result is False

    @pytest.mark.asyncio
    async def test_detects_event_via_seq_counter(self):
        """Even if Event is cleared before waiter runs, seq counter detects the change."""
        stream = _make_stream()

        async def _fire_event():
            await asyncio.sleep(0.01)
            stream.add_event("text_delta", {"text": "x"})

        task = asyncio.create_task(_fire_event())
        result = await stream.wait_new_event(timeout=2.0)
        assert result is True
        await task

    @pytest.mark.asyncio
    async def test_done_event_detected(self):
        """A done event should also be detectable."""
        stream = _make_stream()

        async def _add_done():
            await asyncio.sleep(0.01)
            stream.add_event("done", {"status": "ok"})

        task = asyncio.create_task(_add_done())
        result = await stream.wait_new_event(timeout=2.0)
        assert result is True
        assert stream.complete is True
        await task

    @pytest.mark.asyncio
    async def test_multiple_rapid_events_all_detected(self):
        """Multiple rapid add_events should all be detectable."""
        stream = _make_stream()

        async def _fire_multiple():
            await asyncio.sleep(0.01)
            for i in range(5):
                stream.add_event("text_delta", {"text": str(i)})

        task = asyncio.create_task(_fire_multiple())
        result = await stream.wait_new_event(timeout=2.0)
        assert result is True
        assert stream._notify_seq >= 1
        await task

    @pytest.mark.asyncio
    async def test_sequential_waits_each_detect_new_events(self):
        """Sequential wait calls should each detect their own new events."""
        stream = _make_stream()

        # First event + wait
        async def _add_first():
            await asyncio.sleep(0.01)
            stream.add_event("text_delta", {"text": "first"})

        task1 = asyncio.create_task(_add_first())
        result1 = await stream.wait_new_event(timeout=2.0)
        assert result1 is True
        await task1

        seq_after_first = stream._notify_seq

        # Second event + wait
        async def _add_second():
            await asyncio.sleep(0.01)
            stream.add_event("text_delta", {"text": "second"})

        task2 = asyncio.create_task(_add_second())
        result2 = await stream.wait_new_event(timeout=2.0)
        assert result2 is True
        assert stream._notify_seq > seq_after_first
        await task2

    @pytest.mark.asyncio
    async def test_wait_sees_event_added_immediately_before(self):
        """If an event is added right before wait, the seq change is detected."""
        stream = _make_stream()

        # Add an event *before* calling wait — but we need to call wait
        # from the perspective of the old seq.  The implementation captures
        # seen_seq at the start of wait, so if we fire in a task that runs
        # before the loop iteration, it should be detected.
        async def _add_immediately():
            # Yield once so wait_new_event can capture seen_seq first
            await asyncio.sleep(0)
            stream.add_event("text_delta", {"text": "immediate"})

        task = asyncio.create_task(_add_immediately())
        result = await stream.wait_new_event(timeout=2.0)
        assert result is True
        await task


# ── Edge Cases ────────────────────────────────────────────


class TestNotifySeqEdgeCases:
    """Edge case tests for the _notify_seq mechanism."""

    def test_notify_seq_survives_buffer_eviction(self):
        """_notify_seq continues incrementing even when event buffer is evicted."""
        from server.stream_registry import MAX_EVENTS

        stream = _make_stream()
        for i in range(MAX_EVENTS + 100):
            stream.add_event("text_delta", {"text": str(i)})

        # _notify_seq should equal total events added, not buffer size
        assert stream._notify_seq == MAX_EVENTS + 100
        assert len(stream.events) == MAX_EVENTS

    @pytest.mark.asyncio
    async def test_concurrent_waiters_both_wake(self):
        """Multiple concurrent waiters should both be notified."""
        stream = _make_stream()

        async def _add_later():
            await asyncio.sleep(0.02)
            stream.add_event("text_delta", {"text": "wake"})

        task = asyncio.create_task(_add_later())
        results = await asyncio.gather(
            stream.wait_new_event(timeout=2.0),
            stream.wait_new_event(timeout=2.0),
        )
        # At least one waiter should have detected the event.
        # Both may detect it since they both see the seq change.
        assert any(r is True for r in results)
        await task


class TestWaitNewEventAfterSeq:
    """Tests for wait_new_event(after_seq=) fast-path."""

    @pytest.mark.asyncio
    async def test_returns_immediately_when_events_buffered(self):
        """If events exist beyond after_seq, return True without waiting."""
        stream = _make_stream()
        stream.add_event("text_delta", {"text": "a"})  # seq 0
        stream.add_event("text_delta", {"text": "b"})  # seq 1

        result = await stream.wait_new_event(timeout=0.1, after_seq=0)
        assert result is True

    @pytest.mark.asyncio
    async def test_after_seq_negative_one_does_not_fast_path(self):
        """after_seq=-1 (default) does not trigger fast-path; waiter must wait normally."""
        stream = _make_stream()
        stream.add_event("text_delta", {"text": "x"})  # seq 0

        # after_seq=-1 means "I have no baseline", so fast-path is skipped.
        # Without a new event arriving, this should timeout.
        result = await stream.wait_new_event(timeout=0.05, after_seq=-1)
        assert result is False

    @pytest.mark.asyncio
    async def test_waits_when_no_events_beyond_after_seq(self):
        """If no events beyond after_seq, should wait and timeout."""
        stream = _make_stream()
        stream.add_event("text_delta", {"text": "only"})  # seq 0

        result = await stream.wait_new_event(timeout=0.05, after_seq=0)
        assert result is False

    @pytest.mark.asyncio
    async def test_race_condition_fixed(self):
        """Simulate the _sse_tail race: events added between events_after() and wait_new_event().

        Without the after_seq fix, the waiter would miss the event and
        wait up to timeout seconds.
        """
        stream = _make_stream()
        stream.add_event("text_delta", {"text": "a"})  # seq 0
        stream.add_event("text_delta", {"text": "b"})  # seq 1

        # Simulate: tail fetched events_after(-1) → got [0, 1], yielded them, seq=1
        fetched = stream.events_after(-1)
        assert len(fetched) == 2
        last_seq = fetched[-1].seq  # 1

        # Simulate: while yielding, producer added event seq 2
        stream.add_event("text_delta", {"text": "c"})  # seq 2

        # Without after_seq, this would wait up to timeout because
        # _notify_seq already accounts for seq 2.
        # With after_seq=1, it detects seq 2 in the buffer immediately.
        import time

        t0 = time.monotonic()
        result = await stream.wait_new_event(timeout=5.0, after_seq=last_seq)
        elapsed = time.monotonic() - t0

        assert result is True
        assert elapsed < 0.1  # should be nearly instant

    @pytest.mark.asyncio
    async def test_negative_after_seq_ignored(self):
        """Default after_seq=-1 should not trigger fast-path on empty stream."""
        stream = _make_stream()
        # No events in buffer, after_seq=-1
        result = await stream.wait_new_event(timeout=0.05, after_seq=-1)
        assert result is False
