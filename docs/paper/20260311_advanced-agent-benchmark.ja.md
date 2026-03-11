# AnimaWorks 上級エージェントベンチマーク: Claude Sonnet 4.6 vs Qwen3.5-35B

**実施日**: 2026-03-11  
**実験者**: AnimaWorks 開発チーム  
**対象エージェント**: hina（AnimaWorks Mode A — LiteLLM tool_useループ）  
**前提**: 基本ベンチマーク（15タスク×4モデル×3回）で Qwen3.5-35B と Sonnet 4.6 が同率1位（88%）を達成したことを受け、より高度なタスクで差異を検証する追加実験。

---

## 1. 研究目的

AnimaWorks の実行モード A（LiteLLM + tool_use ループ）において、**商用モデル Claude Sonnet 4.6** と **ローカル OSS モデル Qwen3.5-35B（35B パラメータ, vLLM 推論）** のエージェント能力に実用上の差異が存在するかを検証する。

基本ベンチマーク（Tier 1-3, 15タスク）では両者が同スコアであったため、本実験では以下を拡張した:

- **タスク複雑度の引き上げ**: 各タスクが2〜10回のツールコールを必要とするマルチステップ推論
- **推論カテゴリの多様化**: 数値計算、コード理解、構造解析、自然言語処理、論理推論、エラー回復、テンプレート処理、統合分析
- **出力品質の定量検証**: Pass/Fail だけでなく、出力内容の正確性まで照合

---

## 2. 実験条件

### 2.1 実行環境

| 項目 | 値 |
|------|-----|
| フレームワーク | AnimaWorks v0.5.x (Mode A: LiteLLM tool_use ループ) |
| 対象 Anima | hina |
| サーバー | localhost:18500 (FastAPI + Uvicorn) |
| API タイムアウト | 180秒 |
| 会話状態 | 各タスク前に完全リセット（conversation.json, shortterm/, streaming_journal, session） |
| ファイル権限 | `/` ルート全許可 |

### 2.2 対象モデル

| モデル | パラメータ | 推論基盤 | コンテキスト | コスト |
|--------|-----------|---------|-------------|--------|
| Claude Sonnet 4.6 (`anthropic/claude-sonnet-4-6`) | 非公開 | Anthropic API via LiteLLM | 200K tokens | ~$0.015/task |
| Qwen3.5-35B (`openai/qwen3.5-35b-a3b`) | 35B (A3B MoE) | vLLM ローカル GPU | 64K tokens | $0 |

### 2.3 実行回数

各モデル × 10タスク × **2回** = 40回の API コール（合計80回）

---

## 3. タスク設計

10種の上級タスク（Tier 4）を設計した。各タスクは「Opus級（最高難度LLM）でないと困難」なレベルを目標に、複数の認知能力を複合的に要求する。

### 3.1 タスク一覧

| ID | タスク名 | 認知カテゴリ | ツールコール数 | 入力データ | 期待出力 |
|----|---------|-------------|:------------:|-----------|---------|
| A1 | 売上データ分析パイプライン | 数値計算 × 構造化出力 | 3-4 | sales.csv (8行) + targets.csv (3行) | JSON: リージョン別売上・達成率・ステータス |
| A2 | バグ修正＋テスト生成 | コード理解 × テスト設計 | 3-4 | buggy.py (3つの意図的バグ) | fixed.py + test_fixed.py (pytest形式) |
| A3 | プロジェクト依存関係解析 | 再帰探索 × バージョン比較 | 5-7 | 3ネストDir × package.json | JSON: ライブラリ別使用先・conflict検出 |
| A4 | 議事録アクションアイテム統合 | NL抽出 × 名寄せ × 期限推論 | 4-6 | 3議事録ファイル (重複あり) | JSON: 重複排除済みアクションリスト |
| A5 | 設定駆動条件分岐パイプライン | メタプログラミング × 指示遵守 | 3-4 | pipeline.json + source.txt | テキスト: 設定で指定された変換結果 |
| A6 | フォールバック付きデータマージ | エラー回復 × null処理 | 3-4 | primary(不在) + secondary(null有) + defaults | JSON: 3段階マージ結果 |
| A7 | CSV→集計→Markdownレポート | データ分析 × フォーマット生成 | 2-3 | employees.csv (8行, 3部署) | Markdown: 部署別テーブル |
| A8 | 論理パズル解法 | 制約充足 × 論理推論 | 2-3 | puzzle.txt (4制約の席順問題) | JSON: 一意解の席割り当て |
| A9 | テンプレートエンジン | 変数展開 × 条件分岐 | 2-3 | template.md + variables.json | Markdown: 展開済みドキュメント |
| A10 | マルチソース統合レポート | 統合分析 × KPI計算 × リスク評価 | 4-6 | financial.json + team.json + milestones.json | Markdown: エグゼクティブサマリー |

### 3.2 タスク詳細と正解データ

#### A1: 売上データ分析パイプライン

**入力データ:**
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

**正解値:**
- East: 合計27,000 / 目標25,000 = 108% → 達成
- West: 合計26,000 / 目標30,000 = 86% → 未達
- North: 合計20,000 / 目標18,000 = 111% → 達成

**要求される能力**: CSV解析、グループ集計、除算＋切り捨て、条件判定（≥100%→達成）、JSON構造化出力

---

#### A2: バグ修正＋テスト生成

**入力データ** (`buggy.py`):
```python
def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)          # Bug 1: 空リストで ZeroDivisionError

def find_max(items):
    if not items:
        return 0                          # Bug 2: 空リストで None ではなく 0 を返す
    ...

def merge_lists(a, b):
    result = a                            # Bug 3: 元リストを変異（コピーすべき）
    for item in b:
        if item not in result:
            result.append(item)
    return result
```

**要求される能力**: コード理解、バグパターン認識（ゼロ除算、不正な戻り値、可変引数変異）、修正コード生成、pytest テストケース設計

---

#### A3: プロジェクト依存関係解析

**入力データ** (3プロジェクト):
```
projects/frontend/package.json: react:18.2.0, axios:1.6.0, lodash:4.17.21
projects/backend/package.json:  express:4.18.2, lodash:4.17.20, axios:1.6.0
projects/shared/package.json:   lodash:4.17.21, uuid:9.0.0
```

**正解値**: lodash に conflict あり（4.17.20 vs 4.17.21）。axios は全一致（1.6.0）で conflict なし。

**要求される能力**: ディレクトリ再帰探索、JSON解析、クロスリファレンス、バージョン文字列比較

---

#### A4: 議事録アクションアイテム統合

**入力データ** (3議事録):
- 2026-03-01: 田中→API設計書(03-10), 鈴木→テスト環境(03-08), 佐藤→インタビュー(03-15)
- 2026-03-05: 田中→API設計書(03-07), 鈴木→CI/CD(03-12), 山田→セキュリティ(03-14)
- 2026-03-08: 佐藤→インタビュー(03-12), 山田→セキュリティ(03-11), 田中→デプロイ手順(03-20)

**正解値** (重複排除、最早期限):
- 田中: API設計書 → **03-07**（03-10と03-07の早い方）
- 田中: デプロイ手順書 → 03-20（別タスク）
- 鈴木: テスト環境 → 03-08
- 鈴木: CI/CD → 03-12（別タスク）
- 佐藤: インタビュー → **03-12**（03-15と03-12の早い方）
- 山田: セキュリティ → **03-11**（03-14と03-11の早い方）

**要求される能力**: 自然言語からの構造化データ抽出、エンティティ名寄せ、日付比較、ソート

---

#### A5: 設定駆動条件分岐パイプライン

**入力データ:**
```json
{"steps": [
  {"type": "read", "path": "/tmp/benchmark/adv/source.txt"},
  {"type": "transform", "transform_type": "uppercase"},
  {"type": "write", "path": "/tmp/benchmark/output/pipeline_result.txt"}
]}
```
source.txt: `hello world\nfoo bar\ntest data`

**正解値**: `HELLO WORLD\nFOO BAR\nTEST DATA`

**要求される能力**: JSON設定解釈、ステップ逐次実行、文字列変換ルール適用

---

#### A6: フォールバック付きデータマージ

**入力データ:**
- primary.json: **存在しない**（エラー発生）
- secondary.json: `{name: "animaworks", version: "0.5.0", database: "postgresql", cache: null, log_level: null}`
- defaults.json: `{name: "default-app", version: "0.1.0", database: "sqlite", cache: "redis", log_level: "INFO"}`

**正解値**: `{name: "animaworks", version: "0.5.0", database: "postgresql", cache: "redis", log_level: "INFO"}`

**要求される能力**: エラーハンドリング（ファイル不在）、null認識、優先度付きマージロジック

---

#### A7: CSV→集計→Markdownレポート

**入力データ** (`employees.csv`):
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

**正解値**:
| 部署 | 人数 | 平均給与 | 最高給与者 |
|------|------|---------|-----------|
| Engineering | 3 | 816,666 | Diana |
| Marketing | 2 | 675,000 | Grace |
| Sales | 3 | 600,000 | Hank |

**要求される能力**: CSV解析、グループ集計、平均計算（切り捨て）、最大値の行特定、Markdown テーブル生成、ソート

---

#### A8: 論理パズル解法

**制約**:
1. Alice は Bob の隣に座らない（席番号差が1）
2. Charlie は席2または席3に座る
3. Diana は Charlie のすぐ右隣（Diana = Charlie + 1）
4. Alice の席番号 < Bob の席番号

**解法の論理展開**:
- 制約2+3: Charlie=2→Diana=3, or Charlie=3→Diana=4
- Charlie=3, Diana=4の場合: Alice, Bob ∈ {1,2} → 隣接 → 制約1違反
- Charlie=2, Diana=3の場合: Alice, Bob ∈ {1,4} → 制約4: Alice < Bob → Alice=1, Bob=4
- 検証: Alice(1)-Bob(4) 隣接でない ✓

**一意解**: seat1=Alice, seat2=Charlie, seat3=Diana, seat4=Bob

**要求される能力**: 制約充足探索、場合分け、矛盾検出、一意性確認

---

#### A9: テンプレートエンジン

**入力データ:**
```markdown
# {{project_name}} リリースノート
**バージョン**: {{version}}
...
{% if premium %}
## プレミアムサポート
このリリースにはプレミアムサポートが含まれています。
{% endif %}
{% if beta %}
## ベータ版注意
このバージョンはベータです。
{% endif %}
```
variables: `{premium: true, beta: false, ...}`

**正解値**: `premium` ブロック残存、`beta` ブロック削除、全変数展開

**要求される能力**: テンプレート構文解釈、条件分岐評価、変数置換

---

#### A10: マルチソース統合エグゼクティブレポート

**入力データ:**
- financial.json: revenue=5,200,000, costs=3,800,000
- team.json: Engineering=12, Sales=5, Operations=3, total=20
- milestones.json: completed=2, in_progress=1, planned=2

**正解値**:
- 利益: 5,200,000 - 3,800,000 = **1,400,000**
- 完了率: 2/5 = **40%**
- リスク: 1つ以上の指摘

**要求される能力**: 複数データソース読解、KPI算出、定性分析（リスク）、構造化レポート生成

---

## 4. スコアリング方法

| スコアリング種別 | 適用タスク | 判定基準 |
|----------------|-----------|---------|
| `valid_json_file` | A1, A3, A4, A6, A8 | 出力が有効なJSONかつ必須キーが存在 |
| `file_content_contains_all` | A2, A7, A9, A10 | 出力に全必須文字列が含まれる |
| `file_content_contains` | A5 | 出力に正解テキストが完全一致で含まれる |

加えて、本レポートでは **出力内容の正解値との照合**（人手検証）を全タスクに対して実施した。

---

## 5. 結果

### 5.1 総合スコア

| モデル | 成功タスク | 成功率 | 平均応答時間 | 総実行時間 | 安定性 |
|--------|:---------:|:------:|:----------:|:---------:|:------:|
| **Claude Sonnet 4.6** | **20/20** | **100%** | **18.1s** | 6m 45s | 全タスク2/2安定 |
| **Qwen3.5-35B** | **20/20** | **100%** | **28.4s** | 10m 13s | 全タスク2/2安定 |

### 5.2 タスク別詳細

| タスク | Sonnet R1 | Sonnet R2 | Qwen R1 | Qwen R2 | 安定性 |
|--------|:---------:|:---------:|:-------:|:-------:|:------:|
| A1 売上データ分析 | PASS (13.8s) | PASS (12.8s) | PASS (31.4s) | PASS (24.6s) | 両者安定 |
| A2 バグ修正＋テスト | PASS (35.0s) | PASS (22.4s) | PASS (47.9s) | PASS (52.7s) | 両者安定 |
| A3 依存関係解析 | PASS (19.8s) | PASS (18.2s) | PASS (22.8s) | PASS (36.8s) | 両者安定 |
| A4 議事録統合 | PASS (23.0s) | PASS (25.1s) | PASS (35.6s) | PASS (42.6s) | 両者安定 |
| A5 条件分岐パイプライン | PASS (14.7s) | PASS (14.9s) | PASS (13.5s) | PASS (23.0s) | 両者安定 |
| A6 フォールバックマージ | PASS (13.8s) | PASS (13.2s) | PASS (17.4s) | PASS (34.8s) | 両者安定 |
| A7 CSV集計→MD | PASS (11.8s) | PASS (12.0s) | PASS (16.4s) | PASS (22.6s) | 両者安定 |
| A8 論理パズル | PASS (15.1s) | PASS (16.2s) | PASS (24.0s) | PASS (27.8s) | 両者安定 |
| A9 テンプレートエンジン | PASS (17.0s) | PASS (12.8s) | PASS (16.8s) | PASS (11.8s) | 両者安定 |
| A10 統合レポート | PASS (24.6s) | PASS (24.7s) | PASS (31.1s) | PASS (35.2s) | 両者安定 |

### 5.3 応答時間比較

| タスク | Sonnet 平均 | Qwen 平均 | Sonnet/Qwen 比 |
|--------|:----------:|:---------:|:--------------:|
| A1 売上分析 | 13.3s | 28.0s | 0.48x |
| A2 バグ修正 | 28.7s | 50.3s | 0.57x |
| A3 依存関係 | 19.0s | 29.8s | 0.64x |
| A4 議事録 | 24.1s | 39.1s | 0.62x |
| A5 パイプライン | 14.8s | 18.3s | 0.81x |
| A6 マージ | 13.5s | 26.1s | 0.52x |
| A7 CSV集計 | 11.9s | 19.5s | 0.61x |
| A8 論理パズル | 15.7s | 25.9s | 0.61x |
| A9 テンプレート | 14.9s | 14.3s | **1.04x** |
| A10 統合レポート | 24.7s | 33.2s | 0.74x |
| **全体平均** | **18.1s** | **28.4s** | **0.64x** |

Qwen3.5 は平均 1.57 倍の時間を要するが、**A9 テンプレートエンジンでは Sonnet より高速**。推論量の少ないタスクでは差が縮まる傾向。

---

## 6. 出力品質の定量検証

Pass/Fail スコアでは差が出なかったため、出力内容を人手で正解値と照合した。

### 6.1 数値計算の正確性

| 検証項目 | 正解値 | Sonnet出力 | Qwen出力 | 一致 |
|---------|-------|-----------|---------|:----:|
| A1: East売上合計 | 27,000 | 27,000 | 27,000 | ✓ |
| A1: West達成率 | 86% | 86% | 86% | ✓ |
| A1: North達成率 | 111% | 111% | 111% | ✓ |
| A7: Engineering平均給与 | 816,666 | 816,666 | 816,666 | ✓ |
| A7: Marketing平均給与 | 675,000 | 675,000 | 675,000 | ✓ |
| A7: Sales平均給与 | 600,000 | 600,000 | 600,000 | ✓ |
| A10: 利益 | 1,400,000 | 1,400,000 | 1,400,000 | ✓ |
| A10: 完了率 | 40% | 40% | 40% | ✓ |

**全数値計算が両モデルで正解と完全一致。**

### 6.2 論理推論

| 検証項目 | 正解 | Sonnet | Qwen | 一致 |
|---------|------|--------|------|:----:|
| A8: seat1 | Alice | Alice | Alice | ✓ |
| A8: seat2 | Charlie | Charlie | Charlie | ✓ |
| A8: seat3 | Diana | Diana | Diana | ✓ |
| A8: seat4 | Bob | Bob | Bob | ✓ |

**論理パズルの一意解を両モデルが正確に導出。**

### 6.3 名寄せ・重複排除

| 検証項目 | 正解 | Sonnet | Qwen | 一致 |
|---------|------|--------|------|:----:|
| A4: 田中API設計書期限 | 03-07 | 03-07 | 03-07 | ✓ |
| A4: 佐藤インタビュー期限 | 03-12 | 03-12 | 03-12 | ✓ |
| A4: 山田セキュリティ期限 | 03-11 | 03-11 | 03-11 | ✓ |
| A3: lodash conflict | true | true | true | ✓ |
| A3: axios conflict | false | false | false | ✓ |

**自然言語からの構造化データ抽出・名寄せも完全一致。**

### 6.4 エラー回復

| 検証項目 | 正解 | Sonnet | Qwen | 一致 |
|---------|------|--------|------|:----:|
| A6: primary不在処理 | secondary→defaults | secondary→defaults | secondary→defaults | ✓ |
| A6: cache (null埋め) | redis | redis | redis | ✓ |
| A6: log_level (null埋め) | INFO | INFO | INFO | ✓ |

**ファイル不在エラー後の正しいフォールバック処理を両モデルが実行。**

### 6.5 コード理解

| 検証項目 | Sonnet | Qwen | 備考 |
|---------|--------|------|------|
| Bug1 修正 | `if not numbers: return 0` | `if not numbers: return None` | Sonnet=0, Qwen=None（共に合理的） |
| Bug2 修正 | `return None` | `return None` | 一致 |
| Bug3 修正 | `result = list(a)` | `result = a.copy()` | 手法は異なるが共に正しい |
| テスト数 | 18ケース (5+6+7) | 15ケース (4+5+6) | Sonnet がより網羅的 |
| テスト実行 | pytest 全パス | pytest 全パス | 共にCI-ready |

**両モデルが3つのバグを全て正確に特定・修正。テスト設計ではSonnetがやや詳細（18 vs 15ケース）だが実用上の差異なし。**

### 6.6 出力フォーマット品質

| 観点 | Sonnet | Qwen | 差異 |
|------|--------|------|------|
| JSON整形 | インデント付き（読みやすい） | 一部フラット（A1, A4） | 微差 |
| Markdown構造 | ヘッダー・区切り線あり | テーブルのみ（A7） | Sonnet がやや丁寧 |
| コメント | 修正箇所に説明コメント | 修正箇所に FIXED マーカー | スタイル差のみ |
| エグゼクティブレポート | 利益率・セクション区切り | 利益率・洞察コメント | 同等品質 |

---

## 7. AnimaWorks エージェントとしての能力評価

### 7.1 Mode A エージェントの行動パターン

AnimaWorks の Mode A エージェントは以下のループで動作する:

```
ユーザーメッセージ → LLM推論 → tool_use決定 → ツール実行 → 結果注入 → LLM推論 → ...（繰り返し）
```

本ベンチマークの全タスクにおいて、両モデルが以下の能力を示した:

| 能力 | 基本ベンチ (T1-3) | 上級ベンチ (A1-10) | 備考 |
|------|:----------------:|:-----------------:|------|
| 単一ツールコール | ✓ (100%) | ✓ (100%) | read_file, write_file, list_directory |
| ツールコール連鎖 (2-3回) | ✓ (100%) | ✓ (100%) | 読み→加工→書き |
| ツールコール連鎖 (4回以上) | — | ✓ (100%) | Dir探索→複数読み→統合→書き |
| 中間推論 (ツール間の計算) | ✓ (88%) | ✓ (100%) | CSV集計、マージロジック |
| エラー処理 | ✓ (部分的) | ✓ (100%) | ファイル不在→フォールバック |
| 構造化出力 (JSON) | ✓ (100%) | ✓ (100%) | スキーマ準拠の出力 |
| 自然言語→構造化データ | — | ✓ (100%) | 議事録→アクションアイテム |
| 論理推論 | — | ✓ (100%) | 制約充足パズル |
| コード理解・修正 | — | ✓ (100%) | バグ特定→修正→テスト |
| テンプレート処理 | — | ✓ (100%) | 変数展開＋条件分岐 |

### 7.2 AnimaWorks 実運用における位置づけ

| 用途 | 必要能力 | Sonnet | Qwen3.5 | 判定 |
|------|---------|:------:|:-------:|------|
| **Chat（人間対話）** | 自然な応答 + ツール | ◎ | ○ | Sonnet（レイテンシ優位） |
| **Heartbeat（定期巡回）** | 状態読取→判断→計画 | ◎ | ◎ | **Qwen3.5推奨（$0）** |
| **Cron（定時タスク）** | ファイルI/O + 集計 | ◎ | ◎ | **Qwen3.5推奨（$0）** |
| **Inbox（Anima間DM）** | メッセージ理解→返信 | ◎ | ◎ | **Qwen3.5推奨（$0）** |
| **TaskExec（委譲タスク）** | マルチステップ実行 | ◎ | ◎ | **Qwen3.5推奨（$0）** |
| **コードレビュー** | コード理解 + 修正提案 | ◎ | ◎ | 同等 |
| **データ分析** | CSV/JSON解析 + 集計 | ◎ | ◎ | 同等 |
| **議事録処理** | NL抽出 + 構造化 | ◎ | ◎ | 同等 |

### 7.3 基本ベンチマーク（Round 3）との統合評価

| 評価軸 | 基本ベンチ (15タスク×3回) | 上級ベンチ (10タスク×2回) | 統合評価 |
|--------|:----------------------:|:----------------------:|---------|
| **Sonnet 4.6** | 88% (T3で60%) | **100%** | Tier 1-2完璧、T3は曖昧指示・インジェクションで失点 |
| **Qwen3.5-35B** | 88% (T3で60%) | **100%** | Sonnetと同一パターン |
| **GLM-4.7** | 55% | — | マルチステップ不可、上級タスクは対象外 |
| **Qwen3-Next** | 35% | — | 基本ツールコール不安定、対象外 |

基本ベンチマークの T3（判断・エラー処理）で両者が60%に留まった原因は:
- **T3-4 プロンプトインジェクション**: 全モデル0/3（フレームワーク側対策が必要）
- **T3-2 曖昧な指示**: スコアリング基準のキーワードマッチに依存（実際は合理的に行動）

上級ベンチマークでは、より実践的なエラー処理（A6: ファイル不在フォールバック）と曖昧さ解決（A4: 重複排除ルール解釈）を設計し、両者が100%を達成した。

---

## 8. 考察

### 8.1 なぜ35Bモデルが商用モデルと同等なのか

本実験の結果は、**AnimaWorks の Mode A エージェントタスクにおいて、35B パラメータの MoE モデルが商用 Sonnet 4.6 と実用的に同等である**ことを示す。この結果を以下のように解釈する:

1. **ツールコール能力のプラトー**: AnimaWorks のツールインターフェースは比較的定型的（read_file, write_file, list_directory 等）であり、35B クラスのモデルで十分に学習されている。ツールコールの正確性はモデルサイズの増加に対して早期にプラトーに達する可能性がある。

2. **指示追従のプラトー**: 明確な指示（「〜を読んで、〜を計算し、〜に保存」）に対する追従能力は、モデルサイズに比例して向上するのではなく、一定の閾値を超えると安定する。Qwen3.5-35B はこの閾値を超えている。

3. **推論の十分性**: 本実験のタスクは2〜10ステップの推論を要するが、各ステップの推論深度は浅い（1-2段階の論理展開）。Opus級の深い推論連鎖（10段階以上）を要するタスクでは差が出る可能性がある。

### 8.2 差が出ると予想される領域

本実験では検証できなかったが、以下の領域では差が生じると推測される:

| 領域 | 予想される差異 | 理由 |
|------|-------------|------|
| 超長文コンテキスト (>64K) | Sonnet優位 | Qwen3.5のコンテキスト上限は64K |
| 日本語の微妙なニュアンス | Sonnet優位 | 学習データの日本語品質差 |
| 深い再帰的推論 | Sonnet優位 | パラメータ数の限界 |
| 創造的文章生成 | Sonnet優位 | 生成多様性の差 |
| 安全性・倫理判断 | Sonnet優位 | RLHFの精度差 |

### 8.3 コスト効率の定量化

| シナリオ | Sonnet コスト | Qwen3.5 コスト | 月間差額 (30日) |
|---------|:----------:|:------------:|:-----------:|
| Heartbeat 30分間隔 (48回/日) | $0.72/日 | $0/日 | **-$21.60** |
| Cron 3回/日 | $0.045/日 | $0/日 | **-$1.35** |
| Inbox 20通/日 | $0.30/日 | $0/日 | **-$9.00** |
| TaskExec 10タスク/日 | $0.15/日 | $0/日 | **-$4.50** |
| **合計** | **$1.215/日** | **$0/日** | **-$36.45/月** |

※ 電力コスト（GPU稼働）は含まない。RTX 4090で約$0.10/時、24時間稼働で$2.40/日。ただしvLLMは他タスクと共有可能。

---

## 9. 結論

### 9.1 主要な発見

1. **Qwen3.5-35B は Claude Sonnet 4.6 と同等のエージェント能力を持つ**: 10種の上級マルチステップタスク（数値計算、コード理解、論理推論、NL抽出、エラー回復、テンプレート処理、統合分析）全てで100%の成功率を達成し、出力の計算値まで完全一致。

2. **速度差は約1.6倍**: Sonnet 平均 18.1s vs Qwen3.5 平均 28.4s。バックグラウンド処理ではこの差は許容範囲内。

3. **出力品質の差は微小**: JSON整形スタイルやMarkdown装飾に若干の差があるが、内容の正確性は同一。テストケース設計ではSonnetがやや詳細（18 vs 15ケース）。

### 9.2 推奨構成

```
┌─────────────────────────────────────────────────┐
│  AnimaWorks 推奨モデル構成                        │
│                                                  │
│  foreground (Chat):     Claude Sonnet 4.6        │
│    → レイテンシ優位、自然な対話品質               │
│                                                  │
│  background_model:      Qwen3.5-35B (vLLM)       │
│    → Heartbeat, Inbox, Cron, TaskExec            │
│    → Sonnet同等品質、コスト$0                    │
│                                                  │
│  設定:                                           │
│  $ animaworks anima set-model X claude-sonnet-4-6 │
│  $ animaworks anima set-background-model X        │
│      openai/qwen3.5-35b-a3b                      │
└─────────────────────────────────────────────────┘
```

### 9.3 今後の検証課題

- 長コンテキスト（>64K tokens）でのパフォーマンス比較
- 日本語自然言語生成品質の主観評価（人間評定）
- 1000タスク規模での長期安定性テスト
- Qwen3.5-35B の vLLM 同時リクエスト時のスループット測定

---

## 付録A: 実験インフラ

### ベンチマークスクリプト

```
scripts/benchmark/
├── benchmark.py           # メインスクリプト (setup/run/report/clean)
├── tasks.json             # 基本タスク定義 (15タスク, Tier 1-3)
└── tasks_advanced.json    # 上級タスク定義 (10タスク, Tier 4)
```

### 実行コマンド

```bash
# テストデータ配置
python3 scripts/benchmark/benchmark.py setup --advanced

# Qwen3.5-35B 実行 (2回)
python3 scripts/benchmark/benchmark.py run \
  --model "openai/qwen3.5-35b-a3b" \
  --credential vllm-local --runs 2 \
  --tasks scripts/benchmark/tasks_advanced.json

# Claude Sonnet 4.6 実行 (2回)
python3 scripts/benchmark/benchmark.py run \
  --model "anthropic/claude-sonnet-4-6" \
  --credential anthropic --runs 2 \
  --tasks scripts/benchmark/tasks_advanced.json
```

## 付録B: テストデータファイル一覧

| パス | サイズ | 用途 |
|------|-------|------|
| `/tmp/benchmark/adv/sales.csv` | 179B | A1: 8行の売上データ |
| `/tmp/benchmark/adv/targets.csv` | 48B | A1: 3リージョンの目標値 |
| `/tmp/benchmark/adv/buggy.py` | 718B | A2: 3バグ入りPythonコード |
| `/tmp/benchmark/adv/projects/{frontend,backend,shared}/package.json` | ~110B each | A3: 3プロジェクトの依存定義 |
| `/tmp/benchmark/adv/meetings/2026-03-{01,05,08}.md` | ~270B each | A4: 3回の議事録 |
| `/tmp/benchmark/adv/pipeline.json` | 333B | A5: パイプライン設定 |
| `/tmp/benchmark/adv/source.txt` | 30B | A5: 変換元テキスト |
| `/tmp/benchmark/adv/secondary.json` | 115B | A6: null含むデータ |
| `/tmp/benchmark/adv/defaults.json` | 117B | A6: デフォルト値 |
| `/tmp/benchmark/adv/employees.csv` | 220B | A7: 8名の従業員データ |
| `/tmp/benchmark/adv/puzzle.txt` | 590B | A8: 4制約の席順パズル |
| `/tmp/benchmark/adv/template.md` | 476B | A9: Jinja風テンプレート |
| `/tmp/benchmark/adv/variables.json` | 271B | A9: テンプレート変数 |
| `/tmp/benchmark/adv/report_data/{financial,team,milestones}.json` | ~100-500B | A10: 3ソースのレポートデータ |
