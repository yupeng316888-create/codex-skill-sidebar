#!/usr/bin/env bash
set -euo pipefail

REPO_RAW_BASE="${CODEX_SIDEBAR_RAW_BASE:-https://raw.githubusercontent.com/yupeng316888-create/codex-skill-sidebar/main}"
INSTALL_ROOT="${HOME}"
BIN_DIR="${INSTALL_ROOT}/.local/bin"
CODEX_DIR="${INSTALL_ROOT}/.codex"
CONFIG_FILE="${CODEX_DIR}/config.toml"
ZSHRC_FILE="${INSTALL_ROOT}/.zshrc"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

fetch_file() {
  local remote_path="$1"
  local output_path="$2"
  curl -fsSL "${REPO_RAW_BASE}/${remote_path}" -o "${output_path}"
}

install_binaries() {
  mkdir -p "${BIN_DIR}"
  fetch_file "bin/codex-sidebar-launcher" "${BIN_DIR}/codex-sidebar-launcher"
  fetch_file "bin/codex-skill-sidebar.py" "${BIN_DIR}/codex-skill-sidebar.py"
  chmod +x "${BIN_DIR}/codex-sidebar-launcher" "${BIN_DIR}/codex-skill-sidebar.py"
}

install_zsh_hook() {
  local begin_marker="# >>> codex-skill-sidebar >>>"
  local end_marker="# <<< codex-skill-sidebar <<<"
  local block

  block="$(cat <<'EOF'
# >>> codex-skill-sidebar >>>
codex() {
  "$HOME/.local/bin/codex-sidebar-launcher" "$@"
}

CodeX() {
  "$HOME/.local/bin/codex-sidebar-launcher" "$@"
}
# <<< codex-skill-sidebar <<<
EOF
)"

  touch "${ZSHRC_FILE}"

  if grep -Fq "${begin_marker}" "${ZSHRC_FILE}"; then
    python3 - "${ZSHRC_FILE}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
begin = "# >>> codex-skill-sidebar >>>"
end = "# <<< codex-skill-sidebar <<<"
block = """# >>> codex-skill-sidebar >>>
codex() {
  "$HOME/.local/bin/codex-sidebar-launcher" "$@"
}

CodeX() {
  "$HOME/.local/bin/codex-sidebar-launcher" "$@"
}
# <<< codex-skill-sidebar <<<"""
start = text.index(begin)
finish = text.index(end, start) + len(end)
updated = text[:start] + block + text[finish:]
if not updated.endswith("\n"):
    updated += "\n"
path.write_text(updated, encoding="utf-8")
PY
  else
    if [[ -s "${ZSHRC_FILE}" ]] && [[ "$(tail -c 1 "${ZSHRC_FILE}" 2>/dev/null || true)" != "" ]]; then
      printf '\n' >> "${ZSHRC_FILE}"
    fi
    printf '%s\n' "${block}" >> "${ZSHRC_FILE}"
  fi
}

install_codex_config() {
  mkdir -p "${CODEX_DIR}"

  python3 - "${CONFIG_FILE}" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8") if path.exists() else ""

if "[features]" not in text:
    if text and not text.endswith("\n"):
        text += "\n"
    text += "[features]\napps = false\n"
else:
    section_pattern = re.compile(r"(?ms)^\[features\]\n(?P<body>.*?)(?=^\[|\Z)")
    match = section_pattern.search(text)
    if match:
        body = match.group("body")
        if re.search(r"(?m)^apps\s*=", body):
            body = re.sub(r"(?m)^apps\s*=.*$", "apps = false", body)
        else:
            if body and not body.endswith("\n"):
                body += "\n"
            body += "apps = false\n"
        text = text[:match.start("body")] + body + text[match.end("body"):]

path.write_text(text, encoding="utf-8")
PY
}

print_next_steps() {
  cat <<'EOF'
Installed codex-skill-sidebar.

Next:
  1. Run: source ~/.zshrc
  2. Start Codex with: codex
EOF
}

main() {
  need_cmd curl
  need_cmd python3

  install_binaries
  install_zsh_hook
  install_codex_config
  print_next_steps
}

main "$@"
