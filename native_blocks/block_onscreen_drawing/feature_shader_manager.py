
from typing import Optional
import bpy

# Addon-level imports
from ...addon_helpers.data_structures import Abstract_BL_RTC_List_Syncronizer, Abstract_Feature_Wrapper, Abstract_Shared_UIList_Draw, Enum_Sync_Events

# Inter-block imports
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.runtime_cache import data_sync_tools
from ..block_core.core_features.runtime_cache.data_sync_tools import plan_dataclasses_to_match_collectionprop
from ..block_core.core_features.loggers.feature_wrapper import get_logger

# Intra-block imports
from .builtin_shaders_and_effects.demo_props import ensure_demo_rows
from .common_declarations import  Block_Loggers, Block_RTC_Members
from .helpers import _clear_all_shaders, _rebuild_all_shaders
from .data_structures import Shader_Instance

class Wrapper_Shader_Manager(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Shared_UIList_Draw):

    # ----------------------------------------------------------
    # Public API

    @classmethod
    def repoll(cls, event):
        """
        Re-poll all downstream blocks for their Shader_Declarations and reconcile the live
        shader set against them, REUSING existing Shader_Instance objects where possible
        (their GPU batch, uniforms, is_enabled state and animations survive the repoll).

        Safe to call whether or not drawing is already enabled — unlike the old behaviour
        of merely setting enable_drawing=True (a no-op when it was already True), this always
        performs the reconcile so a downstream block whose declarations changed is honoured.
        """
        props = bpy.context.scene.dgblocks_onscreen_drawing_props
        if not props.enable_drawing:
            # Flipping the master toggle fires _cb_enable_drawing_changed, which reconciles.
            props.enable_drawing = True
        else:
            _rebuild_all_shaders(event)


    @classmethod
    def disable_shaders(cls):
       bpy.context.scene.dgblocks_onscreen_drawing_props.enable_drawing = False


    @classmethod
    def get_shader(cls, uid: str) -> Optional[Shader_Instance]:
        """Return the live Shader_Instance for a given uid, or None if not found."""
        _, shader, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(Block_RTC_Members.SHADERS, "shader_uid", uid)
        return shader
    
    @classmethod
    def get_all_shaders(cls, active_only:bool = False) -> list[Shader_Instance]:
        shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
        if active_only:
            shaders = [s for s in shaders if s.is_enabled]
        return shaders

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Wrapper_Shader_Manager init")
        return True


    @classmethod
    def _remove_wrapper(cls) -> None:
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Wrapper_Shader_Manager destroy — clearing all handlers")
        _clear_all_shaders()

    # ----------------------------------------------------------
    # Abstract_BL_RTC_List_Syncronizer implementation

    @classmethod
    def _update_RTC_with_mirrored_BL_data(cls, event, FWC_instance, data_mirror_instance):
        """
        BL -> RTC direction. Called on undo/redo (and addon init) via the data-mirror system.

        The BL shader_mirror carries only a uid key plus display-only fields; is_enabled is
        RTC-only now, so the planner can never emit an Edit — only Create/Remove/Move/Noop.

        - Structural change (Create/Remove): the desired shader set differs, so re-poll the
          hooks and reconcile. Reuse keeps surviving instances (and their is_enabled and
          animation state) intact.
        - Reorder only (Move): reorder the RTC list in place — no GPU work.
        - No change (Noop only): nothing to do.
        """
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        drawing_props = bpy.context.scene.dgblocks_onscreen_drawing_props
        if event == Enum_Sync_Events.ADDON_INIT:
            return
        if not drawing_props.enable_drawing:
            _clear_all_shaders()
            return

        key_fields = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS) or []
        data_source = drawing_props.shader_mirror
        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        structural_actions = [a for a in actions if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove}]
        move_actions = [a for a in actions if a.__class__ == data_sync_tools.Move]
        logger.debug(
            f"BL: {len(data_source)} items | RTC: {len(data_target)} items | "
            f"{len(structural_actions)} structural, {len(move_actions)} move"
        )

        if structural_actions:
            # Re-poll hooks + reconcile (reuses instances). This also re-pushes the BL mirror.
            sync_BL = event in {
                Enum_Sync_Events.PROPERTY_UPDATE_REDO,
                Enum_Sync_Events.PROPERTY_UPDATE_UNDO,
                Enum_Sync_Events.PROPERTY_UPDATE,
            }
            _rebuild_all_shaders(event, sync_BL)
            return

        # Reorder-only: match the RTC list order to the BL mirror without touching the GPU.
        if move_actions:
            for action in move_actions:
                item = data_target.pop(action.from_idx)
                data_target.insert(action.to_idx, item)
            Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, data_target)

    @classmethod
    def _update_BL_with_mirrored_RTC_data(cls, event, FWC_instance, data_mirror_instance):
        """
        RTC -> BL direction. Rebuilds the shader_mirror CollectionProperty from the live RTC
        shader list. BL holds only the uid key and display-only fields (space/region/phase);
        it is never a source of truth for is_enabled, which lives solely on the RTC instance.
        Assumes _rebuild_all_shaders() has already produced the RTC set for this event.
        """
        drawing_props = bpy.context.scene.dgblocks_onscreen_drawing_props
        cached_shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS) or []

        Wrapper_Runtime_Cache.assert_cache_is_not_syncing(Block_RTC_Members.SHADERS)
        Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.SHADERS, True)
        try:
            # Clear & repopulate the CollectionProperty to mirror the live shader set/order.
            drawing_props.shader_mirror.clear()
            for shader_instance in cached_shaders:
                BL_shader = drawing_props.shader_mirror.add()
                BL_shader.shader_uid = shader_instance.shader_uid
                BL_shader.draw_space = shader_instance.draw_space.name
                BL_shader.draw_region = str(shader_instance.draw_region)
                BL_shader.draw_phase = str(shader_instance.draw_phase)
        finally:
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.SHADERS, False)
