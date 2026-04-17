#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="${HOME}"
BIN_DIR="${INSTALL_ROOT}/.local/bin"
CODEX_DIR="${INSTALL_ROOT}/.codex"
CONFIG_FILE="${CODEX_DIR}/config.toml"
ZSHRC_FILE="${INSTALL_ROOT}/.zshrc"

remove_binaries() {
  rm -f "${BIN_DIR}/codex-sidebar-launcher" "${BIN_DIR}/codex-skill-sidebar.py"
}

remove_zsh_hook() {
  [[ -f "${ZSHRC_FILE}" ]] || return
  python3 - "${ZSHRC_FILE}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
begin = "# >>> codex-skill-sidebar >>>"
end = "# <<< codex-skill-sidebar <<<"
if begin in text and end in text:
    start = text.index(begin)
    finish = text.index(end, start) + len(end)
    text = text[:start] + text[finish:]
    text = text.replace("\n\n\n", "\n\n")
    path.write_text(text.lstrip("\n"), encoding="utf-8")
PY
}

remove_codex_config() {
  [[ -f "${CONFIG_FILE}" ]] || return
  python3 - "${CONFIG_FILE}" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
section_pattern = re.compile(r"(?ms)^\[features\]\n(?P<body>.*?)(?=^\[|\Z)")
match = section_pattern.search(text)
if not match:
    raise SystemExit(0)
body = match.group("body")
new_body = re.sub(r"(?m)^apps\s*=\s*false\s*\n?", "", body)
if new_body == body:
    raise SystemExit(0)
if new_body.strip():
    text = text[:match.start("body")] + new_body + text[match.end("body"):]
else:
    text = text[:match.start()] + text[match.end():]
text = re.sub(r"\n{3,}", "\n\n", text).lstrip("\n")
path.write_text(text, encoding="utf-8")
PY
}

main() {
  remove_binaries
  remove_zsh_hook
  remove_codex_config
  printf '%s\n' 'Removed codex-skill-sidebar.'
  printf '%s\n' '已移除 codex-skill-sidebar。'
  printf '%s\n' 'Run: source ~/.zshrc'
  printf '%s\n' '运行：source ~/.zshrc'
}

main "$@"
