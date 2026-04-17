# v0.1.0

Initial public release of `codex-skill-sidebar`.

## Highlights

- Floating skill sidebar for the Codex terminal workflow on macOS
- Searchable and grouped skill browser
- Immediate `Recent` skill history updates
- Socket-based trigger injection into the active Codex PTY
- Shell and Codex config snippets for quick local installation

## Included

- `codex-sidebar-launcher` PTY wrapper for the real Codex CLI
- `codex-skill-sidebar.py` floating sidebar UI
- `zshrc` integration snippets for `codex` and `CodeX`
- Optional Codex config snippet to disable the built-in `apps` feature if needed

## Notes

- Built for macOS Terminal
- The sidebar is a floating utility window, not a true split pane
- Skills are loaded dynamically from `~/.codex/skills`
