 
# ==============================================================================================================================
# Block package imports
# ==============================================================================================================================

# --------------------------------------------------------------
# Builtin blocks with actual usecases
# --------------------------------------------------------------
from ..native_blocks import (
    block_core, 
    block_debug_console_print, 
    block_timers, 
    block_onscreen_drawing, 
    block_app_handlers, 
    block_geometry_actions,
    block_modal_events,
    block_pip_library_manager,
)


# --------------------------------------------------------------
# Builtin blocks for demos / learning
# --------------------------------------------------------------
#from .native_blocks._example_usecases import _block_usecase_01_minimal, _block_usecase_02_basic#, _block_usecase_02B_basic

# --------------------------------------------------------------
# Builtin unfinished block prototypes
# --------------------------------------------------------------
# from unfinished_blocks import <>

# --------------------------------------------------------------
# External blocks: every `block_*` package linked into external_blocks/ (see its README)
# --------------------------------------------------------------
import importlib
import pkgutil
from .. import external_blocks as _external_blocks_package

# Names listed here register first, in this order; every other discovered block follows
# alphabetically. Only needed when one external block depends on another.
_EXTERNAL_BLOCK_ORDER: tuple = ()

def _discover_external_blocks() -> list:
    names = sorted(
        info.name for info in pkgutil.iter_modules(_external_blocks_package.__path__)
        if info.ispkg and info.name.startswith("block_")
    )
    ordered = [n for n in _EXTERNAL_BLOCK_ORDER if n in names]
    ordered += [n for n in names if n not in _EXTERNAL_BLOCK_ORDER]
    return [importlib.import_module(f"{_external_blocks_package.__name__}.{n}") for n in ordered]

_EXTERNAL_BLOCK_PACKAGES = _discover_external_blocks()

# ==============================================================================================================================
# Blocks registered at startup
# ==============================================================================================================================

# List order must respect the block's dependencies. If block-A depends on block-B, then block-B must be listed after block-A
# In other words, all blocks depend on block_core, so it is the list's first item

_BLOCK_PACKAGES = [
    block_core,
    block_debug_console_print,
    block_timers,              # must precede block_onscreen_drawing — animations depend on it
    block_onscreen_drawing,
    block_app_handlers,
    block_geometry_actions,
    block_modal_events,
    block_pip_library_manager,
    *_EXTERNAL_BLOCK_PACKAGES,   # linked consumer blocks, discovered above
    # _block_usecase_01_minimal,
    # _block_usecase_02_basic,
    # _block_usecase_02B_basic,
]
