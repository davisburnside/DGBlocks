
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional
import bpy  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.data_structures import Abstract_Feature_Wrapper

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.loggers.feature_wrapper import get_logger

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .common_constants import Block_Loggers, Block_RTC_Members
from .drawing_constants import (
    Draw_Space_Types,
    Draw_Region_Type,
    Draw_Phase_type,
    Shader_Def,
    Handler_Def,
    _VALID_SPACE_REGION_PHASE_COMBOS,
    _BUILTIN_SHADER_COMPATIBLE_TYPES,
)
from .feature_shader import Shader_Instance


# ==============================================================================================================================
# RUNTIME INSTANCE
# ==============================================================================================================================

@dataclass
class Handler_Instance:
    """
    Owns a single live Blender draw handler and the Shader_Instance objects
    that belong to it.  Responsible for its own full teardown.
    """
    space: Draw_Space_Types
    region: Draw_Region_Type
    phase: Draw_Phase_type
    shaders: list = field(default_factory=list)  # list[Shader_Instance]
    _handle: Any = field(init=False, default=None)

    def teardown(self) -> None:
        """Remove the Blender draw handler and discard all shader references."""
        if self._handle is not None:
            try:
                self.space.value.draw_handler_remove(self._handle, self.region.value)
            except Exception:
                pass  # handler may already be gone (e.g. context teardown)
            self._handle = None
        self.shaders.clear()


# ==============================================================================================================================
# MODULE-LEVEL DRAW CALLBACK
# One function reused for every draw_handler_add call.
# The handler instance is passed via Blender's args tuple.
# No context is used here.
# ==============================================================================================================================

def _draw_callback(handler_instance: Handler_Instance) -> None:
    for shader in handler_instance.shaders:
        shader.draw()


# ==============================================================================================================================
# WRAPPER CLASS
# ==============================================================================================================================

class Wrapper_Draw_Handlers(Abstract_Feature_Wrapper):
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
        cls._validate_shader_defs(shader_defs)

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
                shader_instance = Shader_Instance(
                    shader_uid=sdef.uid,
                    shader_type=sdef.shader_type,
                    builtin_shader_name=sdef.builtin_shader_name,
                    shader_group_id=sdef.group_id,
                )
                handler_instance.shaders.append(shader_instance)
                rtc_shaders[sdef.uid] = shader_instance
                logger.debug(
                    f"Created Shader_Instance uid='{sdef.uid}' "
                    f"({sdef.shader_type}/{sdef.builtin_shader_name})"
                )

            # Register the Blender draw handler
            handler_instance._handle = hdef.space.value.draw_handler_add(
                _draw_callback,
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

    # ----------------------------------------------------------
    # Internal validation helpers
    # ----------------------------------------------------------

    @classmethod
    def _validate_shader_defs(cls, shader_defs: list) -> None:
        """
        Run all validation checks against a list of Shader_Def objects.
        Raises ValueError with a descriptive message if any check fails.
        All checks complete before any Blender state is mutated.
        """
        # --- duplicate uid check ---
        seen_uids: set = set()
        for sdef in shader_defs:
            if sdef.uid in seen_uids:
                raise ValueError(
                    f"Duplicate shader uid '{sdef.uid}' found in set_state call. "
                    f"Every Shader_Def must have a unique uid."
                )
            seen_uids.add(sdef.uid)

        # --- (space, region, phase) allowlist check ---
        for sdef in shader_defs:
            combo = (sdef.space, sdef.region, sdef.phase)
            if combo not in _VALID_SPACE_REGION_PHASE_COMBOS:
                raise ValueError(
                    f"Shader '{sdef.uid}': "
                    f"({sdef.space.name}, {sdef.region}, {sdef.phase}) "
                    f"is not a known-valid (space, region, phase) combination. "
                    f"See drawing_constants._VALID_SPACE_REGION_PHASE_COMBOS for the allowlist."
                )

        # --- shader_type / builtin_shader_name compatibility check ---
        for sdef in shader_defs:
            allowed_types = _BUILTIN_SHADER_COMPATIBLE_TYPES.get(sdef.builtin_shader_name)
            if allowed_types is None:
                raise ValueError(
                    f"Shader '{sdef.uid}': builtin shader name "
                    f"'{sdef.builtin_shader_name}' is not in the compatibility map. "
                    f"Known names: {list(_BUILTIN_SHADER_COMPATIBLE_TYPES.keys())}"
                )
            if sdef.shader_type not in allowed_types:
                raise ValueError(
                    f"Shader '{sdef.uid}': builtin shader '{sdef.builtin_shader_name}' "
                    f"is not compatible with shader type '{sdef.shader_type}'. "
                    f"Allowed types for this builtin: {sorted(str(t) for t in allowed_types)}"
                )
