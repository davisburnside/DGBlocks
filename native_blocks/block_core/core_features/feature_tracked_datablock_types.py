# Sample License, ignore for now

# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

from dataclasses import dataclass
from enum import Enum
import bpy

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helpers.data_structures import Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager, Enum_Sync_Events

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .feature_logs import get_logger
from ..core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members, Core_Block_Tracked_Datablock_Types
from .feature_runtime_cache import Wrapper_Runtime_Cache

# --------------------------------------------------------------
# Aliases
# --------------------------------------------------------------
cache_key_tracked_types = Core_Runtime_Cache_Members.REGISTRY_ALL_TRACKED_DATABLOCK_TYPES

# ==============================================================================================================================
# RTC DATA (no BL mirror)
# ==============================================================================================================================

@dataclass
class RTC_Tracked_Datablock_Type_Instance:
    # Record — instance state only, no manager logic
    # Each instance represents a datablock type that is actively being tracked

    type_name: str            # e.g. "OBJECT", matches depsgraph.id_type_updated name
    collection_name: str      # e.g. "objects", bpy.data.<collection_name>
    bpy_type_class: type      # e.g. bpy.types.Object
    listener_count: int       # how many blocks want this type tracked (ref-count)

# ==============================================================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS
# ==============================================================================================================================

class Wrapper_Tracked_Datablock_Types(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager):
    """
    Ref-counted registry of which datablock types are actively being monitored.
    Downstream blocks call create_instance / destroy_instance to enable / disable
    tracking for specific datablock types.

    The scene monitor (in feature_block_manager.py) reads this registry to know
    what to diff in the depsgraph callback.
    """

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls, event: Enum_Sync_Events) -> bool:
        return True

    @classmethod
    def init_post_bpy(cls, event: Enum_Sync_Events) -> bool:
        return True

    @classmethod
    def destroy_wrapper(cls, event: Enum_Sync_Events) -> bool:
        """Clear all tracked types on shutdown."""
        Wrapper_Runtime_Cache.set_cache(cache_key_tracked_types, [])
        return True

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_instance(
        cls,
        event: Enum_Sync_Events,
        datablock_type_enum: Enum,
    ):
        """
        Enable tracking for a datablock type. If already tracked, increment ref-count.

        Args:
            event: The sync event triggering this creation.
            datablock_type_enum: A member of Core_Block_Tracked_Datablock_Types.
        """
        logger = get_logger(Core_Block_Loggers.TRACKED_DATABLOCK_TYPES)

        type_name = datablock_type_enum.value[0]
        collection_name = datablock_type_enum.value[1]
        bpy_type_class = datablock_type_enum.value[2]

        cached_types = Wrapper_Runtime_Cache.get_cache(cache_key_tracked_types)

        # Check if already tracked — if so, just increment ref-count
        idx, existing_instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            member_key=cache_key_tracked_types,
            uniqueness_field="type_name",
            uniqueness_field_value=type_name,
        )
        if existing_instance is not None:
            existing_instance.listener_count += 1
            Wrapper_Runtime_Cache.set_cache(cache_key_tracked_types, cached_types)
            logger.debug(f"Incremented listener_count for '{type_name}' to {existing_instance.listener_count}")
            return

        # Create new tracked type instance
        new_instance = RTC_Tracked_Datablock_Type_Instance(
            type_name=type_name,
            collection_name=collection_name,
            bpy_type_class=bpy_type_class,
            listener_count=1,
        )
        cached_types.append(new_instance)
        Wrapper_Runtime_Cache.set_cache(cache_key_tracked_types, cached_types)
        logger.debug(f"Started tracking datablock type '{type_name}' (listener_count=1)")

    @classmethod
    def destroy_instance(
        cls,
        event: Enum_Sync_Events,
        datablock_type_enum: Enum,
    ):
        """
        Disable tracking for a datablock type. Decrements ref-count; removes at 0.

        Args:
            event: The sync event triggering this destruction.
            datablock_type_enum: A member of Core_Block_Tracked_Datablock_Types.
        """
        logger = get_logger(Core_Block_Loggers.TRACKED_DATABLOCK_TYPES)

        type_name = datablock_type_enum.value[0]

        cached_types = Wrapper_Runtime_Cache.get_cache(cache_key_tracked_types)

        idx, existing_instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            member_key=cache_key_tracked_types,
            uniqueness_field="type_name",
            uniqueness_field_value=type_name,
        )
        if existing_instance is None:
            logger.debug(f"'{type_name}' is not tracked, nothing to destroy")
            return

        existing_instance.listener_count -= 1
        if existing_instance.listener_count <= 0:
            del cached_types[idx]
            Wrapper_Runtime_Cache.set_cache(cache_key_tracked_types, cached_types)
            logger.debug(f"Stopped tracking datablock type '{type_name}' (listener_count reached 0)")
        else:
            Wrapper_Runtime_Cache.set_cache(cache_key_tracked_types, cached_types)
            logger.debug(f"Decremented listener_count for '{type_name}' to {existing_instance.listener_count}")

    # --------------------------------------------------------------
    # Public funcs specific to this class
    # --------------------------------------------------------------

    @classmethod
    def get_tracked_type_instances(cls) -> list[RTC_Tracked_Datablock_Type_Instance]:
        """Return all currently active tracked datablock type instances."""
        return Wrapper_Runtime_Cache.get_cache(cache_key_tracked_types, should_copy=True)

    @classmethod
    def is_type_tracked(cls, type_name: str) -> bool:
        """Check if a specific datablock type is currently being tracked."""
        cached_types = Wrapper_Runtime_Cache.get_cache(cache_key_tracked_types)
        return any(t.type_name == type_name for t in cached_types)
    
# ==============================================================================================================================
# UI
# ==============================================================================================================================

col_names = ("Datablock", "Count", "Blocks Using")
col_widths = (2, 1, 3)
def _uilayout_draw_logger_settings(context, container):

    core_props = context.scene.dgblocks_core_props
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_scene_loggers", default_closed=True)
    panel_header.label(text = f"All Loggers ({len(context.scene.dgblocks_core_props.managed_loggers)})")
    if panel_body is not None:    

        # Draw column titles
        # ui_draw_list_headers(panel_body, col_names, col_widths)

        # Draw UIList body
        row = panel_body.row()
        row_count = len(core_props.managed_loggers)
        row.template_list(
            "DGBLOCKS_UL_Tracked_Datablocks",
            "",
            core_props, "managed_loggers", # Collection property
            core_props, "managed_loggers_selected_idx", # Active index property
            rows = row_count,
            maxrows = row_count,
            columns = row_count, 
        )

class DGBLOCKS_UL_Tracked_Datablocks(bpy.types.UIList):
    """UIList to display RTC blocks with enable toggle and alert states."""
    
    def draw_item(self, context, container, data, item, icon, active_data, active_propname, index):
       
        row = container.row(align=True)
        sub = row.row()
        sub.ui_units_x = col_widths[0]
        sub.label(text=item.src_block_id)
        sub = row.row()
        sub.ui_units_x = col_widths[1]
        sub.label(text=item.logger_name)
        sub = row.row()
        sub.ui_units_x = col_widths[2]
        sub.prop(item, "level_name", text = "")
        