
from enum import Enum, StrEnum, auto

# ==========================================
# Cache Key Constants
class Block_Runtime_Cache_Member_Definitions(Enum):
    # Registry for tracking status, availability, and the python module itself of an external lib
    KEY_LIBRARY_INSTALL_REGISTRY = "LIBRARY_INSTALL_REGISTRY"
    KEY_LIBRARY_MODULE_CACHE = "LIBRARY_MODULE_CACHE"
    KEY_LIBRARY_PATH_REGISTERED = "LIBRARY_PATH_REGISTERED"

# ==========================================
# Loggers user by this block
class Block_Loggers(Enum):
    PIP = ("pip", "DEBUG")
