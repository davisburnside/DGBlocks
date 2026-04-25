
from dataclasses import fields as dataclass_fields, is_dataclass
from typing import TypeVar











from dataclasses import dataclass
from typing import TypeVar, Union

T = TypeVar('T')

_ALLOWED_KEY_TYPES = (str, bool, int)


# ---------- helpers ----------

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
                f"Duplicate key {key!r} at indices {out[key]} and {i}; "
                f"key fields {key_fields} must be unique within a collection."
            )
        out[key] = i
    return out


# ---------- action types ----------
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


# ---------- shared planning ----------

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


# ---------- direction 1: dataclasses -> CollectionProperty ----------

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
    actions: list[Action],
    key_fields: list[str],
    data_fields: list[str],
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
            new_item = target.add()        # appends at end
            _copy_fields(source[action.source_idx], new_item, all_fields)
            last = len(target) - 1
            if last != action.to_idx:
                target.move(last, action.to_idx)


# ---------- direction 2: CollectionProperty -> dataclasses ----------

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
    actions: list[Action],
    key_fields: list[str],
    data_fields: list[str],
) -> None:
    """
    Apply actions against a Python list of dataclasses.

    For Remove: calls actual_FWC.destroy_instance(target, from_idx).
    For Create: calls actual_FWC.create_instance(target, insertion_idx,
                                                  **key+data kwargs).
    Both are expected to mutate `target` themselves.
    """
    source_list = list(source)
    all_fields = key_fields + data_fields
    for action in actions:
        if isinstance(action, Remove):
            actual_FWC.destroy_instance(target, action.from_idx)
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
            actual_FWC.create_instance(target, action.to_idx, **kwargs)


# ---------- convenience wrappers (old API) ----------

def update_collectionprop_to_match_dataclasses(
        source, 
        target,
        key_fields, 
        data_fields,
    ):
    
    actions = plan_collectionprop_to_match_dataclasses(
        source, target, key_fields, data_fields)
    
    print("updating BL")
    for a in actions:
        print(a)

    apply_collectionprop_to_match_dataclasses(
        source, target, actions, key_fields, data_fields)

def update_dataclasses_to_match_collectionprop(
        actual_FWC, 
        source, 
        target,
        key_fields, 
        data_fields,
    ):

    actions = plan_dataclasses_to_match_collectionprop(
        source, target, key_fields, data_fields)
    
    print("updating Py list")
    for a in actions:
        print(a)
        
    apply_dataclasses_to_match_collectionprop(
        actual_FWC, source, target, actions, key_fields, data_fields)












# T = TypeVar('T')

# def _get_key_tuple(obj, key_fields: list[str]) -> tuple:
#     """Extract key field values as a tuple for comparison."""
#     return tuple(getattr(obj, name) for name in key_fields)

# def _copy_fields(source, target, field_names: list[str]) -> None:
#     """Copy field values from source to target."""
#     for name in field_names:
#         setattr(target, name, getattr(source, name))

# def update_collectionprop_to_match_dataclasses(
#     source: list[T],
#     target,  # CollectionProperty
#     key_fields: list[str],
#     data_fields: list[str],
# ) -> None:
#     """
#     Update a Blender CollectionProperty to match a list of dataclasses.
    
#     Source (dataclass list) is authoritative. Target collection is mutated
#     in place — items are reused and reordered, not recreated unnecessarily.
#     """
#     # Build index of target items by key tuple
#     target_by_key: dict[tuple, list[int]] = {}
#     for i, item in enumerate(target):
#         key = _get_key_tuple(item, key_fields)
#         target_by_key.setdefault(key, []).append(i)
    
#     # Track which target indices we've claimed
#     claimed_indices: set[int] = set()
    
#     # Determine mapping: source_index -> target_index (or None if needs creation)
#     source_to_target: list[int | None] = []
    
#     for src_item in source:
#         key = _get_key_tuple(src_item, key_fields)
#         candidates = target_by_key.get(key, [])
#         available = [i for i in candidates if i not in claimed_indices]
        
#         if available:
#             chosen = available[0]
#             claimed_indices.add(chosen)
#             source_to_target.append(chosen)
#         else:
#             source_to_target.append(None)
    
#     # Remove unclaimed items (reverse order to preserve indices during removal)
#     indices_to_remove = [i for i in range(len(target)) if i not in claimed_indices]
#     for i in reversed(indices_to_remove):
#         target.remove(i)
    
#     # Rebuild mapping after removals
#     old_to_new: dict[int, int] = {}
#     new_idx = 0
#     for old_idx in range(len(target) + len(indices_to_remove)):
#         if old_idx in claimed_indices:
#             old_to_new[old_idx] = new_idx
#             new_idx += 1
    
#     source_to_target = [
#         old_to_new[i] if i is not None else None 
#         for i in source_to_target
#     ]
    
#     # Process each source item in order
#     for desired_idx, (src_item, current_target_idx) in enumerate(zip(source, source_to_target)):
#         if current_target_idx is None:
#             # Create new item at end, then move to correct position
#             new_item = target.add()
#             _copy_fields(src_item, new_item, key_fields + data_fields)
#             current_pos = len(target) - 1
#             while current_pos > desired_idx:
#                 target.move(current_pos, current_pos - 1)
#                 current_pos -= 1
#         else:
#             # Reuse existing item — reorder if needed
#             if current_target_idx != desired_idx:
#                 target.move(current_target_idx, desired_idx)
#                 # Adjust subsequent mappings affected by this move
#                 for j in range(desired_idx + 1, len(source_to_target)):
#                     if source_to_target[j] is not None:
#                         if current_target_idx > desired_idx:
#                             if desired_idx <= source_to_target[j] < current_target_idx:
#                                 source_to_target[j] += 1
#                         else:
#                             if current_target_idx < source_to_target[j] <= desired_idx:
#                                 source_to_target[j] -= 1
#             # Update sync fields on the reused item
#             _copy_fields(src_item, target[desired_idx], data_fields)

# def update_dataclasses_to_match_collectionprop(
#     actual_FWC: type[T], # The actual Feature Wrapper Class that contains 
#     source,  # CollectionProperty
#     target: list[T], # Python list of same-type @dataclass instances
#     key_fields: list[str],
#     data_fields: list[str],
# ) -> None:
#     """
#     Update a list of dataclasses to match a Blender CollectionProperty.
    
#     Source (collection) is authoritative. Target list is mutated in place —
#     items are reused and reordered, not recreated unnecessarily.
#     """
#     # Build index of target items by key tuple
#     target_by_key: dict[tuple, list[int]] = {}
#     for i, item in enumerate(target):
#         key = _get_key_tuple(item, key_fields)
#         target_by_key.setdefault(key, []).append(i)
    
#     claimed_indices: set[int] = set()
    
#     # Determine mapping: source_index -> target_index (or None if needs creation)
#     source_to_target: list[int | None] = []
    
#     for src_item in source:
#         key = _get_key_tuple(src_item, key_fields)
#         candidates = target_by_key.get(key, [])
#         available = [i for i in candidates if i not in claimed_indices]
        
#         if available:
#             chosen = available[0]
#             claimed_indices.add(chosen)
#             source_to_target.append(chosen)
#         else:
#             source_to_target.append(None)
    
#     # Build list of items to keep (in their current positions for now)
#     kept_items: list[T | None] = [
#         target[i] if i in claimed_indices else None 
#         for i in range(len(target))
#     ]
    
#     # Clear and rebuild the target list in correct order
#     target.clear()
    
#     for src_item, existing_idx in zip(source, source_to_target):
#         if existing_idx is not None:
#             # Reuse existing dataclass instance
#             reused = kept_items[existing_idx]
#             _copy_fields(src_item, reused, data_fields)
#             target.append(reused)
#         else:
#             # Create new dataclass instance with key + sync fields
#             kwargs = {
#                 name: getattr(src_item, name) 
#                 for name in key_fields + data_fields
#             }
#             kwargs["skip_BL_sync"] = True # BL data is already correct. Prevent unneeded BL->RTC->BL sync
#             new_instance = actual_FWC.create_instance(**kwargs)
#             target.append(new_instance)


# ==================================

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

def compare_unique_dicts(dict_a, dict_b):
    """
    Computes the sequence of steps needed to transform dict_a into dict_b.

    Useful for syncing a live dict to a desired target state with minimal,
    discrete operations. Actions are meant to be applied sequentially;
    applying them in order to dict_a will produce dict_b.

    Args:
        dict_a: The current/source dict.
        dict_b: The desired/target dict.

    Returns:
        A list of action dicts in the order they should be applied.
        Each dict contains an 'action' key with one of the following shapes:

            {"action": "remove", "key": k}
            {"action": "add",    "key": k, "value": v}
            {"action": "edit",   "key": k, "old_value": v1, "new_value": v2}
    """
    actions = []

    # Remove keys not in dict_b
    for k in dict_a:
        if k not in dict_b:
            actions.append({"action": "remove", "key": k})

    # Add or edit
    for k, v in dict_b.items():
        if k not in dict_a:
            actions.append({"action": "add", "key": k, "value": v})
        elif dict_a[k] != v:
            actions.append({"action": "edit", "key": k, "old_value": dict_a[k], "new_value": v})

    return actions

