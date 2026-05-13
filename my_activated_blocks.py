 
# ==============================================================================================================================
# Block package imports
# ==============================================================================================================================

# --------------------------------------------------------------
# Builtin blocks with actual usecases
# --------------------------------------------------------------
from .native_blocks import block_core#, block_debug_console_print #, block_pip_library_manager, block_timers

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
# from .external_blocks import block_flatypus_modes_manager

# ==============================================================================================================================
# Blocks registered at startup
# ==============================================================================================================================

# List order must respect the block's dependencies. If block-A depends on block-B, then block-B must be listed after block-A
# In other words, all blocks depend on block_core, so it is the list's first item

_ordered_blocks_list = [
    block_core,
    # block_timers,
    # block_debug_console_print,
    # block_pip_library_manager,
    # _block_usecase_01_minimal,
    # _block_usecase_02_basic,
    # _block_usecase_02B_basic,
]
