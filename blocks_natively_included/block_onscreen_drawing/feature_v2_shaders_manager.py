# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helper_funcs import get_self_block_module, clear_console
from ...my_addon_config import Documentation_URLs, addon_title, addon_name, addon_bl_type_prefix

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .. import _block_core
from .._block_core.core_features.feature_logs import Core_Block_Loggers, get_logger
from .._block_core.core_features.feature_hooks import Wrapper_Hooks
from .._block_core.core_features.feature_block_manager import Wrapper_Block_Management
from .._block_core.core_features.feature_runtime_cache  import Wrapper_Runtime_Cache
from .._block_core.core_helpers.helper_uilayouts import uilayout_draw_block_panel_header


#=================================================================================
# MODULE VARS & CONSTANTS
#=================================================================================

rtc_draw_handlers_key = Runtime_Cache_Members.REGISTRY_ALL_DRAW_HANDLERS

rtc_sync_key_fields = ["handler_uid"]
rtc_sync_data_fields = ["space_type_name", "region_type", "draw_phase", "handler_group_id"]

# Defined by Blender, not DGBlocks
class Draw_Handler_Region_Types(StrEnum):
    WINDOW = auto()
    HEADER = auto()
    TOOLS = auto()
    TOOL_PROPS = auto()
    UI = auto()
    PREVIEW = auto()
    CHANNELS = auto()

# PRE_VIEW / POST_VIEW are VIEW_3D-only. POST_PIXEL works everywhere.
class Draw_Handler_Phases(StrEnum):
    POST_PIXEL = auto()
    POST_VIEW = auto()
    PRE_VIEW = auto()
    BACKDROP = auto()

# Maps string names back to bpy.types.Space subclasses for BL→RTC restoration.
# Extend as needed for your addon's supported spaces.
SPACE_TYPE_MAP: dict[str, type] = {
    "SpaceView3D": bpy.types.SpaceView3D,
    "SpaceImageEditor": bpy.types.SpaceImageEditor,
    "SpaceNodeEditor": bpy.types.SpaceNodeEditor,
    "SpaceClipEditor": bpy.types.SpaceClipEditor,
    "SpaceSequenceEditor": bpy.types.SpaceSequenceEditor,
    "SpaceProperties": bpy.types.SpaceProperties,
}

#=================================================================================
# BLENDER DATA FOR FEATURE - Stored in Scene
#=================================================================================

def _callback_draw_handler_changed(self, context):
    """
    Callback when a BL property on a draw handler mirror changes.
    Syncs the change back into RTC.
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(rtc_draw_handlers_key):
        return
    Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_draw_handlers_key, True)

    # BL data changed → push into RTC
    _, rtc_instance = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
        member_key=rtc_draw_handlers_key,
        uniqueness_field="handler_uid",
        uniqueness_field_value=self.handler_uid,
    )
    if rtc_instance is not None:
        rtc_instance.region_type = self.region_type
        rtc_instance.draw_phase = self.draw_phase
        rtc_instance.handler_group_id = self.handler_group_id

    Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_draw_handlers_key, False)


class DGBLOCKS_PG_Draw_Handler_Instance(bpy.types.PropertyGroup):
    """
    Mirror Dataclass = 'RTC_Draw_Handler_Instance'
    Mirror RTC Key   = 'REGISTRY_ALL_DRAW_HANDLERS'
    Persists draw handler registration metadata across file save/load.
    The actual GPU handle and callback are transient — only the identity
    and config survive in Blender data.
    """

    handler_uid: bpy.props.StringProperty(
        name="Handler UID",
        description="Unique identifier for this draw handler",
        default="",
    )  # type: ignore

    space_type_name: bpy.props.StringProperty(
        name="Space Type",
        description="String key into SPACE_TYPE_MAP, e.g. 'SpaceView3D'",
        default="SpaceView3D",
        update=_callback_draw_handler_changed,
    )  # type: ignore

    region_type: bpy.props.StringProperty(
        name="Region Type",
        description="Region the handler draws into, e.g. 'WINDOW'",
        default="WINDOW",
        update=_callback_draw_handler_changed,
    )  # type: ignore

    draw_phase: bpy.props.StringProperty(
        name="Draw Phase",
        description="When the handler fires relative to the scene draw, e.g. 'POST_PIXEL'",
        default="POST_PIXEL",
        update=_callback_draw_handler_changed,
    )  # type: ignore

    handler_group_id: bpy.props.StringProperty(
        name="Group ID",
        description="Optional group for bulk operations",
        default="",
        update=_callback_draw_handler_changed,
    )  # type: ignore


#=================================================================================
# RTC DATA FOR FEATURE
#=================================================================================

@dataclass
class RTC_Draw_Handler_Instance:
    """
    Record — instance state only, no manager logic.
    Contains all fields of DGBLOCKS_PG_Draw_Handler_Instance, plus transient
    runtime-only fields (callback, handle) that don't survive file save.
    """

    # Identity (synced with BL)
    handler_uid: str
    space_type_name: str          # String key, e.g. "SpaceView3D" — serializable
    region_type: str              # Draw_Handler_Region_Types value
    draw_phase: str               # Draw_Handler_Phases value
    handler_group_id: str = ""

    # Transient / runtime-only — NOT synced to BL PropertyGroup
    space_type: type = field(default=None, repr=False)         # Resolved bpy.types.SpaceXxx class
    callback: Callable = field(default=None, repr=False)       # The actual draw function
    callback_args: tuple = field(default=(), repr=False)       # Args passed to Blender
    _handle: Any = field(init=False, default=None, repr=False) # Opaque handle from draw_handler_add
    _is_registered: bool = field(init=False, default=False)


#=================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS
#=================================================================================

class Wrapper_Draw_Handlers(
    Abstract_Feature_Wrapper,
    Abstract_BL_and_RTC_Data_Syncronizer,
    Abstract_Datawrapper_Instance_Manager,
):

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls) -> bool:
        """
        No draw handlers to create before bpy is available — handlers need
        a live space type. This is a no-op but must return True.
        """
        return True

    @classmethod
    def init_post_bpy(cls) -> bool:
        """
        On startup, BL data may contain persisted handler metadata from a
        previous session. Push it into RTC so the wrapper knows about it.
        Note: actual GPU registration must still be triggered by whatever
        system re-supplies the callbacks (handlers are transient).
        """
        logger = get_logger()
        logger.debug("Running post-bpy init for Wrapper_Draw_Handlers")
        cls.update_RTC_with_mirrored_BL_data()
        return True

    @classmethod
    def destroy_wrapper(cls) -> bool:
        """
        Tear down every registered draw handler. Called during addon unregister.
        """
        logger = get_logger()

        all_instances = Wrapper_Runtime_Cache.get_cache(rtc_draw_handlers_key)
        if all_instances is None:
            return True

        # Iterate a copy — destroy_instance mutates the list
        for instance in list(all_instances):
            cls.destroy_instance(instance.handler_uid, skip_BL_sync=True)

        logger.debug("All draw handlers destroyed during wrapper teardown")
        return True

    # --------------------------------------------------------------
    # Implemented from Abstract_BL_and_RTC_Data_Syncronizer
    # --------------------------------------------------------------

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls):
        """BL → RTC: updates RTC dataclass fields to match saved Blender data."""

        logger = get_logger()
        logger.debug("Updating draw handler cache with mirrored Blender data")

        all_RTC_instances = Wrapper_Runtime_Cache.get_cache(rtc_draw_handlers_key)
        handlers_collectionprop = bpy.context.scene.dgblocks_core_props.scene_RTC_mirror_for_draw_handlers

        update_dataclasses_to_match_collectionprop(
            dataclass_type=RTC_Draw_Handler_Instance,
            source=handlers_collectionprop,
            target=all_RTC_instances,
            key_fields=rtc_sync_key_fields,
            data_fields=rtc_sync_data_fields,
        )

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls):
        """RTC → BL: updates Blender PropertyGroup collection to match RTC."""

        logger = get_logger()
        logger.debug("Updating Blender data with mirrored draw handler cache")

        all_RTC_instances = Wrapper_Runtime_Cache.get_cache(rtc_draw_handlers_key)
        handlers_collectionprop = bpy.context.scene.dgblocks_core_props.scene_RTC_mirror_for_draw_handlers

        update_collectionprop_to_match_dataclasses(
            source=all_RTC_instances,
            target=handlers_collectionprop,
            key_fields=rtc_sync_key_fields,
            data_fields=rtc_sync_data_fields,
        )

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def get_instance(cls, handler_uid: str) -> Optional[RTC_Draw_Handler_Instance]:

        all_handlers = Wrapper_Runtime_Cache.get_cache(rtc_draw_handlers_key)
        if all_handlers is None:
            return None

        for instance in all_handlers:
            if instance.handler_uid == handler_uid:
                return instance
        return None

    @classmethod
    def create_instance(
        cls,
        handler_uid: str,
        space_type: type,
        region_type: str,
        draw_phase: str,
        callback: Callable,
        callback_args: tuple = (),
        handler_group_id: str = "",
        skip_BL_sync: bool = False,
    ) -> Optional[RTC_Draw_Handler_Instance]:
        """
        Creates a draw handler, registers it with Blender's GPU system,
        stores the record in RTC, and optionally syncs to BL data.
        """

        logger = get_logger()
        all_cached_handlers = Wrapper_Runtime_Cache.get_cache(rtc_draw_handlers_key)
        if all_cached_handlers is None:
            all_cached_handlers = []

        # Validate uniqueness
        if Wrapper_Runtime_Cache.cache_list_contains_member(all_cached_handlers, "handler_uid", handler_uid):
            logger.debug(f"Draw handler '{handler_uid}' already exists in RTC. Returning with no action")
            return cls.get_instance(handler_uid)

        # Validate space type
        space_type_name = space_type.__name__
        if not hasattr(space_type, "draw_handler_add"):
            raise Exception(
                f"space_type {space_type_name} has no draw_handler_add — "
                f"is it actually a bpy.types.Space subclass?"
            )

        # Build the RTC record
        rtc_instance = RTC_Draw_Handler_Instance(
            handler_uid=handler_uid,
            space_type_name=space_type_name,
            region_type=region_type,
            draw_phase=draw_phase,
            handler_group_id=handler_group_id,
            space_type=space_type,
            callback=callback,
            callback_args=callback_args,
        )

        # Register with Blender's GPU draw system
        try:
            rtc_instance._handle = space_type.draw_handler_add(
                callback,
                callback_args,
                region_type,
                draw_phase,
            )
            rtc_instance._is_registered = True
        except Exception as e:
            logger.error(
                f"Failed to register draw handler '{handler_uid}' "
                f"(space={space_type_name}, region={region_type}, phase={draw_phase}): {e}"
            )
            raise

        # Store in RTC
        all_cached_handlers.append(rtc_instance)
        Wrapper_Runtime_Cache.set_cache(rtc_draw_handlers_key, all_cached_handlers)
        logger.debug(f"Created draw handler '{handler_uid}'")

        # Sync to BL data
        if is_bpy_ready() and not skip_BL_sync:
            Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_draw_handlers_key, True)
            cls.update_BL_with_mirrored_RTC_data()
            Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_draw_handlers_key, False)

        return rtc_instance

    @classmethod
    def destroy_instance(cls, handler_uid: str, skip_BL_sync: bool = False):
        """
        Removes the GPU-side draw handler, evicts from RTC, and optionally
        syncs the removal to BL data.
        """

        logger = get_logger()

        # Retrieve before destroying — we need the handle and space_type
        instance = cls.get_instance(handler_uid)
        if instance is not None and instance._is_registered and instance._handle is not None:
            try:
                # CRITICAL: must use the same region_type the handler was added with.
                instance.space_type.draw_handler_remove(
                    instance._handle,
                    instance.region_type,
                )
            except Exception as e:
                logger.warning(
                    f"draw_handler_remove failed for '{handler_uid}': {e} "
                    f"(continuing with cache eviction)"
                )
            finally:
                instance._handle = None
                instance._is_registered = False

        # Evict from RTC
        Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
            member_key=rtc_draw_handlers_key,
            uniqueness_field="handler_uid",
            uniqueness_field_value=handler_uid,
        )
        logger.debug(f"Removed draw handler '{handler_uid}'")

        # Sync to BL data
        if is_bpy_ready() and not skip_BL_sync:
            Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_draw_handlers_key, True)
            cls.update_BL_with_mirrored_RTC_data()
            Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_draw_handlers_key, False)

    @classmethod
    def set_instance(cls):
        """no-op"""
        return

    # --------------------------------------------------------------
    # Public helpers specific to draw handlers
    # --------------------------------------------------------------

    @classmethod
    def destroy_group(cls, handler_group_id: str, skip_BL_sync: bool = False) -> int:
        """
        Removes every handler whose handler_group_id matches.
        Returns the count of handlers removed.
        """
        all_instances = Wrapper_Runtime_Cache.get_cache(rtc_draw_handlers_key)
        if all_instances is None:
            return 0

        uids_to_remove = [
            inst.handler_uid for inst in all_instances
            if inst.handler_group_id == handler_group_id
        ]

        # Destroy individually — each call handles GPU removal + RTC eviction.
        # Skip BL sync on all but the final one to avoid N redundant syncs.
        for i, uid in enumerate(uids_to_remove):
            is_last = (i == len(uids_to_remove) - 1)
            cls.destroy_instance(uid, skip_BL_sync=(skip_BL_sync or not is_last))

        return len(uids_to_remove)

    @classmethod
    def is_registered(cls, handler_uid: str) -> bool:
        instance = cls.get_instance(handler_uid)
        return instance is not None and instance._is_registered

    @classmethod
    def replace_callback(
        cls,
        handler_uid: str,
        new_callback: Callable,
        new_callback_args: Optional[tuple] = None,
        skip_BL_sync: bool = False,
    ) -> Optional[RTC_Draw_Handler_Instance]:
        """
        Tears down an existing handler and re-registers it with a new callback.
        Blender does not allow mutating a live handler — this makes the
        unregister→reregister dance explicit.
        """
        instance = cls.get_instance(handler_uid)
        if instance is None:
            return None

        # Capture identity before destruction
        space_type = instance.space_type
        region_type = instance.region_type
        draw_phase = instance.draw_phase
        handler_group_id = instance.handler_group_id
        args = new_callback_args if new_callback_args is not None else instance.callback_args

        cls.destroy_instance(handler_uid, skip_BL_sync=True)

        return cls.create_instance(
            handler_uid=handler_uid,
            space_type=space_type,
            region_type=region_type,
            draw_phase=draw_phase,
            callback=new_callback,
            callback_args=args,
            handler_group_id=handler_group_id,
            skip_BL_sync=skip_BL_sync,
        )