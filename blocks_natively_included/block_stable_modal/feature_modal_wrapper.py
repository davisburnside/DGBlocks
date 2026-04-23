
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import bpy  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_data_structures import Abstract_Feature_Wrapper

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .._block_core.core_features.feature_runtime_cache import Wrapper_Runtime_Cache
from .._block_core.core_features.feature_hooks import Wrapper_Hooks
from .._block_core.core_features.feature_logs import get_logger
from .._block_core.core_features.feature_block_manager import Wrapper_Block_Management

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .block_constants import (
    Block_Logger_Definitions,
    Block_RTC_Members,
    Block_Hooks,
)

# =============================================================================
# PUBLIC API - Usable by any block
# =============================================================================

# --------------------------------------------------------------
# Instance Definition
# --------------------------------------------------------------
@dataclass
class Modal_Instance_Data:
    """
    Record — instance state only, no manager logic.
    Holds all metadata for the single modal instance.
    Unlike timers, there is only ONE modal for the entire addon.
    """
    is_enabled: bool = True
    is_running: bool = False

    # Runtime stats
    timestamp_ms_last_event: int = 0
    count_restarts: int = 0
    
    # Area tracking for area change events
    last_area: Optional[bpy.types.Area] = None

    # Private: actual bpy modal operator instance reference
    _operator_ref: Optional[Any] = field(default=None, init=False, repr=False)

# --------------------------------------------------------------
# Main wrapper for feature
# --------------------------------------------------------------
class Modal_Wrapper(Abstract_Feature_Wrapper):
    """
    Manager — classmethods only, no instance state.
    Manages the Blender modal operator with metadata tracking and hook propagation.
    There is only one modal instance, stored in a single RTC member.
    Scene properties are the source of truth for modal configuration; RTC is rebuilt from them.
    """

    # ------------------------------------------------------------------
    # Abstract_Feature_Wrapper implementations
    # ------------------------------------------------------------------

    @classmethod
    def create_instance(
        cls,
        is_enabled: bool = True,
    ) -> bool:
        """
        Create the modal instance data record.

        Returns:
            True if created successfully, False if instance already exists.
        """
        logger = get_logger(Block_Logger_Definitions.MODAL_LIFECYCLE)

        existing_data = Wrapper_Runtime_Cache.get_instance(Block_RTC_Members.MODAL_INSTANCE)
        if existing_data is not None:
            logger.warning("Modal instance already exists — use set_instance to update it")
            return False

        data = Modal_Instance_Data(is_enabled=is_enabled)
        Wrapper_Runtime_Cache.set_instance(Block_RTC_Members.MODAL_INSTANCE, data)

        logger.info(f"Created modal instance (enabled={is_enabled})")
        return True

    @classmethod
    def get_instance(cls) -> Optional[Modal_Instance_Data]:
        """
        Return the Modal_Instance_Data, or None if not found.
        """
        return Wrapper_Runtime_Cache.get_instance(Block_RTC_Members.MODAL_INSTANCE)

    @classmethod
    def set_instance(
        cls,
        is_enabled: Optional[bool] = None,
    ) -> bool:
        """
        Update the modal's enabled state.
        Starts or stops the modal as needed.

        Returns:
            True if updated, False if the modal does not exist.
        """
        logger = get_logger(Block_Logger_Definitions.MODAL_LIFECYCLE)

        data = Wrapper_Runtime_Cache.get_instance(Block_RTC_Members.MODAL_INSTANCE)
        if data is None:
            logger.warning("Modal instance does not exist — use create_instance first")
            return False

        needs_restart = False

        if is_enabled is not None and is_enabled != data.is_enabled:
            logger.debug(f"Modal: enabled {data.is_enabled} → {is_enabled}")
            data.is_enabled = is_enabled
            needs_restart = True

        if needs_restart:
            if data.is_running:
                cls._stop_modal_operator(data)
            if data.is_enabled:
                cls._start_modal_operator()

        Wrapper_Runtime_Cache.set_instance(Block_RTC_Members.MODAL_INSTANCE, data)
        return True

    @classmethod
    def destroy_instance(cls) -> bool:
        """
        Stop and remove the modal entirely.

        Returns:
            True if removed, False if not found.
        """
        logger = get_logger(Block_Logger_Definitions.MODAL_LIFECYCLE)

        data = Wrapper_Runtime_Cache.get_instance(Block_RTC_Members.MODAL_INSTANCE)
        if data is None:
            logger.warning("Modal instance not found — nothing to destroy")
            return False

        cls._stop_modal_operator(data)
        Wrapper_Runtime_Cache.set_instance(Block_RTC_Members.MODAL_INSTANCE, data)

        logger.info("Destroyed modal instance")
        return True

    @classmethod
    def init_pre_bpy(cls) -> bool:
        """Called during register() before bpy is fully available."""
        return True

    @classmethod
    def init_post_bpy(cls) -> bool:
        """Called during register() before bpy is fully available."""
        return True

    @classmethod
    def destroy_wrapper(cls) -> bool:
        """
        Stop the modal and clear the RTC member.
        Called during unregister().
        """
        logger = get_logger(Block_Logger_Definitions.MODAL_LIFECYCLE)
        logger.debug("Modal_Wrapper.destroy_wrapper: stopping modal")

        data = Wrapper_Runtime_Cache.get_instance(Block_RTC_Members.MODAL_INSTANCE)
        if data is not None:
            cls._stop_modal_operator(data)

        Wrapper_Runtime_Cache.set_instance(Block_RTC_Members.MODAL_INSTANCE, None)
        logger.info("Modal_Wrapper.destroy_wrapper: done")
        return True

    # ------------------------------------------------------------------
    # Public convenience methods
    # ------------------------------------------------------------------

    @classmethod
    def start_modal(cls, context) -> bool:
        """Start the modal operator. No-op if already running."""
        data = Wrapper_Runtime_Cache.get_instance(Block_RTC_Members.MODAL_INSTANCE)
        if data is None:
            return False
        
        if data.is_running:
            return True  # Already running
            
        return cls._start_modal_operator()

    @classmethod
    def stop_modal(cls, context) -> bool:
        """Stop the modal operator. No-op if not running."""
        data = Wrapper_Runtime_Cache.get_instance(Block_RTC_Members.MODAL_INSTANCE)
        if data is None:
            return False
            
        if not data.is_running:
            return True  # Already stopped
            
        return cls._stop_modal_operator(data)
