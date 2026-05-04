# Block Numba Acceleration

## Purpose
Provides Numba Just-In-Time (JIT) compilation integration to accelerate computationally intensive Python functions. This block significantly improves performance for mathematical and array operations by compiling them to optimized machine code, with graceful fallback when Numba is not available.

## Architecture
- `__init__.py`: Main block definition, scene properties, and UI
- `block_constants.py`: Logger definitions, runtime cache keys, and decorator presets
- `feature_numba_function_wrapper.py`: Core decorator system and cache management

## Key Features
- Transparent fallback to standard Python when Numba unavailable
- Automatic Numba detection and function decoration
- Scene-level toggle to enable/disable acceleration
- Disk caching of compiled functions (when addon_saved_data_folder is set)
- UI integration with block_data_enforcement for Numba installation

## Dependencies
- **Internal**: 
  - block-core: Runtime data cache and logging
  - block-data-enforcement: Library installation wrapper
  - block-event-listeners: Hook system
- **External**: 
  - Numba (optional, installed through block-data-enforcement)
  - NumPy (required by Numba)

## API Reference

### Primary API Functions

#### `safe_numba_decorator(**numba_kwargs)`
Decorator factory that enables numba acceleration when available:

```python
from ..block_numba_accelerate.feature_numba_function_wrapper import safe_numba_decorator

@safe_numba_decorator(njit=True, parallel=True, cache=True)
def my_function(data):
    # Function body - write normal Python code
    # Will be accelerated if numba is available and enabled
    result = 0
    for i in range(len(data)):
        result += data[i] * 2
    return result
```

Parameters:
- `njit`: (bool) Use nopython mode (recommended for best performance)
- `parallel`: (bool) Enable parallel execution
- `cache`: (bool) Enable disk caching of compiled code
- Additional kwargs are passed directly to numba decorators

#### `get_numba_imports()`
Get dictionary of numba decorators if available:

```python
from ..block_numba_accelerate.feature_numba_function_wrapper import get_numba_imports

# Get numba decorators
numba = get_numba_imports()
if numba:
    # Numba is available
    @numba['njit']
    def my_function():
        # Function body
```

Returns a dictionary with keys:
- `jit`: Standard JIT decorator
- `njit`: Nopython mode JIT (recommended)
- `vectorize`: Vectorize decorator
- `guvectorize`: Generalized universal vectorize
- `stencil`: Stencil decorator
- `cfunc`: C callback decorator

### Convenience Decorator Presets

For common use cases, predefined configurations are available:

```python
from ..block_numba_accelerate.block_constants import Enum_Numba_Decorator_Configs
from ..block_numba_accelerate.feature_numba_function_wrapper import safe_numba_decorator

# Use a preset configuration
@safe_numba_decorator(**Enum_Numba_Decorator_Configs.PARALLEL_JIT.value)
def parallel_calculation(data):
    # Will use njit=True, parallel=True, cache=True
```

Available presets:
- `BASIC_JIT`: Standard nopython mode JIT with caching (`njit=True, cache=True`)
- `PARALLEL_JIT`: Parallel execution with nopython mode and caching (`njit=True, parallel=True, cache=True`)
- `NO_CACHE_JIT`: Nopython mode without disk caching (`njit=True, cache=False`)

## Usage Examples

### Basic Usage

```python
from ..block_numba_accelerate.feature_numba_function_wrapper import safe_numba_decorator

# Simple function with numba acceleration
@safe_numba_decorator(njit=True)
def calculate_distance(points_a, points_b):
    """Calculate Euclidean distance between two sets of points."""
    result = 0.0
    for i in range(len(points_a)):
        dx = points_a[i][0] - points_b[i][0]
        dy = points_a[i][1] - points_b[i][1]
        dz = points_a[i][2] - points_b[i][2]
        result += (dx*dx + dy*dy + dz*dz) ** 0.5
    return result
```

### With NumPy Integration

```python
import numpy as np
from ..block_numba_accelerate.feature_numba_function_wrapper import safe_numba_decorator

# NumPy-accelerated function
@safe_numba_decorator(njit=True, parallel=True)
def normalize_vectors(vectors):
    """Normalize an array of 3D vectors."""
    result = np.empty_like(vectors)
    for i in range(len(vectors)):
        x, y, z = vectors[i]
        length = (x*x + y*y + z*z) ** 0.5
        if length > 0:
            result[i, 0] = x / length
            result[i, 1] = y / length
            result[i, 2] = z / length
        else:
            result[i] = vectors[i]  # Avoid division by zero
    return result
```

### Dynamic Decorator Import

```python
from ..block_numba_accelerate.feature_numba_function_wrapper import get_numba_imports

# Get numba decorators dictionary
numba = get_numba_imports()

# Define a vectorized function if numba is available
if numba and numba['vectorize']:
    # Create a universal function (ufunc) with numba
    vector_add = numba['vectorize'](['float64(float64, float64)'])(
        lambda x, y: x + y
    )
else:
    # Fallback implementation
    def vector_add(x, y):
        return x + y
```

## Best Practices

1. **Numba-Compatible Code**: Write functions using numba-compatible operations:
   - Avoid Python objects, list comprehensions, dictionaries, sets
   - Use NumPy arrays instead of Python lists
   - Prefer simple loops and mathematical operations

2. **Error Handling**: The `safe_numba_decorator` preserves original error messages whether from original or compiled code.

3. **Runtime Toggle**: The scene-level property `scene.dgblocks_numba_accelerate_props.is_enabled` lets you enable/disable all numba acceleration at runtime.

4. **Cache Management**: Clear the compilation cache through the UI panel if you experience any issues with cached compilations.

5. **Performance Tips**:
   - First call to a numba function compiles it (slower)
   - Subsequent calls use compiled code (much faster)
   - Largest performance gains come from compute-heavy, loop-intensive code

## Troubleshooting

- **Function not accelerated**: Check if numba is installed and enabled in the UI panel
- **Compilation errors**: Ensure your function only uses numba-compatible operations
- **"No compiled version"**: The function may not be compatible with nopython mode
