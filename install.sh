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

info() {
  printf '%s\n' "$1"
}

die() {
  printf 'Install failed: %s\n' "$1" >&2
  printf '安装失败：%s\n' "$1" >&2
  exit 1
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    case "$1" in
      curl)
        die "'curl' is required. Install Xcode Command Line Tools with: xcode-select --install"
        ;;
      python3)
        die "'python3' is required. Install a Python 3 build that includes tkinter, then run this installer again."
        ;;
      *)
        die "missing required command: $1"
        ;;
    esac
  fi
}

has_local_source() {
  [[ -n "${CODEX_SIDEBAR_SOURCE_DIR:-}" ]] && [[ -d "${CODEX_SIDEBAR_SOURCE_DIR}" ]]
}

fetch_file() {
  local remote_path="$1"
  local output_path="$2"
  if [[ -n "${CODEX_SIDEBAR_SOURCE_DIR:-}" ]] && [[ -f "${CODEX_SIDEBAR_SOURCE_DIR}/${remote_path}" ]]; then
    cp "${CODEX_SIDEBAR_SOURCE_DIR}/${remote_path}" "${output_path}"
    return
  fi
  if ! curl -fsSL "${REPO_RAW_BASE}/${remote_path}" -o "${output_path}"; then
    die "could not download ${remote_path}. Check your network connection and try again."
  fi
}

check_platform() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    die "this installer currently supports macOS only."
  fi
}

check_shell() {
  local shell_name
  shell_name="$(basename "${SHELL:-}")"
  if [[ "${shell_name}" != "zsh" ]]; then
    die "this installer currently supports zsh only. Switch your shell to zsh or use the manual install steps."
  fi
}

check_python_tk() {
  if ! python3 - <<'PY' >/dev/null 2>&1
import tkinter
PY
  then
    die "your python3 does not include tkinter. Install a Python build with tkinter support, then run this installer again."
  fi
}

check_codex() {
  if command -v codex >/dev/null 2>&1; then
    return
  fi
  if [[ -x "/usr/local/bin/codex" || -x "/opt/homebrew/bin/codex" ]]; then
    return
  fi
  die "Codex CLI was not found. Install Codex first, then run this installer again."
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
已安装 codex-skill-sidebar。

Next:
  1. Run: source ~/.zshrc
  2. Start Codex with: codex

下一步：
  1. 运行：source ~/.zshrc
  2. 启动 Codex：codex
EOF
}

main() {
  check_platform
  need_cmd python3
  if ! has_local_source; then
    need_cmd curl
  fi
  check_shell
  check_python_tk
  check_codex

  info "Installing codex-skill-sidebar..."
  info "正在安装 codex-skill-sidebar..."
  install_binaries
  install_zsh_hook
  install_codex_config
  print_next_steps
}

main "$@"
