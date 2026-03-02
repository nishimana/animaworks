#!/usr/bin/env python3
"""Debug tool: visualise system prompt sections with color-coded HTML output.

Generates an HTML file showing where each section of an Anima's system prompt
originates from (identity.md, injection.md, templates, computed sections, etc.).

Usage:
    python scripts/debug_prompt_visualizer.py <anima_name> [--output FILE] [--trigger TRIGGER] [--mode MODE]

Examples:
    python scripts/debug_prompt_visualizer.py sakura
    python scripts/debug_prompt_visualizer.py mikoto --output /tmp/mikoto_prompt.html
    python scripts/debug_prompt_visualizer.py mei --trigger heartbeat
    python scripts/debug_prompt_visualizer.py rin --mode a
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import load_config
from core.memory import MemoryManager
from core.paths import PROJECT_DIR, get_data_dir, load_prompt
from core.prompt.builder import (
    EMOTION_INSTRUCTION,
    TIER_FULL,
    TIER_LIGHT,
    TIER_MINIMAL,
    TIER_STANDARD,
    BuildResult,
    _build_emotion_instruction,
    _build_full_org_tree,
    _build_human_notification_guidance,
    _build_messaging_section,
    _build_org_context,
    _build_recent_tool_section,
    _discover_other_animas,
    _is_mcp_mode,
    _load_a_reflection,
    _load_fallback_strings,
    _load_section_strings,
    _scan_all_animas,
    _CURRENT_TASK_MAX_CHARS,
    resolve_prompt_tier,
)
from core.time_utils import now_jst

logger = logging.getLogger("debug_prompt_visualizer")

# ── Section metadata ──────────────────────────────────────────


@dataclass
class Section:
    """A single annotated section of the system prompt."""

    label: str  # Human-readable label (e.g. "identity.md")
    category: str  # Color category (e.g. "identity", "framework")
    source: str  # Source file path or description
    content: str  # The actual text content
    group: int = 0  # Which group (1-6) this belongs to
    builder_line: str = ""  # Reference to builder.py line/function

    @property
    def char_count(self) -> int:
        return len(self.content)

    @property
    def estimated_tokens(self) -> int:
        return self.char_count // 4


# ── Color palette ─────────────────────────────────────────────

CATEGORY_COLORS: dict[str, tuple[str, str, str]] = {
    # category: (bg_color, border_color, badge_color)
    "header": ("#f3f4f6", "#6b7280", "#374151"),
    "framework": ("#dbeafe", "#3b82f6", "#1e40af"),
    "identity": ("#d1fae5", "#10b981", "#065f46"),
    "injection": ("#fef3c7", "#f59e0b", "#92400e"),
    "time": ("#f0fdf4", "#22c55e", "#166534"),
    "company": ("#ede9fe", "#8b5cf6", "#5b21b6"),
    "permissions": ("#fee2e2", "#ef4444", "#991b1b"),
    "state": ("#fef9c3", "#eab308", "#854d0e"),
    "priming": ("#cffafe", "#06b6d4", "#155e75"),
    "memory": ("#fce7f3", "#ec4899", "#9d174d"),
    "knowledge": ("#e0e7ff", "#6366f1", "#3730a3"),
    "organization": ("#ccfbf1", "#14b8a6", "#134e4a"),
    "tools": ("#e8e0ff", "#7c3aed", "#4c1d95"),
    "meta": ("#f9fafb", "#9ca3af", "#4b5563"),
    "shortterm": ("#fff7ed", "#fb923c", "#9a3412"),
    "unknown": ("#fecaca", "#f87171", "#7f1d1d"),
}


# ── Section collector ─────────────────────────────────────────


def collect_sections(
    anima_name: str,
    execution_mode: str = "s",
    trigger: str = "",
    context_window: int = 200_000,
) -> list[Section]:
    """Replicate build_system_prompt logic, capturing section metadata."""
    data_dir = get_data_dir()
    anima_dir = data_dir / "animas" / anima_name

    if not anima_dir.exists():
        print(f"ERROR: Anima directory not found: {anima_dir}", file=sys.stderr)
        sys.exit(1)

    memory = MemoryManager(anima_dir)
    pd = anima_dir
    tier = resolve_prompt_tier(context_window)
    _ss = _load_section_strings()
    _fs = _load_fallback_strings()

    sections: list[Section] = []

    def add(label: str, category: str, source: str, content: str,
            group: int = 0, builder_line: str = "") -> None:
        if content:
            sections.append(Section(
                label=label, category=category, source=source,
                content=content, group=group, builder_line=builder_line,
            ))

    # ── Trigger flags ──
    is_inbox = trigger.startswith("inbox:")
    is_heartbeat = trigger == "heartbeat"
    is_cron = trigger.startswith("cron:")
    is_task = trigger.startswith("task:")
    is_background_auto = is_heartbeat or is_cron
    is_chat = not (is_inbox or is_background_auto or is_task)

    # ── Pre-compute ──
    from core.tooling.prompt_db import get_default_guide, get_prompt_store

    _prompt_store = get_prompt_store()
    other_animas = _discover_other_animas(pd)
    skill_metas = memory.list_skill_metas()
    common_skill_metas = memory.list_common_skill_metas()
    procedure_metas = memory.list_procedure_metas()
    permissions = memory.read_permissions()

    # ════════════════════════════════════════════════════════════
    # Group 1: 動作環境と行動ルール
    # ════════════════════════════════════════════════════════════
    add(
        "Group 1 Header", "header", "builder/sections.md",
        _ss.get("group1_header", "# 1. Environment and Action Rules"),
        group=1, builder_line="L575",
    )

    if is_task:
        add(
            "Task Summary", "framework",
            "(computed: anima name + data_dir)",
            f"Anima: {pd.name}\nData directory: {data_dir}",
            group=1, builder_line="L578",
        )
    else:
        _env = (_prompt_store.get_section("environment") if _prompt_store else None)
        if _env:
            env_source = "prompt_db:environment"
            try:
                _env = _env.format(data_dir=data_dir, anima_name=pd.name)
            except (KeyError, IndexError):
                pass
        else:
            _env = load_prompt("environment", data_dir=data_dir, anima_name=pd.name)
            env_source = "templates/ja/prompts/environment.md"
        if _env:
            if tier == TIER_LIGHT and len(_env) > 8000:
                _env = _env[:8000]
                env_source += " (truncated to 8000)"
            elif tier == TIER_MINIMAL and len(_env) > 4800:
                _env = _env[:4800]
                env_source += " (truncated to 4800)"
            add("Environment", "framework", env_source, _env,
                group=1, builder_line="L580-593")

    # Identity
    identity = memory.read_identity()
    if identity:
        add("identity.md", "identity", f"animas/{anima_name}/identity.md",
            identity, group=1, builder_line="L598-600")

    # Injection
    injection = memory.read_injection()
    if injection:
        add("injection.md", "injection", f"animas/{anima_name}/injection.md",
            injection, group=1, builder_line="L602-604")

    # Current time
    current_time = now_jst().strftime("%Y-%m-%d %H:%M (%Z)")
    add("Current Time", "time", "(computed: now_jst())",
        f"{_ss.get('current_time_label', '**Current time**:')} {current_time}",
        group=1, builder_line="L606-607")

    # Behavior rules
    if tier in (TIER_FULL, TIER_STANDARD):
        _br = (_prompt_store.get_section("behavior_rules") if _prompt_store else None)
        br_source = "prompt_db:behavior_rules" if _br else "templates/ja/prompts/behavior_rules.md"
        if not _br:
            _br = load_prompt("behavior_rules")
        if _br:
            add("Behavior Rules", "framework", br_source, _br,
                group=1, builder_line="L609-614")

    # Tool data interpretation
    if not is_task:
        try:
            _tdi = load_prompt("tool_data_interpretation")
            if _tdi:
                add("Tool Data Interpretation", "framework",
                    "templates/ja/prompts/tool_data_interpretation.md",
                    _tdi, group=1, builder_line="L616-619")
        except FileNotFoundError:
            pass

    # ════════════════════════════════════════════════════════════
    # Group 2: あなた自身
    # ════════════════════════════════════════════════════════════
    add(
        "Group 2 Header", "header", "builder/sections.md",
        _ss.get("group2_header", "# 2. Yourself"),
        group=2, builder_line="L624",
    )

    # Bootstrap
    if not is_task and tier in (TIER_FULL, TIER_STANDARD):
        bootstrap = memory.read_bootstrap()
        if bootstrap:
            add("bootstrap.md", "company", f"animas/{anima_name}/bootstrap.md",
                bootstrap, group=2, builder_line="L626-629")

    # Company vision
    if not is_task and tier in (TIER_FULL, TIER_STANDARD):
        company_vision = memory.read_company_vision()
        if company_vision:
            add("Company Vision", "company", "company/vision.md",
                company_vision, group=2, builder_line="L631-634")

    # Specialty prompt
    if not is_inbox and not is_background_auto and not is_task and tier in (TIER_FULL, TIER_STANDARD):
        specialty = memory.read_specialty_prompt()
        if specialty:
            add("Specialty Prompt", "company",
                f"animas/{anima_name}/specialty_prompt.md",
                specialty, group=2, builder_line="L636-639")

    # Permissions
    if tier != TIER_MINIMAL:
        if permissions:
            add("permissions.md", "permissions",
                f"animas/{anima_name}/permissions.md",
                permissions, group=2, builder_line="L641-643")

    # ════════════════════════════════════════════════════════════
    # Group 3: 現在の状況
    # ════════════════════════════════════════════════════════════
    add(
        "Group 3 Header", "header", "builder/sections.md",
        _ss.get("group3_header", "# 3. Current Situation"),
        group=3, builder_line="L646",
    )

    # Current state
    if not is_task:
        _state_max = {
            TIER_FULL: _CURRENT_TASK_MAX_CHARS,
            TIER_STANDARD: _CURRENT_TASK_MAX_CHARS,
            TIER_LIGHT: 1000,
            TIER_MINIMAL: 500,
        }[tier]
        if is_inbox:
            _state_max = min(_state_max, 500)
        state = memory.read_current_state()
        if state and state.strip() != "status: idle":
            if len(state) > _state_max:
                truncated = state[-_state_max:]
                first_nl = truncated.find("\n")
                if first_nl != -1 and first_nl < _state_max * 0.2:
                    truncated = truncated[first_nl + 1:]
                state = f"{_fs.get('truncated', '(earlier portion omitted)')}\n\n{truncated}"
            add("Task in Progress", "state",
                f"animas/{anima_name}/state/current_task.md + builder/task_in_progress.md",
                load_prompt("builder/task_in_progress", state=state),
                group=3, builder_line="L648-666")
        elif state:
            add("Current State (idle)", "state",
                f"animas/{anima_name}/state/current_task.md",
                f"{_ss.get('current_state_header', '## Current State')}\n\n{state}",
                group=3, builder_line="L667-668")

    # Pending
    if not is_inbox and not is_task:
        pending = memory.read_pending()
        if pending:
            add("Pending Tasks", "state",
                f"animas/{anima_name}/state/pending.md",
                f"{_ss.get('pending_tasks_header', '## Pending Tasks')}\n\n{pending}",
                group=3, builder_line="L670-674")

    # Task Queue & Resolution Registry
    if not is_inbox and not is_task and tier in (TIER_FULL, TIER_STANDARD):
        try:
            from core.memory.task_queue import TaskQueueManager

            task_queue = TaskQueueManager(memory.anima_dir)
            task_summary = task_queue.format_for_priming()
            if task_summary:
                add("Task Queue", "state",
                    f"animas/{anima_name}/state/task_queue.json + builder/task_queue.md",
                    load_prompt("builder/task_queue", task_summary=task_summary),
                    group=3, builder_line="L677-685")
        except Exception as e:
            logger.debug("Failed to inject task queue: %s", e)

        try:
            resolutions = memory.read_resolutions(days=7)
            if resolutions:
                seen_issues: dict[str, dict] = {}
                for r in resolutions:
                    key = r.get("issue", "")
                    seen_issues[key] = r
                deduped = sorted(seen_issues.values(), key=lambda x: x.get("ts", ""))
                res_lines = []
                for r in deduped[-10:]:
                    ts_short = r.get("ts", "")[:16]
                    resolver = r.get("resolver", "unknown")
                    issue = r.get("issue", "")
                    res_lines.append(f"- [{ts_short}] {resolver}: {issue}")
                add("Resolution Registry", "state",
                    "builder/resolution_registry.md + resolutions.jsonl",
                    load_prompt("builder/resolution_registry",
                                res_lines="\n".join(res_lines)),
                    group=3, builder_line="L687-706")
        except Exception as e:
            logger.debug("Failed to inject resolution registry: %s", e)

    # Priming (placeholder — would need PrimingEngine)
    if not is_task:
        add("Priming (placeholder)", "priming",
            "core/memory/priming.py → PrimingEngine.prime_memories()",
            "(Priming section is generated dynamically by PrimingEngine at runtime.\n"
            "Run scripts/debug_priming.py for detailed priming analysis.)",
            group=3, builder_line="L708-710")

    # Recent tool results
    if is_chat and tier in (TIER_FULL, TIER_STANDARD):
        try:
            _model_cfg = memory.read_model_config()
            recent_tools = _build_recent_tool_section(pd, _model_cfg)
            if recent_tools:
                add("Recent Tool Results", "tools",
                    "core/memory/conversation.py → ConversationMemory",
                    recent_tools, group=3, builder_line="L712-720")
        except Exception as e:
            logger.debug("Failed to inject recent tool results: %s", e)

    # ════════════════════════════════════════════════════════════
    # Group 4: 記憶と能力
    # ════════════════════════════════════════════════════════════
    add(
        "Group 4 Header", "header", "builder/sections.md",
        _ss.get("group4_header", "# 4. Memory and Capabilities"),
        group=4, builder_line="L723",
    )

    # Memory guide
    if tier in (TIER_FULL, TIER_STANDARD):
        _none = _fs.get("none", "(none)")
        _common = _ss.get("common_label", "(shared)")
        knowledge_list_str = ", ".join(memory.list_knowledge_files()) or _none
        episode_list_str = ", ".join(memory.list_episode_files()[:7]) or _none
        procedure_list_str = ", ".join(memory.list_procedure_files()) or _none
        skill_lines: list[str] = []
        for m in skill_metas:
            desc = f": {m.description}" if m.description else ""
            skill_lines.append(f"- {m.name}{desc}")
        for m in common_skill_metas:
            desc = f": {m.description}" if m.description else ""
            skill_lines.append(f"- {m.name}{_common}{desc}")
        skill_names = "\n".join(skill_lines) or _none
        shared_users_list = ", ".join(memory.list_shared_users()) or _none

        add("Memory Guide", "memory",
            "templates/ja/prompts/memory_guide.md",
            load_prompt(
                "memory_guide",
                anima_dir=pd,
                knowledge_list=knowledge_list_str,
                episode_list=episode_list_str,
                procedure_list=procedure_list_str,
                skill_names=skill_names,
                shared_users_list=shared_users_list,
            ),
            group=4, builder_line="L725-750")

    # Distilled Knowledge Injection
    if is_task:
        knowledge_budget = 0
    elif tier == TIER_FULL:
        from core.prompt.context import resolve_context_window

        try:
            _model_config = memory.read_model_config()
            ctx_window = resolve_context_window(_model_config.model)
        except Exception:
            ctx_window = 128_000
        knowledge_budget = min(int(ctx_window * 0.05), 4000)
    elif tier == TIER_STANDARD:
        knowledge_budget = min(int(context_window * 0.03), 2000)
    else:
        knowledge_budget = 0

    procedures_list_data, knowledge_list_data = memory.collect_distilled_knowledge_separated()

    used_tokens = 0
    proc_parts: list[str] = []
    proc_sources: list[str] = []
    for entry in procedures_list_data:
        est_tokens = len(entry["content"]) // 3
        if used_tokens + est_tokens <= knowledge_budget:
            proc_parts.append(f"### {entry['name']}\n\n{entry['content']}")
            proc_sources.append(entry["path"])
            used_tokens += est_tokens

    if proc_parts:
        add("Procedures (distilled)", "knowledge",
            "procedures/ → " + ", ".join(proc_sources),
            f"{_ss.get('procedures_header', '## Procedures')}\n\n"
            + "\n\n---\n\n".join(proc_parts),
            group=4, builder_line="L776-792")

    know_parts: list[str] = []
    know_sources: list[str] = []
    for entry in knowledge_list_data:
        est_tokens = len(entry["content"]) // 3
        if used_tokens + est_tokens <= knowledge_budget:
            know_parts.append(f"### {entry['name']}\n\n{entry['content']}")
            know_sources.append(entry["name"])
            used_tokens += est_tokens

    if know_parts:
        add("Distilled Knowledge", "knowledge",
            "knowledge/ → " + ", ".join(know_sources),
            f"{_ss.get('distilled_knowledge_header', '## Distilled Knowledge')}\n\n"
            + "\n\n---\n\n".join(know_parts),
            group=4, builder_line="L794-810")

    if not is_task and tier in (TIER_FULL, TIER_STANDARD):
        common_knowledge_dir = data_dir / "common_knowledge"
        if common_knowledge_dir.exists() and any(common_knowledge_dir.rglob("*.md")):
            try:
                add("Common Knowledge Hint", "memory",
                    "builder/common_knowledge_hint.md",
                    load_prompt("builder/common_knowledge_hint"),
                    group=4, builder_line="L812-815")
            except FileNotFoundError:
                pass

        has_newstaff = any(m.name == "newstaff" for m in skill_metas)
        if has_newstaff:
            hr_key = "builder/hiring_rules_s" if _is_mcp_mode(execution_mode) else "builder/hiring_rules_other"
            try:
                add("Hiring Rules", "organization", f"templates/ja/prompts/{hr_key}.md",
                    load_prompt(hr_key),
                    group=4, builder_line="L817-822")
            except FileNotFoundError:
                pass

    # Tool usage guides
    if is_heartbeat:
        try:
            add("Heartbeat Tool Instruction", "tools",
                "builder/heartbeat_tool_instruction.md",
                load_prompt("builder/heartbeat_tool_instruction"),
                group=4, builder_line="L828-837")
        except FileNotFoundError:
            pass
    else:
        if _is_mcp_mode(execution_mode):
            _s_builtin = (
                _prompt_store.get_guide("s_builtin") if _prompt_store else None
            ) or get_default_guide("s_builtin")
            if _s_builtin:
                add("Tool Guide: S-mode Built-in", "tools",
                    "prompt_db:s_builtin (or DEFAULT_GUIDES fallback)",
                    _s_builtin, group=4, builder_line="L839-844")
            _s_mcp = (
                _prompt_store.get_guide("s_mcp") if _prompt_store else None
            ) or get_default_guide("s_mcp")
            if _s_mcp:
                add("Tool Guide: S-mode MCP", "tools",
                    "prompt_db:s_mcp (or DEFAULT_GUIDES fallback)",
                    _s_mcp, group=4, builder_line="L845-849")
        else:
            _non_s = (
                _prompt_store.get_guide("non_s") if _prompt_store else None
            ) or get_default_guide("non_s")
            if _non_s:
                add("Tool Guide: non-S mode", "tools",
                    "prompt_db:non_s (or DEFAULT_GUIDES fallback)",
                    _non_s, group=4, builder_line="L850-855")

    # External tools guide
    _EXTERNAL_TOOLS_KEYWORDS = {"外部ツール", "External Tools", "external tools"}
    if not is_heartbeat and permissions and any(kw in permissions for kw in _EXTERNAL_TOOLS_KEYWORDS):
        # In debug mode, always show external tools section if permissions mention it
        try:
            from core.tooling.guide import build_tools_guide

            # Read tool_registry from config
            cfg = load_config()
            anima_cfg = cfg.animas.get(anima_name)
            tool_reg = list(anima_cfg.tools) if anima_cfg and anima_cfg.tools else []
            personal = dict(anima_cfg.personal_tools) if anima_cfg and anima_cfg.personal_tools else {}

            if tool_reg or personal:
                if execution_mode == "a":
                    categories = ", ".join(sorted(tool_reg))
                    if personal:
                        personal_cats = ", ".join(sorted(personal.keys()))
                        categories = f"{categories}, {personal_cats}" if categories else personal_cats
                    tools_content = load_prompt("builder/external_tools_guide", categories=categories)
                else:
                    tools_content = build_tools_guide(tool_reg, personal or None)
                if tools_content:
                    add("External Tools Guide", "tools",
                        "core/tooling/guide.py → build_tools_guide()",
                        tools_content, group=4, builder_line="L857-873")
        except Exception as e:
            logger.debug("Failed to build external tools guide: %s", e)

    # ════════════════════════════════════════════════════════════
    # Group 5: 組織とコミュニケーション
    # ════════════════════════════════════════════════════════════
    add(
        "Group 5 Header", "header", "builder/sections.md",
        _ss.get("group5_header", "# 5. Organization and Communication"),
        group=5, builder_line="L876",
    )

    # Hiring context
    if not is_inbox and not is_task and tier in (TIER_FULL, TIER_STANDARD):
        if not other_animas:
            try:
                model_config = memory.read_model_config()
                if model_config.supervisor is None:
                    _hc = (
                        _prompt_store.get_section("hiring_context")
                        if _prompt_store else None
                    )
                    hc_source = "prompt_db:hiring_context" if _hc else "templates/ja/prompts/hiring_context.md"
                    if not _hc:
                        _hc = load_prompt("hiring_context")
                    if _hc:
                        add("Hiring Context", "organization", hc_source,
                            _hc, group=5, builder_line="L878-891")
            except Exception:
                pass

    # Org context
    if tier in (TIER_FULL, TIER_STANDARD):
        org_context = _build_org_context(pd.name, other_animas, execution_mode)
        if org_context:
            add("Organization Context", "organization",
                "_build_org_context() → org_context template + communication_rules",
                org_context, group=5, builder_line="L893-896")

        # Messaging
        if not is_task:
            _msg = _build_messaging_section(pd, other_animas, execution_mode)
            if is_background_auto and len(_msg) > 500:
                _msg = _msg[:500] + "\n" + _fs.get("summary", "(summary)")
            msg_key = "messaging_s" if _is_mcp_mode(execution_mode) else "messaging"
            add("Messaging", "organization",
                f"_build_messaging_section() → templates/ja/prompts/{msg_key}.md",
                _msg, group=5, builder_line="L898-902")

            # Human notification
            if not is_inbox:
                try:
                    from core.config import load_config as _load_cfg

                    _cfg = _load_cfg()
                    _my_pcfg = _cfg.animas.get(pd.name)
                    _is_top_level = _my_pcfg is None or _my_pcfg.supervisor is None
                    if _is_top_level and _cfg.human_notification.enabled:
                        add("Human Notification", "organization",
                            "_build_human_notification_guidance() → builder/human_notification.md",
                            _build_human_notification_guidance(execution_mode),
                            group=5, builder_line="L904-914")
                except Exception:
                    pass

    elif not is_task and tier == TIER_LIGHT:
        try:
            add("Light Tier Org", "organization",
                "builder/light_tier_org.md",
                load_prompt("builder/light_tier_org", anima_name=pd.name),
                group=5, builder_line="L915-920")
        except FileNotFoundError:
            pass

    # ════════════════════════════════════════════════════════════
    # Group 6: メタ設定
    # ════════════════════════════════════════════════════════════
    add(
        "Group 6 Header", "header", "builder/sections.md",
        _ss.get("group6_header", "# 6. Meta Settings"),
        group=6, builder_line="L923",
    )

    # Emotion
    if not is_background_auto and not is_task and tier in (TIER_FULL, TIER_STANDARD):
        _ei = (
            _prompt_store.get_section("emotion_instruction")
            if _prompt_store else None
        )
        ei_source = "prompt_db:emotion_instruction" if _ei else "builder/emotion_instruction.md"
        if not _ei:
            _ei = EMOTION_INSTRUCTION
        if _ei:
            add("Emotion Instruction", "meta", ei_source,
                _ei, group=6, builder_line="L925-932")

    # A reflection
    if not is_inbox and not is_background_auto and tier in (TIER_FULL, TIER_STANDARD):
        if execution_mode == "a":
            _ar = (
                _prompt_store.get_section("a_reflection")
                if _prompt_store else None
            ) or _load_a_reflection()
            if _ar:
                add("A-mode Reflection", "meta",
                    "prompt_db:a_reflection or templates a_reflection.md",
                    _ar, group=6, builder_line="L934-942")

    # C response requirement
    if execution_mode == "c" and not is_background_auto and not is_task:
        add("C-mode Response Requirement", "meta", "(hardcoded in builder.py)",
            "## 応答要件\n"
            "あなたはユーザーとの対話において、**必ずテキストで応答**してください。\n"
            "ツール呼び出しを行った場合でも、その結果の要約やユーザーへの返答を\n"
            "テキストメッセージとして出力してください。\n"
            "挨拶・質問・雑談などの会話メッセージには、ツール呼び出しの前後に\n"
            "自然なテキスト応答を必ず含めてください。",
            group=6, builder_line="L944-955")

    # ── Shortterm memory (inject_shortterm) ──
    from core.memory.shortterm import ShortTermMemory

    shortterm = ShortTermMemory(pd)
    st_content = shortterm.load_markdown()
    if st_content:
        add("Short-term Memory", "shortterm",
            f"animas/{anima_name}/shortterm/ → ShortTermMemory.load_markdown()",
            st_content, group=6, builder_line="inject_shortterm() L971-983")

    return sections


# ── HTML generation ───────────────────────────────────────────

GROUP_NAMES = {
    1: "動作環境と行動ルール",
    2: "あなた自身",
    3: "現在の状況",
    4: "記憶と能力",
    5: "組織とコミュニケーション",
    6: "メタ設定",
}


def render_html(
    sections: list[Section],
    anima_name: str,
    execution_mode: str,
    trigger: str,
    context_window: int,
) -> str:
    """Render sections as a color-coded HTML page."""
    total_chars = sum(s.char_count for s in sections)
    total_tokens = sum(s.estimated_tokens for s in sections)
    tier = resolve_prompt_tier(context_window)
    timestamp = now_jst().strftime("%Y-%m-%d %H:%M:%S %Z")

    # ── Build TOC ──
    toc_items: list[str] = []
    for i, sec in enumerate(sections):
        bg, border, badge = CATEGORY_COLORS.get(sec.category, CATEGORY_COLORS["unknown"])
        token_str = f"{sec.estimated_tokens:,}"
        pct = (sec.estimated_tokens / total_tokens * 100) if total_tokens else 0
        toc_items.append(
            f'<tr onclick="document.getElementById(\'sec-{i}\').scrollIntoView({{behavior:\'smooth\'}})" '
            f'style="cursor:pointer">'
            f'<td><span class="badge" style="background:{badge}">{sec.category}</span></td>'
            f'<td>{escape(sec.label)}</td>'
            f'<td class="num">{token_str}</td>'
            f'<td class="num">{pct:.1f}%</td>'
            f'<td class="source-cell">{escape(sec.source)}</td>'
            f'</tr>'
        )

    # ── Build section blocks ──
    section_blocks: list[str] = []
    current_group = 0
    for i, sec in enumerate(sections):
        bg, border, badge = CATEGORY_COLORS.get(sec.category, CATEGORY_COLORS["unknown"])

        # Group separator
        if sec.group != current_group and sec.group > 0:
            current_group = sec.group
            gname = GROUP_NAMES.get(sec.group, f"Group {sec.group}")
            section_blocks.append(
                f'<div class="group-divider" id="group-{sec.group}">'
                f'<span>Group {sec.group}: {escape(gname)}</span></div>'
            )

        content_escaped = escape(sec.content)
        section_blocks.append(
            f'<div class="section" id="sec-{i}" style="border-left:4px solid {border}; '
            f'background:{bg}">\n'
            f'  <div class="section-header">\n'
            f'    <div class="section-title">\n'
            f'      <span class="badge" style="background:{badge}">{escape(sec.category)}</span>\n'
            f'      <strong>{escape(sec.label)}</strong>\n'
            f'      <span class="token-count">{sec.estimated_tokens:,} tokens '
            f'({sec.char_count:,} chars)</span>\n'
            f'    </div>\n'
            f'    <div class="section-source">\n'
            f'      📁 {escape(sec.source)}'
            f'      <span class="builder-ref">builder.py {escape(sec.builder_line)}</span>\n'
            f'    </div>\n'
            f'  </div>\n'
            f'  <div class="section-body"><pre>{content_escaped}</pre></div>\n'
            f'  <button class="toggle-btn" onclick="toggleSection(this)">▼ collapse</button>\n'
            f'</div>'
        )

    # ── Legend ──
    legend_items = []
    seen_cats: set[str] = set()
    for sec in sections:
        if sec.category not in seen_cats:
            seen_cats.add(sec.category)
            bg, border, badge = CATEGORY_COLORS.get(sec.category, CATEGORY_COLORS["unknown"])
            legend_items.append(
                f'<span class="legend-item">'
                f'<span class="legend-swatch" style="background:{bg};border-color:{border}"></span>'
                f'{escape(sec.category)}</span>'
            )

    # ── Token breakdown by category ──
    cat_totals: dict[str, int] = {}
    for sec in sections:
        cat_totals[sec.category] = cat_totals.get(sec.category, 0) + sec.estimated_tokens
    bar_segments = []
    for cat, tokens in sorted(cat_totals.items(), key=lambda x: -x[1]):
        bg, border, badge = CATEGORY_COLORS.get(cat, CATEGORY_COLORS["unknown"])
        pct = (tokens / total_tokens * 100) if total_tokens else 0
        if pct >= 1:
            bar_segments.append(
                f'<div class="bar-seg" style="width:{pct}%;background:{badge}" '
                f'title="{escape(cat)}: {tokens:,} tokens ({pct:.1f}%)">'
                f'{escape(cat) if pct > 5 else ""}</div>'
            )
    bar_html = '<div class="bar-chart">' + "".join(bar_segments) + '</div>'

    cat_table_rows = []
    for cat, tokens in sorted(cat_totals.items(), key=lambda x: -x[1]):
        bg, border, badge = CATEGORY_COLORS.get(cat, CATEGORY_COLORS["unknown"])
        pct = (tokens / total_tokens * 100) if total_tokens else 0
        cat_table_rows.append(
            f'<tr><td><span class="badge" style="background:{badge}">{escape(cat)}</span></td>'
            f'<td class="num">{tokens:,}</td>'
            f'<td class="num">{pct:.1f}%</td></tr>'
        )

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>System Prompt Debug — {escape(anima_name)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #1a1a2e; color: #e0e0e0; line-height: 1.6;
    padding: 20px; max-width: 1400px; margin: 0 auto;
}}
h1 {{ color: #fff; margin-bottom: 8px; font-size: 1.6em; }}
.meta {{ color: #9ca3af; font-size: 0.85em; margin-bottom: 20px; }}
.meta span {{ margin-right: 16px; }}
.stats-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px; margin-bottom: 24px;
}}
.stat-card {{
    background: #16213e; border-radius: 8px; padding: 12px 16px;
    border: 1px solid #2a2a4a;
}}
.stat-card .label {{ font-size: 0.75em; color: #9ca3af; text-transform: uppercase; }}
.stat-card .value {{ font-size: 1.5em; font-weight: bold; color: #fff; }}
.stat-card .sub {{ font-size: 0.75em; color: #6b7280; }}

/* Legend */
.legend {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
.legend-item {{
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 0.8em; color: #d1d5db;
}}
.legend-swatch {{
    display: inline-block; width: 14px; height: 14px; border-radius: 3px;
    border: 1px solid;
}}

/* Bar chart */
.bar-chart {{
    display: flex; height: 24px; border-radius: 4px; overflow: hidden;
    margin-bottom: 24px; border: 1px solid #2a2a4a;
}}
.bar-seg {{
    display: flex; align-items: center; justify-content: center;
    font-size: 0.65em; color: #fff; font-weight: 600;
    white-space: nowrap; overflow: hidden; min-width: 2px;
}}

/* Category breakdown table */
.cat-breakdown {{
    background: #16213e; border-radius: 8px; padding: 16px;
    margin-bottom: 24px; border: 1px solid #2a2a4a;
}}
.cat-breakdown h3 {{ font-size: 0.9em; color: #9ca3af; margin-bottom: 8px; }}
.cat-breakdown table {{ width: 100%; border-collapse: collapse; }}
.cat-breakdown td {{ padding: 4px 8px; font-size: 0.85em; }}

/* TOC */
.toc {{
    background: #16213e; border-radius: 8px; padding: 16px;
    margin-bottom: 24px; border: 1px solid #2a2a4a;
}}
.toc h2 {{ font-size: 1em; color: #9ca3af; margin-bottom: 8px; }}
.toc table {{ width: 100%; border-collapse: collapse; }}
.toc th {{
    text-align: left; padding: 6px 8px; font-size: 0.75em;
    color: #6b7280; border-bottom: 1px solid #2a2a4a;
    text-transform: uppercase;
}}
.toc td {{ padding: 4px 8px; font-size: 0.85em; border-bottom: 1px solid #1a1a2e; }}
.toc tr:hover {{ background: #1e2a4a; }}
.source-cell {{ color: #6b7280; font-size: 0.8em; max-width: 300px; overflow: hidden; text-overflow: ellipsis; }}

/* Badge */
.badge {{
    display: inline-block; padding: 1px 8px; border-radius: 9999px;
    font-size: 0.7em; color: #fff; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
}}

/* Num alignment */
.num {{ text-align: right; font-variant-numeric: tabular-nums; }}

/* Group divider */
.group-divider {{
    margin: 32px 0 16px; padding: 8px 16px;
    background: #0f3460; border-radius: 6px;
    font-size: 1.1em; font-weight: bold; color: #e0e0e0;
    border-left: 4px solid #e94560;
}}

/* Section block */
.section {{
    margin-bottom: 12px; border-radius: 8px; overflow: hidden;
}}
.section-header {{
    padding: 10px 16px;
}}
.section-title {{
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}}
.section-title strong {{ color: #111827; font-size: 0.95em; }}
.token-count {{
    font-size: 0.75em; color: #6b7280; margin-left: auto;
    font-variant-numeric: tabular-nums;
}}
.section-source {{
    font-size: 0.75em; color: #4b5563; margin-top: 2px;
    display: flex; align-items: center; gap: 8px;
}}
.builder-ref {{
    color: #9ca3af; font-family: "SF Mono", "Fira Code", monospace;
    font-size: 0.9em;
}}
.section-body {{
    padding: 0 16px 12px;
}}
.section-body pre {{
    font-family: "SF Mono", "Fira Code", "Cascadia Code", Consolas, monospace;
    font-size: 0.8em; line-height: 1.5; color: #1f2937;
    white-space: pre-wrap; word-wrap: break-word;
    max-height: 600px; overflow-y: auto;
    background: rgba(255,255,255,0.4); border-radius: 4px; padding: 8px;
}}
.toggle-btn {{
    display: block; width: 100%; padding: 4px; border: none;
    background: rgba(0,0,0,0.05); color: #6b7280; cursor: pointer;
    font-size: 0.75em;
}}
.toggle-btn:hover {{ background: rgba(0,0,0,0.1); }}
.section-body.collapsed {{ display: none; }}

/* Controls */
.controls {{
    display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap;
}}
.controls button {{
    padding: 6px 14px; border: 1px solid #2a2a4a; border-radius: 6px;
    background: #16213e; color: #d1d5db; cursor: pointer; font-size: 0.85em;
}}
.controls button:hover {{ background: #1e2a4a; border-color: #3b82f6; }}
.controls input {{
    padding: 6px 14px; border: 1px solid #2a2a4a; border-radius: 6px;
    background: #16213e; color: #d1d5db; font-size: 0.85em; flex: 1; min-width: 200px;
}}
</style>
</head>
<body>
<h1>System Prompt Debug — {escape(anima_name)}</h1>
<div class="meta">
    <span>Generated: {escape(timestamp)}</span>
    <span>Mode: {escape(execution_mode)}</span>
    <span>Trigger: {escape(trigger or "chat")}</span>
    <span>Tier: {escape(tier)}</span>
    <span>Context Window: {context_window:,}</span>
</div>

<div class="stats-grid">
    <div class="stat-card">
        <div class="label">Total Tokens (est.)</div>
        <div class="value">{total_tokens:,}</div>
        <div class="sub">{total_chars:,} chars</div>
    </div>
    <div class="stat-card">
        <div class="label">Sections</div>
        <div class="value">{len(sections)}</div>
        <div class="sub">{len(set(s.category for s in sections))} categories</div>
    </div>
    <div class="stat-card">
        <div class="label">Context Usage</div>
        <div class="value">{total_tokens / (context_window // 4) * 100:.1f}%</div>
        <div class="sub">of ~{context_window // 4:,} token budget</div>
    </div>
    <div class="stat-card">
        <div class="label">Largest Section</div>
        <div class="value">{max(s.estimated_tokens for s in sections):,}</div>
        <div class="sub">{max(sections, key=lambda s: s.estimated_tokens).label}</div>
    </div>
</div>

<div class="legend">{"".join(legend_items)}</div>
{bar_html}

<div class="cat-breakdown">
    <h3>Token Breakdown by Category</h3>
    <table>{"".join(cat_table_rows)}</table>
</div>

<div class="controls">
    <button onclick="expandAll()">Expand All</button>
    <button onclick="collapseAll()">Collapse All</button>
    <button onclick="collapseAllExcept('identity')">Show Identity Only</button>
    <button onclick="collapseAllExcept('injection')">Show Injection Only</button>
    <button onclick="collapseAllExcept('framework')">Show Framework Only</button>
    <input type="text" id="search-input" placeholder="Search in prompt content..."
           oninput="searchContent(this.value)">
</div>

<div class="toc">
    <h2>Table of Contents ({len(sections)} sections)</h2>
    <table>
        <tr><th>Category</th><th>Section</th><th>Tokens</th><th>%</th><th>Source</th></tr>
        {"".join(toc_items)}
    </table>
</div>

{"".join(section_blocks)}

<script>
function toggleSection(btn) {{
    const body = btn.previousElementSibling;
    body.classList.toggle('collapsed');
    btn.textContent = body.classList.contains('collapsed') ? '▶ expand' : '▼ collapse';
}}
function expandAll() {{
    document.querySelectorAll('.section-body').forEach(b => b.classList.remove('collapsed'));
    document.querySelectorAll('.toggle-btn').forEach(b => b.textContent = '▼ collapse');
}}
function collapseAll() {{
    document.querySelectorAll('.section-body').forEach(b => b.classList.add('collapsed'));
    document.querySelectorAll('.toggle-btn').forEach(b => b.textContent = '▶ expand');
}}
function collapseAllExcept(category) {{
    document.querySelectorAll('.section').forEach(sec => {{
        const badge = sec.querySelector('.badge');
        const body = sec.querySelector('.section-body');
        const btn = sec.querySelector('.toggle-btn');
        if (badge && badge.textContent.trim().toLowerCase() === category) {{
            body.classList.remove('collapsed');
            btn.textContent = '▼ collapse';
        }} else {{
            body.classList.add('collapsed');
            btn.textContent = '▶ expand';
        }}
    }});
}}
function searchContent(query) {{
    if (!query) {{
        document.querySelectorAll('.section').forEach(s => s.style.display = '');
        document.querySelectorAll('.group-divider').forEach(d => d.style.display = '');
        return;
    }}
    const q = query.toLowerCase();
    document.querySelectorAll('.section').forEach(sec => {{
        const text = sec.textContent.toLowerCase();
        sec.style.display = text.includes(q) ? '' : 'none';
    }});
    document.querySelectorAll('.group-divider').forEach(d => d.style.display = 'none');
}}
</script>
</body>
</html>'''


# ── Main ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualise Anima system prompt with color-coded source annotations",
    )
    parser.add_argument("anima", help="Anima name (e.g. sakura, mikoto, mei)")
    parser.add_argument(
        "--output", "-o", default="",
        help="Output HTML path (default: /tmp/prompt_dump_<anima>.html)",
    )
    parser.add_argument(
        "--trigger", "-t", default="",
        help="Trigger type: '' (chat), 'heartbeat', 'inbox:sender', 'cron:job', 'task:id'",
    )
    parser.add_argument(
        "--mode", "-m", default="s",
        help="Execution mode: s (SDK/MCP), a (autonomous), c (codex) (default: s)",
    )
    parser.add_argument(
        "--context-window", "-c", type=int, default=200_000,
        help="Context window size in tokens (default: 200000)",
    )
    args = parser.parse_args()

    output_path = args.output or f"/tmp/prompt_dump_{args.anima}.html"

    print(f"Collecting sections for: {args.anima}")
    print(f"  mode={args.mode}, trigger={args.trigger or 'chat'}, "
          f"context_window={args.context_window:,}")

    sections = collect_sections(
        anima_name=args.anima,
        execution_mode=args.mode,
        trigger=args.trigger,
        context_window=args.context_window,
    )

    total_chars = sum(s.char_count for s in sections)
    total_tokens = sum(s.estimated_tokens for s in sections)

    print(f"\nCollected {len(sections)} sections:")
    for i, sec in enumerate(sections):
        pct = (sec.estimated_tokens / total_tokens * 100) if total_tokens else 0
        print(f"  [{i:2d}] {sec.label:35s} {sec.estimated_tokens:>6,} tokens "
              f"({pct:5.1f}%)  ← {sec.source}")

    print(f"\nTotal: {total_chars:,} chars ≈ {total_tokens:,} tokens")
    print(f"Tier: {resolve_prompt_tier(args.context_window)}")

    html = render_html(
        sections, args.anima, args.mode, args.trigger, args.context_window,
    )

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"\nHTML written to: {output_path}")
    print(f"Open in browser: file://{Path(output_path).resolve()}")


if __name__ == "__main__":
    main()
