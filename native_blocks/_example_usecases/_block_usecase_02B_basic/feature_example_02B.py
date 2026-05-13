import bpy # type: ignore
from dataclasses import dataclass

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helpers.data_structures import  Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Datawrapper_Instance_Manager, Enum_Sync_Actions, Enum_Sync_Events, RTC_FWC_Data_Mirror_List_Reference
from ....addon_helpers.generic_tools import get_self_block_module, is_bpy_ready
from ....addon_helpers.ui import ui_draw_block_panel_header, ui_draw_list_headers
from ....my_addon_config import Documentation_URLs, addon_title, addon_bl_type_prefix

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ...block_core.core_features.loggers.feature_wrapper import get_logger
from ...block_core.core_features.runtime_cache import Wrapper_Runtime_Cache
from ...block_core.core_helpers.BL_RTC_data_sync_tools import update_collectionprop_to_match_dataclasses, update_dataclasses_to_match_collectionprop
from ...block_core.core_helpers.constants import Core_Runtime_Cache_Members

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Loggers, Block_RTC_Members
from .feature_example_02B import Wrapper_Example_Mirror_02B

# --------------------------------------------------------------
# Aliases
# --------------------------------------------------------------
cache_key_FWC_data_mirrors = Core_Runtime_Cache_Members.REGISTRY_ALL_FWC_DATA_MIRRORS
cache_key_example_usecase_02b = Block_RTC_Members.MIRROR_ITEMS

# ==============================================================================================================================
# MIRRORED DATA FOR RTC & BLENDER
# ==============================================================================================================================

# --------------------------------------------------------------
# Blender data, stored in scene
# --------------------------------------------------------------

def _callback_BL_instance_updated(self, context):
    """Called when any mirrored item property changes. Syncs BL -> RTC."""
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.MIRROR_ITEMS) or not is_bpy_ready():
        return
    Wrapper_Example_Mirror_02B.update_RTC_with_mirrored_BL_data(event=Enum_Sync_Events.PROPERTY_UPDATE)

class DGBLOCKS_PG_Example_02B_Instance(bpy.types.PropertyGroup):
    """
    Mirror of RTC_Example_Mirror_Item.
    RTC Key = 'MIRROR_ITEMS'
    """
    item_name: bpy.props.StringProperty(name="Name", default="", update=_callback_BL_instance_updated) # type: ignore
    item_value: bpy.props.StringProperty(name="Value", default="something", update=_callback_BL_instance_updated) # type: ignore

# --------------------------------------------------------------
# RTC data
# --------------------------------------------------------------

# Used during RTC <-> BL data sync
rtc_sync_key_fields = {"item_name"}
rtc_sync_data_fields = {"item_value"}

@dataclass
class RTC_Example_Mirror_Item:
    """Record — instance state only, no manager logic."""
    item_name: str
    item_value: str

# ==============================================================================================================================
# FEATURE WRAPPER CLASS
# ==============================================================================================================================

class Wrapper_Example_Mirror_02B(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Datawrapper_Instance_Manager):
    """
    Manager — classmethods only, no instance state.
    Demonstrates a full BL↔RTC data mirror for a custom collection.
    """

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls, event: Enum_Sync_Events) -> bool:
        "Noop"
        return

    @classmethod
    def init_post_bpy(cls, event: Enum_Sync_Events) -> bool:

        logger = get_logger(Block_Loggers.EXAMPLE_USECASE_02B)
        logger.debug("Running post-bpy init for Wrapper_Example_Mirror_02B")

        # Setup data mirror reference
        self_feature_name = cls.__name__
        FWC_data_mirror_ref = RTC_FWC_Data_Mirror_List_Reference(
            FWC_name = self_feature_name,
            BL_collectionprop_path = "dgblocks_core_props.managed_hooks", 
            RTC_key = cache_key_example_usecase_02b,
        )
        Wrapper_Runtime_Cache.append_to_cached_list(cache_key_FWC_data_mirrors, FWC_data_mirror_ref)

        # BL<->RTC 2-way sync
        cls.update_BL_with_mirrored_RTC_data(event)
        cls.update_RTC_with_mirrored_BL_data(event)
        return True

    @classmethod
    def destroy_wrapper(cls, event: Enum_Sync_Events) -> bool:
        logger = get_logger(Block_Loggers.EXAMPLE_USECASE_02B)
        logger.debug("Running destroy_wrapper for Wrapper_Example_Mirror_02B")
        return True

    # --------------------------------------------------------------
    # Implemented from Abstract_BL_RTC_List_Syncronizer
    # --------------------------------------------------------------

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events):
        """Sync BL -> RTC. Blender is the source of truth."""
        
        block_props = bpy.context.scene.dgblocks_example_mirror_02b_props
        logger = get_logger(Block_Loggers.EXAMPLE_USECASE_02B)
        logger.debug("Updating ExampleMirror02B RTC with mirrored BL Data")

        cached_items = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MIRROR_ITEMS)
        scene_items = block_props.mirror_items

        update_dataclasses_to_match_collectionprop(
            actual_FWC=cls,
            source=scene_items,
            target=cached_items,
            key_fields=rtc_sync_key_fields,
            data_fields=rtc_sync_data_fields,
            actions_denied=set(),
            debug_logger=None,
        )

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events):
        """Sync RTC -> BL. Persist runtime data into Blender."""

        block_props = bpy.context.scene.dgblocks_example_mirror_02b_props
        logger = get_logger(Block_Loggers.EXAMPLE_USECASE_02B)
        logger.debug("Updating ExampleMirror02B BL Data with mirrored RTC")

        Wrapper_Runtime_Cache.asset_cache_is_not_syncing(Block_RTC_Members.MIRROR_ITEMS, cls)

        cached_items = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MIRROR_ITEMS)
        scene_items = block_props.mirror_items

        actions_denied = set()
        if event == Enum_Sync_Events.ADDON_INIT:
            actions_denied = {Enum_Sync_Actions.EDIT}  # type: ignore

        Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.MIRROR_ITEMS, True)
        update_collectionprop_to_match_dataclasses(
            source=cached_items,
            target=scene_items,
            key_fields=rtc_sync_key_fields,
            data_fields=rtc_sync_data_fields,
            actions_denied=actions_denied,
            debug_logger=None,
        )
        Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.MIRROR_ITEMS, False)

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_instance(cls, event: Enum_Sync_Events, item_name: str, item_value: str = "something", skip_BL_sync: bool = False):
        logger = get_logger(Block_Loggers.EXAMPLE_USECASE_02B)
        cached_items = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MIRROR_ITEMS)

        # Validate uniqueness
        if any(i.item_name == item_name for i in cached_items):
            logger.warning(f"Mirror item '{item_name}' already exists. Skipping.")
            return

        new_item = RTC_Example_Mirror_Item(item_name=item_name, item_value=item_value)
        cached_items.append(new_item)
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MIRROR_ITEMS, cached_items)
        logger.info(f"Created mirror item '{item_name}'")

        if is_bpy_ready() and not skip_BL_sync:
            cls.update_BL_with_mirrored_RTC_data(event)

    @classmethod
    def destroy_instance(cls, event: Enum_Sync_Events, item_name: str, skip_BL_sync: bool = False):
        logger = get_logger(Block_Loggers.EXAMPLE_USECASE_02B)
        Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
            member_key=Block_RTC_Members.MIRROR_ITEMS,
            uniqueness_field="item_name",
            uniqueness_field_value=item_name,
        )
        logger.info(f"Removed mirror item '{item_name}'")

        if is_bpy_ready() and not skip_BL_sync:
            cls.update_BL_with_mirrored_RTC_data(event)

# ==============================================================================================================================
# FEATURE OPERATORS
# ==============================================================================================================================

class DGBLOCKS_OT_Example_Mirror_02B_Edit(bpy.types.Operator):
    bl_idname = "dgblocks.example_mirror_02b_edit"
    bl_label = "Add Item"
    bl_options = {"REGISTER", "UNDO"}

    action: bpy.props.StringProperty

    def execute(self, context):

        logger = get_logger(Block_Loggers.EXAMPLE_USECASE_02B)
        props = context.scene.dgblocks_example_mirror_02b_props

        if self.action == "ADD":

            new_item = props.mirror_items.add()
            new_item.item_name = f"item_{len(props.mirror_items)}"
            new_item.item_value = "something"
            props.mirror_items_selected_idx = len(props.mirror_items) - 1
            logger.info(f"Added mirror item '{new_item.item_name}'")

        elif self.action == "REMOVE":
            idx = props.mirror_items_selected_idx
            if 0 <= idx < len(props.mirror_items):
                name = props.mirror_items[idx].item_name
                props.mirror_items.remove(idx)
                props.mirror_items_selected_idx = max(0, idx - 1)
                logger.info(f"Removed mirror item '{name}'")

        else:
            raise Exception(f"Invalid action '{self.action}'")

        return {"FINISHED"}

# ==============================================================================================================================
# FEATURE UI
# ==============================================================================================================================

col_names = ("Name", "Value")
col_widths = (3, 5)

def _uilayout_draw_usecase_02b_settings(context, container):

    block_props = context.scene.dgblocks_example_mirror_02b_props
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_scene_loggers", default_closed=True)
    panel_header.label(text = f"All Loggers ({len(block_props.mirror_items)})")
    if panel_body is not None:        
        
        # Draw column titles
        ui_draw_list_headers(panel_body, col_names, col_widths)

        # Draw UIList body
        row = container.row()
        row_count = max(3, len(block_props.mirror_items))
        row.template_list(
            "DGBLOCKS_UL_Example_Mirror_02B",
            "",
            block_props, "mirror_items",
            block_props, "mirror_items_selected_idx",
            rows=row_count,
            maxrows=row_count,
        )

        # Add / Remove operators
        row = container.row(align=True)
        row.operator("dgblocks.example_mirror_02b_edit", icon="ADD").action = "ADD"
        row.operator("dgblocks.example_mirror_02b_edit", icon="REMOVE").action = "REMOVE"

class DGBLOCKS_UL_Example_Mirror_02B(bpy.types.UIList):
    """UIList to display mirrored RTC items."""

    def draw_item(self, context, container, data, item, icon, active_data, active_propname, index):
        row = container.row(align=True)
        sub = row.row()
        sub.ui_units_x = col_widths[0]
        sub.prop(item, "item_name", text="")
        sub = row.row()
        sub.ui_units_x = col_widths[1]
        sub.prop(item, "item_value", text="")
