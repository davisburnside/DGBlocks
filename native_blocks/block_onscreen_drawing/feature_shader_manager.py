
from collections import defaultdict
import types
from typing import Optional
import bpy

# Addon-level imports
from ...addon_helpers.data_structures import Abstract_BL_RTC_List_Syncronizer, Abstract_Feature_Wrapper, Enum_Sync_Events

# Inter-block imports
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.runtime_cache.data_sync_tools import default_data_mirror_BL_colprop_update_logic, plan_dataclasses_to_match_collectionprop # type: ignore
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks

# Intra-block imports
from .common_constants import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .block_data_structures import Shader_Instance, Drawhandler_Instance
from .helpers import _teardown_draw_handler, _universal_draw_callback
from .BL_gpu_data_structures import _BUILTIN_SHADER_COMPATIBLE_TYPES, _VALID_SPACE_REGION_PHASE_COMBOS 

# ==============================================================================================================================
# WRAPPER CLASS
# ==============================================================================================================================

class Wrapper_Shader_Manager(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer):

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation
    # ----------------------------------------------------------

    @classmethod
    def init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Wrapper_Shader_Manager init")
        cls.clear_all_shaders()
        return True


    @classmethod
    def destroy_wrapper(cls) -> None:
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Wrapper_Shader_Manager destroy — clearing all handlers")
        cls.clear_all_shaders()

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    # ----------------------------------------------------------

    @classmethod
    def rebuild_all_shaders(cls) -> None:
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
        cls.validate_shader_definitions(list_shaders_from_blocks)

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

        # --- Restore user's is_enabled preferences from BL mirror ---
        # cls._apply_bl_is_enabled_from_mirror()

        # cls._sync_shaders_to_bl_mirror()

        # default_data_mirror_BL_colprop_update_logic(
        #     FWC_instance,
        #     data_mirror_instance,
        #     cached_RTC_list,
        #     actions_denied,
        #     logger = None)

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
            drawing_props.shader_mirror_index = 0

        logger.debug("clear complete")


    @classmethod
    def get_shader(cls, uid: str) -> Optional[Shader_Instance]:
        """Return the live Shader_Instance for a given uid, or None if not found."""
        return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS).get(uid)

    # ----------------------------------------------------------
    # Abstract_BL_RTC_List_Syncronizer implementation
    # ----------------------------------------------------------

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls, event, FWC_instance, data_mirror_instance):

        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug(f"update_RTC_with_mirrored_BL_data: event={event}")

        drawing_props = bpy.context.scene.dgblocks_onscreen_drawing_props
        if not bpy.context.scene.dgblocks_onscreen_drawing_props.enable_drawing:
            cls.clear_all_shaders()
            return
        
        key_fields = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
        data_source = drawing_props.shader_mirror
        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)

        if len(actions) > 0:
            cls.rebuild_all_shaders()

        
        # # Collect what downstream blocks currently declare
        # shaders_from_blocks = Wrapper_Hooks.run_hooked_funcs(
        #     hook_func_name=Block_Hook_Sources.hook_get_shader_definitions,
        #     should_halt_on_exception=False,
        # )
        # list_shaders_from_blocks = sum(shaders_from_blocks.values(), [])

        # if cls._shaders_structurally_match_definitions(list_shaders_from_blocks):
        #     logger.debug(
        #         "update_RTC_with_mirrored_BL_data: RTC structure matches BL — "
        #         "restoring is_enabled only (no shader rebuild)"
        #     )
        #     cls._apply_bl_is_enabled_from_mirror()
        # else:
        #     logger.debug(
        #         "update_RTC_with_mirrored_BL_data: RTC structure differs from BL — "
        #         "performing full rebuild"
        #     )
        #     cls.rebuild_all_shaders()


    @classmethod
    def update_BL_with_mirrored_RTC_data(cls, event, FWC_instance, data_mirror_instance):
        """
        Push current RTC SHADERS state into the BL shader_mirror CollectionProperty.
        Delegates to _sync_shaders_to_bl_mirror, which handles add/remove/update of rows
        while preserving the user-owned is_enabled values on existing rows.
        """
        
        
        return
        # logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        # logger.debug(f"update_BL_with_mirrored_RTC_data: event={event}")
        
        # # No action needed during init
        # if event == Enum_Sync_Events.ADDON_INIT:
        #     return
        
        # cls._sync_shaders_to_bl_mirror()

    # ----------------------------------------------------------
    # Private helpers
    # ----------------------------------------------------------

    @classmethod
    def validate_shader_definitions(cls, shader_defs: list) -> None:
        """
        Run all validation checks against a list of Shader_Definition objects.
        Raises ValueError with a descriptive message if any check fails.
        All checks complete before any Blender state is mutated.
        """
        # --- duplicate uid check ---
        seen_uids: set = set()
        for sdef in shader_defs:
            if sdef.shader_uid in seen_uids:
                raise ValueError(
                    f"Duplicate shader uid '{sdef.shader_uid}' in definition_accumulator. "
                    f"Every Shader_Definition must have a unique uid."
                )
            seen_uids.add(sdef.shader_uid)

        # --- (space, region, phase) allowlist check ---
        for sdef in shader_defs:
            combo = (sdef.space, sdef.region, sdef.phase)
            if combo not in _VALID_SPACE_REGION_PHASE_COMBOS:
                raise ValueError(
                    f"Shader '{sdef.shader_uid}': "
                    f"({sdef.space.name}, {sdef.region}, {sdef.phase}) "
                    f"is not a known-valid (space, region, phase) combination. "
                    f"See drawing_constants._VALID_SPACE_REGION_PHASE_COMBOS for the allowlist."
                )

        # --- builtin vs custom mutual-exclusion check ---
        for sdef in shader_defs:
            has_builtin = sdef.builtin_shader_name is not None
            has_custom  = sdef.custom_shader_class is not None
            if has_builtin and has_custom:
                raise ValueError(
                    f"Shader '{sdef.shader_uid}': both builtin_shader_name and custom_shader_class "
                    f"are set. Exactly one must be provided."
                )
            if not has_builtin and not has_custom:
                raise ValueError(
                    f"Shader '{sdef.shader_uid}': neither builtin_shader_name nor custom_shader_class "
                    f"is set. Exactly one must be provided."
                )

        # --- shader_type / builtin_shader_name compatibility check (builtin shaders only) ---
        for sdef in shader_defs:
            if sdef.builtin_shader_name is None:
                continue  # custom shader — no builtin compatibility to check
            allowed_types = _BUILTIN_SHADER_COMPATIBLE_TYPES.get(sdef.builtin_shader_name)
            if allowed_types is None:
                raise ValueError(
                    f"Shader '{sdef.shader_uid}': builtin shader name "
                    f"'{sdef.builtin_shader_name}' is not in the compatibility map. "
                    f"Known names: {list(_BUILTIN_SHADER_COMPATIBLE_TYPES.keys())}"
                )
            if sdef.shader_type not in allowed_types:
                raise ValueError(
                    f"Shader '{sdef.shader_uid}': builtin shader '{sdef.builtin_shader_name}' "
                    f"is not compatible with shader type '{sdef.shader_type}'. "
                    f"Allowed types for this builtin: {sorted(str(t) for t in allowed_types)}"
                )


    @classmethod
    def _shaders_structurally_match_definitions(cls, definitions: list) -> bool:
        """
        Return True if the current RTC SHADERS dict is structurally identical to the
        supplied list of Shader_Definitions — same UIDs in the same order, with the same
        (space, region, phase) per UID.

        Returns False if the RTC is empty when definitions are non-empty, or vice-versa,
        or if any UID, order, or location field differs.
        """
        rtc_shaders: dict = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)

        if len(rtc_shaders) != len(definitions):
            return False

        rtc_items = list(rtc_shaders.items())  # preserves insertion order (Python 3.7+)
        for i, sdef in enumerate(definitions):
            rtc_uid, rtc_shader = rtc_items[i]
            if rtc_uid != sdef.shader_uid:
                return False
            if rtc_shader.draw_space  != sdef.space:
                return False
            if rtc_shader.draw_region != sdef.region:
                return False
            if rtc_shader.draw_phase  != sdef.phase:
                return False

        return True


    @classmethod
    def _apply_bl_is_enabled_from_mirror(cls) -> None:
        """
        Read is_enabled from every BL shader_mirror row and apply to the matching
        live Shader_Instance.  Called at the end of rebuild_all_shaders so that
        user toggle preferences survive undo/redo and full rebuilds.
        Silent no-op if bpy.context or the scene property is unavailable.
        """
        try:
            scene = bpy.context.scene
            if scene is None:
                return
            props = scene.dgblocks_onscreen_drawing_props
        except AttributeError:
            return

        rtc_shaders: dict = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
        for row in props.shader_mirror:
            shader = rtc_shaders.get(row.shader_uid)
            if shader is not None:
                shader.is_enabled = row.is_enabled


    @classmethod
    def _sync_shaders_to_bl_mirror(cls) -> None:
        """
        Update the BL shader_mirror CollectionProperty to match the current live
        SHADERS RTC dict:
          - Adds rows for shaders not yet in the mirror (is_enabled defaults to True).
          - Removes rows for shaders that no longer exist.
          - Updates draw_space/region/phase display fields on existing rows.

        is_enabled on existing rows is intentionally NOT overwritten — the user owns it.
        Guards with flag_cache_as_syncing to suppress _cb_is_enabled_changed during
        the structural mirror update.
        Silent no-op if bpy.context or the scene property is unavailable.
        """
        try:
            scene = bpy.context.scene
            if scene is None:
                return
            props = scene.dgblocks_onscreen_drawing_props
        except AttributeError:
            return

        rtc_shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)

        Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.SHADERS, True)
        try:
            # Index existing rows by uid for O(1) lookup
            existing: dict = {row.shader_uid: i for i, row in enumerate(props.shader_mirror)}

            # Remove rows for shaders no longer alive.
            # Sort descending by index so that removing a high-index row
            # does not shift lower-index rows that are still pending removal.
            uids_to_remove = [uid for uid in existing if uid not in rtc_shaders]
            for uid in sorted(uids_to_remove, key=lambda u: existing[u], reverse=True):
                props.shader_mirror.remove(existing[uid])

            # Re-index after removals
            existing = {row.uid: i for i, row in enumerate(props.shader_mirror)}

            # Add new rows; update display fields on existing rows
            for uid, shader in rtc_shaders.items():
                space_name   = shader.draw_space.name  if shader.draw_space  is not None else ""
                region_str   = str(shader.draw_region) if shader.draw_region is not None else ""
                phase_str    = str(shader.draw_phase)  if shader.draw_phase  is not None else ""

                if uid not in existing:
                    row             = props.shader_mirror.add()
                    row.uid         = uid
                    row.is_enabled  = shader.is_enabled
                    row.draw_space  = space_name
                    row.draw_region = region_str
                    row.draw_phase  = phase_str
                else:
                    row             = props.shader_mirror[existing[uid]]
                    row.draw_space  = space_name
                    row.draw_region = region_str
                    row.draw_phase  = phase_str
                    # is_enabled is NOT touched — user preference is authoritative
        finally:
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.SHADERS, False)
