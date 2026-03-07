---
auto_consolidated: false
confidence: 0.7
created_at: '2026-03-02T12:00:00+09:00'
version: 1
---

# Competitor Analysis Methodology

> Created: 2026-03-02
> Author: Nova (Customer Success / Assistant)
> Purpose: Standard competitor analysis procedure established during the v0.4 five-company comparison

## 5-Stage Analysis Process

### Stage 1: Web Research (30 min per company)

```
Search query patterns:
- "{company} vs AI design tool 2026 comparison"
- "{company} AI features {year}"
- "{company} pricing plans"
- "{company} user reviews"
```

Information to collect:
- Key feature list
- AI-related capabilities and characteristics
- Pricing plans (Free/Pro/Enterprise)
- User count and market share
- Latest updates and announcements

### Stage 2: Feature Comparison Table

| Feature Category | Comparison Items |
|-----------------|-----------------|
| Core Design | Template count, custom elements, layer management |
| AI Features | Text-to-image, style transfer, auto layout |
| Collaboration | Real-time co-editing, comments, version history |
| Export | Supported formats, resolution options, batch export |
| API | REST API, webhooks, plugins |
| Pricing | Free tier, Pro pricing, Enterprise pricing |

### Stage 3: Pricing Comparison

Organize each company's plans by monthly/annual pricing:

```
| Plan   | PixelForge | Figma | Canva | Adobe Express |
|--------|-----------|-------|-------|--------------|
| Free   | $0        | $0    | $0    | $0           |
| Pro    | $15/mo    | $15   | $13   | $10          |
| Team   | $25/mo    | $45   | $30   | $22          |
| Ent.   | Custom    | Custom| Custom| Custom       |
```

### Stage 4: UI/UX Evaluation

5-point qualitative scoring:
- Intuitiveness (can a new user operate it immediately?)
- Response speed (does it feel snappy?)
- AI experience (how easy are AI features to use?)
- Customizability (can fine-grained adjustments be made?)
- Mobile support

### Stage 5: Executive Summary

A one-page summary the CEO can read in 3 minutes:

```
## Executive Summary

### PixelForge Market Position
{one sentence}

### Key Differentiators (Top 3)
1. {differentiator 1}
2. {differentiator 2}
3. {differentiator 3}

### Threats
{competitor strengths — areas requiring attention}

### Recommended Actions
{what to tackle in the next version}
```

## HTML Report Template

Comparison reports are converted to HTML for easy printing and sharing:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Competitor Comparison Report — PixelForge</title>
  <style>
    body { font-family: 'Inter', sans-serif; max-width: 800px; margin: auto; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background: #f5f5f5; }
    @media print {
      .page-break { page-break-before: always; }
    }
  </style>
</head>
```

## v0.4 Five-Company Comparison Results

- Research time: approximately 3 hours (5 companies × 30 min + 1 hour HTML formatting)
- Deliverable: 650-line HTML report (A4 print-ready)
- 3 differentiators: AI custom generation, API-first design, low pricing

## Areas for Improvement

- Include each company's official documentation and blog in research
- Add review site scores (G2, Capterra)
- Establish a quarterly update cadence
