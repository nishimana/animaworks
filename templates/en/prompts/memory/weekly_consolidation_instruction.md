# Memory Consolidation Task (Weekly)

{anima_name}, it is time to organize your memory for the past week.

## Current knowledge files ({total_knowledge_count} total)

{knowledge_files_list}

## Merge candidates (similar file pairs)

{merge_candidates}

## Critical constraints
- **You MUST perform this work yourself directly**. Do NOT use `delegate_task`, `submit_tasks`, or `send_message`. Complete all work using only memory operation tools

## Workflow

### Step 1: Merge duplicate files (highest priority — MUST)

When merge candidates are provided, process **every pair**.
Additionally, review the file list above and find duplicate files covering the same topic yourself.

Merge procedure:
1. Use `read_memory_file` to review both contents
2. Combine the information and write to one file with `write_memory_file`
3. Archive the redundant one with `archive_memory_file`
4. If `[IMPORTANT]` tag exists, preserve it in the merged file

- "Merge later" or "too complex, skip" is NOT allowed. Complete all merges now

### Step 2: Conceptual integration of [IMPORTANT] knowledge

Consolidate `[IMPORTANT]`-tagged knowledge/ files older than 30 days.

1. Use `search_memory` to find knowledge/ with `[IMPORTANT]`; review those 30+ days old
2. Group by related themes and extract abstract principles
3. Create `concept-{theme}.md` (include `[IMPORTANT]` at the top)
4. Remove `[IMPORTANT]` tag from original files (keep the files themselves)

Skip isolated `[IMPORTANT]` entries or those less than 30 days old.

### Step 3: Procedure knowledge organization

Review files in procedures/:
- Outdated procedures → update or archive
- Similar procedures → merge

### Step 4: Compress old episodes

If episodes/ has files older than 30 days:
- Compress entries without `[IMPORTANT]` tag to key points only

### Step 5: Resolve knowledge contradictions

Check for contradictory knowledge files; keep the accurate one and archive the outdated one.

After completion, output a summary (include number of pairs merged and files archived).
