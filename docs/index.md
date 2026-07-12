---
slug: /
sidebar_label: Introduction
sidebar_position: 1
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# arc

Stacked PRs without the manual overhead.

arc keeps a branch stack current, opens the PRs for each layer, and restacks everything above when one merges, so you can ship small, reviewable diffs instead of one giant PR.

**[Quickstart →](start/quickstart)** · **[Command reference →](reference/commands)**

---

## How it works

Organize changes into a chain of branches, each building on the one below. arc manages the chain:

- **`arc sync`**: fetch from `main` and cascade a rebase bottom-up through the whole stack
- **`arc push`**: force-push all branches atomically
- **`arc submit`**: open or update a PR for each branch, each targeting the one below it
- **`arc land`**: merge a PR and restack everything above it

See [Concepts](guide/concepts) for the full vocabulary.

---

## Install

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

**Requires:** Python 3.11+, git, and [GitHub CLI](https://cli.github.com) (`gh auth login`).

See [Install](start/install) for upgrade instructions and shell completions.
