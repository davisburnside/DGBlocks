import os
import sys
import importlib
from functools import wraps
from addon_helpers.generic_helpers import get_addon_preferences
import bpy

from ..addon_config import addon_name

from ..native_blocks._block_core.core_feature_runtime_cache import Wrapper_Runtime_Cache.get_cache, Wrapper_Runtime_Cache.set_cache
from ..native_blocks._block_core.core_feature_logs import get_logger

from ..block_data_enforcement.feature_library_import.library_installation_wrapper import Library_Installation_Wrapper

from .block_constants import Block_Logger_Definitions, Enum_Runtime_Cache_Keys

#================================================================
# PUBLIC API - For use by other blocks
#================================================================

def safe_numba_decorator(**numba_kwargs):
    """
    Decorator factory that handles numba acceleration gracefully.
    
    Returns an actual numba decorator if numba is installed, else returns a no-op
    decorator that just returns the original function. Also handles cache directory
    setup if enabled.
    
    Args:
        **numba_kwargs: Keyword arguments to pass to the numba decorator.
            - njit=True: Use njit (nopython mode) instead of jit
            - cache=True: Enable disk caching of compiled functions
            - parallel=True: Enable parallel execution
            - Other arguments are passed directly to numba decorators
    
    Returns:
        A decorator function that will either apply numba acceleration or return
        the original function unchanged.
    
    Example:
        @safe_numba_decorator(njit=True, parallel=True)
        def heavy_calculation(array):
            # Function body here
            return result
    """
    def decorator(func):
        # Register original function in runtime cache
        _register_numba_function(func.__name__, func)
        
        # Check if numba is installed
        numba_module = Library_Installation_Wrapper.get_module("numba")
        
        # If numba is not installed, return the original function
        if not numba_module:
            return func
        
        # Get scene property to check if numba is enabled
        def get_is_numba_enabled():
            try:
                return bpy.context.scene.dgblocks_numba_accelerate_props.is_enabled
            except (AttributeError, TypeError):
                return False
        
        # Create a wrapper that decides at runtime whether to use numba
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not get_is_numba_enabled():
                return func(*args, **kwargs)
            
            # If we get here, numba is installed and enabled
            # Get the compiled function (creating it if needed)
            compiled_func = _get_or_create_compiled_func(func, numba_kwargs)
            if compiled_func:
                return compiled_func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        
        return wrapper
    
    return decorator

def get_numba_imports():
    """
    Returns dictionary with numba decorators if available, or None if not installed.
    
    Returns:
        dict or None: Dictionary with keys 'jit', 'njit', 'vectorize', etc. mapping to
                     numba decorator functions if numba is installed, or None.
    
    Example:
        numba = get_numba_imports()
        if numba:
            @numba['njit']
            def my_func():
                # ...
    """
    # Check if already cached
    imports = Wrapper_Runtime_Cache.get_cache(Enum_Runtime_Cache_Keys.NUMBA_MODULE_IMPORTS)
    if imports is not None:
        return imports
    
    # Try to import
    numba_module = Library_Installation_Wrapper.get_module("numba")
    if not numba_module:
        return None
    
    # Create dict of important decorators
    imports = {
        'jit': getattr(numba_module, 'jit', None),
        'njit': getattr(numba_module, 'njit', None),
        'vectorize': getattr(numba_module, 'vectorize', None),
        'guvectorize': getattr(numba_module, 'guvectorize', None),
        'stencil': getattr(numba_module, 'stencil', None),
        'cfunc': getattr(numba_module, 'cfunc', None),
    }
    
    # Cache and return
    Wrapper_Runtime_Cache.set_cache(Enum_Runtime_Cache_Keys.NUMBA_MODULE_IMPORTS, imports)
    return imports

#================================================================
# BLOCK-INTERNAL API - Private functions
#================================================================

def _get_numba_cache_dir():
    """
    Returns the directory path for numba cache if valid, or None.
    
    The cache directory is only valid if the addon_saved_data_folder 
    preference is set and the directory exists.
    
    Returns:
        str or None: Path to numba cache directory or None if invalid
    """
    logger = get_logger(Block_Logger_Definitions.NUMBA_CACHE)
    
    try:
        prefs = get_addon_preferences(context)
        base_path = prefs.addon_saved_data_folder
        
        if not base_path or not os.path.isdir(base_path):
            logger.debug(f"No valid addon_saved_data_folder: {base_path}")
            return None
        
        # Create specific path for numba cache
        cache_dir = os.path.join(base_path, "numba_cache")
        return cache_dir
    
    except (AttributeError, KeyError) as e:
        logger.debug(f"Error getting numba cache dir: {e}")
        return None

def _ensure_numba_cache_dir():
    """
    Creates the numba cache directory if it doesn't exist.
    
    Returns:
        str or None: Path to created cache directory or None if failed
    """
    logger = get_logger(Block_Logger_Definitions.NUMBA_CACHE)
    cache_dir = _get_numba_cache_dir()
    
    if not cache_dir:
        return None
    
    try:
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
            logger.info(f"Created numba cache directory: {cache_dir}")
        
        return cache_dir
    except Exception as e:
        logger.error(f"Failed to create numba cache directory: {e}")
        return None

def _clear_numba_cache():
    """
    Clears all cached numba compilations.
    
    Returns:
        bool: True if cache was cleared, False otherwise
    """
    logger = get_logger(Block_Logger_Definitions.NUMBA_CACHE)
    cache_dir = _get_numba_cache_dir()
    
    if not cache_dir or not os.path.exists(cache_dir):
        logger.debug("No cache directory to clear")
        return False
    
    try:
        # Clear numba's environment cache
        numba_module = Library_Installation_Wrapper.get_module("numba")
        if numba_module and hasattr(numba_module, 'cuda'):
            numba_module.cuda.cudadrv.driver._driver_lock = None
            logger.debug("Reset numba cuda driver lock")
        
        # Remove all files in cache directory
        for root, dirs, files in os.walk(cache_dir):
            for file in files:
                try:
                    os.remove(os.path.join(root, file))
                    logger.debug(f"Removed cache file: {file}")
                except Exception as e:
                    logger.warning(f"Failed to remove {file}: {e}")
        
        logger.info(f"Cleared numba cache at: {cache_dir}")
        return True
    
    except Exception as e:
        logger.error(f"Error clearing numba cache: {e}")
        return False

def _register_numba_function(func_name, original_func, compiled_func=None):
    """
    Registers a function in the numba function registry.
    
    Args:
        func_name: Name of the function
        original_func: Original Python function
        compiled_func: Compiled numba function (if available)
    """
    # Get or create the registry
    registry = Wrapper_Runtime_Cache.get_cache(Enum_Runtime_Cache_Keys.NUMBA_FUNCTION_REGISTRY)
    if registry is None:
        registry = {}
        Wrapper_Runtime_Cache.set_cache(Enum_Runtime_Cache_Keys.NUMBA_FUNCTION_REGISTRY, registry)
    
    # Register the function
    registry[func_name] = {
        'original': original_func,
        'compiled': compiled_func,
        'module': original_func.__module__,
    }

def _get_or_create_compiled_func(func, numba_kwargs):
    """
    Gets or creates a compiled version of a function.
    
    Args:
        func: Original Python function
        numba_kwargs: Numba decorator kwargs
    
    Returns:
        Compiled function or None if compilation fails
    """
    logger = get_logger(Block_Logger_Definitions.NUMBA_CORE)
    numba_module = Library_Installation_Wrapper.get_module("numba")
    
    if not numba_module:
        return None
    
    # Check registry for existing compiled version
    registry = Wrapper_Runtime_Cache.get_cache(Enum_Runtime_Cache_Keys.NUMBA_FUNCTION_REGISTRY)
    if registry and func.__name__ in registry and registry[func.__name__].get('compiled'):
        return registry[func.__name__]['compiled']
    
    # Set up cache directory if caching is enabled
    if numba_kwargs.get("cache", True):
        cache_dir = _ensure_numba_cache_dir()
        if cache_dir:
            numba_kwargs["cache"] = True
            os.environ["NUMBA_CACHE_DIR"] = cache_dir
        else:
            numba_kwargs["cache"] = False
    
    # Determine which decorator to use
    try:
        if "njit" in numba_kwargs and numba_kwargs.pop("njit", False):
            decorator_func = numba_module.njit
        else:
            decorator_func = numba_module.jit
        
        # Apply the decorator
        compiled_func = decorator_func(**numba_kwargs)(func)
        
        # Update registry
        _register_numba_function(func.__name__, func, compiled_func)
        return compiled_func
    
    except Exception as e:
        logger.error(f"Failed to compile {func.__name__}: {e}")
        return None