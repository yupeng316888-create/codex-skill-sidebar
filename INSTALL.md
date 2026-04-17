# Install Guide

## Recommended install

With Homebrew:

```bash
brew install --formula https://raw.githubusercontent.com/yupeng316888-create/codex-skill-sidebar/main/Formula/codex-skill-sidebar.rb
codex-skill-sidebar install
```

Without Homebrew:

```bash
curl -fsSL https://raw.githubusercontent.com/yupeng316888-create/codex-skill-sidebar/main/install.sh | bash
```

Then run:

```bash
source ~/.zshrc
codex
```

If you use Homebrew, you also get:

- `codex-skill-sidebar doctor`
- `brew upgrade` for future updates
- `brew uninstall codex-skill-sidebar` for removing the helper command later

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

Homebrew install:

```bash
codex-skill-sidebar uninstall
brew uninstall codex-skill-sidebar
```

Direct install:

```bash
curl -fsSL https://raw.githubusercontent.com/yupeng316888-create/codex-skill-sidebar/main/uninstall.sh | bash
```
