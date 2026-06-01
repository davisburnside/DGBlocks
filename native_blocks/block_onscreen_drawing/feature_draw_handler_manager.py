
from collections import defaultdict
from dataclasses import dataclass, field
import time
from typing import Any, Optional
import bpy

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.data_structures import Abstract_BL_RTC_List_Syncronizer, Abstract_Feature_Wrapper, Enum_Sync_Events
from ...addon_helpers.generic_tools import get_exception_last_n_lines

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.loggers.feature_wrapper import get_logger

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .common_constants import Block_Loggers, Block_RTC_Members
from .data_structures import Draw_Space_Types, Draw_Region_Type, Draw_Phase_type, Handler_Def, Handler_Instance, Shader_Instance
from .helpers import callback_omnishader_draw, validate_shader_definitions  # type: ignore

# ==============================================================================================================================
# WRAPPER CLASS
# ==============================================================================================================================

class Wrapper_Draw_Handlers(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer):
    """
    Manages all onscreen-drawing state for the addon.

    Public API:
        set_state(shader_defs)  — declare the full desired set of shaders.
                                  Tears down any existing state first, then
                                  groups defs by (space, region, phase), registers
                                  one Blender draw handler per group, and creates
                                  Shader_Instance objects.
        clear()                 — tear down all live handlers and shaders.
        get_shader(uid)         — return a live Shader_Instance by uid, or None.

    All state is stored in Block_RTC_Members.DRAW_PHASES and
    Block_RTC_Members.SHADERS so the debug panel (and any other block) can
    inspect it.
    """

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation
    # ----------------------------------------------------------

    @classmethod
    def init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Wrapper_Draw_Handlers init — initialising empty RTC state")
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, {})
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, {})
        return True

    @classmethod
    def destroy_wrapper(cls) -> None:
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Wrapper_Draw_Handlers destroy — clearing all handlers")
        cls.clear()

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    @classmethod
    def set_state(cls, shader_defs: list) -> None:
        """
        Declare the complete desired set of shaders.

        All validation runs before any Blender state is mutated, so either the
        full state is applied or nothing changes.

        Args:
            shader_defs: list[Shader_Def] — one entry per logical shader.
        """
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug(f"set_state called with {len(shader_defs)} shader def(s)")

        # ----------------------------------------------------------
        # 1. Validate — all checks before touching Blender state
        # ----------------------------------------------------------
        validate_shader_definitions(shader_defs)

        # ----------------------------------------------------------
        # 2. Tear down existing state
        # ----------------------------------------------------------
        cls.clear()

        # ----------------------------------------------------------
        # 3. Group shader_defs by (space, region, phase) → Handler_Def list
        # ----------------------------------------------------------
        groups: dict = defaultdict(list)  # (space, region, phase) → list[Shader_Def]
        for sdef in shader_defs:
            key = (sdef.space, sdef.region, sdef.phase)
            groups[key].append(sdef)

        handler_defs = [
            Handler_Def(space=key[0], region=key[1], phase=key[2], shaders=sdefs)
            for key, sdefs in groups.items()
        ]
        logger.debug(
            f"Grouped into {len(handler_defs)} handler group(s): "
            + ", ".join(
                f"({hd.space.name}/{hd.region}/{hd.phase}, {len(hd.shaders)} shader(s))"
                for hd in handler_defs
            )
        )

        # ----------------------------------------------------------
        # 4. Build Handler_Instance objects, register Blender handlers,
        #    create Shader_Instance objects, store in RTC
        # ----------------------------------------------------------
        rtc_draw_phases: dict = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)
        rtc_shaders: dict = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)

        for hdef in handler_defs:
            handler_instance = Handler_Instance(
                space=hdef.space,
                region=hdef.region,
                phase=hdef.phase,
            )

            # Create Shader_Instance objects for this handler
            for sdef in hdef.shaders:
                if sdef.custom_shader_class is not None:
                    # Custom shader — instantiate the subclass with any extra kwargs
                    shader_instance = sdef.custom_shader_class(
                        shader_uid=sdef.uid,
                        shader_type=sdef.shader_type,
                        builtin_shader_name=None,
                        shader_group_id=sdef.group_id,
                        **sdef.custom_shader_kwargs,
                    )
                    logger.debug(
                        f"Created custom Shader_Instance uid='{sdef.uid}' "
                        f"(class={sdef.custom_shader_class.__name__}, type={sdef.shader_type})"
                    )
                else:
                    # Builtin shader
                    shader_instance = Shader_Instance(
                        shader_uid=sdef.uid,
                        shader_type=sdef.shader_type,
                        builtin_shader_name=sdef.builtin_shader_name,
                        shader_group_id=sdef.group_id,
                        draw_override_func=sdef.draw_override_func,
                        draw_override_args=sdef.draw_override_args,
                    )
                    logger.debug(
                        f"Created Shader_Instance uid='{sdef.uid}' "
                        f"({sdef.shader_type}/{sdef.builtin_shader_name})"
                        + (f" [draw_override set]" if sdef.draw_override_func is not None else "")
                    )
                handler_instance.shaders.append(shader_instance)
                rtc_shaders[sdef.uid] = shader_instance

            # Register the Blender draw handler
            handler_instance._handle = hdef.space.value.draw_handler_add(
                callback_omnishader_draw,
                (handler_instance,),
                hdef.region.value,
                hdef.phase.value,
            )

            # Key: (space, region, phase) tuple for easy lookup
            rtc_key = (hdef.space, hdef.region, hdef.phase)
            rtc_draw_phases[rtc_key] = handler_instance

            logger.debug(
                f"Registered draw handler for "
                f"({hdef.space.name}, {hdef.region}, {hdef.phase})"
            )

        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, rtc_draw_phases)
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, rtc_shaders)

        logger.debug("set_state complete")

    @classmethod
    def clear(cls) -> None:
        """Tear down all live Blender draw handlers and discard all shaders."""
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)

        rtc_draw_phases: dict = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)
        for rtc_key, handler_instance in rtc_draw_phases.items():
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
        """Return the live Shader_Instance for a given uid, or None."""
        return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS).get(uid)
