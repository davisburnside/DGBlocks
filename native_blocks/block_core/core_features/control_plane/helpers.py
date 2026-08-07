
from dataclasses import fields

import bpy # type: ignore

# Addon-level imports
from .....addon_helpers.data_structures import  Block_Declaration, Enum_Sync_Events, Hook_Source_Declaration, Logger_Declaration, RTC_FWC_Data_Mirror_Instance, RTC_FWC_Instance, Shared_UIList_Instance
from .....addon_helpers.generic_tools import  determine_FWC_abstract_funcs, get_folder_parts, is_same_class_by_name, validate_func_args
from .....addon_config.static_settings import addon_name

# Intra-block imports
from ...core_helpers.constants import Core_Block_Hook_Sources, Core_Data_Mirrors, Core_Runtime_Cache_Members, _BLOCK_ID as core_block_id
from ...core_features.control_plane.data_structures import RTC_Block_Instance
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import Wrapper_Loggers
from ..hooks.feature_wrapper import Wrapper_Hooks

# Aliases
cache_key_FWCs = Core_Runtime_Cache_Members.REGISTRY_ALL_FWCS
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
cache_key_loggers = Core_Runtime_Cache_Members.REGISTRY_ALL_LOGGERS
cache_key_data_mirrors = Core_Runtime_Cache_Members.REGISTRY_ALL_DATA_MIRRORS
cache_key_shared_uilist_declarations = Core_Runtime_Cache_Members.SHARED_UILIST_CONFIGS
enum_hook_post_startup = Core_Block_Hook_Sources.hook_post_startup

# ==============================================================================================================================
# VALIDATION

def shallow_validate_block_module(block_module):

    # Validate both-or-none logic of block property register/unregister
    # if not hasattr(block_module, "_BLOCK_DECLARATION"):
    has_reg_func = hasattr(block_module, "register_block_props") and hasattr(block_module.register_block_props, "__call__")
    has_unreg_func = hasattr(block_module, "unregister_block_props") and hasattr(block_module.unregister_block_props, "__call__")
    if has_reg_func and not has_unreg_func:
        raise Exception(f"Function 'register_block_props' is present, but 'unregister_block_props'. Blocks must have both or neither ")
    if has_unreg_func and not has_reg_func:
        raise Exception(f"Function 'unregister_block_props' is present, but 'register_block_props'. Blocks must have both or neither ")
    if has_reg_func:
        validate_func_args(block_module.register_block_props, [])
    if has_unreg_func:
        validate_func_args(block_module.unregister_block_props, [])

    # Validate block Declaration
    file_dunder_name = block_module.__name__
    if not hasattr(block_module, "_BLOCK_DECLARATION"):
        raise Exception(f"Could not register {file_dunder_name} as a Block. Its __init__.py is missing a required '_BLOCK_DECLARATION' object")
    if not is_same_class_by_name(block_module._BLOCK_DECLARATION, Block_Declaration):#  .__name__ != Block_Declaration.__name__:
        raise Exception(f"Could not register {file_dunder_name} as a Block. Its '_BLOCK_DECLARATION' object is the supposed to be a {Block_Declaration.__class__}, is instead a {block_module._BLOCK_DECLARATION.__class__}")

    # Validate uniqueness
    block_id = block_module._BLOCK_DECLARATION
    cached_blocks = Wrapper_Runtime_Cache.get_cache(cache_key_blocks)
    block_names_and_versions = {i.block_id: i.block_version for i in cached_blocks}
    if block_id in block_names_and_versions.keys():
        raise Exception(f"A Block with ID '{block_id}' is already registered")

    # Validate dependencies
    # for block_dep in block_module._BLOCK_DECLARATION.block_dependencies:
    #     if isinstance(block_dep, str):
    #         if block_dep not in block_names_and_versions.keys():
    #             raise Exception(f"Block '{block_dep}' is not installed. Unable to register '{block_id}'")


def shallow_validate_block_declaration(block_declaration, logger):

    block_id = block_declaration.block_id
    idx, block_instance, cached_blocks_list = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
        member_key = cache_key_blocks,
        uniqueness_field = "block_id",
        uniqueness_field_value = block_id,
    )

    # Check uniqueness
    if block_instance:
        return f"Block '{block_id}' record already exists in RTC REGISTRY_ALL_BLOCKS"

    # Check types of each component
    expected_declaration_types = {
        Logger_Declaration: block_declaration.block_loggers,
        Hook_Source_Declaration: block_declaration.block_hook_sources,
        Core_Data_Mirrors: block_declaration.block_data_mirrors,
        Core_Runtime_Cache_Members: block_declaration.block_hook_sources,
    }

    for dec_type, object_declarations in expected_declaration_types.items():
        for single_dec in object_declarations:
            if not isinstance(single_dec, dec_type):
                return f"Invlaid type: Declaration '{single_dec}' needs to be a {dec_type.__class__}"

# ==============================================================================================================================
# BLOCK CREATION

def _create_new_block_properties(block_declaration, logger):

    if hasattr(block_declaration.block_module, "register_block_props"):
        block_declaration.block_module.register_block_props()


def _create_new_block_bpy_classes(block_declaration, logger):

    for bpy_class in block_declaration.block_bpy_classes:
        if bpy_class.is_registered:
            logger.debug(f"class {str(bpy_class)} is already registered")
        else:
            logger.debug(f"Registering BPY class '{bpy_class.__name__}'")
            bpy.utils.register_class(bpy_class)


def _create_and_init_new_block_FWCs(block_declaration, logger):

    new_FWC_instances = []
    cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
    for actual_class in block_declaration.block_feature_wrapper_classes:
        feature_name = actual_class.__name__

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
        # all_parent_classes = get_names_of_parent_classes(actual_class)
        # if Abstract_BL_RTC_List_Syncronizer.__name__ in all_parent_classes:
            has_BL_mirrored_data = True

        # Create & cache a new FWC instance. If a data mirror exists, it will be added in a later step
        FWC_instance = RTC_FWC_Instance(
            src_block_id = block_declaration.block_id,
            feature_name = feature_name,
            actual_class = actual_class,
        )
        cached_FWCs.append(FWC_instance)
        new_FWC_instances.append(FWC_instance)

    Wrapper_Runtime_Cache.set_cache(cache_key_FWCs, cached_FWCs)
    return new_FWC_instances


def _create_new_block_record(block_declaration, new_FWC_instances, error_str, logger):

    block_id = block_declaration.block_id
    package_name = ".".join(get_folder_parts(block_declaration.block_module)[-2:])

    cached_blocks = Wrapper_Runtime_Cache.get_cache(cache_key_blocks)

    block_instance = RTC_Block_Instance(
        block_id,
        block_version = block_declaration.block_version,
        block_module = block_declaration.block_module,
        block_package_name = package_name,
        block_dependencies = block_declaration.block_dependencies,
        block_bpy_types_classes = block_declaration.block_bpy_classes,
        block_FWC_instances = new_FWC_instances,
        block_RTC_member_names = [m.name for m in block_declaration.block_RTC_members],
    )

    # Store the block's index in the block list, for fast lookup
    block_instance.block_index = len(cached_blocks)

    if error_str is not None:
        block_instance.is_valid = False
        block_instance.error_message = error_str

    cached_blocks.append(block_instance)
    Wrapper_Runtime_Cache.set_cache(cache_key_blocks, cached_blocks)


def _create_new_block_standard_features(block_declaration, logger):

    event = Enum_Sync_Events.ADDON_INIT

    # Loggers - initialized with default log levels
    for logger_enum in block_declaration.block_loggers:
        Wrapper_Loggers._create_instance(
            event,
            src_block_id = block_declaration.block_id,
            logger_name = logger_enum.name,
            level_name = logger_enum.value.default_level,
        )

    # Hook Sources - remain unchanged after init
    for idx, hook_source_enum in enumerate(block_declaration.block_hook_sources):
        Wrapper_Hooks._create_instance(
            event,
            src_block_id = block_declaration.block_id,
            hook_func_name = hook_source_enum.name,
            hook_func_named_args = hook_source_enum.value.arg_types,
        )

    # RTC Registries - initialized with empty list/dict/dataclass containers, or a default value.
    # Note that caches for core-block (loggers, hooks, blocks...) already exist in the RTC, created during addon bootstrap
    for RTC_member_enum in block_declaration.block_RTC_members:
        Wrapper_Runtime_Cache.create_cache(
            new_key = RTC_member_enum.name,
            new_value = RTC_member_enum.value.default_value,
        )


def _create_new_block_RTC_data_mirrors(block_declaration, logger):

    # Create data mirrors references for certain RTC members
    cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
    cached_data_mirrors = Wrapper_Runtime_Cache.get_cache(cache_key_data_mirrors)

    all_known_FWC_names = [f.feature_name for f in cached_FWCs]
    new_data_mirrors = []

    for data_mirror_enum in block_declaration.block_data_mirrors:
        
        data_mirror_dec = data_mirror_enum.value
        associated_FWC_name = data_mirror_dec.FWC_name
        associated_RTC_key = data_mirror_dec.RTC_key

        # Cache validation
        mirrored_cache = Wrapper_Runtime_Cache.get_cache(associated_RTC_key)
        if mirrored_cache is None:
            raise Exception(f"Unable to make data mirror for '{associated_RTC_key}', the cache is not present in RTC")
        if associated_FWC_name not in all_known_FWC_names:
            raise Exception(f"Unable to make data mirror for '{associated_RTC_key}' because feature '{associated_FWC_name}' is not present in RTC")
        
        # FWC Validation

        # Validation for data container type
        cache_data_type = None
        if isinstance(mirrored_cache, list):
            RTC_member_type = "list"
        elif isinstance(mirrored_cache, dict):
            RTC_member_type = "dict"
        else:
            raise Exception(f"Invalid RTC member type for data mirror '{associated_RTC_key}', data type = '{mirrored_cache.__class__}'")

        # Add data-mirror instance as child of existing FWC instance.
        # list_idx = all_known_FWC_names.index(associated_FWC_name)
        # associated_FWC_instance = cached_FWCs[list_idx]
        # new_data_mirror = RTC_FWC_Data_Mirror_Instance(
        #     associated_RTC_key,
        #     associated_FWC_name,
        #     RTC_member_type,
        #     enum_val.mirrored_key_field_names,
        #     enum_val.mirrored_data_field_names,
        #     scene_colprop_path = enum_val.scene_colprop_path,
        # )
        # cached_data_mirrors.append(new_data_mirror)

        # Just a copy: no new fields
        data_mirror_instance = RTC_FWC_Data_Mirror_Instance(
            **{f.name: getattr(data_mirror_dec, f.name) for f in fields(data_mirror_dec)},
            uid = tuple([associated_FWC_name, associated_RTC_key]),
            RTC_member_type = RTC_member_type
        )
        cached_data_mirrors.append(data_mirror_instance)
        new_data_mirrors.append(data_mirror_instance)

    Wrapper_Runtime_Cache.set_cache(cache_key_data_mirrors, cached_data_mirrors)
    return new_data_mirrors


def _create_new_block_shared_UILists(block_declaration, logger):

    cached_shared_UIList_decs = Wrapper_Runtime_Cache.get_cache(cache_key_shared_uilist_declarations)
    for enum in block_declaration.block_uilist_configs:

        uilist_config_dec = enum.value

        # Just a copy: no new fields
        uilist_config_instance = Shared_UIList_Instance(
            **{f.name: getattr(uilist_config_dec, f.name) for f in fields(uilist_config_dec)},
        )
        cached_shared_UIList_decs.append(uilist_config_instance)

    Wrapper_Runtime_Cache.set_cache(cache_key_shared_uilist_declarations, cached_shared_UIList_decs)

# ==============================================================================================================================
# BLOCK REMOVAL

def _remove_block_properties(block_instance, logger):

    try:
        if hasattr(block_instance.block_module, "unregister_block_props"):
            block_instance.block_module.unregister_block_props()
    except Exception as e:
        logger.error(e, exc_info = True)


def _remove_block_bpy_classes(block_instance, logger):

    # 1: Unregister bpy classes
    for bpy_class in reversed(block_instance.block_bpy_types_classes):
        if bpy_class.is_registered:
            try:
                logger.debug(f"Unregistering BPY class '{bpy_class.__name__}'")
                bpy.utils.unregister_class(bpy_class)
            except Exception as e:
                logger.error(e, exc_info = True)


def _remove_block_FWC_instances(block_instance, logger):

    if block_instance.block_id != core_block_id:
        for FWC_instance in reversed(block_instance.block_FWC_instances):
            try:
                FWC_instance.actual_class._remove_wrapper()
                Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
                    member_key=cache_key_FWCs,
                    uniqueness_field="feature_name",
                    uniqueness_field_value=FWC_instance.feature_name,
                )
            except Exception as e:
                logger.error(e, exc_info = True)

# ==============================================================================================================================
# RELOAD

reload_flag_name = f"{addon_name}_is_reloading"

def reset_reload_flag_if_needed(blocks_cache: list[RTC_Block_Instance]):
    
    return_data = {}
    wm = bpy.context.window_manager
    for block_instance in blocks_cache:
        surviving_data = wm.get(block_instance.block_id, None)
        if surviving_data:
            return_data[block_instance.block_id] = surviving_data
    return return_data
    
    # if hasattr(bpy.context.window_manager, reload_flag_name):
    #     surviving_data = bpy.context.window_manager[reload_flag_name]
    #     del bpy.context.window_manager[reload_flag_name]
    #     return surviving_data
