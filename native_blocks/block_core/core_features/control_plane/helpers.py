from abc import ABC
import inspect
from typing import Callable

import bpy  # type: ignore
from bpy.app.handlers import persistent


# Addon-level imports
from .....addon_helpers.data_structures import  Abstract_BL_RTC_List_Syncronizer, Enum_Sync_Events, RTC_FWC_Data_Mirror_Instance, RTC_FWC_Data_Mirror_List_Reference, RTC_FWC_Instance
from .....addon_helpers.data_tools import fast_deepcopy_with_fallback
from .....addon_helpers.generic_tools import  get_names_of_parent_classes

# Intra-block imports
from ...core_helpers.constants import Core_Block_Loggers, Core_Block_Hook_Sources, Core_Runtime_Cache_Members
from ..runtime_cache import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import Wrapper_Loggers, get_logger
from ..hooks.feature_wrapper import Wrapper_Hooks
from .data_structures import RTC_Block_Instance

# Aliases
cache_key_FWCs = Core_Runtime_Cache_Members.REGISTRY_ALL_FWCS
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
cache_key_loggers = Core_Runtime_Cache_Members.REGISTRY_ALL_LOGGERS
enum_hook_blocks_registered = Core_Block_Hook_Sources.hook_block_registered
enum_hook_blocks_unregistered = Core_Block_Hook_Sources.hook_block_unregistered

def determine_FWC_abstract_funcs(actual_class: type) -> list[str]:

        # Collect all ABC bases (excluding the class itself and object)
        abc_bases = [
            base for base in inspect.getmro(actual_class)
            if base not in (actual_class, object) and issubclass(base, ABC)
        ]

        # Collect all abstract method names defined in those bases
        abstract_methods = {
            name
            for base in abc_bases
            for name, member in vars(base).items()
            if getattr(member, "__isabstractmethod__", False)
        }

        missing_func_implementations = [
            name for name in abstract_methods
            if not (
                isinstance(vars(actual_class).get(name), classmethod)
                and not getattr(vars(actual_class).get(name), "__isabstractmethod__", False)
            )
        ]

        present_func_implementations = [
            name for name in abstract_methods
            if (
                isinstance(vars(actual_class).get(name), classmethod)
                and not getattr(vars(actual_class).get(name), "__isabstractmethod__", False)
            )
        ]

        return present_func_implementations, missing_func_implementations

# ==============================================================================================================================
# BLOCK CREATION
# ==============================================================================================================================

def _create_new_block_bpy_classes(block_bpy_types_classes, logger):

    for bpy_class in block_bpy_types_classes:
        if bpy_class.is_registered:
            logger.debug(f"class {str(bpy_class)} is already registered")
        else:
            logger.debug(f"Registering BPY class '{bpy_class.__name__}'")
            bpy.utils.register_class(bpy_class)


def _create_new_block_feature_wrapper_classes(block_id, block_feature_wrapper_classes, logger):


    cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
    for actual_class in block_feature_wrapper_classes:
        feature_name = actual_class.__name__

        # Skip for self, as "create_instance" is already being called
        if feature_name == "Wrapper_Control_Plane":
            continue

        # Validate FWC uniqueness
        all_FWC_names = [f.feature_name for f in cached_FWCs]
        if feature_name in all_FWC_names:
            all_FWCs_str = "', '".join(all_FWC_names)
            raise Exception(f"Feature Wrapper '{feature_name}' already exists in RTC, unable to create duplicate. All features: '{all_FWCs_str}'")

        # Validate presence of required abstract func implementations
        missing_func_impls, present_func_impls = determine_FWC_abstract_funcs(actual_class)
        if len(missing_func_impls) > 0:
            missing_func_str = "'" + "', '".join(missing_func_impls) + "'"

        # Determine if the FWC will need BL<->RTC data sync actions
        has_BL_mirrored_data = False
        all_parent_classes = get_names_of_parent_classes(actual_class)
        if Abstract_BL_RTC_List_Syncronizer.__name__ in all_parent_classes:
            has_BL_mirrored_data = True

        # Create & cache a new FWC instance
        FWC_instance = RTC_FWC_Instance(
            src_block_id=block_id,
            feature_name=feature_name,
            actual_class=actual_class,
            has_BL_mirrored_data=has_BL_mirrored_data,
        )
        cached_FWCs.append(FWC_instance)

    Wrapper_Runtime_Cache.set_cache(cache_key_FWCs, cached_FWCs)


def _create_new_block_record(block_module, block_bpy_types_classes, block_feature_wrapper_classes, block_hook_source_enums, block_logger_enums, block_RTC_member_enums, logger):

    block_id = block_module._BLOCK_ID
    block_dependencies = block_module._BLOCK_DEPENDENCIES

    idx, block_instance, cached_blocks_list = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
        member_key = cache_key_blocks,
        uniqueness_field = "block_id",
        uniqueness_field_value = block_id,
    )
    if block_instance:
        logger.info(f"Block '{block_id}' record already exists in RTC REGISTRY_ALL_BLOCKS. Continuing with other RTC members")
    else:
        block_instance = RTC_Block_Instance(
            block_id,
            block_disabled_reason = "",
            should_block_be_enabled = True,
            is_block_enabled = True,
            is_block_valid = True,
            is_block_dependencies_valid_and_enabled = True,
            block_module = block_module,
            block_dependencies = block_dependencies,
            block_bpy_types_classes = block_bpy_types_classes,
            block_feature_wrapper_classes = block_feature_wrapper_classes,
            block_hook_source_names = [h.func_name for h in block_hook_source_enums],
            block_logger_names = [l.logger_name for l in block_logger_enums],
            block_RTC_member_names = [m.RTC_key for m in block_RTC_member_enums],
        )
        cached_blocks_list.append(block_instance)
        Wrapper_Runtime_Cache.set_cache(cache_key_blocks, cached_blocks_list)


def _create_new_block_standard_features(event, block_id, block_logger_enums, block_hook_source_enums, block_RTC_member_enums, block_RTC_data_mirror_enums):

    # Loggers - initialized with default log levels
    for idx, logger_enum in enumerate(block_logger_enums):
        is_last = idx + 1 == len(block_logger_enums)
        Wrapper_Loggers.create_instance(
            event,
            src_block_id = block_id,
            logger_name = logger_enum.name,
            level_name = logger_enum.value.default_level,
            skip_BL_sync = not is_last,
        )

    # Hook Sources - remain unchanged after init
    for idx, hook_source_enum in enumerate(block_hook_source_enums):
        is_last = idx + 1 == len(block_hook_source_enums)
        Wrapper_Hooks.create_instance(
            event,
            src_block_id = block_id,
            new_hook_func_id = hook_source_enum.name,
            new_hook_func_named_args = hook_source_enum.value.arg_types,
            skip_BL_sync = not is_last,
            skip_subscriber_cache_rebuild = not is_last,
        )

    # RTC Registries - initialized with empty list/dict/dataclass containers, or a default value.
    # Note that caches for core-block (loggers, hooks, blocks...) already exist in the RTC, created during addon bootstrap
    for RTC_member_enum in block_RTC_member_enums:
        Wrapper_Runtime_Cache.create_cache(
            new_key = RTC_member_enum.name,
            new_value = RTC_member_enum.value.data_type,
        )


def _create_new_block_RTC_data_mirrors(block_RTC_data_mirror_enums):

    # Create data mirrors references for certain RTC members
    cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
    all_known_FWC_names = [f.feature_name for f in cached_FWCs]
    for data_mirror_enum in block_RTC_data_mirror_enums:
        
        enum_val = data_mirror_enum.value
        associated_FWC_name = enum_val.FWC_name
        associated_RTC_key = enum_val.RTC_key
        RTC_member = Wrapper_Runtime_Cache.get_cache(associated_RTC_key)

        # Validation for associated objects
        if RTC_member is None:
            raise Exception(f"Unable to make data mirror for '{associated_RTC_key}', the cache is not present in RTC")
        if associated_FWC_name not in all_known_FWC_names:
            raise Exception(f"Unable to make data mirror for '{associated_RTC_key}' because feature '{associated_FWC_name}' is not present in RTC")
        
        # Validation for data container type
        if isinstance(RTC_member, list):
            is_list_type = True
        elif isinstance(RTC_member, dict):
            is_list_type = False
        else:
            raise Exception(f"Invalid RTC member type for data mirror '{associated_RTC_key}', data type = '{RTC_member.__class__}'")

        # Add data-mirror instance as child of existing FWC instance.
        FWC_idx = all_known_FWC_names.index(associated_FWC_name)
        if is_list_type:
            new_data_mirror = RTC_FWC_Data_Mirror_List_Reference(
                RTC_key = associated_RTC_key,
                default_BL_scene_data_path = enum_val.default_BL_scene_data_path,
                sync_key_field_names = enum_val.sync_key_field_names,
                sync_key_data_names = enum_val.sync_key_data_names,
            )
            cached_FWCs[FWC_idx].data_mirror_lists.append(new_data_mirror)


def init_and_register_block_components(
        event,
        block_module,
        block_bpy_types_classes,
        block_feature_wrapper_classes,
        block_RTC_member_enums,
        block_RTC_data_mirror_enums,
        block_hook_source_enums,
        block_logger_enums,
    ):

        logger = get_logger(Core_Block_Loggers.REGISTRATE)
        block_id = block_module._BLOCK_ID
        block_dependencies = block_module._BLOCK_DEPENDENCIES

        # 1: Register the new block's bpy.types.* classes into Blender's native registry
        _create_new_block_bpy_classes(block_bpy_types_classes, logger)

        # 2: Register the new block's feature-wrapper classes
        _create_new_block_feature_wrapper_classes(block_id, block_feature_wrapper_classes, logger)

        # 3: Add block module to global block registry in RTC
        _create_new_block_record(block_module, block_bpy_types_classes, block_feature_wrapper_classes, block_hook_source_enums, block_logger_enums, block_RTC_member_enums, logger)

        # 4: Register the new block's RTC members, loggers, and hook sources. Only sync to Blender on the last iteration
        _create_new_block_standard_features(block_id, event, block_logger_enums, block_hook_source_enums, block_RTC_member_enums, block_RTC_data_mirror_enums)

        # 5: Create data mirrors to link certain FWCs / RTC members / BL data
        _create_new_block_RTC_data_mirrors(block_RTC_data_mirror_enums)

# ==============================================================================================================================
# BLOCK REMOVAL
# ==============================================================================================================================




# ==============================================================================================================================
# DEFAULT DATA MIRROR LIST LOGIC
# ==============================================================================================================================


def default_update_RTC_with_mirrored_BL_data(event: Enum_Sync_Events, FWC_instance: Abstract_BL_RTC_List_Syncronizer, data_mirror_instance: RTC_FWC_Data_Mirror_Instance):
    """
    Synchronizes RTC with the Blender Logger info
    """

    # Default behavior is to use current scene
    core_props = bpy.context.scene.dgblocks_core_props
    
    logger = get_logger(Core_Block_Loggers.RTC_DATA_SYNC)
    logger.debug(f"Updating {data_mirror_instance.RTC_key} list with mirrored BL Data")
    debug_logger = logger if core_props.debug_log_all_RTC_BL_sync_actions else None

    # Get mirrored BL/RTC data (potentially de-synced)
    RTC_list = Wrapper_Runtime_Cache.get_cache(cache_key_loggers)
    BL_collectionprop = bpy.context.scene.path_resolve(data_mirror_instance.default_BL_scene_data_path)

    # Get FWC that
    FWC = Wrapper_Runtime_Cache.get_cache(cache_key_loggers)

    # BL->RTC Sync
    update_dataclasses_to_match_collectionprop(
        actual_FWC = FWC_instance,
        source = BL_collectionprop,
        target = RTC_list,
        key_fields = data_mirror_instance.sync_key_field_names,
        data_fields = data_mirror_instance.sync_data_field_names,
        actions_denied = set(),
        debug_logger=debug_logger,
    )

@classmethod
def update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events):
    """
    Synchronizes Blender log levels with the RTC logger info
    """
    import bpy  # type: ignore
    core_props = bpy.context.scene.dgblocks_core_props
    logger = get_logger(Core_Block_Loggers.RTC_DATA_SYNC)
    logger.debug(f"Updating loggers BL Data with mirrored RTC")
    debug_logger = logger if core_props.debug_log_all_RTC_BL_sync_actions else None

    # Sanity check before sync
    Wrapper_Runtime_Cache.asset_cache_is_not_syncing(cache_key_loggers, cls)

    # Get mirrored BL/RTC data (potentially de-synced)
    cached_loggers = Wrapper_Runtime_Cache.get_cache(cache_key_loggers)
    scene_loggers = core_props.managed_loggers

    # During init, allow add/move/remove but not edit. This allows user choices to be reloaded after save
    actions_denied = set()
    if event == Enum_Sync_Events.ADDON_INIT:
        actions_denied = {Enum_Sync_Actions.EDIT}

    # BL->RTC Sync
    Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_loggers, True)
    update_collectionprop_to_match_dataclasses(
        source=cached_loggers,
        target=scene_loggers,
        key_fields=rtc_sync_key_fields,
        data_fields=rtc_sync_data_fields,
        debug_logger=debug_logger,
        actions_denied=actions_denied,
    )
    Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_loggers, False)





# ==============================================================================================================================
# FEATURE WRAPPER SUPPORT CLASSES
# ==============================================================================================================================

def determine_blocks_to_update_status(cached_blocks: list[RTC_Block_Instance]) -> tuple[list[str], list[str]]:

    prior_statuses = {b.block_id: b.is_block_enabled for b in cached_blocks}
    block_map = {n.block_id: n for n in cached_blocks}

    # Build reverse dependency graph
    dependents: dict[str, list[str]] = {n.block_id: [] for n in cached_blocks}
    for node in cached_blocks:
        for dep_id in node.block_dependencies:
            if dep_id in dependents:
                dependents[dep_id].append(node.block_id)

    # Evaluate each block's own state
    for node in cached_blocks:
        node.is_block_dependencies_valid_and_enabled = True
        if not node.should_block_be_enabled:
            node.block_disabled_reason = "self is disabled"
            node.is_block_enabled = False
        elif not node.is_block_valid:
            node.block_disabled_reason = "self is invalid"
            node.is_block_enabled = False
        else:
            node.block_disabled_reason = ""
            node.is_block_enabled = True

    # BFS: propagate disabled/invalid states to dependents
    queue = [n.block_id for n in cached_blocks if not n.is_block_enabled]
    visited = set(queue)
    while queue:
        current_id = queue.pop(0)
        current = block_map[current_id]

        for dep_id in dependents[current_id]:
            dependent = block_map[dep_id]
            if dependent.is_block_dependencies_valid_and_enabled:
                dependent.is_block_dependencies_valid_and_enabled = False
                if dependent.should_block_be_enabled and dependent.is_block_valid:
                    dependent.block_disabled_reason = f"dependency '{current_id}' is disabled or invalid"
                    dependent.is_block_enabled = False
            if dep_id not in visited:
                visited.add(dep_id)
                queue.append(dep_id)

    was_enabled = [b for b in cached_blocks if b.is_block_enabled and not prior_statuses[b.block_id]]
    was_disabled = [b for b in cached_blocks if not b.is_block_enabled and prior_statuses[b.block_id]]

    return was_enabled, was_disabled


def evaluate_and_update_block_statuses(event, _Wrapper_Control_Plane: Callable):

    # Update RTC to match Blender/UI
    _Wrapper_Control_Plane.update_RTC_with_mirrored_BL_data(event)

    # Update enabled/disabled status for all block instances
    cached_blocks = Wrapper_Runtime_Cache.get_cache(cache_key_blocks)
    blocks_to_enable, blocks_to_disable = _Wrapper_Control_Plane.determine_blocks_to_update_status(cached_blocks)

    for block in blocks_to_enable:
        block.block_module.register_block(event)

    for block in blocks_to_disable:
        block.block_module.unregister_block(event)

    # Apply changes back to mirrored Blender data
    _Wrapper_Control_Plane.update_BL_with_mirrored_RTC_data(Enum_Sync_Events.PROPERTY_UPDATE)

    # Final step: Run hook to notify subscribers of block registration/unregistration
    if len(blocks_to_enable) > 0:
        kwargs = {"block_instances": blocks_to_enable}
        _ = Wrapper_Hooks.run_hooked_funcs(
            hook_func_name=enum_hook_blocks_registered,
            should_halt_on_exception=False,
            **kwargs)
    if len(blocks_to_disable) > 0:
        kwargs = {"block_instances": blocks_to_disable}
        _ = Wrapper_Hooks.run_hooked_funcs(
            hook_func_name=enum_hook_blocks_unregistered,
            should_halt_on_exception=False,
            **kwargs)
