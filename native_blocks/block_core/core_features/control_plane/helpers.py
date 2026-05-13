from abc import ABC
import inspect
from typing import Callable

import bpy  # type: ignore
from bpy.app.handlers import persistent


# Addon-level imports
from .....addon_helpers.data_structures import  Abstract_BL_RTC_List_Syncronizer, Enum_Sync_Events, Enum_Sync_Actions, Global_Addon_State, RTC_FWC_Data_Mirror_List_Reference, RTC_FWC_Instance
from .....addon_helpers.data_tools import fast_deepcopy_with_fallback, reset_propertygroup
from .....addon_helpers.generic_tools import is_bpy_ready, force_redraw_ui, get_names_of_parent_classes

# Intra-block imports
from ...core_helpers.constants import Core_Block_Loggers, Core_Block_Hook_Sources, Core_Runtime_Cache_Members
from ...core_helpers.BL_RTC_data_sync_tools import update_collectionprop_to_match_dataclasses, update_dataclasses_to_match_collectionprop
from ..runtime_cache import Wrapper_Runtime_Cache
from ..loggers import Wrapper_Loggers, get_logger
from ..hooks import Wrapper_Hooks
from .data_structures import RTC_Block_Instance

# Aliases
cache_key_FWCs = Core_Runtime_Cache_Members.REGISTRY_ALL_FWCS
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
enum_hook_blocks_registered = Core_Block_Hook_Sources.CORE_EVENT_BLOCKS_REGISTERED
enum_hook_blocks_unregistered = Core_Block_Hook_Sources.CORE_EVENT_BLOCKS_UNREGISTERED

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


def init_and_register_block_components(
        event,
        block_module,
        block_bpy_types_classes,
        block_feature_wrapper_classes,
        block_RTC_member_enums,
        block_hook_source_enums,
        block_logger_enums,
    ):

        logger = get_logger(Core_Block_Loggers.REGISTRATE)
        block_id = block_module._BLOCK_ID
        block_dependencies = block_module._BLOCK_DEPENDENCIES

        # ----------------------------------------------------------------------------------------------------------------------------
        # 1: Register the new block's bpy.types.* classes into Blender's native registry
        for bpy_class in block_bpy_types_classes:
            if bpy_class.is_registered:
                logger.debug(f"class {str(bpy_class)} is already registered")
            else:
                logger.debug(f"Registering BPY class '{bpy_class.__name__}'")
                bpy.utils.register_class(bpy_class)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 2: Register the new block's feature-wrapper classes
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

        # ----------------------------------------------------------------------------------------------------------------------------
        # 3: Add block module to global block registry in RTC
        idx, block_instance, cached_blocks_list = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            member_key=cache_key_blocks,
            uniqueness_field="block_id",
            uniqueness_field_value=block_id,
        )
        if block_instance:
            logger.info(f"Block '{block_id}' record already exists in RTC REGISTRY_ALL_BLOCKS. Continuing with other RTC members")
        else:
            block_instance = RTC_Block_Instance(
                block_id,
                block_disabled_reason="",
                should_block_be_enabled=True,
                is_block_enabled=True,
                is_block_valid=True,
                is_block_dependencies_valid_and_enabled=True,
                block_module=block_module,
                block_dependencies=block_dependencies,
                block_bpy_types_classes=block_bpy_types_classes,
                block_feature_wrapper_classes=block_feature_wrapper_classes,
                block_hook_source_names=[h.value[0] for h in block_hook_source_enums],
                block_logger_names=[l.name for l in block_logger_enums],
                block_RTC_member_names=[m.name for m in block_RTC_member_enums],
            )
            cached_blocks_list.append(block_instance)
            Wrapper_Runtime_Cache.set_cache(cache_key_blocks, cached_blocks_list)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 4: Register the new block's RTC members, loggers, and hook sources. Only sync to Blender on the last iteration

        # Loggers - initialized with default log levels
        for idx, enum_logger in enumerate(block_logger_enums):
            is_last = idx + 1 == len(block_logger_enums)
            Wrapper_Loggers.create_instance(
                event,
                src_block_id=block_id,
                logger_name=enum_logger.name,
                level_name=enum_logger.value[1],
                skip_BL_sync=not is_last,
            )

        # Hook Sources - remain unchanged after init
        for idx, enum_hook in enumerate(block_hook_source_enums):
            is_last = idx + 1 == len(block_hook_source_enums)
            Wrapper_Hooks.create_instance(
                event,
                src_block_id=block_id,
                new_hook_func_id=enum_hook.value[0],
                new_hook_func_named_args=enum_hook.value[1],
                skip_BL_sync=not is_last,
                skip_subscriber_cache_rebuild=not is_last,
            )

        # RTC Registries - initialized with empty data containers
        for enum_cache_key in block_RTC_member_enums:
            Wrapper_Runtime_Cache.create_cache(
                new_key=enum_cache_key.name,
                new_value=fast_deepcopy_with_fallback(enum_cache_key.value[1]),
            )


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
