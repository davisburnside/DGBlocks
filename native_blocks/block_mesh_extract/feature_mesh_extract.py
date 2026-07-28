
from typing import Optional
import numpy as np
import bpy

# Addon-level imports
from ...addon_helpers.data_structures import (
    Abstract_BL_RTC_List_Syncronizer,
    Abstract_Feature_Wrapper,
    Abstract_Shared_UIList_Draw,
    Enum_Sync_Events,
)

# Inter-block imports
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.runtime_cache import data_sync_tools
from ..block_core.core_features.runtime_cache.data_sync_tools import plan_dataclasses_to_match_collectionprop
from ...native_blocks.block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks

# Intra-block imports
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .data_structures import RTC_Mesh_Extract_Instance, default_mesh_extract_field_names
from .helpers import _new_mesh_extract_instance_from_mesh, merge_mesh_extract_targets, run_mesh_extract


class Wrapper_Mesh_Extract(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Shared_UIList_Draw):
    """
    Feature Wrapper for block_mesh_extract.

    Manages the lifecycle of RTC_Mesh_Extract_Instance objects.
    Extraction is triggered by:
        - Calling Wrapper_Mesh_Extract.run_mesh_extract_for_object() from any downstream block.
        - Setting bpy.context.scene.dgblocks_mesh_extract_props.run_mesh_extract = True
          (auto-resets to False after triggering).

    After extraction completes, hook_mesh_extract_ready is fired with the list of
    processed object names.
    """

    # ----------------------------------------------------------
    # Public API

    @classmethod
    def repoll(depsgraph):
        """
        Full extraction cycle:
            1. Fire hook_get_mesh_extract_targets — collect Numpy_Mesh_Extract_Declaration lists from all blocks.
            2. Merge targets by object_name (silent union for attrs; last-writer-wins for callbacks).
            3. Get the current depsgraph.
            4. For each object: call _new_mesh_extract_instance_from_mesh, reusing or creating an RTC instance.
            5. Push updated list to RTC.
            6. Sync BL data mirror.
            7. Fire hook_mesh_extract_ready with the list of processed object names.
    
        Returns list of object names that were processed (regardless of is_valid).
        """
        logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)
        logger.debug("run_mesh_extract: starting")
    
        # Step 1: Collect
        raw_results = Wrapper_Hooks.run_hooked_funcs(
            hook_func_name = Block_Hook_Sources.hook_get_mesh_extract_targets,
            should_halt_on_exception = False,
        )
        targets_by_block = {}
        for block_id, result in raw_results.items():
            if isinstance(result, list):
                targets_by_block[block_id] = result
            else:
                logger.warning(
                    f"run_mesh_extract: block '{block_id}' returned {type(result)!r} "
                    f"from hook_get_mesh_extract_targets — expected list[Numpy_Mesh_Extract_Declaration], skipping."
                )
    
        if not targets_by_block:
            logger.info("run_mesh_extract: no Mesh_Extract_Targets returned — returning early.")
            return []
    
        # Step 2: Merge
        merged_targets = merge_mesh_extract_targets(targets_by_block)
        logger.debug(f"run_mesh_extract: merged into {len(merged_targets)} object mesh_extract_dec(s)")
    
        # Step 4: Extract each object
        # existing_instances: dict[str, RTC_Mesh_Extract_Instance] = {
        #     inst.object_name: inst
        #     for inst in Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES)
        # }
        new_instances: list[RTC_Mesh_Extract_Instance] = []
        processed_names: list[str] = []
        for object_name, mesh_extract_dec in merged_targets.items():
            instance = _new_mesh_extract_instance_from_mesh(object_name, mesh_extract_dec, depsgraph)
            new_instances.append(instance)
            processed_names.append(object_name)
    
        # Step 5: Push to RTC
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES, new_instances)
    
        # Step 6: Sync BL mirror
        cache_key = Block_RTC_Members.MESH_EXTRACT_INSTANCES
        # try:
        #     FWC_instance, data_mirror_instance = Wrapper_Runtime_Cache.get_FWC_and_data_mirror(cache_key)
        #     Wrapper_Runtime_Cache.resync_single_data_mirror(
        #         event                = Enum_Sync_Events.PROPERTY_UPDATE,
        #         BL_is_truth_source   = False,
        #         cache_key            = cache_key,
        #         FWC_instance         = FWC_instance,
        #         data_mirror_instance = data_mirror_instance,
        #         actions_denied       = set(),
        #         logger               = logger,
        #     )
        # except Exception as e:
        #     logger.error("run_mesh_extract: BL mirror sync failed", exc_info=True)
    
        # Step 7: Fire ready hook
        Wrapper_Hooks.run_hooked_funcs(
            hook_func_name = Block_Hook_Sources.hook_mesh_extract_ready,
            should_halt_on_exception = False,
            object_names = processed_names,
        )
    
        logger.info(f"run_mesh_extract: complete — {len(processed_names)} object(s) processed.")
        return new_instances

    @classmethod
    def run_mesh_extract_for_object(cls, mesh_extract_declaration, object, depsgraph = None, existing_instance = None) -> list[str]:
        """
        Trigger a full mesh extraction cycle from any downstream block.
        Returns the list of object names that were processed.
        Raises ValueError if MET validation fails.
        """

        logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)
        logger.debug("Running Mesh extract for Object '{object.name}'")
        if depsgraph is None:
            depsgraph = bpy.context.evaluated_depsgraph_get()
        new_mesh_extract = _new_mesh_extract_instance_from_mesh(object, mesh_extract_declaration, depsgraph, existing_instance)
        return new_mesh_extract

    @classmethod
    def get_instance(cls, object_name: str) -> Optional[RTC_Mesh_Extract_Instance]:
        """
        Return the live RTC_Mesh_Extract_Instance for a given object name, or None.
        Only returns the instance if is_valid is True.
        To access invalid instances, use get_instance_raw().
        """
        _, instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            Block_RTC_Members.MESH_EXTRACT_INSTANCES, "object_name", object_name
        )
        if instance is not None and instance.is_valid:
            return instance
        return None

    @classmethod
    def get_instance_raw(cls, object_name: str) -> Optional[RTC_Mesh_Extract_Instance]:
        """
        Return the RTC_Mesh_Extract_Instance for a given object name regardless of is_valid.
        Returns None if not found.
        """
        _, instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            Block_RTC_Members.MESH_EXTRACT_INSTANCES, "object_name", object_name
        )
        return instance

    @classmethod
    def get_all_instances(cls) -> list[RTC_Mesh_Extract_Instance]:
        """Return all live RTC_Mesh_Extract_Instance objects (valid and invalid)."""
        return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES)

    @classmethod
    def combine_instances(
        cls,
        instance_a: RTC_Mesh_Extract_Instance,
        instance_b: RTC_Mesh_Extract_Instance,
    ) -> RTC_Mesh_Extract_Instance:
        """
        Combine two RTC_Mesh_Extract_Instance objects for the same object into one.

        Both instances must share the same object_name (raises ValueError if they differ).
        Each domain field (vertex_co, edge_vertices, face_normal, custom_attribute_arrays
        keys, extract_metadata keys, etc.) must appear in at most one of the two instances —
        a collision raises ValueError naming the conflicting field/key.

        The returned instance is a new object; neither input is mutated.

        Typical use-case: two downstream blocks each request different attributes for the
        same object and you want to hand a single combined instance to a third consumer.
        """
        # ── Guard: same object ─────────────────────────────────────────────────────
        if instance_a.object_name != instance_b.object_name:
            raise ValueError(
                f"combine_instances: object_name mismatch — "
                f"'{instance_a.object_name}' vs '{instance_b.object_name}'. "
                f"Both instances must refer to the same object."
            )

        # ── Merge first-level array fields ─────────────────────────────────────────
        # Each field is None when it was not requested during extraction.
        # A conflict means both instances have a non-None value for the same field.
        merged_fields: dict = {}
        for field_name in default_mesh_extract_field_names:
            val_a = getattr(instance_a, field_name)
            val_b = getattr(instance_b, field_name)
            if val_a is not None and val_b is not None:
                raise ValueError(
                    f"combine_instances: conflict on field '{field_name}' — "
                    f"both instances for '{instance_a.object_name}' have a non-None value."
                )
            merged_fields[field_name] = val_a if val_a is not None else val_b

        # ── Merge custom_attribute_arrays ──────────────────────────────────────────
        merged_custom: dict = {}
        for key in instance_a.custom_attribute_arrays:
            merged_custom[key] = instance_a.custom_attribute_arrays[key]
        for key, value in instance_b.custom_attribute_arrays.items():
            if key in merged_custom:
                raise ValueError(
                    f"combine_instances: conflict on custom_attribute_arrays key '{key}' — "
                    f"both instances for '{instance_a.object_name}' define this key."
                )
            merged_custom[key] = value

        # ── Merge extract_metadata ─────────────────────────────────────────────────
        merged_metadata: dict = {}
        for key in instance_a.extract_metadata:
            merged_metadata[key] = instance_a.extract_metadata[key]
        for key, value in instance_b.extract_metadata.items():
            if key in merged_metadata:
                raise ValueError(
                    f"combine_instances: conflict on extract_metadata key '{key}' — "
                    f"both instances for '{instance_a.object_name}' define this key."
                )
            merged_metadata[key] = value

        # ── Merge status fields ────────────────────────────────────────────────────
        combined_is_valid = instance_a.is_valid and instance_b.is_valid
        error_parts = [s for s in (instance_a.error_str, instance_b.error_str) if s is not None]
        combined_error_str = "; ".join(error_parts) if error_parts else None

        # ── Build and return the combined instance ─────────────────────────────────
        return RTC_Mesh_Extract_Instance(
            object_name              = instance_a.object_name,
            is_valid                 = combined_is_valid,
            error_str                = combined_error_str,
            custom_attribute_arrays  = merged_custom,
            extract_metadata         = merged_metadata,
            **merged_fields,
        )

    # @classmethod
    # def diff_instances(
    #     cls,
    #     old: RTC_Mesh_Extract_Instance,
    #     new: RTC_Mesh_Extract_Instance,
    # ) -> list[str]:
    #     """
    #     Compare two RTC_Mesh_Extract_Instance objects for the same object and return
    #     the names of all fields/keys that have changed.

    #     Only fields present (non-None) in **both** instances are compared — fields
    #     present in only one instance are skipped.  custom_attribute_arrays keys
    #     present in only one instance are likewise skipped.

    #     Comparison strategy:
    #       - Different shapes                → changed immediately (no element scan).
    #       - Same-shape numpy arrays         → np.any(old != new)  (strict bitwise).
    #       - CSR tuples (idx, off)           → each component array compared the same way.
    #       - Non-numpy values                → old != new  (try/except → True on error).

    #     Returns a list[str] of changed field names.  An empty list means all shared
    #     data is identical (mesh is unchanged for the compared attributes).
    #     """
    #     changed: list[str] = []

    #     # ── Helper: compare two numpy arrays ──────────────────────────────────────
    #     def _arrays_differ(a: np.ndarray, b: np.ndarray) -> bool:
    #         if a.shape != b.shape:
    #             return True
    #         return bool(np.any(a != b))

    #     # ── Helper: compare an arbitrary value (array, CSR tuple, or other) ───────
    #     def _values_differ(a, b) -> bool:
    #         # CSR tuple: (indices_array, offsets_array)
    #         if (
    #             isinstance(a, tuple) and isinstance(b, tuple)
    #             and len(a) == 2 and len(b) == 2
    #             and isinstance(a[0], np.ndarray)
    #         ):
    #             return _arrays_differ(a[0], b[0]) or _arrays_differ(a[1], b[1])
    #         # Plain numpy array
    #         if isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
    #             return _arrays_differ(a, b)
    #         # Fallback — use Python equality; treat comparison errors as changed
    #         try:
    #             return bool(a != b)
    #         except Exception:
    #             return True

    #     # ── First-level array fields ───────────────────────────────────────────────
    #     for field_name in default_mesh_extract_field_names:
    #         val_old = getattr(old, field_name)
    #         val_new = getattr(new, field_name)
    #         if val_old is None or val_new is None:
    #             continue  # not shared — skip
    #         if _arrays_differ(val_old, val_new):
    #             changed.append(field_name)

    #     # ── custom_attribute_arrays — shared keys only ─────────────────────────────
    #     for key in old.custom_attribute_arrays:
    #         if key not in new.custom_attribute_arrays:
    #             continue  # not shared — skip
    #         if _values_differ(old.custom_attribute_arrays[key], new.custom_attribute_arrays[key]):
    #             changed.append(key)

    #     return changed


    # ── Helper: compare two numpy arrays ──────────────────────────────────────────
    @classmethod
    def _arrays_differ(cls, a: np.ndarray, b: np.ndarray) -> bool:
        if a.shape != b.shape:
            return True
        return bool(np.any(a != b))

    # ── Helper: compare an arbitrary value (array, CSR tuple, or other) ───────────
    @classmethod
    def _values_differ(cls, a, b) -> bool:
        # CSR tuple: (indices_array, offsets_array)
        if (
            isinstance(a, tuple) and isinstance(b, tuple)
            and len(a) == 2 and len(b) == 2
            and isinstance(a[0], np.ndarray)
        ):
            return (
                cls._arrays_differ(a[0], b[0])
                or cls._arrays_differ(a[1], b[1])
            )
        # Plain numpy array
        if isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
            return cls._arrays_differ(a, b)
        # Fallback — use Python equality; treat comparison errors as changed
        try:
            return bool(a != b)
        except Exception:
            return True

    @classmethod
    def diff_instances(
        cls,
        old: RTC_Mesh_Extract_Instance,
        new: RTC_Mesh_Extract_Instance,
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Compare two RTC_Mesh_Extract_Instance objects for the same object and
        classify every attribute name into one of three buckets:

          added   — None/absent in **old**, present in **new**
          removed — present in **old**, None/absent in **new**
          edited  — present in both, but the data differs

        Attributes that are None/absent in both instances are omitted entirely.
        custom_attribute_arrays is diffed over the union of both key sets.

        Comparison strategy:
          - Different shapes                → changed immediately (no element scan).
          - Same-shape numpy arrays         → np.any(old != new)  (strict bitwise).
          - CSR tuples (idx, off)           → each component array compared the same way.
          - Non-numpy values                → old != new  (try/except → True on error).

        Returns (added, removed, edited).  All three empty means the two instances
        carry identical data (mesh is unchanged for the compared attributes).
        """
        added: list[str] = []
        removed: list[str] = []
        edited: list[str] = []

        # ── First-level array fields ───────────────────────────────────────────────
        first_level_fields = [
            "vertex_co",
            "vertex_normal",
            "vertex_crease",
            "vertex_bevel_weight",
            "edge_vertices",
            "edge_crease",
            "edge_sharp",
            "edge_seam",
            "face_normal",
            "face_area",
            "face_loop_start",
            "face_loop_total",
            "corner_vertex_index",
        ]

        for field_name in first_level_fields:
            val_old = getattr(old, field_name)
            val_new = getattr(new, field_name)
            if val_old is None and val_new is None:
                continue  # absent from both — skip
            if val_old is None:
                added.append(field_name)
            elif val_new is None:
                removed.append(field_name)
            elif cls._values_differ(val_old, val_new):
                edited.append(field_name)

        # ── custom_attribute_arrays — union of keys ────────────────────────────────
        old_attrs = old.custom_attribute_arrays or {}
        new_attrs = new.custom_attribute_arrays or {}

        for key in sorted(old_attrs.keys() | new_attrs.keys()):
            val_old = old_attrs.get(key)
            val_new = new_attrs.get(key)
            if val_old is None and val_new is None:
                continue  # absent from both — skip
            if val_old is None:
                added.append(key)
            elif val_new is None:
                removed.append(key)
            elif cls._values_differ(val_old, val_new):
                edited.append(key)

        return added, removed, edited


    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)
        logger.debug("Wrapper_Mesh_Extract._init_wrapper")
        # No active initialization needed — extraction is demand-driven.
        # RTC list starts empty; instances are created on first run_mesh_extract_for_object() call.
        return True

    @classmethod
    def _remove_wrapper(cls) -> None:
        logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)
        logger.debug("Wrapper_Mesh_Extract._remove_wrapper — clearing all instances")
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES, [])

    # ----------------------------------------------------------
    # Abstract_BL_RTC_List_Syncronizer implementation

    @classmethod
    def _update_RTC_with_mirrored_BL_data(cls, event, FWC_instance, data_mirror_instance):
        """
        Called on undo/redo/reload. The extract_mirror CollectionProperty holds only
        object_name (key) and is_valid (data) — it does not store numpy arrays.
        On structural change (object added/removed from mirror), we simply clear the
        RTC list. The user must re-trigger extraction if they want fresh data.
        On edit-only changes (is_valid toggled — unusual but possible), no action needed.
        """
        return
        logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)

        try:
            mesh_extract_props = bpy.context.scene.dgblocks_mesh_extract_props
        except AttributeError:
            logger.warning("_update_RTC_with_mirrored_BL_data: bpy.context.scene not available")
            return

        key_fields  = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES)
        data_source = mesh_extract_props.extract_mirror

        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        structural_actions = [
            a for a in actions
            if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove}
        ]

        if structural_actions:
            logger.debug(
                f"_update_RTC_with_mirrored_BL_data: structural change detected "
                f"({len(structural_actions)} action(s)) — clearing RTC instances."
            )
            Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES, [])

    @classmethod
    def _update_BL_with_mirrored_RTC_data(cls, event, FWC_instance, data_mirror_instance):
        """
        Push current RTC instance list to the BL extract_mirror CollectionProperty.
        Called after run_mesh_extract() and on undo/redo.
        """
        return
        logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)

        try:
            mesh_extract_props = bpy.context.scene.dgblocks_mesh_extract_props
        except AttributeError:
            logger.warning("_update_BL_with_mirrored_RTC_data: bpy.context.scene not available")
            return

        cached_instances = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES)

        key_fields  = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = cached_instances
        data_source = mesh_extract_props.extract_mirror

        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        structural_actions = [
            a for a in actions
            if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove, data_sync_tools.Move}
        ]

        if structural_actions:
            Wrapper_Runtime_Cache.assert_cache_is_not_syncing(Block_RTC_Members.MESH_EXTRACT_INSTANCES)
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.MESH_EXTRACT_INSTANCES, True)
            try:
                mesh_extract_props.extract_mirror.clear()
                for inst in cached_instances:
                    row = mesh_extract_props.extract_mirror.add()
                    row.object_name = inst.object_name
                    row.is_valid    = inst.is_valid
            finally:
                Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.MESH_EXTRACT_INSTANCES, False)

            logger.debug(
                f"_update_BL_with_mirrored_RTC_data: synced {len(cached_instances)} row(s)"
            )

    # ----------------------------------------------------------
    # Abstract_Shared_UIList_Draw implementation

    @classmethod
    def shared_uilist_get_data_path(cls, shared_uilist_instance) -> str:
        return shared_uilist_instance.scene_colprop_path
