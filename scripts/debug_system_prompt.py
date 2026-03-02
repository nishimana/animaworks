#!/usr/bin/env python3
"""Debug tool: visualize an Anima's system prompt with color-coded source annotations.

Generates an HTML file showing where each section of the system prompt
originates from (identity.md, injection.md, templates, computed data, etc.).

Usage:
    python scripts/debug_system_prompt.py <anima_name> [--output FILE] [--trigger TRIGGER]

Examples:
    python scripts/debug_system_prompt.py sakura
    python scripts/debug_system_prompt.py mikoto --output /tmp/mikoto_prompt.html
    python scripts/debug_system_prompt.py mei --trigger heartbeat
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Section categories and colors ───────────────────────────

COLORS: dict[str, tuple[str, str]] = {
    # (background, text)
    "header":       ("#1f2937", "#f9fafb"),
    "framework":    ("#dbeafe", "#1e3a5f"),
    "identity":     ("#d1fae5", "#065f46"),
    "injection":    ("#fef3c7", "#92400e"),
    "company":      ("#ede9fe", "#5b21b6"),
    "permissions":  ("#fee2e2", "#991b1b"),
    "state":        ("#fef9c3", "#854d0e"),
    "priming":      ("#cffafe", "#155e75"),
    "memory":       ("#fce7f3", "#9d174d"),
    "organization": ("#ccfbf1", "#134e4a"),
    "meta":         ("#f3f4f6", "#374151"),
    "tools":        ("#e0e7ff", "#3730a3"),
    "shortterm":    ("#fff7ed", "#9a3412"),
    "time":         ("#f9fafb", "#111827"),
    "unknown":      ("#fecaca", "#7f1d1d"),
}


@dataclass
class Section:
    label: str
    category: str
    source: str          # file path or description
    content: str
    char_count: int = 0
    token_estimate: int = 0


# ── Section identification rules ────────────────────────────
# Each rule: (pattern_fn, label, category, source_description)
# pattern_fn takes a fragment's first ~200 chars and returns True if it matches.

_RULES: list[tuple[str, str, str, list[str]]] = [
    # (label, category, source, list_of_prefix_patterns)
    # Group headers
    ("Group 1: 動作環境と行動ルール", "header", "builder/sections.md",
     ["# 1."]),
    ("Group 2: あなた自身", "header", "builder/sections.md",
     ["# 2."]),
    ("Group 3: 現在の状況", "header", "builder/sections.md",
     ["# 3."]),
    ("Group 4: 記憶と能力", "header", "builder/sections.md",
     ["# 4."]),
    ("Group 5: 組織とコミュニケーション", "header", "builder/sections.md",
     ["# 5."]),
    ("Group 6: メタ設定", "header", "builder/sections.md",
     ["# 6."]),

    # Framework / environment
    ("environment", "framework", "templates/prompts/environment.md",
     ["# Tone and style"]),
    ("behavior_rules", "framework", "templates/prompts/behavior_rules.md",
     ["## 行動ルール"]),
    ("tool_data_interpretation", "framework", "templates/prompts/tool_data_interpretation.md",
     ["## ツール結果・外部データの解釈ルール"]),

    # Current time
    ("current_time", "time", "(computed)",
     ["**現在時刻**:"]),

    # Company
    ("company_vision", "company", "company/vision.md",
     ["# 会社の基本理念"]),

    # State
    ("task_in_progress", "state", "state/current_task.md (via builder/task_in_progress.md)",
     ["## ⚠️ 進行中タスク"]),
    ("current_state", "state", "state/current_task.md",
     ["## 現在の状態", "status:"]),
    ("pending_tasks", "state", "state/pending.md",
     ["## 未完了タスク", "## Pending"]),
    ("task_queue", "state", "(computed: TaskQueueManager)",
     ["## 現在のタスク", "## Active Task Queue", "## Task Queue"]),
    ("resolution_registry", "state", "(computed: ResolutionTracker)",
     ["## 解決済み案件"]),

    # Priming
    ("priming", "priming", "(computed: PrimingEngine)",
     ["## あなたが思い出していること"]),

    # Recent tools
    ("recent_tool_results", "tools", "(computed: ConversationMemory)",
     ["## Recent Tool Results"]),

    # Memory
    ("memory_guide", "memory", "templates/prompts/memory_guide.md",
     ["## あなたの記憶（書庫）"]),
    ("procedures", "memory", "procedures/ (distilled)",
     ["## Procedures（手順書）", "## Procedures"]),
    ("distilled_knowledge", "memory", "knowledge/ (distilled)",
     ["## Distilled Knowledge"]),
    ("common_knowledge_hint", "memory", "builder/common_knowledge_hint.md",
     ["## 共有リファレンス"]),

    # Hiring
    ("hiring_rules", "organization", "builder/hiring_rules_s.md",
     ["## 雇用ルール"]),

    # Tool guides
    ("mcp_tools", "tools", "(computed: tool guides — s_mcp / prompt_db)",
     ["## MCPツール", "## ツールの使い方"]),
    ("external_tools", "tools", "(computed: build_tools_guide)",
     ["## 外部ツール"]),
    ("heartbeat_tool_instruction", "tools", "builder/heartbeat_tool_instruction.md",
     ["Heartbeatでは**観察"]),

    # Organization
    ("org_context", "organization", "(computed: _build_org_context)",
     ["## あなたの組織上の位置"]),
    ("messaging", "organization", "templates/prompts/messaging_s.md",
     ["## メッセージ送信"]),
    ("board", "organization", "(part of messaging template)",
     ["## Board（共有チャネル）"]),
    ("human_notification", "organization", "builder/human_notification.md",
     ["## 人間への連絡"]),
    ("hiring_context", "organization", "(computed: hiring_context)",
     ["## 雇用ガイド", "新しいAnimaの雇用"]),

    # Meta
    ("emotion", "meta", "builder/emotion_instruction.md",
     ["## 表情メタデータ"]),
    ("a_reflection", "meta", "templates/prompts/a_reflection.md",
     ["## 自己反省"]),
    ("c_response_requirement", "meta", "(hardcoded in builder)",
     ["## 応答要件"]),

    # Shortterm
    ("shortterm_memory", "shortterm", "shortterm/session_state.md",
     ["## 短期記憶", "# 短期記憶"]),
]


def _identify_fragment(text: str, anima_sources: dict[str, str]) -> tuple[str, str, str] | None:
    """Try to identify a prompt fragment by its content.

    Returns (label, category, source) or None if unidentified.
    Fragments that are sub-sections (### heading) of a parent section
    return None so they get merged with the previous section.
    """
    stripped = text.strip()
    if not stripped:
        return None

    first_line = stripped.split("\n")[0]

    # 1. Check anima-specific sources FIRST (identity.md, injection.md, etc.)
    #    These take priority even if they start with ### sub-headings.
    _ANIMA_FILE_MAP = {
        "identity":    ("identity.md", "identity", "animas/<name>/identity.md"),
        "injection":   ("injection.md", "injection", "animas/<name>/injection.md"),
        "permissions": ("permissions.md", "permissions", "animas/<name>/permissions.md"),
        "bootstrap":   ("bootstrap.md", "state", "animas/<name>/bootstrap.md"),
        "specialty":   ("specialty_prompt.md", "company", "animas/<name>/specialty_prompt.md"),
    }
    for key, source_content in anima_sources.items():
        if not source_content:
            continue
        src_first = source_content.strip().split("\n")[0][:80]
        if src_first and first_line[:80] == src_first:
            if key in _ANIMA_FILE_MAP:
                return _ANIMA_FILE_MAP[key]

    # 2. Check pattern rules (heading-based, reliable)
    for label, category, source, prefixes in _RULES:
        for prefix in prefixes:
            if stripped.startswith(prefix):
                return (label, category, source)

    # 3. Sub-headings (### or deeper) that didn't match any known source
    #    are continuations of the parent section (procedures/knowledge items
    #    joined with \n\n---\n\n inside a single builder part).
    if first_line.startswith("### ") or first_line.startswith("#### "):
        return None

    # 4. Italic/bold-only lines (e.g. footer quotes in vision.md) are continuations
    if first_line.startswith("*") and not first_line.startswith("**現在時刻"):
        return None

    # 5. Anima/task mode declarations
    if stripped.startswith("Anima:") and "Data directory:" in stripped[:200]:
        return ("task_mode_header", "framework", "(computed: task mode)")

    return None


def _build_anima_sources(anima_dir: Path) -> dict[str, str]:
    """Read anima-specific source files for matching."""
    sources: dict[str, str] = {}
    for name, filename in [
        ("identity", "identity.md"),
        ("injection", "injection.md"),
        ("permissions", "permissions.md"),
        ("bootstrap", "bootstrap.md"),
        ("specialty", "specialty_prompt.md"),
    ]:
        p = anima_dir / filename
        if p.exists():
            sources[name] = p.read_text(encoding="utf-8")
        else:
            sources[name] = ""
    return sources


def _split_and_identify(
    prompt: str,
    anima_sources: dict[str, str],
    anima_name: str,
) -> list[Section]:
    """Split the prompt by section separators and identify each section."""
    separator = "\n\n---\n\n"
    fragments = prompt.split(separator)

    sections: list[Section] = []
    for frag in fragments:
        if not frag.strip():
            continue

        ident = _identify_fragment(frag, anima_sources)
        if ident:
            label, category, source = ident
            source = source.replace("<name>", anima_name)
            sections.append(Section(
                label=label,
                category=category,
                source=source,
                content=frag,
                char_count=len(frag),
                token_estimate=len(frag) // 3,
            ))
        else:
            # Unidentified: try to merge with previous section
            # (handles environment.md's internal --- separator)
            if sections:
                prev = sections[-1]
                prev.content += separator + frag
                prev.char_count = len(prev.content)
                prev.token_estimate = prev.char_count // 3
            else:
                sections.append(Section(
                    label="(unknown)",
                    category="unknown",
                    source="?",
                    content=frag,
                    char_count=len(frag),
                    token_estimate=len(frag) // 3,
                ))

    return sections


# ── HTML generation ─────────────────────────────────────────

def _render_html(sections: list[Section], anima_name: str, trigger: str) -> str:
    """Generate a color-coded HTML visualization."""
    total_chars = sum(s.char_count for s in sections)
    total_tokens = sum(s.token_estimate for s in sections)

    # Build legend
    seen_categories: dict[str, str] = {}
    for s in sections:
        if s.category not in seen_categories:
            seen_categories[s.category] = s.label

    legend_items = []
    for cat in seen_categories:
        bg, fg = COLORS.get(cat, COLORS["unknown"])
        legend_items.append(
            f'<span style="background:{bg};color:{fg};padding:2px 8px;'
            f'border-radius:4px;margin:2px;display:inline-block;font-size:13px">'
            f'{escape(cat)}</span>'
        )

    # Build TOC
    toc_rows = []
    for i, s in enumerate(sections):
        bg, fg = COLORS.get(s.category, COLORS["unknown"])
        pct = (s.char_count / total_chars * 100) if total_chars > 0 else 0
        toc_rows.append(
            f'<tr>'
            f'<td style="text-align:right;padding:2px 8px;color:#6b7280">{i+1}</td>'
            f'<td><a href="#section-{i}" style="text-decoration:none">'
            f'<span style="background:{bg};color:{fg};padding:1px 6px;border-radius:3px;font-size:12px">'
            f'{escape(s.category)}</span> '
            f'{escape(s.label)}</a></td>'
            f'<td style="text-align:right;padding:2px 8px;font-family:monospace;font-size:13px">'
            f'{s.char_count:,}</td>'
            f'<td style="text-align:right;padding:2px 8px;font-family:monospace;font-size:13px">'
            f'~{s.token_estimate:,}</td>'
            f'<td style="text-align:right;padding:2px 8px;font-family:monospace;font-size:13px">'
            f'{pct:.1f}%</td>'
            f'<td style="color:#9ca3af;font-size:12px;padding:2px 8px">'
            f'{escape(s.source)}</td>'
            f'</tr>'
        )

    # Build section blocks
    section_blocks = []
    for i, s in enumerate(sections):
        bg, fg = COLORS.get(s.category, COLORS["unknown"])
        # Use a lighter version for the content background
        content_bg = bg + "40" if bg.startswith("#") else bg  # won't work with hex
        # Compute a very light background
        section_blocks.append(f'''
<div id="section-{i}" style="margin-bottom:16px;">
  <div style="background:{bg};color:{fg};padding:6px 12px;border-radius:8px 8px 0 0;
              display:flex;justify-content:space-between;align-items:center;
              position:sticky;top:0;z-index:10">
    <div>
      <strong>#{i+1} {escape(s.label)}</strong>
      <span style="opacity:0.7;margin-left:12px;font-size:13px">{escape(s.category)}</span>
    </div>
    <div style="font-size:12px;opacity:0.8">
      {s.char_count:,} chars (~{s.token_estimate:,} tokens)
      &middot; {escape(s.source)}
    </div>
  </div>
  <pre style="background:#1e1e2e;color:#cdd6f4;padding:12px;margin:0;
              border-radius:0 0 8px 8px;overflow-x:auto;font-size:13px;
              line-height:1.5;white-space:pre-wrap;word-wrap:break-word;
              border:1px solid {bg};border-top:none">{escape(s.content)}</pre>
</div>''')

    # Bar chart
    bar_segments = []
    for s in sections:
        bg, _ = COLORS.get(s.category, COLORS["unknown"])
        pct = (s.char_count / total_chars * 100) if total_chars > 0 else 0
        if pct >= 0.5:  # Only show segments >= 0.5%
            bar_segments.append(
                f'<div title="{escape(s.label)} ({pct:.1f}%)" '
                f'style="width:{pct}%;background:{bg};height:100%;'
                f'display:inline-block"></div>'
            )

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>System Prompt Debug: {escape(anima_name)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f0f23;
    color: #e0e0e0;
    padding: 20px;
    max-width: 1200px;
    margin: 0 auto;
  }}
  h1 {{ color: #f9fafb; margin-bottom: 8px; }}
  a {{ color: #93c5fd; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #374151;
       color: #9ca3af; font-size: 13px; }}
  tr:hover {{ background: #1f2937; }}
</style>
</head>
<body>

<h1>System Prompt Debug: {escape(anima_name)}</h1>
<p style="color:#9ca3af;margin-bottom:4px">
  Trigger: <code>{escape(trigger)}</code> &middot;
  Sections: {len(sections)} &middot;
  Total: {total_chars:,} chars (~{total_tokens:,} tokens)
</p>

<div style="margin:16px 0">
  <p style="color:#9ca3af;font-size:13px;margin-bottom:4px">Categories:</p>
  <div>{"".join(legend_items)}</div>
</div>

<div style="margin:16px 0">
  <p style="color:#9ca3af;font-size:13px;margin-bottom:4px">Size distribution:</p>
  <div style="height:24px;border-radius:6px;overflow:hidden;background:#1f2937;
              display:flex">{"".join(bar_segments)}</div>
</div>

<details style="margin:16px 0" open>
  <summary style="cursor:pointer;color:#93c5fd;font-size:15px;margin-bottom:8px">
    Section Table ({len(sections)} sections)
  </summary>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Section</th><th>Chars</th><th>Tokens</th><th>%</th><th>Source</th>
      </tr>
    </thead>
    <tbody>
      {"".join(toc_rows)}
    </tbody>
  </table>
</details>

<hr style="border:1px solid #374151;margin:24px 0">

{"".join(section_blocks)}

<footer style="color:#6b7280;font-size:12px;margin-top:32px;padding-top:16px;
               border-top:1px solid #374151">
  Generated by debug_system_prompt.py &middot;
  {escape(anima_name)} &middot; trigger={escape(trigger)}
</footer>

</body>
</html>'''


# ── Main ────────────────────────────────────────────────────

def _build_prompt(anima_name: str, trigger: str) -> str:
    """Build the system prompt for the given anima and trigger."""
    from core.memory import MemoryManager
    from core.memory.priming import PrimingEngine, format_priming_section
    from core.memory.shortterm import ShortTermMemory
    from core.paths import get_data_dir, get_shared_dir
    from core.prompt.builder import build_system_prompt, inject_shortterm

    data_dir = get_data_dir()
    anima_dir = data_dir / "animas" / anima_name

    if not anima_dir.exists():
        print(f"ERROR: Anima directory not found: {anima_dir}", file=sys.stderr)
        sys.exit(1)

    memory = MemoryManager(anima_dir)

    # Read model config for context window
    try:
        model_config = memory.read_model_config()
        context_window = 200_000  # default
        # Try to get actual context window
        from core.prompt.context import resolve_context_window
        if model_config.model:
            context_window = resolve_context_window(model_config.model)
    except Exception:
        context_window = 200_000

    # Build priming section
    priming_section = ""
    try:
        shared_dir = get_shared_dir()
        engine = PrimingEngine(anima_dir, shared_dir, context_window=context_window)

        sender = "taka"
        message = "テスト"
        channel = trigger.split(":")[0] if ":" in trigger else trigger

        result = asyncio.run(engine.prime_memories(
            message=message,
            sender_name=sender,
            channel=channel,
        ))
        priming_section = format_priming_section(result, sender_name=sender)
    except Exception as e:
        print(f"WARNING: Priming failed: {e}", file=sys.stderr)

    # Tool registry (simplified)
    tool_registry: list[str] = []
    personal_tools: dict[str, str] = {}
    try:
        from core.tooling.external import ExternalToolDispatcher
        dispatcher = ExternalToolDispatcher(anima_dir)
        tool_registry = list(dispatcher.list_categories())
        personal_tools = {}  # Would need more setup
    except Exception:
        pass

    # Determine execution mode from status.json
    execution_mode = "s"
    try:
        status_path = anima_dir / "status.json"
        if status_path.exists():
            status = json.loads(status_path.read_text(encoding="utf-8"))
            execution_mode = status.get("execution_mode", "s")
    except Exception:
        pass

    # Build the prompt
    build_result = build_system_prompt(
        memory=memory,
        tool_registry=tool_registry,
        personal_tools=personal_tools or None,
        priming_section=priming_section,
        execution_mode=execution_mode,
        message="テスト",
        trigger=trigger,
        context_window=context_window,
    )

    # Inject shortterm
    try:
        shortterm = ShortTermMemory(anima_dir)
        prompt = inject_shortterm(build_result.system_prompt, shortterm)
    except Exception:
        prompt = build_result.system_prompt

    return prompt


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualize an Anima's system prompt with color-coded source annotations"
    )
    parser.add_argument("anima", help="Anima name (e.g. sakura, mikoto)")
    parser.add_argument(
        "--output", "-o",
        default="/tmp/prompt_debug_{anima}.html",
        help="Output HTML file path (default: /tmp/prompt_debug_<anima>.html)",
    )
    parser.add_argument(
        "--trigger", "-t",
        default="chat",
        help="Trigger mode: chat, heartbeat, inbox:<sender>, cron:<name>, task:<id> (default: chat)",
    )
    args = parser.parse_args()

    output_path = args.output.replace("{anima}", args.anima)
    anima_name = args.anima
    trigger = args.trigger

    print(f"Building system prompt for: {anima_name} (trigger={trigger})")

    # Build the actual prompt
    prompt = _build_prompt(anima_name, trigger)
    print(f"Prompt built: {len(prompt):,} chars (~{len(prompt)//3:,} tokens)")

    # Read anima-specific sources for identification
    from core.paths import get_data_dir
    anima_dir = get_data_dir() / "animas" / anima_name
    anima_sources = _build_anima_sources(anima_dir)

    # Split and identify sections
    sections = _split_and_identify(prompt, anima_sources, anima_name)
    print(f"Identified {len(sections)} sections:")
    for i, s in enumerate(sections):
        print(f"  {i+1:2d}. [{s.category:13s}] {s.label:30s} {s.char_count:>6,} chars  <- {s.source}")

    # Check for unknown sections
    unknowns = [s for s in sections if s.category == "unknown"]
    if unknowns:
        print(f"\nWARNING: {len(unknowns)} unidentified section(s):")
        for s in unknowns:
            preview = s.content[:100].replace("\n", "\\n")
            print(f"  - {preview}...")

    # Generate HTML
    html = _render_html(sections, anima_name, trigger)
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"\nHTML written to: {output_path}")

    # Also dump raw prompt for reference
    raw_path = output_path.replace(".html", "_raw.txt")
    Path(raw_path).write_text(prompt, encoding="utf-8")
    print(f"Raw prompt written to: {raw_path}")


if __name__ == "__main__":
    main()
