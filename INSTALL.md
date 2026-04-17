# Install Guide

## One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/yupeng316888-create/codex-skill-sidebar/main/install.sh | bash
```

Then run:

```bash
source ~/.zshrc
codex
```

## What the installer does

- installs `codex-sidebar-launcher` and `codex-skill-sidebar.py` into `~/.local/bin`
- adds `codex` and `CodeX` wrappers into `~/.zshrc`
- ensures `apps = false` exists in `~/.codex/config.toml`

## Requirements

- macOS
- `zsh`
- `python3` with `tkinter`
- Codex CLI already installed

## Common install errors

`curl` missing

- Run `xcode-select --install`
- Rerun the installer

`python3` or `tkinter` missing

- Install a Python 3 build with `tkinter`
- Rerun the installer

`codex` missing

- Install the Codex CLI first
- Rerun the installer

Not using `zsh`

- Switch your shell to `zsh`
- Or use the manual install steps from `README.md`

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/yupeng316888-create/codex-skill-sidebar/main/uninstall.sh | bash
```
