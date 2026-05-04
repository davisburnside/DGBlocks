 
from .native_blocks import block_core, block_debug_console_print, block_stable_modal, block_onscreen_drawing
from .external_blocks import block_flatypus_modes_manager

# Each folder/package is a "block": a swappable, standardized unit. 
# Some blocks depend on others. If block-A depends on block-B, then block-B must be listed after block-A
# Block folder names are arbitrary, but I recommend you follow the existing name standard
_ordered_blocks_list = [
    block_core,
    block_debug_console_print,
    # block_example_simple,
    # block_example_complex_A,
    # block_stable_modal,
    # block_onscreen_drawing,
    # block_flatypus_modes_manager,
    # block_2tone_tests,
    # ... Add other block defininions here
]
