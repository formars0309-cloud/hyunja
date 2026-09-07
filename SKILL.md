---
name: 현자
description: 현자(賢者) — 같은 질문을 claude·codex·grok·Antigravity CLI에 동시에 던지고 네 답을 한 HTML 화면(가로 4단)과 마크다운으로 모아 보여준다. 코딩이 아니라 "여러 AI 의견을 나란히 보고 싶을 때" 쓴다. 트리거 — "현자", "현자에게 물어봐", "현자 소집", "다 같이 물어봐", "여러 AI에게 동시에", "클로드 코덱스 그록 비교", "askall", "동시 답변", "AI 여러 개 의견", "ask all".
---

# 현자

`ask_all.py` 하나가 전부다. 표준 라이브러리만 쓰고, 각 CLI의 비대화형 모드를 병렬로 실행한다.

| 이름 | 실행 방식 |
|---|---|
| claude | `claude -p "질문"` |
| codex | `codex exec --skip-git-repo-check -s read-only -o <파일> "질문"` (최종 답만 파일로) |
| grok | `grok -p "질문"` |
| antigravity | `agy -p "질문"` (`-a gemini`도 같은 명령을 부르는 옛 이름) |

## 사용

```
현자 "질문"                      # 터미널 어디서나. askall "질문" 도 같은 명령
askall -a claude,grok "질문"     # 일부만
askall -t 600 "질문"             # 타임아웃 초 (기본 300)
askall --no-open "질문"          # 브라우저 안 열기
askall --commit "질문"           # 작업 폴더가 git 저장소면 답을 곧바로 커밋
python3 ask_all.py "질문"        # 직접 실행
```

결과: `$HYUNJA_HOME/answers/<시각>.md`·`.html` (기본 브라우저로 자동 열림). 터미널에도 마크다운을 그대로 찍는다.

## 에이전트가 쓸 때

사용자가 "여러 AI에게 같이 물어봐"라고 하면 위 명령을 실행하고, 네 답의 **차이점**을 짧게 요약해 준다. 답 전체를 다시 옮겨 적지 않는다(HTML이 이미 열려 있다).

## 작업 폴더

환경변수 `HYUNJA_HOME`(기본 `~/.hyunja`). 네 CLI가 거기서 실행되고, 처음 실행할 때 `templates/`의 `AGENTS.md`(공통 지침: 한국어, 결론 먼저, 파일 안 읽기, 300자 안팎)와 `CLAUDE.md`·`GEMINI.md`(`@AGENTS.md` 한 줄)를 복사해 넣는다. grok·codex는 AGENTS.md를 직접 읽는다. 답변 방식을 바꾸려면 작업 폴더의 `AGENTS.md`만 고친다. `HYUNJA_COMMIT=1`은 `--commit`과 같다.

## 설치 구조

- macOS·Linux: `install.sh`가 `~/.local/bin/현자`·`askall`(셸 스크립트 → `python3 ask_all.py`)과 `~/.claude/skills/현자`·`~/.codex/skills/현자` 심볼릭 링크를 만든다.
- 윈도우: `install.cmd` → `windows/install.py`. 배치 파일은 ASCII만 담고 한글 경로는 파이썬 실행기(`askall.py`)가 다룬다. 콘솔 코드페이지 65001에서 cmd.exe가 한글 경로가 든 줄을 어긋나게 읽기 때문이다. 스킬 등록은 정션.

## 한계

- 네 CLI는 현재 프로젝트가 아니라 작업 폴더에서 돈다. 프로젝트 문맥이 필요한 질문엔 맞지 않는다.
- 로그인·API 키는 각 CLI가 이미 갖고 있어야 한다. 없는 CLI는 "(CLI 없음)"으로 표시된다. agy는 터미널에서 `agy`를 한 번 실행해 브라우저 구글 로그인을 마쳐야 한다(브라우저가 코드를 보여주면 터미널에 붙여넣는다).
- 응답 시간은 가장 느린 CLI에 맞춰진다.
