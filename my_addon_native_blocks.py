 
from .blocks_natively_included import _block_core, block_debug_console_print, block_stable_modal
from .blocks_cloned_from_git import block_example_simple, block_example_complex_A

# Each folder/package is a "block": a swappable, standardized unit. 
# Some blocks depend on others. If block-A depends on block-B, then block-B must be listed after block-A
# Block folder names are arbitrary, but I recommend you follow the existing name standard
_ordered_blocks_list = [
    _block_core,
    block_debug_console_print,
    block_example_simple,
    block_example_complex_A,
    block_stable_modal,
    # ... Add other block defininions here
]
