# Multiple worktrees, windows and Blender sessions

One git worktree per task, one VS Code window per worktree, one Blender process per window,
each with its own preferences. Blocks are shared across all of them through links.

## Create, use, remove

```
python dgblocks/Developer/setup/new_worktree.py new my-task            # <dev>/dgblocks-my-task on branch task/my-task
code <dev>/dgblocks-my-task                                            # or File > Open Folder
                                                                       # Blender: Start in that window
python dgblocks/Developer/setup/new_worktree.py remove my-task --delete-branch   # when merged (see merging.md)
```

`new` does three things: `git worktree add`, links every `<dev>/block_*` repo into
`external_blocks/`, and creates the empty `.blender-profile/` tree. Everything else happens
on the first Blender: Start.

## Why sessions don't collide

Blender keeps the enabled-addon list in `userpref.blend` inside its config directory. Two
Blenders sharing one config directory would each try to load both checkouts' copies of the
addon, and the class-registration prefix would be registered twice. The committed
`.vscode/settings.json` gives every checkout its own config and scripts directory, so:

- each Blender has its own prefs, its own enabled-addon list, its own recent-files;
- the extension's addon link (in `.blender-profile/scripts/addons/`) points at exactly that
  checkout;
- the debugger port is allocated per window by the extension.

Extensions, datafiles, and the bundled scripts stay shared at Blender's default location.

## What every window sees of a block

All checkouts link to the same block working copy. An uncommitted edit in Flatypus shows up
in every session after a script reload (`bpy.ops.script.reload()`, or the extension's reload
on save). That is the intended loop for "a DGBlocks tweak forces a small block change": fix
the block once, every session picks it up.

Set breakpoints in block files by opening them **through the worktree path**
(`<dev>/dgblocks-my-task/external_blocks/block_.../file.py`). Blender imports the block through
the link, so that is the path the debugger matches. A file opened from `<dev>/block_.../`
directly is the same bytes at a different path and its breakpoints won't bind.

To see the block's git status inside the same VS Code window, add `../block_<name>` as a
second workspace folder (File > Add Folder to Workspace). The relative path holds on every
machine, so a saved `.code-workspace` can be shared.

## When a task needs its own block branch

Sharing one block working copy assumes block `main` stays compatible with DGBlocks `main`
(the contract in [teamwork.md](teamwork.md)). For a long-lived divergence, give that one
worktree a real block worktree instead of a link:

```
rmdir <dev>/dgblocks-my-task/external_blocks/block_<name>        # removes only the link (Windows: rmdir; Unix: rm)
git -C <dev>/block_<name> worktree add ../dgblocks-my-task/external_blocks/block_<name> -b task/my-task
```

`list` still reports it as `ok` because it resolves into the same repo. When the task is
done, `git -C <dev>/block_<name> worktree remove ...` before `remove my-task`, or `remove`
will refuse because the entry is a directory rather than a link.

## Blender profiles, briefly

Blender has no named-profile feature. It has one user-resource tree per version
(`config/`, `scripts/`, `extensions/`, `datafiles/`) at an OS-specific location, and four
environment variables that redirect the subtrees individually (`BLENDER_USER_CONFIG`,
`BLENDER_USER_SCRIPTS`, `BLENDER_USER_EXTENSIONS`, `BLENDER_USER_DATAFILES`), plus
`BLENDER_USER_RESOURCES` for the whole tree. Redirection is per process, paths are used
verbatim (no version suffix is appended), and there is no in-app switch. Relative paths work
and resolve against the process working directory; that is what makes the committed settings
machine-independent.
