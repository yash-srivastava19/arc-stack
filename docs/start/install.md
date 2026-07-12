---
sidebar_position: 2
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Install

## Requirements

- Python 3.11 or later
- [git](https://git-scm.com)
- [GitHub CLI](https://cli.github.com) — authenticated via `gh auth login`

---

## Install arc

<Tabs>
  <TabItem value="brew" label="macOS (Homebrew)" default>

  ```bash
  brew install yash-srivastava19/arc/arc-prs
  ```

  </TabItem>
  <TabItem value="pipx" label="pipx">

  ```bash
  pipx install arc-prs
  ```

  </TabItem>
  <TabItem value="uv" label="uv">

  ```bash
  uv tool install arc-prs
  ```

  </TabItem>
</Tabs>

Verify your environment after installing:

```bash
arc setup
```

`arc setup` checks that `git` and `gh` are on `PATH`, that `gh` is authenticated, and that `git rerere` is enabled. It writes no configuration files — it only reads your environment.

---

## Upgrade

```bash
arc upgrade
```

Upgrades arc using whichever package manager installed it. Pass `--help` to see the detected installer.

---

## Shell completions

<Tabs>
  <TabItem value="bash" label="bash" default>

  Add to `~/.bashrc` or `~/.bash_profile`:

  ```bash
  eval "$(arc completions bash)"
  ```

  </TabItem>
  <TabItem value="zsh" label="zsh">

  Add to `~/.zshrc`:

  ```bash
  eval "$(arc completions zsh)"
  ```

  </TabItem>
  <TabItem value="fish" label="fish">

  Run once, or add to `~/.config/fish/config.fish`:

  ```fish
  arc completions fish | source
  ```

  </TabItem>
</Tabs>

---

## Uninstall

```bash
# Homebrew
brew uninstall arc-prs

# pipx
pipx uninstall arc-prs

# uv
uv tool uninstall arc-prs
```

arc does not write anything outside your project. The only per-repo artifact is `.arc/state.json`, which is git-ignored and safe to delete.
