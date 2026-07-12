# Install

## Requirements

- Python 3.11 or later
- [git](https://git-scm.com)
- [GitHub CLI](https://cli.github.com) — authenticated via `gh auth login`

---

## Install arc

=== "macOS (Homebrew)"

    ```bash
    brew install yash-srivastava19/arc/arc-prs
    ```

=== "pipx"

    ```bash
    pipx install arc-prs
    ```

=== "uv"

    ```bash
    uv tool install arc-prs
    ```

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

=== "bash"

    Add to `~/.bashrc` or `~/.bash_profile`:

    ```bash
    eval "$(arc completions bash)"
    ```

=== "zsh"

    Add to `~/.zshrc`:

    ```bash
    eval "$(arc completions zsh)"
    ```

=== "fish"

    Run once, or add to `~/.config/fish/config.fish`:

    ```fish
    arc completions fish | source
    ```

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
