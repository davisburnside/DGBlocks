# Pip Library Manager

`block-pip-library-manager` manages optional, exact-version Python wheel requirements without
writing into Blender's installation. Requirements are discovered from hooks and installed only
after a feature explicitly requests them and the user confirms the action.

## Storage

The existing `addon_saved_data_folder` preference is the root. The managed environment is scoped
by addon, Blender major/minor, Python ABI, and platform:

```text
<data-root>/python_libs/<addon-environment-id>/b<major><minor>/<python>-<platform>/site/
```

`addon_python_environment_id` lives in `addon_config/static_settings.py`. Keep it stable across
updates and unique among addons. This prevents filesystem collisions, but all addons still share
one Python process and `sys.modules`; incompatible versions cannot safely be loaded together.

## Declaring a requirement

Dependent blocks list `"block-pip-library-manager"` in their dependencies and return declarations
from a top-level hook:

```python
from ...native_blocks.block_pip_library_manager import (
    Library_Source_Policy,
    Python_Library_Requirement_Declaration,
)

def hook_get_python_library_requirements():
    return [
        Python_Library_Requirement_Declaration(
            requirement_uid="NUMBA_ACCELERATION",
            distribution_name="numba",
            import_names=("numba",),
            required_version="0.61.2",
            feature_label="Numba acceleration",
            reason="Accelerates repeated geometry analysis.",
            source_policy=Library_Source_Policy.ONLINE_ONLY,
        )
    ]
```

`repoll()` only reads declarations and distribution metadata. It never imports or installs.

## Lazy enforcement API

```python
result = Wrapper_Pip_Library_Manager.ensure_requirement(
    requirement_uid="NUMBA_ACCELERATION",
    requesting_block_id=_BLOCK_ID,
    action_token="RUN_ACCELERATED_ANALYSIS",
    context=context,
)
```

If available, the result is `Library_Ensure_Result.AVAILABLE`. Otherwise the manager opens a
detailed confirmation dialog. A successful asynchronous install fires the targeted callback:

```python
def hook_python_library_requirement_available(requirement_uid, action_token):
    ...
```

Use `get_module(requirement_uid, requesting_block_id)` as the explicit lazy import boundary.

Other public APIs include `repoll`, `get_library_info`, `get_all_library_infos`,
`get_requirement_info`, `is_library_installed`, `is_requirement_satisfied`,
`prompt_for_requirement`, and `cancel_operation`.

## Bundled wheels

Bundled artifacts must be wheels inside the requesting block:

```text
block_my_feature/wheels/windows-x64/cp311/*.whl
block_my_feature/wheels/linux-x64/cp311/*.whl
block_my_feature/wheels/macos-arm64/cp311/*.whl
block_my_feature/wheels/any/py3/*.whl
```

Set `bundled_wheel_root="wheels"` and choose `BUNDLED_ONLY` or `PREFER_BUNDLED`. The manager
rejects absolute/traversing paths. `bundled_wheel_sha256` can optionally verify selected wheel
files before pip runs. A bundled-only wheelhouse must contain all required dependency wheels.

## Safety and limitations

- Wheel-only: source distributions and arbitrary installers are intentionally unsupported.
- Installs happen in a staging copy and replace the managed environment only after pip succeeds.
- Pip output is streamed to a rolling native UI log and a full disk log.
- Blender data and UI are touched only on Blender's main thread.
- Replacing an already-imported package results in `RESTART_REQUIRED`; native modules cannot be
  safely unloaded by deleting `sys.modules` entries.
- Exact versions are used because this addon does not depend on or vendor `packaging` for PEP 440
  range evaluation.
- The block never uninstalls or replaces Blender-owned/global packages.
- On Windows, long target paths receive a warning because wheel internals and DLL loaders may
  still encounter path-length limitations.

## Data architecture

The filesystem and RTC are authoritative. Scene collection rows are ephemeral UI projections.
Addon preferences own only the persistent root path. Package status is deliberately not saved in
`.blend` files because it is machine-, interpreter-, and platform-specific.
