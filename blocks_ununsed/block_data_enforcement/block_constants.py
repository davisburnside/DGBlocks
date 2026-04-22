
from enum import Enum, StrEnum, auto

from ..blocks_natively_included._block_core.core_block_constants import Core_Block_Loggers

# ==========================================
# Determines if stable ids are assigned immediately on creation or only when requested.
SHOULD_LAZY_CREATE = False 

# ==========================================
# Cache Key Constants
class Block_Runtime_Cache_Member_Definitions(Enum):
    # bl_datablocks & stable_ids have a 1-1 association. Keeping a regular & inverted dict allows O(1) lookup for both
    KNOWN_OBJECT_IDS = "CACHE_KNOWN_OBJECT_IDS" 
    KNOWN_OBJECT_IDS_INVERTED = "CACHE_KNOWN_OBJECT_IDS_INVERTED" 
    # Registry for tracking status, availability, and the python module itself of an external lib
    KEY_LIBRARY_INSTALL_REGISTRY = "LIBRARY_INSTALL_REGISTRY"
    KEY_LIBRARY_MODULE_CACHE = "LIBRARY_MODULE_CACHE"
    KEY_LIBRARY_PATH_REGISTERED = "LIBRARY_PATH_REGISTERED"

# ==========================================
# Loggers user by this block
class Block_Logger_Definitions(Enum):
    DATA_ENFORCE = Core_Block_Loggers("DATA_ENFORCE", "WARNING")
    PIP = Core_Block_Loggers("PIP", "WARNING")
    STABLE_ID = Core_Block_Loggers("STABLE_ID", "WARNING")
    OBJ_MOD = Core_Block_Loggers("OBJ_MOD", "WARNING")