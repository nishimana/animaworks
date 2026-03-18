# 태스크 보드 (사람용 대시보드)

조직의 오너 (사람)가 전체 태스크를 한눈에 파악하기 위한 공유 파일입니다.

## 목적

AnimaWorks의 태스크 관리는 `task_queue.jsonl` + `current_state.md` + `delegate_task`로
에이전트 간에는 완결되지만, **사람이 한눈에 전체를 파악할 수단이 없습니다**.
`shared/task-board.md`는 이 문제를 해결하는 사람용 대시보드입니다.

## 위치 구분

| 리소스 | 용도 | 대상 |
|--------|------|------|
| `state/task_queue.jsonl` | 태스크 추적 (append-only) | 에이전트 |
| `state/current_state.md` | 현재 작업 메모 | 에이전트 개인 |
| `state/task_results/` | 태스크 실행 결과 | 시스템 자동 |
| **`shared/task-board.md`** | **전체 태스크 조감** | **사람 (오너)** |

## 형식

```markdown
# 태스크 보드

최종 업데이트: YYYY-MM-DD HH:MM by {업데이트 담당자}

## 🔴 블록 중 (사람 대응 대기)
| # | 태스크 | 담당 | 블로커 | 기한 |
|---|--------|------|--------|------|

## 🟡 진행 중
| # | 태스크 | 담당 | 상태 | 기한 |
|---|--------|------|------|------|

## 📋 미착수 (예정)
| # | 태스크 | 담당 | 비고 | 기한 |
|---|--------|------|------|------|

## ✅ 이번 주 완료
| 태스크 | 담당 | 완료일 |
|--------|------|--------|
```

## 운영 규칙

1. **supervisor (CEO에 해당하는 Anima)가 관리합니다**
   - 태스크 위임 시: task-board.md에 추가한 후 send_message
   - 완료 보고를 받으면: 진행 중 → 완료로 이동
   - heartbeat 시: 기한 초과 확인, 블로커 상태 업데이트

2. **각 에이전트는 자신의 태스크 완료 시 업데이트합니다**
   - 진행 중 → ✅ 이번 주 완료로 이동

3. **주간 리셋**
   - "✅ 이번 주 완료" 섹션의 전주 분을 클리어
   - 미착수 태스크의 기한과 우선순위를 재검토

## Slack 동기화 (옵션)

`slack_channel_post`와 `slack_channel_update` 도구를 사용하여
Slack 채널의 고정 메시지로 동기화할 수 있습니다.
`slack_channel_update` (chat.update API)는 알림 없이 메시지를 덮어쓰므로
라이브 대시보드로 기능합니다.

> 이들은 gated 액션입니다. 사용하려면 permissions.json에
> `slack_channel_post: yes` / `slack_channel_update: yes`가 필요합니다.

### 설정 절차

1. `slack_channel_post`로 초기 게시 → 반환된 `ts`를 저장
2. Slack에서 해당 메시지를 고정
3. 이후 `slack_channel_update`로 덮어쓰기 업데이트

### ts 저장 위치

`shared/task-board-slack.json`에 저장합니다:
```json
{"channel_id": "C0XXXXXXXX", "ts": "1741XXXXXXX.XXXXXX"}
```
