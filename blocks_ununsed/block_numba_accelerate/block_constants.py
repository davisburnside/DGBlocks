from enum import Enum, StrEnum, auto

from ..blocks_natively_included._block_core.core_block_constants import Core_Block_Loggers

# Loggers for this block
class Block_Logger_Definitions(Enum):
    NUMBA_CORE = Core_Block_Loggers("NUMBA-CORE", "WARNING")
    NUMBA_CACHE = Core_Block_Loggers("NUMBA-CACHE", "WARNING")

# Runtime cache keys
class Enum_Runtime_Cache_Keys(StrEnum):
    NUMBA_FUNCTION_REGISTRY = auto()
    NUMBA_MODULE_IMPORTS = auto()  # Stores imported numba decorators

# Decorator presets (optional convenience)
class Enum_Numba_Decorator_Configs(Enum):
    BASIC_JIT = {"njit": True, "cache": True}
    PARALLEL_JIT = {"njit": True, "parallel": True, "cache": True}
    NO_CACHE_JIT = {"njit": True, "cache": False}