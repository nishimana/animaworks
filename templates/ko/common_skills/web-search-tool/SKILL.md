---
name: web-search-tool
description: >-
  웹 검색 도구. Brave Search API를 사용하여 인터넷을 검색합니다.
  "검색" "웹 검색" "찾아보기" "Brave"
tags: [search, web, external]
---

# Web Search 도구

Brave Search API를 사용한 웹 검색 외부 도구입니다.

## 호출 방법

**Bash**: `animaworks-tool web_search "검색 쿼리" [옵션]`으로 실행합니다.

## 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| query | string | (필수) | 검색 쿼리 |
| count | integer | 10 | 조회 건수 |
| lang | string | "ja" | 검색 언어 |
| freshness | string | null | 최신도 필터 (pd=24시간, pw=1주일, pm=1개월, py=1년) |

## CLI 사용법

```bash
animaworks-tool web_search "검색 쿼리" [-n 10] [-l ja] [-f pd]
```

## 주의사항

- BRAVE_API_KEY가 설정되어 있어야 합니다
- 검색 결과는 외부 소스(untrusted)로 취급됩니다
