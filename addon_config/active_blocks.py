 
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
# Your blocks, used in your addon
# --------------------------------------------------------------
from ..external_blocks.block_flatypus_modes_manager import block_flatypus_modes_manager

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
    # block_flatypus_modes_manager,
    # _block_usecase_01_minimal,
    # _block_usecase_02_basic,
    # _block_usecase_02B_basic,
]
