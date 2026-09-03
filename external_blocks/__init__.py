"""
external_blocks -- consumer blocks that live in their OWN repos.

Nothing but links belongs here. Each `block_<name>/` entry is a directory junction
(Windows) or symlink (macOS/Linux) to a sibling checkout of that block's repo, created by
`devkit/new_worktree.py link`. `addon_config/active_blocks.py` discovers and registers
every `block_*` package found here, after the native blocks.
"""
