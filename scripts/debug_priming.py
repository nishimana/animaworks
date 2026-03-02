#!/usr/bin/env python3
"""Priming layer debug dump.

Runs PrimingEngine.prime_memories for all trigger modes and dumps
formatted priming sections + raw JSON to /tmp/priming_debug/.
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import load_config
from core.memory.priming import PrimingEngine, PrimingResult, format_priming_section
from core.paths import get_data_dir, get_shared_dir


OUTPUT_DIR = Path("/tmp/priming_debug")


def _result_to_dict(r: PrimingResult) -> dict:
    d = asdict(r)
    d["_total_chars"] = r.total_chars()
    d["_estimated_tokens"] = r.estimated_tokens()
    return d


async def dump_priming(anima_name: str, message: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    data_dir = get_data_dir()
    anima_dir = data_dir / "animas" / anima_name
    shared_dir = get_shared_dir()

    if not anima_dir.exists():
        print(f"ERROR: Anima directory not found: {anima_dir}")
        sys.exit(1)

    engine = PrimingEngine(anima_dir, shared_dir, context_window=128_000)

    triggers = [
        ("chat",      "taka",   message),
        ("inbox",     "rin",    "sakuraさん、PRレビューお願いします"),
        ("heartbeat", "system", ""),
        ("cron",      "system", ""),
        ("task",      "system", ""),
    ]

    summary_lines: list[str] = []
    summary_lines.append(f"# Priming Debug Dump — {anima_name}")
    summary_lines.append(f"Message: {message}")
    summary_lines.append(f"Anima dir: {anima_dir}")
    summary_lines.append(f"Shared dir: {shared_dir}")
    summary_lines.append("")

    for trigger, sender, msg in triggers:
        print(f"\n{'='*60}")
        print(f"  Trigger: {trigger}  |  Sender: {sender}")
        print(f"{'='*60}")

        channel = trigger
        effective_msg = msg or f"[{trigger} trigger]"

        try:
            result = await engine.prime_memories(
                message=effective_msg,
                sender_name=sender,
                channel=channel,
                enable_dynamic_budget=(trigger != "chat"),
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            summary_lines.append(f"## {trigger} — ERROR: {e}\n")
            continue

        section = format_priming_section(result, sender_name=sender)

        # Write formatted section
        out_md = OUTPUT_DIR / f"{trigger}.md"
        out_md.write_text(f"# Priming: {trigger} (sender={sender})\n\n{section}\n", encoding="utf-8")

        # Write raw JSON
        out_json = OUTPUT_DIR / f"{trigger}_raw.json"
        out_json.write_text(json.dumps(_result_to_dict(result), ensure_ascii=False, indent=2), encoding="utf-8")

        # Print summary
        print(f"  sender_profile:   {len(result.sender_profile):>6} chars")
        print(f"  recent_activity:  {len(result.recent_activity):>6} chars")
        print(f"  related_knowledge:{len(result.related_knowledge):>6} chars")
        print(f"  related_knowledge_untrusted:{len(result.related_knowledge_untrusted):>6} chars")
        print(f"  matched_skills:   {result.matched_skills}")
        print(f"  pending_tasks:    {len(result.pending_tasks):>6} chars")
        print(f"  recent_outbound:  {len(result.recent_outbound):>6} chars")
        print(f"  TOTAL:            {result.total_chars():>6} chars (~{result.estimated_tokens()} tokens)")

        summary_lines.append(f"## {trigger} (sender={sender})")
        summary_lines.append(f"| Channel | Chars |")
        summary_lines.append(f"|---------|-------|")
        summary_lines.append(f"| sender_profile | {len(result.sender_profile)} |")
        summary_lines.append(f"| recent_activity | {len(result.recent_activity)} |")
        summary_lines.append(f"| related_knowledge | {len(result.related_knowledge)} |")
        summary_lines.append(f"| related_knowledge_untrusted | {len(result.related_knowledge_untrusted)} |")
        summary_lines.append(f"| matched_skills | {result.matched_skills} |")
        summary_lines.append(f"| pending_tasks | {len(result.pending_tasks)} |")
        summary_lines.append(f"| recent_outbound | {len(result.recent_outbound)} |")
        summary_lines.append(f"| **TOTAL** | **{result.total_chars()}** (~{result.estimated_tokens()} tokens) |")
        summary_lines.append("")

    # Write summary
    summary_path = OUTPUT_DIR / "summary.md"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"\n{'='*60}")
    print(f"Output written to: {OUTPUT_DIR}")
    print(f"  summary.md + per-trigger .md and _raw.json")


if __name__ == "__main__":
    anima = sys.argv[1] if len(sys.argv) > 1 else "sakura"
    msg = sys.argv[2] if len(sys.argv) > 2 else "最近の進捗を教えてください"
    asyncio.run(dump_priming(anima, msg))
