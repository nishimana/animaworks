---
name: transcribe-tool
description: >-
  음성 문자 변환 도구. Whisper 모델로 오디오 파일을 텍스트로 변환합니다. LLM 후처리 옵션 지원.
  "문자 변환" "transcribe" "음성 인식" "Whisper" "STT"
tags: [audio, transcription, whisper, external]
---

# Transcribe 도구

Whisper (faster-whisper)를 사용한 음성 문자 변환 도구입니다.

## 호출 방법

**Bash**: `animaworks-tool transcribe transcribe <오디오 파일> [옵션]`으로 실행합니다.

### audio — 음성 문자 변환
```bash
animaworks-tool transcribe transcribe audio_file.wav [-l ja] [-m large-v3-turbo]
```

## 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| audio_path | string | (필수) | 오디오 파일 경로 |
| language | string | null | 언어 코드 (ja, en 등). null이면 자동 감지 |
| model | string | "large-v3-turbo" | Whisper 모델명 |
| raw | boolean | false | true인 경우 LLM 후처리를 건너뜀 |

## CLI 사용법

```bash
animaworks-tool transcribe transcribe audio_file.wav [-l ja] [-m large-v3-turbo]
```

## 주의사항

- faster-whisper가 설치되어 있어야 합니다
- GPU 사용 시 CUDA 호환 ctranslate2가 필요합니다
- 최초 실행 시 모델이 자동 다운로드됩니다
