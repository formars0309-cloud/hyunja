#!/bin/sh
# 현자 설치 (macOS · Linux)
#   ~/.local/bin/현자 · askall  → 이 폴더의 ask_all.py 를 python3 로 실행
#   ~/.claude/skills/현자, ~/.codex/skills/현자 → 이 폴더로 심볼릭 링크 (해당 에이전트가 설치돼 있을 때만)
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
BIN="${HOME}/.local/bin"
mkdir -p "$BIN"
for name in 현자 askall; do
  printf '#!/bin/sh\nexec python3 "%s/ask_all.py" "$@"\n' "$REPO" > "$BIN/$name"
  chmod +x "$BIN/$name"
done
echo "명령 설치: $BIN/현자, $BIN/askall"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "PATH에 $BIN 이 없습니다. 셸 설정에 추가하세요: export PATH=\"\$HOME/.local/bin:\$PATH\"";; esac
for agent in .claude .codex; do
  if [ -d "$HOME/$agent" ]; then
    mkdir -p "$HOME/$agent/skills"
    ln -sfn "$REPO" "$HOME/$agent/skills/현자"
    echo "스킬 등록: ~/$agent/skills/현자"
  fi
done
for cli in claude codex grok agy; do
  if command -v "$cli" >/dev/null 2>&1; then echo "확인: $cli"; else echo "없음: $cli (해당 열은 '(CLI 없음)'으로 표시됩니다)"; fi
done
echo "완료. 사용: 현자 \"질문\""
