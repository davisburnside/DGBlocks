
"""
handler_callbacks.py — @persistent bpy.app.handlers callbacks for block_app_handlers.

Architecture
------------
Every Blender handler calls _fire_handler(type_name, **kwargs), which performs:
  1. Re-entrancy guard   — skips if this type is already executing (prevents infinite loops).
  2. is_enabled check    — skips hook notification if user has disabled this handler in the UIList.
  3. Frequency filter    — skips if less than frequency_filter_seconds have elapsed since last fire.
  4. Hook notification   — calls Wrapper_Hooks.run_hooked_funcs(hook_app_handler_<type_name>, **kwargs).

install_handler / uninstall_handler / uninstall_all_handlers are called by Wrapper_App_Handlers.
They are the only functions that touch bpy.app.handlers.
"""

import time

import bpy
from bpy.app.handlers import persistent  # type: ignore

# Inter-block imports
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks

# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members


# ==============================================================================================================================
# CENTRAL DISPATCH
# ==============================================================================================================================

def _get_status_instance(handler_type_name: str):
    """Return the RTC_App_Handler_Status_Instance for the given type name, or None."""
    status_list = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.APP_HANDLER_STATUS_LIST)
    for item in status_list:
        if item.handler_type_name == handler_type_name:
            return item
    return None


def _fire_handler(handler_type_name: str, **kwargs):
    """
    Central dispatch called by every @persistent callback.
    Applies re-entrancy guard, is_enabled check, frequency filter, then fires the hook.
    """
    logger = get_logger(Block_Loggers.APP_HANDLERS_EVENTS)

    executing = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.APP_HANDLERS_CURRENTLY_EXECUTING)
    _, handler_instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(Block_RTC_Members.APP_HANDLER_STATUS_LIST, "handler_type_name", handler_type_name)
    if not handler_instance or not handler_instance.is_registered:
        logger.warning(f"App Handler '{handler_instance}' is not registered")
    if not handler_instance.is_enabled:
        return
    if handler_type_name in executing:
        logger.warning(
            f"Re-entrant '{handler_type_name}' call detected — "
            f"skipping notification hook to prevent infinite loop"
        )
        return

    executing.add(handler_type_name)
    try:
        status = _get_status_instance(handler_type_name)
        if status is None:
            logger.debug(f"'{handler_type_name}': no status instance found — skipping")
            return

        if not status.is_enabled:
            logger.debug(f"'{handler_type_name}' is disabled — skipping notification hook")
            return

        if status.frequency_filter_seconds > 0.0:
            now = time.monotonic()
            elapsed = now - status.last_fired_timestamp
            if elapsed < status.frequency_filter_seconds:
                logger.debug(
                    f"'{handler_type_name}' rate-limited "
                    f"({elapsed:.3f}s < {status.frequency_filter_seconds:.3f}s) — skipping"
                )
                return
            status.last_fired_timestamp = now
        else:
            status.last_fired_timestamp = time.monotonic()

        status.fire_count += 1
        logger.debug(
            f"Firing 'hook_app_handler_{handler_type_name}' "
            f"(fire #{status.fire_count})"
        )

        Wrapper_Hooks.run_hooked_funcs(
            hook_func_name           = f"hook_app_handler_{handler_type_name}",
            should_halt_on_exception = False,
            **kwargs,
        )

    except Exception:
        logger = get_logger(Block_Loggers.APP_HANDLERS_LIFECYCLE)
        logger.error(
            f"Unhandled exception in app handler dispatch for '{handler_type_name}'",
            exc_info=True,
        )
    finally:
        executing.discard(handler_type_name)


# ==============================================================================================================================
# @PERSISTENT BLENDER CALLBACKS — File I/O
# ==============================================================================================================================

@persistent
def _cb_save_pre(scene, *args):
    _fire_handler("save_pre", scene=scene)

@persistent
def _cb_save_post(scene, *args):
    _fire_handler("save_post", scene=scene)

@persistent
def _cb_load_pre(*args):
    _fire_handler("load_pre")


@persistent
def _cb_depsgraph_update_pre(scene, depsgraph, *args):
    _fire_handler("depsgraph_update_pre", scene=scene, depsgraph=depsgraph)
@persistent
def _cb_depsgraph_update_post(scene, depsgraph, *args):
    _fire_handler("depsgraph_update_post", scene=scene, depsgraph=depsgraph)

# ==============================================================================================================================
# @PERSISTENT BLENDER CALLBACKS — Render
# ==============================================================================================================================

@persistent
def _cb_render_init(scene, *args):
    _fire_handler("render_init", scene=scene)

@persistent
def _cb_render_pre(scene, *args):
    _fire_handler("render_pre", scene=scene)

@persistent
def _cb_render_post(scene, *args):
    _fire_handler("render_post", scene=scene)

@persistent
def _cb_render_write(scene, *args):
    _fire_handler("render_write", scene=scene)

@persistent
def _cb_render_stats(scene, *args):
    _fire_handler("render_stats", scene=scene)

@persistent
def _cb_render_cancel(scene, *args):
    _fire_handler("render_cancel", scene=scene)

@persistent
def _cb_render_complete(scene, *args):
    _fire_handler("render_complete", scene=scene)


# ==============================================================================================================================
# @PERSISTENT BLENDER CALLBACKS — Bake
# ==============================================================================================================================

@persistent
def _cb_object_bake_pre(scene, *args):
    _fire_handler("object_bake_pre", scene=scene)

@persistent
def _cb_object_bake_complete(scene, *args):
    _fire_handler("object_bake_complete", scene=scene)

@persistent
def _cb_object_bake_cancel(scene, *args):
    _fire_handler("object_bake_cancel", scene=scene)


# ==============================================================================================================================
# @PERSISTENT BLENDER CALLBACKS — Animation
# ==============================================================================================================================

@persistent
def _cb_frame_change_pre(scene, depsgraph, *args):
    _fire_handler("frame_change_pre", scene=scene, depsgraph=depsgraph)

@persistent
def _cb_frame_change_post(scene, depsgraph, *args):
    _fire_handler("frame_change_post", scene=scene, depsgraph=depsgraph)


# ==============================================================================================================================
# @PERSISTENT BLENDER CALLBACKS — Annotation
# ==============================================================================================================================

@persistent
def _cb_annotation_pre(scene, *args):
    _fire_handler("annotation_pre", scene=scene)

@persistent
def _cb_annotation_post(scene, *args):
    _fire_handler("annotation_post", scene=scene)


# ==============================================================================================================================
# @PERSISTENT BLENDER CALLBACKS — Compositing
# ==============================================================================================================================

@persistent
def _cb_composite_pre(scene, *args):
    _fire_handler("composite_pre", scene=scene)

@persistent
def _cb_composite_post(scene, *args):
    _fire_handler("composite_post", scene=scene)

@persistent
def _cb_composite_cancel(scene, *args):
    _fire_handler("composite_cancel", scene=scene)


# ==============================================================================================================================
# @PERSISTENT BLENDER CALLBACKS — Version / XR
# ==============================================================================================================================

@persistent
def _cb_version_update(*args):
    _fire_handler("version_update")

@persistent
def _cb_xr_session_start_pre(*args):
    _fire_handler("xr_session_start_pre")

@persistent
def _cb_xr_session_end(*args):
    _fire_handler("xr_session_end")


# ==============================================================================================================================
# CALLBACK REGISTRY
# Maps handler_type_name -> callback function.
# bpy.app.handlers.<type_name> == type_name, so no separate attr-name mapping needed.
# ==============================================================================================================================

_CALLBACK_MAP: dict[str, object] = {
    "save_pre":              _cb_save_pre,
    "save_post":             _cb_save_post,
    "depsgraph_update_pre":  _cb_depsgraph_update_pre,
    "depsgraph_update_post":  _cb_depsgraph_update_post,
    "load_pre":              _cb_load_pre,
    "render_init":           _cb_render_init,
    "render_pre":            _cb_render_pre,
    "render_post":           _cb_render_post,
    "render_write":          _cb_render_write,
    "render_stats":          _cb_render_stats,
    "render_cancel":         _cb_render_cancel,
    "render_complete":       _cb_render_complete,
    "object_bake_pre":       _cb_object_bake_pre,
    "object_bake_complete":  _cb_object_bake_complete,
    "object_bake_cancel":    _cb_object_bake_cancel,
    "frame_change_pre":      _cb_frame_change_pre,
    "frame_change_post":     _cb_frame_change_post,
    "annotation_pre":        _cb_annotation_pre,
    "annotation_post":       _cb_annotation_post,
    "composite_pre":         _cb_composite_pre,
    "composite_post":        _cb_composite_post,
    "composite_cancel":      _cb_composite_cancel,
    "version_update":        _cb_version_update,
    "xr_session_start_pre":  _cb_xr_session_start_pre,
    "xr_session_end":        _cb_xr_session_end,
}


# ==============================================================================================================================
# INSTALL / UNINSTALL HELPERS
# ==============================================================================================================================

def install_handler(type_name: str, logger) -> bool:
    """
    Append the @persistent callback for type_name to the matching bpy.app.handlers list.
    Returns True if the callback was newly added, False if already present or unknown.
    """
    if type_name not in _CALLBACK_MAP:
        logger.warning(f"install_handler: unknown handler type '{type_name}'")
        return False

    callback = _CALLBACK_MAP[type_name]
    handler_list = getattr(bpy.app.handlers, type_name, None)
    if handler_list is None:
        logger.warning(f"install_handler: bpy.app.handlers.{type_name} not found")
        return False

    if callback not in handler_list:
        handler_list.append(callback)
        logger.debug(f"install_handler: appended callback for '{type_name}'")
        return True

    logger.debug(f"install_handler: callback for '{type_name}' already present")
    return False


def uninstall_handler(type_name: str, logger) -> bool:
    """
    Remove the @persistent callback for type_name from the matching bpy.app.handlers list.
    Returns True if the callback was removed, False if not present or unknown.
    """
    if type_name not in _CALLBACK_MAP:
        return False

    callback = _CALLBACK_MAP[type_name]
    handler_list = getattr(bpy.app.handlers, type_name, None)
    if handler_list is not None and callback in handler_list:
        handler_list.remove(callback)
        logger.debug(f"uninstall_handler: removed callback for '{type_name}'")
        return True

    return False


def uninstall_all_handlers(logger):
    """Remove all @persistent callbacks registered by this block."""
    for type_name in list(_CALLBACK_MAP.keys()):
        uninstall_handler(type_name, logger)
    logger.debug("uninstall_all_handlers: all callbacks removed")
