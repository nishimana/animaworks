---
auto_consolidated: false
confidence: 0.7
created_at: '2026-03-02T12:00:00+09:00'
version: 1
---

# 競合調査手法

> 作成日: 2026-03-02
> 作成者: Hina（カスタマーサクセス / アシスタント）
> 目的: v0.4の5社比較で確立した競合調査の標準手順

## 5段階調査手順

### Stage 1: Web検索（各社30分）

```
検索クエリパターン:
- "{会社名} vs AI design tool 2026 comparison"
- "{会社名} AI features {年}"
- "{会社名} pricing plans"
- "{会社名} user reviews"
```

収集する情報:
- 主要機能一覧
- AI関連機能の有無と特徴
- 料金プラン（Free/Pro/Enterprise）
- ユーザー数・市場シェア
- 最新のアップデート情報

### Stage 2: 機能比較表作成

| 機能カテゴリ | 比較項目 |
|------------|---------|
| デザイン基本 | テンプレート数、カスタム要素、レイヤー管理 |
| AI機能 | テキスト→画像、スタイル変換、自動レイアウト |
| コラボレーション | リアルタイム共同編集、コメント、バージョン管理 |
| エクスポート | 対応形式、解像度、一括エクスポート |
| API | REST API、Webhook、プラグイン |
| 価格 | 無料枠、Pro価格、Enterprise価格 |

### Stage 3: 価格比較

各社の料金プランを月額/年額で整理:

```
| プラン | PixelForge | Figma | Canva | Adobe Express |
|--------|-----------|-------|-------|--------------|
| Free   | $0        | $0    | $0    | $0           |
| Pro    | $15/mo    | $15   | $13   | $10          |
| Team   | $25/mo    | $45   | $30   | $22          |
| Ent.   | Custom    | Custom| Custom| Custom       |
```

### Stage 4: UI/UX評価

定性評価の5段階スコア:
- 直感性（初見で操作できるか）
- レスポンス速度（操作のサクサク感）
- AI体験（AI機能の使いやすさ）
- カスタマイズ性（細かい調整ができるか）
- モバイル対応

### Stage 5: エグゼクティブサマリー作成

CEOが3分で読める1ページの要約:

```
## エグゼクティブサマリー

### PixelForge の市場ポジション
{一言で}

### 主要差別化ポイント（Top 3）
1. {差別化1}
2. {差別化2}
3. {差別化3}

### 脅威
{競合の強み — 対策が必要な点}

### 推奨アクション
{次のバージョンで取り組むべきこと}
```

## HTML化テンプレート

比較レポートはHTML化して印刷・共有しやすくする:

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>競合比較レポート — PixelForge</title>
  <style>
    body { font-family: 'Noto Serif JP', serif; max-width: 800px; margin: auto; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background: #f5f5f5; }
    @media print {
      .page-break { page-break-before: always; }
    }
  </style>
</head>
```

## v0.4 の5社比較実績

- 調査時間: 約3時間（5社 × 30分 + HTML化1時間）
- 成果物: 650行のHTML（A4印刷対応）
- 差別化ポイント3つ: AIカスタム生成、APIファースト、低価格

## 改善点

- 各社の公式ドキュメント・ブログも調査に含める
- ユーザーレビューサイト（G2, Capterra）のスコアを追加
- 四半期ごとに定期更新する仕組みを作る
