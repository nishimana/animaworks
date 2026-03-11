# AnimaWorks Advanced Agent Benchmark: Claude Sonnet 4.6 vs Qwen3.5-35B

**Date**: 2026-03-11  
**Authors**: AnimaWorks Development Team  
**Subject Agent**: hina (AnimaWorks Mode A — LiteLLM tool_use loop)  
**Context**: Following a basic benchmark (15 tasks × 4 models × 3 runs) where Qwen3.5-35B and Sonnet 4.6 tied at 88%, this study uses more advanced tasks to identify remaining differences.

---

## 1. Research Objective

To determine whether a practical capability gap exists between **Claude Sonnet 4.6** (commercial) and **Qwen3.5-35B** (open-source, 35B parameters, local vLLM inference) when used as AnimaWorks Mode A agents (LiteLLM + tool_use loop).

The basic benchmark (Tier 1–3, 15 tasks) yielded identical scores. This experiment extends the evaluation by:

- **Increasing task complexity**: Each task requires 2–10 tool calls with multi-step reasoning
- **Diversifying cognitive categories**: Numerical computation, code comprehension, structural analysis, NLP, logical reasoning, error recovery, template processing, and integrated analysis
- **Quantitative output verification**: Beyond pass/fail—manual verification of output correctness against ground truth

---

## 2. Experimental Setup

### 2.1 Execution Environment

| Item | Value |
|------|-------|
| Framework | AnimaWorks v0.5.x (Mode A: LiteLLM tool_use loop) |
| Target Anima | hina |
| Server | localhost:18500 (FastAPI + Uvicorn) |
| API Timeout | 180 seconds |
| Conversation State | Fully reset before each task (conversation.json, shortterm/, streaming_journal, session) |
| File Permissions | Root `/` full access |

### 2.2 Models Under Test

| Model | Parameters | Inference Backend | Context | Cost |
|-------|-----------|------------------|---------|------|
| Claude Sonnet 4.6 (`anthropic/claude-sonnet-4-6`) | Undisclosed | Anthropic API via LiteLLM | 200K tokens | ~$0.015/task |
| Qwen3.5-35B (`openai/qwen3.5-35b-a3b`) | 35B (A3B MoE) | vLLM local GPU | 64K tokens | $0 |

### 2.3 Trial Count

Each model × 10 tasks × **2 runs** = 40 API calls (80 total)

---

## 3. Task Design

Ten advanced tasks (Tier 4) were designed to target "Opus-level" difficulty, requiring compound cognitive abilities across multiple tool calls.

### 3.1 Task Overview

| ID | Task Name | Cognitive Category | Tool Calls | Input Data | Expected Output |
|----|-----------|-------------------|:----------:|------------|----------------|
| A1 | Sales Data Analysis Pipeline | Numerical × Structured Output | 3–4 | sales.csv (8 rows) + targets.csv (3 rows) | JSON: per-region sales, achievement %, status |
| A2 | Bug Fix + Test Generation | Code Comprehension × Test Design | 3–4 | buggy.py (3 intentional bugs) | fixed.py + test_fixed.py (pytest format) |
| A3 | Nested Project Dependency Analysis | Recursive Traversal × Version Comparison | 5–7 | 3 nested dirs × package.json | JSON: library usage, version conflicts |
| A4 | Meeting Minutes Action Item Consolidation | NL Extraction × Entity Resolution × Date Reasoning | 4–6 | 3 meeting minute files (with duplicates) | JSON: deduplicated action item list |
| A5 | Config-Driven Conditional Pipeline | Meta-programming × Instruction Following | 3–4 | pipeline.json + source.txt | Text: transformation result per config |
| A6 | Fallback Data Merge | Error Recovery × Null Handling | 3–4 | primary (missing) + secondary (nulls) + defaults | JSON: 3-tier merged result |
| A7 | CSV → Aggregation → Markdown Report | Data Analysis × Format Generation | 2–3 | employees.csv (8 rows, 3 departments) | Markdown: department-level table |
| A8 | Logic Puzzle Solver | Constraint Satisfaction × Logical Reasoning | 2–3 | puzzle.txt (4-constraint seating problem) | JSON: unique solution assignment |
| A9 | Template Engine | Variable Expansion × Conditional Blocks | 2–3 | template.md + variables.json | Markdown: rendered document |
| A10 | Multi-Source Executive Report | Integrated Analysis × KPI Calculation × Risk Assessment | 4–6 | financial.json + team.json + milestones.json | Markdown: executive summary |

### 3.2 Task Details and Ground Truth

#### A1: Sales Data Analysis Pipeline

**Input data:**
```
sales.csv:
product,region,amount
Widget A,East,12000    Widget B,East,8000     Widget C,East,7000
Widget A,West,15000    Widget B,West,6000     Widget C,West,5000
Widget B,North,9000    Widget A,North,11000

targets.csv:
region,target
East,25000    West,30000    North,18000
```

**Ground truth:**
- East: total 27,000 / target 25,000 = 108% → Achieved
- West: total 26,000 / target 30,000 = 86% → Not achieved
- North: total 20,000 / target 18,000 = 111% → Achieved

**Required capabilities**: CSV parsing, group aggregation, division with floor truncation, conditional logic (≥100% → achieved), JSON structured output

---

#### A2: Bug Fix + Test Generation

**Input data** (`buggy.py`):
```python
def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)          # Bug 1: ZeroDivisionError on empty list

def find_max(items):
    if not items:
        return 0                          # Bug 2: should return None, not 0
    ...

def merge_lists(a, b):
    result = a                            # Bug 3: mutates original list (should copy)
    for item in b:
        if item not in result:
            result.append(item)
    return result
```

**Required capabilities**: Code comprehension, bug pattern recognition (division by zero, incorrect return value, mutable argument mutation), corrected code generation, pytest test case design

---

#### A3: Nested Project Dependency Analysis

**Input data** (3 projects):
```
projects/frontend/package.json: react:18.2.0, axios:1.6.0, lodash:4.17.21
projects/backend/package.json:  express:4.18.2, lodash:4.17.20, axios:1.6.0
projects/shared/package.json:   lodash:4.17.21, uuid:9.0.0
```

**Ground truth**: lodash has a conflict (4.17.20 vs 4.17.21). axios has no conflict (all 1.6.0).

**Required capabilities**: Recursive directory traversal, JSON parsing, cross-referencing, version string comparison

---

#### A4: Meeting Minutes Action Item Consolidation

**Input data** (3 meeting minutes):
- 2026-03-01: Tanaka → API spec (03-10), Suzuki → Test env (03-08), Sato → Interview (03-15)
- 2026-03-05: Tanaka → API spec (03-07), Suzuki → CI/CD (03-12), Yamada → Security review (03-14)
- 2026-03-08: Sato → Interview (03-12), Yamada → Security review (03-11), Tanaka → Deploy guide (03-20)

**Ground truth** (deduplicated, earliest deadlines):
- Tanaka: API spec → **03-07** (earliest of 03-10 and 03-07)
- Tanaka: Deploy guide → 03-20 (distinct task)
- Suzuki: Test env → 03-08
- Suzuki: CI/CD → 03-12 (distinct task)
- Sato: Interview → **03-12** (earliest of 03-15 and 03-12)
- Yamada: Security review → **03-11** (earliest of 03-14 and 03-11)

**Required capabilities**: Structured data extraction from natural language, entity resolution, date comparison, sorting

---

#### A5: Config-Driven Conditional Pipeline

**Input data:**
```json
{"steps": [
  {"type": "read", "path": "/tmp/benchmark/adv/source.txt"},
  {"type": "transform", "transform_type": "uppercase"},
  {"type": "write", "path": "/tmp/benchmark/output/pipeline_result.txt"}
]}
```
source.txt: `hello world\nfoo bar\ntest data`

**Ground truth**: `HELLO WORLD\nFOO BAR\nTEST DATA`

**Required capabilities**: JSON config interpretation, sequential step execution, string transformation rule application

---

#### A6: Fallback Data Merge

**Input data:**
- primary.json: **does not exist** (triggers error)
- secondary.json: `{name: "animaworks", version: "0.5.0", database: "postgresql", cache: null, log_level: null}`
- defaults.json: `{name: "default-app", version: "0.1.0", database: "sqlite", cache: "redis", log_level: "INFO"}`

**Ground truth**: `{name: "animaworks", version: "0.5.0", database: "postgresql", cache: "redis", log_level: "INFO"}`

**Required capabilities**: Error handling (missing file), null detection, priority-based merge logic

---

#### A7: CSV → Aggregation → Markdown Report

**Input data** (`employees.csv`):
| name | department | salary | years |
|------|-----------|--------|-------|
| Alice | Engineering | 800,000 | 5 |
| Bob | Engineering | 750,000 | 3 |
| Diana | Engineering | 900,000 | 8 |
| Charlie | Sales | 600,000 | 7 |
| Frank | Sales | 580,000 | 2 |
| Hank | Sales | 620,000 | 5 |
| Eve | Marketing | 650,000 | 4 |
| Grace | Marketing | 700,000 | 6 |

**Ground truth**:
| Department | Count | Avg Salary | Top Earner |
|-----------|-------|-----------|-----------|
| Engineering | 3 | 816,666 | Diana |
| Marketing | 2 | 675,000 | Grace |
| Sales | 3 | 600,000 | Hank |

**Required capabilities**: CSV parsing, group aggregation, average calculation (floor), max-row identification, Markdown table generation, sorting

---

#### A8: Logic Puzzle Solver

**Constraints**:
1. Alice does not sit adjacent to Bob (seat number difference = 1)
2. Charlie sits in seat 2 or seat 3
3. Diana sits immediately to the right of Charlie (Diana = Charlie + 1)
4. Alice's seat number < Bob's seat number

**Solution derivation**:
- Constraints 2+3: Charlie=2→Diana=3, or Charlie=3→Diana=4
- Charlie=3, Diana=4: Alice, Bob ∈ {1,2} → adjacent → violates constraint 1
- Charlie=2, Diana=3: Alice, Bob ∈ {1,4} → constraint 4: Alice < Bob → Alice=1, Bob=4
- Verification: Alice(1)–Bob(4) not adjacent ✓

**Unique solution**: seat1=Alice, seat2=Charlie, seat3=Diana, seat4=Bob

**Required capabilities**: Constraint satisfaction search, case analysis, contradiction detection, uniqueness verification

---

#### A9: Template Engine

**Input data:**
```markdown
# {{project_name}} Release Notes
**Version**: {{version}}
...
{% if premium %}
## Premium Support
This release includes premium support.
{% endif %}
{% if beta %}
## Beta Notice
This version is beta.
{% endif %}
```
variables: `{premium: true, beta: false, ...}`

**Ground truth**: `premium` block retained, `beta` block removed, all variables expanded

**Required capabilities**: Template syntax interpretation, conditional evaluation, variable substitution

---

#### A10: Multi-Source Executive Report

**Input data:**
- financial.json: revenue=5,200,000, costs=3,800,000
- team.json: Engineering=12, Sales=5, Operations=3, total=20
- milestones.json: completed=2, in_progress=1, planned=2

**Ground truth:**
- Profit: 5,200,000 − 3,800,000 = **1,400,000**
- Completion rate: 2/5 = **40%**
- Risk factors: at least 1 identified

**Required capabilities**: Multi-source data comprehension, KPI calculation, qualitative analysis (risk), structured report generation

---

## 4. Scoring Methodology

| Scoring Type | Applied Tasks | Criteria |
|-------------|--------------|---------|
| `valid_json_file` | A1, A3, A4, A6, A8 | Output is valid JSON with all required keys present |
| `file_content_contains_all` | A2, A7, A9, A10 | Output contains all required strings |
| `file_content_contains` | A5 | Output contains exact match of expected text |

Additionally, **manual verification against ground truth** was performed for all tasks in this report.

---

## 5. Results

### 5.1 Overall Scores

| Model | Tasks Passed | Pass Rate | Avg Response Time | Total Time | Stability |
|-------|:-----------:|:---------:|:-----------------:|:----------:|:---------:|
| **Claude Sonnet 4.6** | **20/20** | **100%** | **18.1s** | 6m 45s | All tasks 2/2 stable |
| **Qwen3.5-35B** | **20/20** | **100%** | **28.4s** | 10m 13s | All tasks 2/2 stable |

### 5.2 Per-Task Details

| Task | Sonnet R1 | Sonnet R2 | Qwen R1 | Qwen R2 | Stability |
|------|:---------:|:---------:|:-------:|:-------:|:---------:|
| A1 Sales Analysis | PASS (13.8s) | PASS (12.8s) | PASS (31.4s) | PASS (24.6s) | Both stable |
| A2 Bug Fix + Tests | PASS (35.0s) | PASS (22.4s) | PASS (47.9s) | PASS (52.7s) | Both stable |
| A3 Dependency Analysis | PASS (19.8s) | PASS (18.2s) | PASS (22.8s) | PASS (36.8s) | Both stable |
| A4 Minutes Consolidation | PASS (23.0s) | PASS (25.1s) | PASS (35.6s) | PASS (42.6s) | Both stable |
| A5 Conditional Pipeline | PASS (14.7s) | PASS (14.9s) | PASS (13.5s) | PASS (23.0s) | Both stable |
| A6 Fallback Merge | PASS (13.8s) | PASS (13.2s) | PASS (17.4s) | PASS (34.8s) | Both stable |
| A7 CSV → MD Report | PASS (11.8s) | PASS (12.0s) | PASS (16.4s) | PASS (22.6s) | Both stable |
| A8 Logic Puzzle | PASS (15.1s) | PASS (16.2s) | PASS (24.0s) | PASS (27.8s) | Both stable |
| A9 Template Engine | PASS (17.0s) | PASS (12.8s) | PASS (16.8s) | PASS (11.8s) | Both stable |
| A10 Executive Report | PASS (24.6s) | PASS (24.7s) | PASS (31.1s) | PASS (35.2s) | Both stable |

### 5.3 Response Time Comparison

| Task | Sonnet Avg | Qwen Avg | Sonnet/Qwen Ratio |
|------|:----------:|:---------:|:-----------------:|
| A1 Sales Analysis | 13.3s | 28.0s | 0.48x |
| A2 Bug Fix | 28.7s | 50.3s | 0.57x |
| A3 Dependencies | 19.0s | 29.8s | 0.64x |
| A4 Minutes | 24.1s | 39.1s | 0.62x |
| A5 Pipeline | 14.8s | 18.3s | 0.81x |
| A6 Merge | 13.5s | 26.1s | 0.52x |
| A7 CSV Aggregation | 11.9s | 19.5s | 0.61x |
| A8 Logic Puzzle | 15.7s | 25.9s | 0.61x |
| A9 Template | 14.9s | 14.3s | **1.04x** |
| A10 Executive Report | 24.7s | 33.2s | 0.74x |
| **Overall Average** | **18.1s** | **28.4s** | **0.64x** |

Qwen3.5 requires on average 1.57× more time, but was **faster than Sonnet on A9 (Template Engine)**. The gap narrows for tasks requiring less reasoning.

---

## 6. Quantitative Output Verification

Since pass/fail scores showed no differentiation, output contents were manually verified against ground truth.

### 6.1 Numerical Computation Accuracy

| Verification Item | Ground Truth | Sonnet Output | Qwen Output | Match |
|------------------|-------------|--------------|------------|:-----:|
| A1: East total sales | 27,000 | 27,000 | 27,000 | ✓ |
| A1: West achievement % | 86% | 86% | 86% | ✓ |
| A1: North achievement % | 111% | 111% | 111% | ✓ |
| A7: Engineering avg salary | 816,666 | 816,666 | 816,666 | ✓ |
| A7: Marketing avg salary | 675,000 | 675,000 | 675,000 | ✓ |
| A7: Sales avg salary | 600,000 | 600,000 | 600,000 | ✓ |
| A10: Profit | 1,400,000 | 1,400,000 | 1,400,000 | ✓ |
| A10: Completion rate | 40% | 40% | 40% | ✓ |

**All numerical computations matched ground truth exactly for both models.**

### 6.2 Logical Reasoning

| Verification Item | Ground Truth | Sonnet | Qwen | Match |
|------------------|-------------|--------|------|:-----:|
| A8: seat1 | Alice | Alice | Alice | ✓ |
| A8: seat2 | Charlie | Charlie | Charlie | ✓ |
| A8: seat3 | Diana | Diana | Diana | ✓ |
| A8: seat4 | Bob | Bob | Bob | ✓ |

**Both models derived the unique solution to the logic puzzle correctly.**

### 6.3 Entity Resolution & Deduplication

| Verification Item | Ground Truth | Sonnet | Qwen | Match |
|------------------|-------------|--------|------|:-----:|
| A4: Tanaka API spec deadline | 03-07 | 03-07 | 03-07 | ✓ |
| A4: Sato interview deadline | 03-12 | 03-12 | 03-12 | ✓ |
| A4: Yamada security deadline | 03-11 | 03-11 | 03-11 | ✓ |
| A3: lodash conflict | true | true | true | ✓ |
| A3: axios conflict | false | false | false | ✓ |

**Structured data extraction from natural language and entity deduplication matched exactly.**

### 6.4 Error Recovery

| Verification Item | Ground Truth | Sonnet | Qwen | Match |
|------------------|-------------|--------|------|:-----:|
| A6: primary missing handling | secondary→defaults | secondary→defaults | secondary→defaults | ✓ |
| A6: cache (null fill) | redis | redis | redis | ✓ |
| A6: log_level (null fill) | INFO | INFO | INFO | ✓ |

**Both models executed correct fallback processing after file-not-found error.**

### 6.5 Code Comprehension

| Verification Item | Sonnet | Qwen | Notes |
|------------------|--------|------|-------|
| Bug 1 fix | `if not numbers: return 0` | `if not numbers: return None` | Both reasonable approaches |
| Bug 2 fix | `return None` | `return None` | Identical |
| Bug 3 fix | `result = list(a)` | `result = a.copy()` | Different methods, both correct |
| Test count | 18 cases (5+6+7) | 15 cases (4+5+6) | Sonnet slightly more thorough |
| Test execution | All pytest pass | All pytest pass | Both CI-ready |

**Both models correctly identified and fixed all 3 bugs. Sonnet produced slightly more test cases (18 vs 15) but no practical difference.**

### 6.6 Output Format Quality

| Aspect | Sonnet | Qwen | Difference |
|--------|--------|------|-----------|
| JSON formatting | Indented (readable) | Partially flat (A1, A4) | Minor |
| Markdown structure | Headers + horizontal rules | Tables only (A7) | Sonnet slightly more polished |
| Comments | Explanatory comments at fix sites | FIXED markers at fix sites | Style difference only |
| Executive report | Profit margin + section dividers | Profit margin + insight comments | Equivalent quality |

---

## 7. Agent Capability Assessment in AnimaWorks

### 7.1 Mode A Agent Behavior Pattern

AnimaWorks Mode A agents operate in the following loop:

```
User message → LLM inference → tool_use decision → Tool execution → Result injection → LLM inference → ... (repeat)
```

Both models demonstrated the following capabilities across all benchmark tasks:

| Capability | Basic Bench (T1–3) | Advanced Bench (A1–10) | Notes |
|-----------|:------------------:|:---------------------:|-------|
| Single tool call | ✓ (100%) | ✓ (100%) | read_file, write_file, list_directory |
| Tool chain (2–3 calls) | ✓ (100%) | ✓ (100%) | read → transform → write |
| Tool chain (4+ calls) | — | ✓ (100%) | Dir traversal → multi-read → integrate → write |
| Intermediate reasoning | ✓ (88%) | ✓ (100%) | CSV aggregation, merge logic |
| Error handling | ✓ (partial) | ✓ (100%) | File not found → fallback |
| Structured output (JSON) | ✓ (100%) | ✓ (100%) | Schema-compliant output |
| NL → Structured data | — | ✓ (100%) | Meeting minutes → action items |
| Logical reasoning | — | ✓ (100%) | Constraint satisfaction puzzle |
| Code comprehension + fix | — | ✓ (100%) | Bug identification → fix → test |
| Template processing | — | ✓ (100%) | Variable expansion + conditionals |

### 7.2 Positioning in AnimaWorks Production Use

| Use Case | Required Capability | Sonnet | Qwen3.5 | Verdict |
|---------|-------------------|:------:|:-------:|---------|
| **Chat (Human Interaction)** | Natural responses + tools | ◎ | ○ | Sonnet (latency advantage) |
| **Heartbeat (Periodic Patrol)** | State reading → judgment → planning | ◎ | ◎ | **Qwen3.5 recommended ($0)** |
| **Cron (Scheduled Tasks)** | File I/O + aggregation | ◎ | ◎ | **Qwen3.5 recommended ($0)** |
| **Inbox (Inter-Anima DM)** | Message comprehension → reply | ◎ | ◎ | **Qwen3.5 recommended ($0)** |
| **TaskExec (Delegated Tasks)** | Multi-step execution | ◎ | ◎ | **Qwen3.5 recommended ($0)** |
| **Code Review** | Code comprehension + suggestions | ◎ | ◎ | Equivalent |
| **Data Analysis** | CSV/JSON parsing + aggregation | ◎ | ◎ | Equivalent |
| **Minutes Processing** | NL extraction + structuring | ◎ | ◎ | Equivalent |

### 7.3 Integrated Evaluation with Basic Benchmark (Round 3)

| Model | Basic Bench (15 tasks × 3 runs) | Advanced Bench (10 tasks × 2 runs) | Integrated Assessment |
|-------|:-------------------------------:|:----------------------------------:|----------------------|
| **Sonnet 4.6** | 88% (60% on T3) | **100%** | T1–2 perfect; T3 losses from ambiguous instructions + injection |
| **Qwen3.5-35B** | 88% (60% on T3) | **100%** | Identical pattern to Sonnet |
| **GLM-4.7** | 55% | — | Cannot do multi-step; excluded from advanced |
| **Qwen3-Next** | 35% | — | Unstable basic tool calls; excluded |

The T3 (judgment/error handling) failures at 60% were caused by:
- **T3-4 Prompt injection**: All models 0/3 (framework-level defenses needed)
- **T3-2 Ambiguous instructions**: Keyword-match scoring limitations (models actually behaved reasonably)

The advanced benchmark designed more practical error handling (A6: file-not-found fallback) and ambiguity resolution (A4: deduplication rule interpretation), where both models achieved 100%.

---

## 8. Discussion

### 8.1 Why Does a 35B Model Match a Commercial Model?

These results demonstrate that **a 35B-parameter MoE model is practically equivalent to commercial Sonnet 4.6 for AnimaWorks Mode A agent tasks**. We interpret this as follows:

1. **Tool-calling capability plateau**: AnimaWorks tool interfaces are relatively standardized (read_file, write_file, list_directory, etc.) and are well-learned by 35B-class models. Tool-calling accuracy likely reaches a plateau early with respect to model size.

2. **Instruction-following plateau**: The ability to follow explicit instructions ("read X, compute Y, save to Z") stabilizes beyond a certain threshold rather than scaling proportionally with model size. Qwen3.5-35B exceeds this threshold.

3. **Reasoning sufficiency**: While the tasks require 2–10 reasoning steps, each individual step has shallow depth (1–2 logical derivations). Tasks requiring Opus-level deep reasoning chains (10+ steps) may reveal differences.

### 8.2 Domains Where Differences Are Expected

The following domains were not tested but are expected to show capability gaps:

| Domain | Expected Advantage | Reason |
|--------|-------------------|--------|
| Ultra-long context (>64K) | Sonnet | Qwen3.5 context limit is 64K |
| Nuanced Japanese generation | Sonnet | Japanese training data quality gap |
| Deep recursive reasoning | Sonnet | Parameter count limitations |
| Creative writing | Sonnet | Generation diversity gap |
| Safety/ethical judgment | Sonnet | RLHF precision gap |

### 8.3 Cost Efficiency Quantification

| Scenario | Sonnet Cost | Qwen3.5 Cost | Monthly Delta (30 days) |
|---------|:----------:|:------------:|:----------------------:|
| Heartbeat every 30min (48/day) | $0.72/day | $0/day | **−$21.60** |
| Cron 3 runs/day | $0.045/day | $0/day | **−$1.35** |
| Inbox 20 messages/day | $0.30/day | $0/day | **−$9.00** |
| TaskExec 10 tasks/day | $0.15/day | $0/day | **−$4.50** |
| **Total** | **$1.215/day** | **$0/day** | **−$36.45/month** |

※ Electricity costs (GPU operation) not included. RTX 4090 costs approximately $0.10/hour, $2.40/day at 24h operation. However, vLLM can be shared with other workloads.

---

## 9. Conclusions

### 9.1 Key Findings

1. **Qwen3.5-35B matches Claude Sonnet 4.6 in agent capability**: Achieved 100% pass rate across all 10 advanced multi-step tasks (numerical computation, code comprehension, logical reasoning, NL extraction, error recovery, template processing, integrated analysis), with computed output values matching exactly.

2. **Speed difference is approximately 1.6×**: Sonnet averaged 18.1s vs Qwen3.5 at 28.4s. This gap is acceptable for background processing.

3. **Output quality difference is minimal**: Minor variations in JSON formatting and Markdown decoration, but content accuracy is identical. Sonnet produced slightly more thorough test cases (18 vs 15).

### 9.2 Recommended Configuration

```
┌──────────────────────────────────────────────────────┐
│  AnimaWorks Recommended Model Configuration           │
│                                                       │
│  foreground (Chat):     Claude Sonnet 4.6             │
│    → Latency advantage, natural conversation quality  │
│                                                       │
│  background_model:      Qwen3.5-35B (vLLM)            │
│    → Heartbeat, Inbox, Cron, TaskExec                 │
│    → Sonnet-equivalent quality at $0 cost             │
│                                                       │
│  Configuration:                                       │
│  $ animaworks anima set-model X claude-sonnet-4-6     │
│  $ animaworks anima set-background-model X \          │
│      openai/qwen3.5-35b-a3b                           │
└──────────────────────────────────────────────────────┘
```

### 9.3 Future Work

- Long-context performance comparison (>64K tokens)
- Subjective Japanese language generation quality evaluation (human raters)
- Long-term stability testing at 1,000-task scale
- Qwen3.5-35B vLLM concurrent request throughput measurement

---

## Appendix A: Experimental Infrastructure

### Benchmark Scripts

```
scripts/benchmark/
├── benchmark.py           # Main script (setup/run/report/clean)
├── tasks.json             # Basic task definitions (15 tasks, Tier 1–3)
└── tasks_advanced.json    # Advanced task definitions (10 tasks, Tier 4)
```

### Execution Commands

```bash
# Deploy test data
python3 scripts/benchmark/benchmark.py setup --advanced

# Qwen3.5-35B (2 runs)
python3 scripts/benchmark/benchmark.py run \
  --model "openai/qwen3.5-35b-a3b" \
  --credential vllm-local --runs 2 \
  --tasks scripts/benchmark/tasks_advanced.json

# Claude Sonnet 4.6 (2 runs)
python3 scripts/benchmark/benchmark.py run \
  --model "anthropic/claude-sonnet-4-6" \
  --credential anthropic --runs 2 \
  --tasks scripts/benchmark/tasks_advanced.json
```

## Appendix B: Test Data Files

| Path | Size | Purpose |
|------|------|---------|
| `/tmp/benchmark/adv/sales.csv` | 179B | A1: 8-row sales data |
| `/tmp/benchmark/adv/targets.csv` | 48B | A1: 3-region targets |
| `/tmp/benchmark/adv/buggy.py` | 718B | A2: Python code with 3 bugs |
| `/tmp/benchmark/adv/projects/{frontend,backend,shared}/package.json` | ~110B each | A3: 3-project dependency definitions |
| `/tmp/benchmark/adv/meetings/2026-03-{01,05,08}.md` | ~270B each | A4: 3 meeting minutes |
| `/tmp/benchmark/adv/pipeline.json` | 333B | A5: Pipeline configuration |
| `/tmp/benchmark/adv/source.txt` | 30B | A5: Transformation source text |
| `/tmp/benchmark/adv/secondary.json` | 115B | A6: Data with nulls |
| `/tmp/benchmark/adv/defaults.json` | 117B | A6: Default values |
| `/tmp/benchmark/adv/employees.csv` | 220B | A7: 8-employee dataset |
| `/tmp/benchmark/adv/puzzle.txt` | 590B | A8: 4-constraint seating puzzle |
| `/tmp/benchmark/adv/template.md` | 476B | A9: Jinja-style template |
| `/tmp/benchmark/adv/variables.json` | 271B | A9: Template variables |
| `/tmp/benchmark/adv/report_data/{financial,team,milestones}.json` | ~100–500B | A10: 3-source report data |
