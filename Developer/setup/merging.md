# Merging a worktree back to the origins and tearing it down

A task worktree is a branch plus a folder. Merging is ordinary git; the folder is removed
afterwards with the script so the block links come off cleanly.

## 1. Bring the task branch up to date

In the task worktree:

```
git fetch origin
git rebase origin/main          # or merge, per team preference; rebase keeps history linear
```

Resolve conflicts, run Blender: Start, exercise what you changed. If the task also touched
a block, `git status` in `<dev>/block_<name>` shows that work too; it is a separate repo and
a separate commit.

## 2. Push and open the PR

```
git push -u origin task/<name>
```

Open the PR against `main`. If a block change accompanies it, commit and push that in the
block repo and cross-link the two PRs. Merge order follows the contract in
[teamwork.md](teamwork.md): block-side compatibility first when possible.

## 3. After merge: update main, remove the worktree

```
git -C <dev>/dgblocks pull                                            # main catches up
python dgblocks/Developer/setup/new_worktree.py remove <name> --delete-branch
```

`remove` unlinks every `external_blocks/` entry (the link only; the block repo is untouched),
runs `git worktree remove`, and deletes the local branch with `-d`, which refuses if the
branch still has unmerged commits. Use `--force` only for a task you are abandoning with
uncommitted changes.

Housekeeping every so often: `git -C <dev>/dgblocks worktree prune` (drops registrations
whose folders are gone) and `git fetch --prune`.

## Block repos: no worktrees needed

Block work commits directly in `<dev>/block_<name>` on whatever branch you use there, then
pushes to the block's origin. Since every DGBlocks checkout sees that one copy, there is
nothing to merge across worktrees; the only thing to merge is your branch into the block's
`main`, as in any project.

## Squash or not

Squash-merge task branches whose commits are checkpoints. Keep the commits when they tell a
story a future reader needs (a data-model change followed by its migration, for instance).
Either way, the DGBlocks commit message names any block that had to change with it.

## Moving to a fresh history

When a repo is rebased or re-rooted (new `main`, squashed past), every worktree pointing at
the old commits must be removed first (`remove` each task), then recreated from the new
`main`. Worktrees are cheap; don't try to carry them across a history rewrite.
