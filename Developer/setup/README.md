# Developer/setup — dev environment, worktrees, blocks, team workflow

Everything needed to go from a fresh clone to a running, debuggable Blender session, on any
OS, with one procedure for framework developers and block developers alike. The only tool is
[new_worktree.py](new_worktree.py) (stdlib Python; runs on Blender's bundled interpreter too).

| Read | When |
|---|---|
| this file | first-time setup, the layout, daily commands |
| [custom_blocks.md](custom_blocks.md) | creating your own block, or cloning an existing block repo (Flatypus etc.) |
| [worktrees.md](worktrees.md) | several tasks at once: multiple worktrees, VS Code windows, Blender sessions |
| [teamwork.md](teamwork.md) | branches, ownership, the DGBlocks-vs-block compatibility contract |
| [merging.md](merging.md) | getting a finished worktree back into the origins and tearing it down |
| [os_notes.md](os_notes.md) | Windows / macOS / Linux specifics (links, path limits, sync folders, Blender paths) |

## Layout

```
<dev>/                                one plain folder. NOT a git repo, NOT cloud-synced.
  dgblocks/                           main DGBlocks checkout      (branch: main)
  dgblocks-<task>/                    one git worktree per task   (made by the script)
  block_flatypus_modes_manager/       a block repo, one checkout  (its own git history)
  block_<yours>/                      another block repo
```

Rules that keep the layout unambiguous:

- A block repo's folder name **is** its Python package name and starts with `block_`.
- A block is **never** checked out inside a DGBlocks checkout. Inside each checkout,
  `external_blocks/block_<name>` is only a link (junction/symlink) back to `<dev>/block_<name>`.
  The link is the only thing that ever appears in `external_blocks/`.
- Task worktrees are named `<main-folder>-<task>` so they never collide with block names.
- Nothing tracked in any repo contains a machine-specific path.

## One-time machine setup

1. Pick `<dev>`. It must not be inside OneDrive, iCloud Drive, Dropbox or similar (see
   [os_notes.md](os_notes.md) for the Windows "Documents is really OneDrive" trap). Keep the
   path short.
2. Clone into it:
   ```
   git clone <dgblocks-url> dgblocks
   git clone <block-url> block_<name>        # each block repo you work on, e.g. Flatypus
   ```
3. VS Code: open `dgblocks/`, accept the recommended extension (`jacqueslucke.blender-development`),
   and set the Blender executable path in your **user** settings. That path is the only
   machine-specific setting and it lives outside every repo.
4. Link the blocks into the main checkout:
   ```
   python dgblocks/Developer/setup/new_worktree.py link
   ```
   No Python on PATH? Blender's works: `blender -b --python dgblocks/Developer/setup/new_worktree.py -- link`
5. **Blender: Start** from the VS Code command palette. Done.

## Daily commands

Run from `<dev>` (or anywhere; the script finds its own checkout and the main via git).

| You want | Command |
|---|---|
| Link blocks into a checkout (after cloning a new block repo) | `python dgblocks/Developer/setup/new_worktree.py link [CHECKOUT]` |
| A new task worktree, linked and profile-ready | `python dgblocks/Developer/setup/new_worktree.py new my-task` |
| ... branched from a given ref | `... new my-task --from origin/main` |
| See every checkout, branch, profile and link health | `python dgblocks/Developer/setup/new_worktree.py list` |
| Tear a task down (links unlinked first; block repos untouched) | `python dgblocks/Developer/setup/new_worktree.py remove my-task [--delete-branch]` |

Then open the checkout folder in its own VS Code window and run **Blender: Start**.

## What Blender: Start does here

The checkout's committed `.vscode/settings.json` carries

```json
"BLENDER_USER_CONFIG":  ".blender-profile/config",
"BLENDER_USER_SCRIPTS": ".blender-profile/scripts"
```

Blender uses those paths verbatim, relative to the process working directory, which is the
workspace folder for the extension's task. Result: every checkout has its own `userpref.blend`
(enabled-addon list, theme, keymap) and its own `scripts/addons/` where the extension places
the addon link. Extensions and datafiles stay at Blender's default location and are shared.
First start of a checkout is factory prefs; drop a `userpref.blend` into
`.blender-profile/config/` beforehand if you want your usual theme and keymap.

**Confirm once on a new machine:** after the first Blender: Start, `.blender-profile/` inside
the checkout must contain files. If they landed elsewhere the task cwd wasn't the workspace
folder; fallback is absolute paths in that checkout's `.vscode/settings.json` followed by
`git update-index --skip-worktree .vscode/settings.json`.

## Troubleshooting

- **"is a real directory, not a link"** — a block was checked out inside a DGBlocks checkout.
  Move it to `<dev>/block_<name>` and re-run `link`.
- **Moved `<dev>`** — `git -C dgblocks worktree repair`, then `link` on each checkout
  (worktree pointers and Windows junctions are absolute).
- **Two copies of the addon registered** — two checkouts share a config dir. Check the
  relative `BLENDER_USER_*` entries are still in that checkout's `.vscode/settings.json`.
- **"Filename too long" / files silently missing** — Windows path limit; see [os_notes.md](os_notes.md).
- **Deleting a worktree by hand** — use `remove`, or unlink the `external_blocks/` entries
  first. A recursive delete that follows links would empty the block repo.
