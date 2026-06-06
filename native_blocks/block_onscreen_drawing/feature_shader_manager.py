
from collections import defaultdict
import types
from typing import Optional
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.data_structures import Abstract_Feature_Wrapper
# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .common_constants import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .block_data_structures import Shader_Instance, Drawhandler_Instance
from .helpers import callback_omnishader_draw, validate_shader_definitions

# ==============================================================================================================================
# WRAPPER CLASS
# ==============================================================================================================================

class Wrapper_Shader_Manager(Abstract_Feature_Wrapper):
    """
    Manages all onscreen-drawing state for the addon.

    Primary concern: a live registry of Shader_Instance objects.
    Draw handlers are internal plumbing — created and destroyed as needed
    to deliver the shaders declared by downstream blocks.

    Public API:
        rebuild_all_shaders()  — fires hook_get_shader_definitions to collect Shader_Definition
                                  objects from all registered downstream blocks, tears down
                                  existing state, creates Shader_Instances and draw handlers,
                                  restores is_enabled from the BL mirror, then fires
                                  hook_before_first_draw so downstream blocks can push geometry.
        clear_all_shaders()                — tear down all live handlers and shaders.
        get_shader(uid)        — return a live Shader_Instance by uid, or None.

    All shader state is stored in Block_RTC_Members.SHADERS.
    Draw handler bookkeeping lives in Block_RTC_Members.DRAW_PHASES.
    """

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation
    # ----------------------------------------------------------

    @classmethod
    def init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Wrapper_Shader_Manager init — initialising empty RTC state")
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, {})
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, {})
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
    def rebuild_all_shaders(cls) -> None:
        """
        Full rebuild cycle:
          1. Clear existing draw handlers and shader instances.
          2. Fire hook_get_shader_definitions — downstream blocks append Shader_Definition
             objects to the shared definition_accumulator list.
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
        logger.debug("rebuild_all_shaders: starting")

        cls.clear_all_shaders()

        # --- Collect Shader_Definitions from all downstream blocks ---
        definition_accumulator = []
        Wrapper_Hooks.run_hooked_funcs(
            hook_func_name=Block_Hook_Sources.hook_get_shader_definitions,
            should_halt_on_exception=False,
            definition_accumulator=definition_accumulator,
        )

        if not definition_accumulator:
            logger.debug("rebuild_all_shaders: no shader definitions collected — done")
            return

        # --- Validate all definitions before touching Blender state ---
        validate_shader_definitions(definition_accumulator)

        # --- Group definitions by (space, region, phase) ---
        groups: dict = defaultdict(list)
        for sdef in definition_accumulator:
            key = (sdef.space, sdef.region, sdef.phase)
            groups[key].append(sdef)

        logger.debug(
            f"rebuild_all_shaders: {len(definition_accumulator)} shader(s) across "
            f"{len(groups)} draw handler group(s)"
        )

        # --- Build Shader_Instances and register draw handlers ---
        rtc_draw_phases: dict = {}
        rtc_shaders: dict = {}

        for (space, region, phase), sdefs in groups.items():
            handler_instance = Drawhandler_Instance(space=space, region=region, phase=phase)

            for sdef in sdefs:
                if sdef.custom_shader_class is not None:
                    shader_instance = sdef.custom_shader_class(
                        shader_uid=sdef.uid,
                        shader_type=sdef.shader_type,
                        builtin_shader_name=None,
                        draw_space=sdef.space,
                        draw_region=sdef.region,
                        draw_phase=sdef.phase,
                        **sdef.custom_shader_kwargs,
                    )
                    logger.debug(
                        f"Created custom Shader_Instance uid='{sdef.uid}' "
                        f"(class={sdef.custom_shader_class.__name__}, type={sdef.shader_type})"
                    )
                else:
                    shader_instance = Shader_Instance(
                        shader_uid=sdef.uid,
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
                        f"Created builtin Shader_Instance uid='{sdef.uid}' "
                        f"({sdef.shader_type}/{sdef.builtin_shader_name})"
                    )

                shader_instance._shader_init()
                handler_instance.shaders.append(shader_instance)
                rtc_shaders[sdef.uid] = shader_instance

            # Register one Blender draw handler for this (space, region, phase) group
            handler_instance._handle = space.value.draw_handler_add(
                callback_omnishader_draw,
                (handler_instance,),
                region.value,
                phase.value,
            )
            rtc_draw_phases[(space, region, phase)] = handler_instance
            logger.debug(f"Registered draw handler for ({space.name}, {region}, {phase})")

        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, rtc_draw_phases)
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, rtc_shaders)

        # --- Restore user's is_enabled preferences from BL mirror ---
        cls._apply_bl_is_enabled_from_mirror()

        # --- Sync BL mirror rows to match the new live shader set ---
        cls._sync_shaders_to_bl_mirror()

        # --- Notify downstream blocks: push initial geometry now ---
        Wrapper_Hooks.run_hooked_funcs(
            hook_func_name=Block_Hook_Sources.hook_before_first_draw,
            should_halt_on_exception=False,
        )

        logger.debug("rebuild_all_shaders: complete")

    @classmethod
    def clear_all_shaders(cls) -> None:
        """Tear down all live Blender draw handlers and discard all shader instances.
        Does NOT modify the BL shader_mirror — user preferences are preserved."""
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)

        rtc_draw_phases: dict = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)
        for _key, handler_instance in rtc_draw_phases.items():
            handler_instance.teardown()
            logger.debug(
                f"Torn down handler for ({handler_instance.space.name}, "
                f"{handler_instance.region}, {handler_instance.phase})"
            )

        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, {})
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, {})
        logger.debug("clear complete")

    @classmethod
    def get_shader(cls, uid: str) -> Optional[Shader_Instance]:
        """Return the live Shader_Instance for a given uid, or None if not found."""
        return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS).get(uid)

    # ----------------------------------------------------------
    # Private helpers
    # ----------------------------------------------------------

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
            shader = rtc_shaders.get(row.uid)
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

        rtc_shaders: dict = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)

        Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.SHADERS, True)
        try:
            # Index existing rows by uid for O(1) lookup
            existing: dict = {row.uid: i for i, row in enumerate(props.shader_mirror)}

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
