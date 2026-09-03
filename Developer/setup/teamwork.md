# Working on a team

## Who owns what

| Repo | Owner | Others do |
|---|---|---|
| DGBlocks | framework maintainers | clone, pull, open issues/PRs; never fork-and-edit for project needs |
| each `block_<name>` | that block's team | clone if they collaborate on it, otherwise ignore it |

DGBlocks history never references a block; block history never contains DGBlocks. The only
coupling is the import surface: `native_blocks/` and `addon_helpers/` are the framework API.

## Branches

- DGBlocks: `main` is always runnable. Work happens on `task/<name>` branches in worktrees
  created by `new_worktree.py`. Short-lived: days, not weeks.
- Blocks: `main` is always compatible with DGBlocks `main`. Feature work on the block uses
  the block's own branches inside its own checkout, as in any repo.

## The compatibility contract

Every DGBlocks checkout on a machine shares one working copy of each block. That only holds
together if block `main` runs against DGBlocks `main`. So:

1. A framework change that breaks a block is not finished until the block's fix exists.
2. Land them so that at no point does `main` + `main` fail:
   - fix the block in a **backward-compatible** way first when possible (works with old and
     new framework), push it, then merge the framework change; or
   - merge the framework change and push the block fix within the same sitting, and tell the
     team.
3. Framework changes that alter a public surface (a hook name, an RTC key, a data-structure
   field, a Feature Wrapper signature) say so in the commit message and in
   `Developer/AI_Assist/Memory_Bank/activeContext.md`, so block authors can grep for it.

Two DGBlocks worktrees far apart in history sharing one block copy is the failure mode.
Merge the older one before starting block-sensitive work in the newer one, or give the
newer one its own block worktree ([worktrees.md](worktrees.md), last section).

## Reviewing a change that spans both repos

Two PRs, cross-linked in their descriptions. Review the framework PR first; the block PR
shows that the framework change is actually consumable. Merge in the order the contract
above requires.

## What is and isn't shared

Shared through git: everything in the repos, including `.vscode/settings.json` and
`.vscode/extensions.json`.
Per machine, never committed: the Blender executable path (VS Code user settings), the
`<dev>` location, `.blender-profile/`, the links in `external_blocks/`, any locally installed
Python libraries.

## Onboarding someone

Send them [README.md](README.md). The whole setup is: clone DGBlocks, clone the blocks they
work on, run `link`, set the Blender path once, Blender: Start. If they hit anything not
covered in [os_notes.md](os_notes.md), that's a doc bug; fix it there.
