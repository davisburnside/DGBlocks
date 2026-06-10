
from collections import defaultdict
import types
from typing import Optional
import bpy

# Addon-level imports
from ...addon_helpers.data_structures import Abstract_BL_RTC_List_Syncronizer, Abstract_Feature_Wrapper, Abstract_Shared_UIList_Draw, Enum_Sync_Events

# Inter-block imports
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.runtime_cache import data_sync_tools
from ..block_core.core_features.runtime_cache.data_sync_tools import plan_dataclasses_to_match_collectionprop
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks

# Intra-block imports
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .helpers import _teardown_draw_handler, _uilist_draw_selection_details, _universal_draw_callback, validate_shader_definitions
from .data_structures import Shader_Instance, Drawhandler_Instance

# Aliases
cache_key_shaders = Block_RTC_Members.SHADERS

# ==============================================================================================================================
# WRAPPER CLASS
# ==============================================================================================================================

class Wrapper_Shader_Manager(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Shared_UIList_Draw):

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation
    # ----------------------------------------------------------

    @classmethod
    def init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Wrapper_Shader_Manager init")

        # Setup UIList for Debug Panel
        # set_shared_uilist_config(
        #     list_id="BLOCKS_LIST",
        #     col_names=("Enabled", "Shader UID", "Draw-Phase/Region/Space"),
        #     col_widths=(1, 3, 3),
        #     # columns_def=[
        #     #     {"type": "ICON", "field": "is_enabled", "icon_true": "HIDE_OFF", "icon_false": "HIDE_ON"},
        #     #     {"type": "LABEL", "field": "shader_uid"},
        #     #     {"type": "RAW_TEXT", "field": "shader_uid"},
        #     # ],
        #     row_func = t1,
        #     details_func=_uilist_draw_selection_details
        # )

        # The initial pass only exists in the RTC. BL data is not overwritten yet
        event = Enum_Sync_Events.ADDON_INIT
        cls.rebuild_all_shaders(event, sync_BL = False)
        return True


    @classmethod
    def destroy_wrapper(cls) -> None:
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Wrapper_Shader_Manager destroy — clearing all handlers")
        cls.clear_all_shaders()

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    @classmethod
    def rebuild_all_shaders(cls, event: Enum_Sync_Events, sync_BL = True) -> None:
        """
        Full rebuild cycle:
          1. Clear existing draw handlers and shader instances.
          2. Fire hook_get_shader_definitions — downstream blocks return Shader_Definition
             objects.
          3. Validate all collected definitions (uid uniqueness, valid space/region/phase
             combos, builtin-vs-custom exclusivity, shader type compatibility).
          4. Group by (space, region, phase), create Shader_Instances, register one Blender
             draw handler per group.
          5. Restore is_enabled from the BL shader_mirror (user preferences survive rebuilds
             and undo/redo).
          6. Sync BL shader_mirror rows to reflect the current live shader set.
          7. Fire hook_before_first_draw — downstream blocks push initial geometry here.
        """
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Rebuilding all Shaders")

        cls.clear_all_shaders()

        # Collect Shader_Definitions from all downstream blocks
        shaders_from_blocks = Wrapper_Hooks.run_hooked_funcs(
            hook_func_name=Block_Hook_Sources.hook_get_shader_definitions,
            should_halt_on_exception=False,
        )
        list_shaders_from_blocks = sum(shaders_from_blocks.values(), [])
        if len(list_shaders_from_blocks) == 0:
            logger.info("No Shaders to draw, returning early")
            return
        validate_shader_definitions(list_shaders_from_blocks)

        # Group definitions by (space, region, phase)
        groups: dict = defaultdict(list)
        for sdef in list_shaders_from_blocks:
            key = (sdef.space, sdef.region, sdef.phase)
            groups[key].append(sdef)

        # --- Build Shader_Instances and register draw handlers ---
        rtc_draw_phases = []
        rtc_shaders = []
        for (space, region, phase), sdefs in groups.items():
            handler_instance = Drawhandler_Instance(space=space, region=region, phase=phase)
            for sdef in sdefs:
                if sdef.custom_shader_class is not None:
                    shader_instance = sdef.custom_shader_class(
                        shader_uid=sdef.shader_uid,
                        shader_type=sdef.shader_type,
                        builtin_shader_name=None,
                        draw_space=sdef.space,
                        draw_region=sdef.region,
                        draw_phase=sdef.phase,
                        **sdef.custom_shader_kwargs,
                    )
                    logger.debug(
                        f"Created custom Shader_Instance uid='{sdef.shader_uid}' "
                        f"(class={sdef.custom_shader_class.__name__}, type={sdef.shader_type})"
                    )
                else:
                    shader_instance = Shader_Instance(
                        shader_uid=sdef.shader_uid,
                        shader_type=sdef.shader_type,
                        builtin_shader_name=sdef.builtin_shader_name,
                        draw_space=sdef.space,
                        draw_region=sdef.region,
                        draw_phase=sdef.phase,
                    )

                    # Monkeypatch optional before/after draw callbacks
                    if sdef.builtin_shader_before_draw is not None:
                        shader_instance._builtin_shader_before_draw = types.MethodType(
                            sdef.builtin_shader_before_draw, shader_instance
                        )
                    if sdef.builtin_shader_after_draw is not None:
                        shader_instance._builtin_shader_after_draw = types.MethodType(
                            sdef.builtin_shader_after_draw, shader_instance
                        )
                    logger.debug(
                        f"Created builtin Shader_Instance uid='{sdef.shader_uid}' "
                        f"({sdef.shader_type}/{sdef.builtin_shader_name})"
                    )

                shader_instance._shader_init()
                handler_instance.shader_names.append(sdef.shader_uid)
                rtc_shaders.append(shader_instance)

            # Register one Blender draw handler for this (space, region, phase) group
            handler_instance._handle = space.value.draw_handler_add(
                _universal_draw_callback,
                (handler_instance,),
                region.value,
                phase.value,
            )
            rtc_draw_phases.append(handler_instance)
            logger.debug(f"Registered draw handler for ({space.name}, {region}, {phase})")

        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, rtc_draw_phases)
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, rtc_shaders)
        
        if sync_BL:
            FWC_instance, data_mirror_instance = Wrapper_Runtime_Cache.get_FWC_and_data_mirror(cache_key_shaders)
            cls.update_BL_with_mirrored_RTC_data(event, FWC_instance, data_mirror_instance)

        DH_count = len(Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES))
        logger.info(f"Created {len(list_shaders_from_blocks)} Shaders across {DH_count} Draw Handlers")

        # Notify downstream blocks before the first draw. Blocks can populate Shader Instrance's points/colors arrays from this hook
        Wrapper_Hooks.run_hooked_funcs(
            hook_func_name=Block_Hook_Sources.hook_before_first_draw,
            should_halt_on_exception=False,
        )


    @classmethod
    def clear_all_shaders(cls, include_BL_data = True) -> None:

        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)

        rtc_draw_phases = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)
        for handler_instance in rtc_draw_phases:
            _teardown_draw_handler(handler_instance)
            logger.debug(
                f"Torn down handler for ({handler_instance.space.name}, "
                f"{handler_instance.region}, {handler_instance.phase})"
            )

        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, [])
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, [])

        if include_BL_data:
            drawing_props = bpy.context.scene.dgblocks_onscreen_drawing_props
            # drawing_props.enable_drawing = False
            drawing_props.shader_mirror.clear()
            drawing_props.shader_mirror_selected_idx = 0

        logger.debug("clear complete")


    @classmethod
    def get_shader(cls, uid: str) -> Optional[Shader_Instance]:
        """Return the live Shader_Instance for a given uid, or None if not found."""
        _, shader, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(Block_RTC_Members.SHADERS, "shader_uid", uid)
        return shader

    # ----------------------------------------------------------
    # Abstract_BL_RTC_List_Syncronizer implementation
    # ----------------------------------------------------------

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls, event, FWC_instance, data_mirror_instance):

        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        drawing_props = bpy.context.scene.dgblocks_onscreen_drawing_props
        if event == Enum_Sync_Events.ADDON_INIT:
            return
        if not drawing_props.enable_drawing:
            cls.clear_all_shaders()
            return
        
        key_fields = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
        data_source = drawing_props.shader_mirror
        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        filtered_actions = [a for a in actions if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove}]
        logger.debug(f"BL: {len(data_source)} items | RTC: {len(data_target)} items. | {len(filtered_actions)} Actions")

        # sync_BL = event != Enum_Sync_Events.ADDON_INIT
        if len(filtered_actions) > 0:
            sync_BL = event in {Enum_Sync_Events.PROPERTY_UPDATE_REDO, Enum_Sync_Events.PROPERTY_UPDATE_UNDO, Enum_Sync_Events.PROPERTY_UPDATE}
            cls.rebuild_all_shaders(event, sync_BL)

        # Toggle is_enabled for each row marked for edit. is_enabled is the only UI-editable property of shaders
        edit_actions = [a for a in actions if a.__class__ == data_sync_tools.Edit]
        for action in edit_actions:
            shader_instance = data_target[action.source_idx]
            shader_instance.is_enabled = not shader_instance.is_enabled
        

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls, event, FWC_instance, data_mirror_instance):
        
        # This function assumes that rebuild_all_shaders() has been already executed after the RTC update event
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        drawing_props = bpy.context.scene.dgblocks_onscreen_drawing_props
        cached_shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)

        key_fields = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
        data_source = drawing_props.shader_mirror
        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        filtered_actions = [a for a in actions if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove, data_sync_tools.Move}]
        if len(filtered_actions) > 0:
            Wrapper_Runtime_Cache.assert_cache_is_not_syncing(Block_RTC_Members.SHADERS)
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.SHADERS, True)
            try:

                # Clear & Repopulate CollectionProperty
                drawing_props.shader_mirror.clear()
                for shader_instance in cached_shaders:
                    space_name = shader_instance.draw_space.name
                    region_str = str(shader_instance.draw_region)
                    phase_str = str(shader_instance.draw_phase)
                    BL_shader = drawing_props.shader_mirror.add()
                    BL_shader.shader_uid = shader_instance.shader_uid
                    BL_shader.is_enabled = shader_instance.is_enabled
                    BL_shader.draw_space = space_name
                    BL_shader.draw_region = region_str
                    BL_shader.draw_phase = phase_str

            finally:
                Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.SHADERS, False)

    # ----------------------------------------------------------
    # Abstract_Shared_UIList_Draw implementation
    # ----------------------------------------------------------

    @classmethod
    def shared_uilist_draw_row(cls, context, container, BL_ColProp_item, RTC_list_item, idx):
        pass

    @classmethod
    def shared_uilist_draw_details_footer(cls, context, container, BL_ColProp_item, RTC_list_item, idx):
        pass
