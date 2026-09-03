# external_blocks/

This folder holds **links, not code**. Every `block_<name>/` entry is a junction/symlink to a
block repo that lives *beside* the DGBlocks checkout:

```
<dev>/
  dgblocks/                    this checkout (or dgblocks-<task>/ worktrees)
  block_<name>/                the block's own git repo
```

`devkit/new_worktree.py link` creates the links; `addon_config/active_blocks.py` registers
whatever it finds. Everything except `__init__.py` and this file is gitignored, so DGBlocks
history never references a consumer block. See `<dev>/devkit/README.md` for the full setup.
