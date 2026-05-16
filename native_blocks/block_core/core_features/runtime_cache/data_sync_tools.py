

# Sample License, ignore for now

import logging
from typing import Optional, TypeVar
from dataclasses import dataclass
from typing import TypeVar, Union
import bpy

from .....addon_helpers.data_structures import Enum_Sync_Events

T = TypeVar('T')

_ALLOWED_KEY_TYPES = (str, bool, int)

# --------------------------------------------------------------
# Action types 
# --------------------------------------------------------------

# Actions are emitted in the order they must be applied. Each action's
# indices are valid at the moment of application, assuming all prior
# actions in the list have already been applied.
#
# A single source item can produce:
#   - one of {Noop, Edit, Create}  (position already correct or new)
#   - a Move, optionally followed by an Edit  (position differs + data differs)
# Removed items produce a single Remove.

@dataclass(frozen=True)
class Remove:
    """Remove the target item currently at `from_idx`."""
    from_idx: int

@dataclass(frozen=True)
class Noop:
    """Item at `idx` matches the source item in both key and data fields.
    Apply does nothing; emitted for completeness / diff inspection."""
    source_idx: int
    idx: int

@dataclass(frozen=True)
class Edit:
    """Item at `idx` has correct position but data fields differ from
    source; copy data fields."""
    source_idx: int
    idx: int

@dataclass(frozen=True)
class Move:
    """Move the target item from `from_idx` to `to_idx`. Does NOT touch
    data fields — if a data update is also needed, an Edit will follow
    in the action list."""
    source_idx: int
    from_idx: int
    to_idx: int

@dataclass(frozen=True)
class Create:
    """Create a new target item from `source[source_idx]` at position `to_idx`."""
    source_idx: int
    to_idx: int

Action = Union[Remove, Noop, Edit, Move, Create]

# --------------------------------------------------------------
# Helper funcs
# --------------------------------------------------------------

def _get_key_tuple(obj, key_fields: list[str]) -> tuple:
    """Extract key field values as a tuple. Validates each value is str/bool/int."""
    key = tuple(getattr(obj, name) for name in key_fields)
    for name, val in zip(key_fields, key):
        if not isinstance(val, _ALLOWED_KEY_TYPES):
            raise TypeError(
                f"Key field {name!r} on {type(obj).__name__} has "
                f"unsupported type {type(val).__name__}; "
                f"key fields must be str, bool, or int."
            )
    return key

def _copy_fields(source, target, field_names: list[str]) -> None:
    for name in field_names:
        setattr(target, name, getattr(source, name))

def _data_fields_equal(a, b, data_fields: list[str]) -> bool:
    return all(getattr(a, name) == getattr(b, name) for name in data_fields)

def _index_by_key(items, key_fields: list[str]) -> dict[tuple, int]:
    """Build {key_tuple: index}, raising on duplicate keys."""
    out: dict[tuple, int] = {}
    for i, item in enumerate(items):
        key = _get_key_tuple(item, key_fields)
        if key in out:
            raise ValueError(
                f"Duplicate key {key!r} at indices {out[key]} and {i}; ",
                f"key fields {key_fields} must be unique within a collection.",
                f"Current: {out}"
            )
        out[key] = i
    return out

def _plan_sync(
    source,
    target,
    key_fields: list[str],
    data_fields: list[str],
) -> list[Action]:
    """
    Build an ordered action list that transforms `target` into `source`.

    Assumes keys are unique within each collection. Validates key types
    (str/bool/int only) and raises on duplicates.

    Action order:
      1. Removes, descending by from_idx.
      2. For each source item in order: Noop / Edit / Create, or
         Move (possibly followed by Edit).
    """
    src_index = _index_by_key(source, key_fields)
    tgt_index = _index_by_key(target, key_fields)

    # Match: source_idx -> original target_idx (if found).
    claimed: dict[int, int] = {}
    used_target: set[int] = set()
    for key, s_idx in src_index.items():
        t_idx = tgt_index.get(key)
        if t_idx is not None:
            claimed[s_idx] = t_idx
            used_target.add(t_idx)

    actions: list[Action] = []

    # --- removes, descending ---
    removed_sorted = sorted(
        i for i in range(len(target)) if i not in used_target
    )
    for i in reversed(removed_sorted):
        actions.append(Remove(from_idx=i))

    # --- per-source-item actions, in order ---
    def post_removal_index(orig: int) -> int:
        lo, hi = 0, len(removed_sorted)
        while lo < hi:
            mid = (lo + hi) // 2
            if removed_sorted[mid] < orig:
                lo = mid + 1
            else:
                hi = mid
        return orig - lo

    # current_pos[original_target_idx] = its current index in the (post-removal,
    # mid-move-sequence) target list.
    current_pos: dict[int, int] = {
        orig: post_removal_index(orig) for orig in used_target
    }

    for dest_idx in range(len(source)):
        if dest_idx not in claimed:
            actions.append(Create(source_idx=dest_idx, to_idx=dest_idx))
            # Insert shifts everything at >= dest_idx right by 1.
            for other_orig, pos in current_pos.items():
                if pos >= dest_idx:
                    current_pos[other_orig] = pos + 1
            continue

        orig = claimed[dest_idx]
        from_idx = current_pos[orig]
        src_item = source[dest_idx]
        tgt_item = target[orig]      # original target reference; still valid
        data_matches = _data_fields_equal(src_item, tgt_item, data_fields)

        if from_idx == dest_idx:
            # Position already correct.
            if data_matches:
                actions.append(Noop(source_idx=dest_idx, idx=dest_idx))
            else:
                actions.append(Edit(source_idx=dest_idx, idx=dest_idx))
        else:
            # Needs to move. from_idx > dest_idx always (positions < dest_idx
            # are finalized by prior iterations).
            assert from_idx > dest_idx
            actions.append(Move(source_idx=dest_idx,
                                from_idx=from_idx,
                                to_idx=dest_idx))
            # Items in [dest_idx, from_idx) shift right by 1.
            for other_orig, pos in current_pos.items():
                if other_orig != orig and dest_idx <= pos < from_idx:
                    current_pos[other_orig] = pos + 1
            current_pos[orig] = dest_idx
            # Data update, if needed, follows the move.
            if not data_matches:
                actions.append(Edit(source_idx=dest_idx, idx=dest_idx))

    return actions

def _print_actions(source, target, actions, logger):

    reformatted_actions = [a for a in actions if not isinstance(a, Noop)]
    if len(reformatted_actions) == 0:
        logger.log(logger.level, "Source & target already match, no updates needed")
        return

    logger.log(logger.level, f"updating target (len={len(target)}) to match source (len={len(source)})")
    for action in reformatted_actions:
        logger.log(logger.level, action)

# --------------------------------------------------------------
# Direction 1: dataclasses -> CollectionProperty
# --------------------------------------------------------------

def plan_collectionprop_to_match_dataclasses(
    source: list[T],
    target,
    key_fields: list[str],
    data_fields: list[str],
) -> list[Action]:
    return _plan_sync(source, target, key_fields, data_fields)

def apply_collectionprop_to_match_dataclasses(
    source: list[T],
    target,
    key_fields: list[str],
    data_fields: list[str],
    actions: list[Action],
) -> None:
    all_fields = key_fields + data_fields
    for action in actions:
        if isinstance(action, Remove):
            target.remove(action.from_idx)
        elif isinstance(action, Noop):
            pass
        elif isinstance(action, Edit):
            _copy_fields(source[action.source_idx],
                         target[action.idx],
                         data_fields)
        elif isinstance(action, Move):
            target.move(action.from_idx, action.to_idx)
        elif isinstance(action, Create):
            new_item = target.add()
            _copy_fields(source[action.source_idx], new_item, all_fields)
            last = len(target) - 1
            if last != action.to_idx:
                target.move(last, action.to_idx)

# --------------------------------------------------------------
# Direction 2: CollectionProperty -> dataclasses 
# --------------------------------------------------------------

def plan_dataclasses_to_match_collectionprop(
    source,
    target: list[T],
    key_fields: list[str],
    data_fields: list[str],
) -> list[Action]:
    return _plan_sync(list(source), target, key_fields, data_fields)

def apply_dataclasses_to_match_collectionprop(
    actual_FWC: type[T],
    source,
    target: list[T],
    key_fields: list[str],
    data_fields: list[str],
    actions: list[Action],
) -> None:
    """
    Apply actions against a Python list of dataclasses.

    For Remove: calls actual_FWC.destroy_instance(target, from_idx).
    For Create: calls actual_FWC.create_instance(target, insertion_idx,
                                                  **key+data kwargs).
    Both are expected to mutate `target` themselves.
    """
    event = Enum_Sync_Events.PROPERTY_UPDATE
    source_list = list(source)
    target_list = list(target)
    all_fields = key_fields + data_fields
    for action in actions:
        if isinstance(action, Remove):
            src_item = target_list[action.from_idx]
            kwargs = {n: getattr(src_item, n) for n in key_fields}
            actual_FWC.destroy_instance(
                event, 
                skip_BL_sync = True, 
                **kwargs)
        elif isinstance(action, Noop):
            pass
        elif isinstance(action, Edit):
            _copy_fields(source_list[action.source_idx],
                         target[action.idx],
                         data_fields)
        elif isinstance(action, Move):
            item = target.pop(action.from_idx)
            target.insert(action.to_idx, item)
        elif isinstance(action, Create):
            src_item = source_list[action.source_idx]
            kwargs = {n: getattr(src_item, n) for n in all_fields}
            actual_FWC.create_instance(
                event, 
                skip_BL_sync = True, 
                **kwargs)

# --------------------------------------------------------------
# Convenience funcs
# --------------------------------------------------------------

def default_data_mirror_RTC_list_update_logic(
        FWC_instance,
        data_mirror_instance,
        cached_RTC_list,
        actions_denied,
        logger):
    """
    Synchronizes RTC with its Blender data mirror, BL as source of truth
    """
    
    RTC_key = data_mirror_instance.RTC_key
    BL_data_path = data_mirror_instance.default_data_path_in_scene
    key_fields = data_mirror_instance.mirrored_key_field_names
    data_fields = data_mirror_instance.mirrored_data_field_names

    # Validate inputs and get source & target data
    if BL_data_path is None:
        raise Exception("Data path for mirror is missing '{RTC_key}' is missing")
    BL_colprop = bpy.context.scene.path_resolve(BL_data_path)
    if BL_colprop is None:
        raise Exception("CollectionProperty does not exist in Blender: 'scene.{BL_data_path}'")
    data_source = BL_colprop
    data_target = cached_RTC_list

    # Get ordered actions list to perform on target, to make in-sync with source
    actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
    
    # Optional deep logging
    core_props = bpy.context.scene.dgblocks_core_props
    if core_props.debug_log_all_RTC_BL_sync_actions:
        _print_actions(data_source, data_target, actions, logger)
    
    apply_dataclasses_to_match_collectionprop(FWC_instance, data_source, data_target, key_fields, data_fields, actions)

def default_data_mirror_BL_colprop_update_logic(
        FWC_instance,
        data_mirror_instance,
        cached_RTC_list,
        actions_denied,
        logger):
    """
    Synchronizes Blender with its RTC data mirror, RTC as source of truth
    """
    
    RTC_key = data_mirror_instance.RTC_key
    BL_data_path = data_mirror_instance.default_data_path_in_scene
    key_fields = data_mirror_instance.mirrored_key_field_names
    data_fields = data_mirror_instance.mirrored_data_field_names

    # Validate inputs and get source & target data
    if BL_data_path is None:
        raise Exception("Data path for mirror is missing '{RTC_key}' is missing")
    BL_colprop = bpy.context.scene.path_resolve(BL_data_path)
    if BL_colprop is None:
        raise Exception("CollectionProperty does not exist in Blender: 'scene.{BL_data_path}'")
    data_source = cached_RTC_list
    data_target = BL_colprop

    # Get ordered actions list to perform on target, to make in-sync with source
    actions = plan_collectionprop_to_match_dataclasses(data_source, data_target, key_fields, data_fields)
    
    # Optional deep logging
    core_props = bpy.context.scene.dgblocks_core_props
    if core_props.debug_log_all_RTC_BL_sync_actions:
        _print_actions(data_source, data_target, actions, logger)
    
    apply_collectionprop_to_match_dataclasses(data_source, data_target, key_fields, data_fields, actions)

# --------------------------------------------------------------
# Other
# --------------------------------------------------------------

def compare_unique_tuple_lists(list_a, list_b):
    """
    Computes the sequence of steps needed to transform list_a into list_b.

    Useful for syncing a live ordered list to a desired target state with
    minimal, discrete operations. Actions are meant to be applied sequentially;
    applying them in order to list_a will produce list_b.

    Note: Tuples must be unique within each list — duplicates will cause
    incorrect index resolution.

    Args:
        list_a: The current/source list of unique tuples.
        list_b: The desired/target list of unique tuples.

    Returns:
        A list of action dicts in the order they should be applied.
        Each dict contains an 'action' key with one of the following shapes:

            {"action": "remove", "tuple": t, "index": i}
            {"action": "move",   "tuple": t, "from_index": i, "index": j}
            {"action": "add",    "tuple": t, "index": i}

        Where 'index' refers to the position in the list at the time
        that action is applied, not the original list.
    """

    actions = []
    current = list(list_a)  # simulate the live state

    # Step 1: Remove tuples not in list_b
    set_b = set(list_b)
    for t in list(current):
        if t not in set_b:
            idx = current.index(t)
            actions.append({"action": "remove", "tuple": t, "index": idx})
            current.pop(idx)

    # Step 2: Move tuples that are in the wrong position
    # and Add tuples that are missing — walk list_b in order
    for target_idx, t in enumerate(list_b):
        if t in current:
            current_idx = current.index(t)
            if current_idx != target_idx:
                actions.append({
                    "action": "move",
                    "tuple": t,
                    "from_index": current_idx,
                    "index": target_idx
                })
                current.pop(current_idx)
                current.insert(target_idx, t)
        else:
            actions.append({"action": "add", "tuple": t, "index": target_idx})
            current.insert(target_idx, t)

    return actions
