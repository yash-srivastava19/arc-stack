# arc

Stacked PRs without the manual overhead.

`arc` keeps a branch stack current, opens the PRs for each layer, and restacks everything above when one merges — so you can ship small, reviewable diffs instead of one giant PR.

<div class="grid cards" markdown>

-   :material-clock-fast: **[Quickstart](start/quickstart.md)**

    Build your first stacked PR in five minutes.

-   :material-sync: **[Syncing](guide/syncing.md)**

    Keep the stack current after `main` moves.

-   :material-source-pull: **[Submitting](guide/submitting.md)**

    Push branches and open PRs.

-   :material-merge: **[Landing](guide/landing.md)**

    Merge a PR and clean up the stack.

-   :material-hook: **[Hooks](guide/hooks.md)**

    Gate or notify on any arc event.

-   :material-book-open-page-variant: **[Command reference](reference/commands.md)**

    Every command and every flag.

</div>

---

## How arc works

You organize your changes into a chain of branches, each building on the one below. `arc` manages the chain:

- **`arc sync`** — fetch from `main` and cascade a rebase bottom-up through the whole stack
- **`arc push`** — force-push all branches atomically
- **`arc submit`** — open or update a PR for each branch, each targeting the one below it
- **`arc land`** — merge a PR and restack everything above it

See [Concepts](guide/concepts.md) for the full vocabulary.

---

## Install

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

**Requires:** Python 3.11+, git, and [GitHub CLI](https://cli.github.com) (`gh auth login`).

See [Install](start/install.md) for upgrade instructions and shell completions.
