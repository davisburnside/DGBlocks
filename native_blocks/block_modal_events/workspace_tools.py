"""Registration helpers for declarative modal workspace tools.

Blender exposes toolbar tools through ``bpy.utils.register_tool`` rather than normal
``register_class``. One logical DGBlocks declaration may therefore expand to several concrete
WorkSpaceTool classes, one for each editor/mode placement.
"""

import re

import bpy
from bpy.types import WorkSpaceTool

from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .data_structures import (
    Workspace_Tool_Definition,
    Workspace_Tool_Placement,
    RTC_Workspace_Tool_Instance,
)


_FALLBACK_TOOL_ICON = "ops.generic.select"
_ICON_HANDLE_PREFIX = "dgblocks.image."
_LISTENER_EVENT_OPERATOR_ID = "dgblocks.workspace_tool_listener_event"


def _safe_id_part(value) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "all").lower()).strip("_")


def _concrete_tool_id(logical_tool_id: str, placement: Workspace_Tool_Placement) -> str:
    return ".".join((
        logical_tool_id,
        _safe_id_part(placement.space_type),
        _safe_id_part(placement.context_mode),
    ))


def _image_icon_handle(logical_tool_id: str, image_name: str) -> str:
    return f"{_ICON_HANDLE_PREFIX}{_safe_id_part(logical_tool_id)}.{_safe_id_part(image_name)}"


def _bind_image_icon(handle: str, image_name: str) -> bool:
    """Bind a loaded Image preview to Blender's toolbar icon cache.

    WorkSpaceTool only publicly accepts a string name for Blender's ``.dat`` toolbar-icon
    system. This contained compatibility bridge supplies the preview icon id under a synthetic
    handle. Failure is harmless: callers retain Blender's built-in ``none`` fallback.
    """
    image = bpy.data.images.get(image_name)
    if image is None:
        return False

    try:
        # UILayout.icon() is Blender's public datablock->icon-value API. In Blender 5 an
        # Image.preview may legitimately report icon_id == 0 even though this call returns a
        # valid generated icon value.
        icon_id = bpy.types.UILayout.icon(image)
        if not icon_id:
            return False
        from bl_ui import space_toolsystem_common
        space_toolsystem_common._icon_cache[handle] = icon_id
        return True
    except Exception:
        get_logger(Block_Loggers.MODAL_LIFECYCLE).error(
            f"Unable to create workspace-tool icon from Image '{image_name}'",
            exc_info=True,
        )
        return False


def _remove_icon_handle(handle: str) -> None:
    """Forget our cache entry without releasing the Image-owned preview icon id."""
    if not handle.startswith(_ICON_HANDLE_PREFIX):
        return
    try:
        from bl_ui import space_toolsystem_common
        space_toolsystem_common._icon_cache.pop(handle, None)
    except Exception:
        pass


def _validate_definitions(definitions_by_block: dict) -> list[tuple[str, Workspace_Tool_Definition]]:
    flattened = []
    logical_ids = set()
    concrete_ids = set()

    for block_id, definitions in (definitions_by_block or {}).items():
        if definitions is None:
            continue
        if not isinstance(definitions, (list, tuple)):
            raise TypeError(
                f"Block '{block_id}' must return list[Workspace_Tool_Definition], "
                f"got {type(definitions)}"
            )
        for definition in definitions:
            if not isinstance(definition, Workspace_Tool_Definition):
                raise TypeError(
                    f"Block '{block_id}' returned {type(definition)} instead of "
                    "Workspace_Tool_Definition"
                )
            if not definition.tool_id or "." not in definition.tool_id:
                raise ValueError(
                    f"Workspace tool id '{definition.tool_id}' from '{block_id}' must be namespaced"
                )
            if definition.tool_id in logical_ids:
                raise ValueError(f"Duplicate logical workspace tool id '{definition.tool_id}'")
            if not definition.placements:
                raise ValueError(f"Workspace tool '{definition.tool_id}' has no placements")

            logical_ids.add(definition.tool_id)
            for placement in definition.placements:
                if not isinstance(placement, Workspace_Tool_Placement):
                    raise TypeError(
                        f"Workspace tool '{definition.tool_id}' contains an invalid placement"
                    )
                concrete_id = _concrete_tool_id(definition.tool_id, placement)
                if concrete_id in concrete_ids:
                    raise ValueError(f"Duplicate concrete workspace tool id '{concrete_id}'")
                concrete_ids.add(concrete_id)
            flattened.append((block_id, definition))
    return flattened


def _make_tool_class(
    definition: Workspace_Tool_Definition,
    placement: Workspace_Tool_Placement,
    concrete_id: str,
    icon_handle: str,
):
    declared_keymap = placement.keymap if placement.keymap is not None else definition.keymap
    keymap_entries = list(declared_keymap or ())
    for binding in definition.listener_events:
        event_args = {
            "type": binding.type,
            "value": binding.value,
        }
        for modifier_name in ("shift", "ctrl", "alt", "oskey", "any"):
            modifier_value = getattr(binding, modifier_name)
            if modifier_value:
                event_args[modifier_name] = modifier_value
        keymap_entries.append((
            _LISTENER_EVENT_OPERATOR_ID,
            event_args,
            {"properties": [("logical_tool_id", definition.tool_id)]},
        ))

    attrs = {
        "bl_space_type": placement.space_type,
        "bl_context_mode": placement.context_mode,
        "bl_idname": concrete_id,
        "bl_label": definition.label,
        "bl_description": definition.description,
        "bl_icon": icon_handle,
        "bl_widget": definition.widget,
        "bl_keymap": tuple(keymap_entries) if keymap_entries else None,
        "__module__": __name__,
    }
    if definition.cursor is not None:
        attrs["bl_cursor"] = definition.cursor
    if definition.draw_settings is not None:
        attrs["draw_settings"] = staticmethod(definition.draw_settings)
    class_name = "DGBLOCKS_WST_" + _safe_id_part(concrete_id).upper()
    return type(class_name, (WorkSpaceTool,), attrs)


def register_declared_workspace_tools() -> None:
    """Collect all startup tool declarations and register their concrete placements."""
    logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
    unregister_all_workspace_tools()

    definitions_by_block = Wrapper_Hooks.run_hooked_funcs(
        hook_func_name=Block_Hook_Sources.hook_get_workspace_tool_definitions,
        should_halt_on_exception=False,
    ) or {}
    legacy_definitions_by_block = Wrapper_Hooks.run_hooked_funcs(
        hook_func_name=Block_Hook_Sources.hook_get_modal_workspace_tool_definitions,
        should_halt_on_exception=False,
    ) or {}
    definitions_by_block = {
        block_id: list(block_definitions or [])
        for block_id, block_definitions in definitions_by_block.items()
    }
    for block_id, legacy_definitions in legacy_definitions_by_block.items():
        definitions_by_block.setdefault(block_id, []).extend(legacy_definitions or [])
    definitions = _validate_definitions(definitions_by_block)
    registered = []

    try:
        for block_id, definition in definitions:
            for placement in definition.placements:
                concrete_id = _concrete_tool_id(definition.tool_id, placement)
                fallback_icon = definition.icon or _FALLBACK_TOOL_ICON
                icon_handle = fallback_icon
                if definition.image_icon_name:
                    candidate = _image_icon_handle(definition.tool_id, definition.image_icon_name)
                    if _bind_image_icon(candidate, definition.image_icon_name):
                        icon_handle = candidate
                    else:
                        logger.warning(
                            f"Image '{definition.image_icon_name}' for workspace tool "
                            f"'{definition.tool_id}' is missing; using '{fallback_icon}'"
                        )

                tool_class = _make_tool_class(
                    definition, placement, concrete_id, icon_handle
                )
                bpy.utils.register_tool(
                    tool_class,
                    after=set(definition.after) or None,
                    separator=definition.separator,
                    group=definition.group,
                )
                registered.append(RTC_Workspace_Tool_Instance(
                    src_block_id=block_id,
                    logical_tool_id=definition.tool_id,
                    concrete_tool_id=concrete_id,
                    space_type=placement.space_type,
                    context_mode=placement.context_mode,
                    image_icon_name=definition.image_icon_name,
                    fallback_icon=fallback_icon,
                    icon_handle=icon_handle,
                    actual_tool_class=tool_class,
                ))
    except Exception:
        logger.error("Workspace-tool registration failed; rolling back", exc_info=True)
        for instance in reversed(registered):
            try:
                bpy.utils.unregister_tool(instance.actual_tool_class)
            except Exception:
                pass
            _remove_icon_handle(instance.icon_handle)
        registered = []

    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.WORKSPACE_TOOLS, registered)
    logger.info(f"Registered {len(registered)} workspace-tool placement(s)")


def unregister_all_workspace_tools() -> None:
    """Unregister all concrete tools owned by this block; safe to call repeatedly."""
    instances = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.WORKSPACE_TOOLS) or []
    for instance in reversed(instances):
        try:
            bpy.utils.unregister_tool(instance.actual_tool_class)
        except Exception:
            get_logger(Block_Loggers.MODAL_LIFECYCLE).debug(
                f"Workspace tool '{instance.concrete_tool_id}' was already unregistered"
            )
        _remove_icon_handle(instance.icon_handle)
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.WORKSPACE_TOOLS, [])


def _replace_registered_tool_icon(instance, desired_handle: str) -> None:
    """Replace Blender's immutable ToolDef in its concrete toolbar/mode list."""
    from bl_ui.space_toolsystem_common import ToolSelectPanelHelper

    tool_panel_class = ToolSelectPanelHelper._tool_class_from_space_type(instance.space_type)
    if tool_panel_class is None:
        return
    tools = tool_panel_class._tools[instance.context_mode]
    old_tool_def = instance.actual_tool_class._bl_tool
    new_tool_def = old_tool_def._replace(icon=desired_handle)

    for index, item in enumerate(tools):
        if item is old_tool_def:
            tools[index] = new_tool_def
            break
        if isinstance(item, tuple):
            replaced = tuple(new_tool_def if sub_item is old_tool_def else sub_item for sub_item in item)
            if replaced != item:
                tools[index] = replaced
                break

    instance.actual_tool_class._bl_tool = new_tool_def
    instance.actual_tool_class.bl_icon = desired_handle


def refresh_workspace_tool_icons() -> int:
    """Retry Image-backed icons and return the number now resolved successfully."""
    resolved = 0
    instances = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.WORKSPACE_TOOLS) or []
    for instance in instances:
        desired_handle = instance.fallback_icon
        if instance.image_icon_name:
            candidate = _image_icon_handle(instance.logical_tool_id, instance.image_icon_name)
            if _bind_image_icon(candidate, instance.image_icon_name):
                desired_handle = candidate
                resolved += 1

        old_handle = instance.icon_handle
        instance.icon_handle = desired_handle
        if hasattr(instance.actual_tool_class, "_bl_tool"):
            _replace_registered_tool_icon(instance, desired_handle)
        if old_handle != desired_handle:
            _remove_icon_handle(old_handle)

    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return resolved


def get_registered_logical_tool_ids() -> set[str]:
    instances = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.WORKSPACE_TOOLS) or []
    return {instance.logical_tool_id for instance in instances}


def activate_workspace_tool(logical_tool_id: str, context) -> bool:
    """Activate the concrete placement matching the current editor and mode."""
    area = getattr(context, "area", None)
    if area is None:
        return False
    instances = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.WORKSPACE_TOOLS) or []
    instance = next(
        (
            item for item in instances
            if item.logical_tool_id == logical_tool_id
            and item.space_type == area.type
            and item.context_mode == context.mode
        ),
        None,
    )
    if instance is None:
        return False
    try:
        result = bpy.ops.wm.tool_set_by_id(name=instance.concrete_tool_id)
        return result == {"FINISHED"}
    except Exception:
        get_logger(Block_Loggers.MODAL_LIFECYCLE).error(
            f"Unable to activate workspace tool '{logical_tool_id}'", exc_info=True
        )
        return False


def get_active_logical_tool_id(context) -> str | None:
    """Resolve the active concrete tool in the current placement to its logical tool id."""
    area = getattr(context, "area", None)
    workspace = getattr(context, "workspace", None)
    if area is None or workspace is None:
        return None

    try:
        if area.type == "VIEW_3D":
            active_tool = workspace.tools.from_space_view3d_mode(context.mode, create=False)
        else:
            return None
    except Exception:
        return None

    active_concrete_id = getattr(active_tool, "idname", None)
    if not active_concrete_id:
        return None
    instances = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.WORKSPACE_TOOLS) or []
    return next(
        (
            instance.logical_tool_id
            for instance in instances
            if instance.concrete_tool_id == active_concrete_id
        ),
        None,
    )