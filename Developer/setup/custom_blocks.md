# Custom blocks: creating your own, cloning someone else's

DGBlocks is the framework and the addon package root. Your project is a **block**: one
Python package, one git repo, living beside the DGBlocks checkout and linked into it. You
never fork or edit DGBlocks itself.

## Cloning an existing block (e.g. Flatypus)

```
cd <dev>
git clone <block-url> block_<name>           # folder name == package name, must start with block_
python dgblocks/Developer/setup/new_worktree.py link      # plus `link <each worktree>` you already have
```

Blender: Start. `addon_config/active_blocks.py` discovers every `block_*` package in
`external_blocks/` and registers it after the native blocks. Nothing else to configure.

The folder name matters: it is the package name Python imports, and it must match what the
block's own relative imports expect (repo root == package root, `__init__.py` at the top).

## Creating a new block

1. `mkdir <dev>/block_<name> && cd <dev>/block_<name> && git init`
2. Build the package. The authoring recipe with skeleton code is
   [Developer/AI_Assist/Memory_Bank/blockAuthoringGuide.md](../AI_Assist/Memory_Bank/blockAuthoringGuide.md);
   the dense pattern reference is
   [Developer/AI_Assist/Summarized_Memory_Bank.md](../AI_Assist/Summarized_Memory_Bank.md).
   Minimum: `__init__.py` with `_BLOCK_DECLARATION`, `constants.py` with the enum classes, one
   `feature_*.py` per Feature Wrapper Class, a `README.md`.
3. Import the framework by **relative import from the addon root**, three levels up from the
   block's top-level modules:
   ```python
   from ...native_blocks.block_core.core_features.loggers.feature_wrapper import get_logger
   from ...addon_helpers.data_structures import Block_Declaration
   ```
   One more dot for each sub-folder level inside your block. Never absolute-import the addon
   by name: the addon's package name is whatever folder Blender loaded it from.
4. `python dgblocks/Developer/setup/new_worktree.py link`, then Blender: Start.
5. Commit in your block repo. Push to your own remote.

## Rules that keep it modular

- Depend only on blocks named in your `_BLOCK_DECLARATION.block_dependencies`, and only on
  `native_blocks/` and `addon_helpers/`. Never on another external block unless declared.
- Two external blocks that depend on each other must also be ordered: set
  `_EXTERNAL_BLOCK_ORDER` in `addon_config/active_blocks.py` (listed names register first, in
  that order; the rest follow alphabetically). That is the one DGBlocks file a consumer may
  need to touch, and only for that case.
- Python libraries your block needs go through `block_pip_library_manager` declarations,
  not manual installs, so every checkout and every teammate gets them the same way.
- Blender data your block creates should carry your block's prefix so several blocks can
  coexist in one scene.

## Updating the framework under your block

`git pull` in `dgblocks/`. Your block's files are not in DGBlocks history, so a pull can't
conflict with them. If a framework change breaks your block, that's a block commit, not a
DGBlocks edit; see [teamwork.md](teamwork.md) for how framework and block changes are
sequenced.
