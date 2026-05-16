from abc import ABC
from enum import Enum
import inspect
from types import ModuleType
from typing import Callable

import bpy # type: ignore

# Addon-level imports
from .....addon_helpers.data_structures import  Abstract_BL_RTC_List_Syncronizer, Enum_Sync_Events, RTC_FWC_Data_Mirror_Instance, RTC_FWC_Instance
from .....addon_helpers.generic_tools import  determine_FWC_abstract_funcs, get_names_of_parent_classes

# Intra-block imports
from ...core_helpers.constants import Core_Block_Loggers, Core_Block_Hook_Sources, Core_Runtime_Cache_Members
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import Wrapper_Loggers, get_logger
from ..hooks.feature_wrapper import Wrapper_Hooks
from .data_structures import RTC_Block_Instance

# Aliases
cache_key_FWCs = Core_Runtime_Cache_Members.REGISTRY_ALL_FWCS
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
cache_key_loggers = Core_Runtime_Cache_Members.REGISTRY_ALL_LOGGERS
enum_hook_blocks_registered = Core_Block_Hook_Sources.hook_block_registered
enum_hook_blocks_unregistered = Core_Block_Hook_Sources.hook_block_unregistered

# ==============================================================================================================================
# BLOCK CREATION

def _create_new_block_bpy_classes(block_bpy_types_classes, logger):

    for bpy_class in block_bpy_types_classes:
        if bpy_class.is_registered:
            logger.debug(f"class {str(bpy_class)} is already registered")
        else:
            logger.debug(f"Registering BPY class '{bpy_class.__name__}'")
            bpy.utils.register_class(bpy_class)


def _create_and_init_new_block_FWCs(event, block_id, block_feature_wrapper_classes, FWCs_to_skip_init, logger):

    cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
    for actual_class in block_feature_wrapper_classes:
        feature_name = actual_class.__name__

        # Skip for self, as "create_instance" is already being called
        # if feature_name == "Wrapper_Control_Plane":
        #     continue

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
            src_block_id = block_id,
            feature_name = feature_name,
            actual_class = actual_class,
            has_BL_mirrored_data = has_BL_mirrored_data,
            data_mirrors = [],
        )
        cached_FWCs.append(FWC_instance)

        if feature_name not in FWCs_to_skip_init:
            FWC_instance.actual_class.init_pre_bpy(event, FWC_instance)

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
            block_hook_source_names = [h.name for h in block_hook_source_enums],
            block_logger_names = [l.name for l in block_logger_enums],
            block_RTC_member_names = [m.name for m in block_RTC_member_enums],
        )
        cached_blocks_list.append(block_instance)
        Wrapper_Runtime_Cache.set_cache(cache_key_blocks, cached_blocks_list)


def _create_new_block_standard_features(event, block_id, block_logger_enums, block_hook_source_enums, block_RTC_member_enums, logger):

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
            new_value = RTC_member_enum.value.default_value,
        )


def _create_new_block_RTC_data_mirrors(block_RTC_data_mirror_enums, logger):

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
        RTC_member_type = None
        if isinstance(RTC_member, list):
            RTC_member_type = "list"
        elif isinstance(RTC_member, dict):
            RTC_member_type = "dict"
        else:
            raise Exception(f"Invalid RTC member type for data mirror '{associated_RTC_key}', data type = '{RTC_member.__class__}'")

        # Add data-mirror instance as child of existing FWC instance.
        list_idx = all_known_FWC_names.index(associated_FWC_name)
        associated_FWC_instance = cached_FWCs[list_idx]
        new_data_mirror = RTC_FWC_Data_Mirror_Instance(
            associated_RTC_key,
            RTC_member_type,
            enum_val.mirrored_key_field_names,
            enum_val.mirrored_data_field_names,
            default_data_path_in_scene = enum_val.default_data_path_in_scene,
        )
        associated_FWC_instance.data_mirrors.append(new_data_mirror)


def register_and_init_block_components(
        event: Enum_Sync_Events,
        block_module: ModuleType,
        block_bpy_types_classes: list[bpy.types],
        block_feature_wrapper_classes: list[Enum],
        block_RTC_member_enums: list[Enum],
        block_RTC_data_mirror_enums: list[Enum],
        block_hook_source_enums: list[Enum],
        block_logger_enums: list[Enum],
        FWCs_to_skip_init: list[str]
        
    ):

        logger = get_logger(Core_Block_Loggers.REGISTRATE)
        block_id = block_module._BLOCK_ID
        block_dependencies = block_module._BLOCK_DEPENDENCIES

        # 1: Register the new block's bpy.types.* classes into Blender's native registry
        _create_new_block_bpy_classes(block_bpy_types_classes, logger)

        # 2: Register the new block's feature-wrapper classes
        _create_and_init_new_block_FWCs(event, block_id, block_feature_wrapper_classes, FWCs_to_skip_init, logger)

        # 3: Add block module to global block registry in RTC
        _create_new_block_record(block_module, block_bpy_types_classes, block_feature_wrapper_classes, block_hook_source_enums, block_logger_enums, block_RTC_member_enums, logger)

        # 4: Register the new block's RTC members, loggers, and hook sources. Only sync to Blender on the last iteration
        _create_new_block_standard_features(event, block_id, block_logger_enums, block_hook_source_enums, block_RTC_member_enums, logger)

        # 5: Create data mirrors to link certain FWCs / RTC members / BL data
        _create_new_block_RTC_data_mirrors(block_RTC_data_mirror_enums, logger)

# ==============================================================================================================================
# BLOCK DEPENDENCY HELPERS

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
