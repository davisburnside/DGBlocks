
from dataclasses import fields as dataclass_fields, is_dataclass
from typing import TypeVar

T = TypeVar('T')

def _get_key_tuple(obj, key_fields: list[str]) -> tuple:
    """Extract key field values as a tuple for comparison."""
    return tuple(getattr(obj, name) for name in key_fields)

def _copy_fields(source, target, field_names: list[str]) -> None:
    """Copy field values from source to target."""
    for name in field_names:
        setattr(target, name, getattr(source, name))

def update_collectionprop_to_match_dataclasses(
    source: list[T],
    target,  # CollectionProperty
    key_fields: list[str],
    data_fields: list[str],
) -> None:
    """
    Update a Blender CollectionProperty to match a list of dataclasses.
    
    Source (dataclass list) is authoritative. Target collection is mutated
    in place — items are reused and reordered, not recreated unnecessarily.
    """
    # Build index of target items by key tuple
    target_by_key: dict[tuple, list[int]] = {}
    for i, item in enumerate(target):
        key = _get_key_tuple(item, key_fields)
        target_by_key.setdefault(key, []).append(i)
    
    # Track which target indices we've claimed
    claimed_indices: set[int] = set()
    
    # Determine mapping: source_index -> target_index (or None if needs creation)
    source_to_target: list[int | None] = []
    
    for src_item in source:
        key = _get_key_tuple(src_item, key_fields)
        candidates = target_by_key.get(key, [])
        available = [i for i in candidates if i not in claimed_indices]
        
        if available:
            chosen = available[0]
            claimed_indices.add(chosen)
            source_to_target.append(chosen)
        else:
            source_to_target.append(None)
    
    # Remove unclaimed items (reverse order to preserve indices during removal)
    indices_to_remove = [i for i in range(len(target)) if i not in claimed_indices]
    for i in reversed(indices_to_remove):
        target.remove(i)
    
    # Rebuild mapping after removals
    old_to_new: dict[int, int] = {}
    new_idx = 0
    for old_idx in range(len(target) + len(indices_to_remove)):
        if old_idx in claimed_indices:
            old_to_new[old_idx] = new_idx
            new_idx += 1
    
    source_to_target = [
        old_to_new[i] if i is not None else None 
        for i in source_to_target
    ]
    
    # Process each source item in order
    for desired_idx, (src_item, current_target_idx) in enumerate(zip(source, source_to_target)):
        if current_target_idx is None:
            # Create new item at end, then move to correct position
            new_item = target.add()
            _copy_fields(src_item, new_item, key_fields + data_fields)
            current_pos = len(target) - 1
            while current_pos > desired_idx:
                target.move(current_pos, current_pos - 1)
                current_pos -= 1
        else:
            # Reuse existing item — reorder if needed
            if current_target_idx != desired_idx:
                target.move(current_target_idx, desired_idx)
                # Adjust subsequent mappings affected by this move
                for j in range(desired_idx + 1, len(source_to_target)):
                    if source_to_target[j] is not None:
                        if current_target_idx > desired_idx:
                            if desired_idx <= source_to_target[j] < current_target_idx:
                                source_to_target[j] += 1
                        else:
                            if current_target_idx < source_to_target[j] <= desired_idx:
                                source_to_target[j] -= 1
            # Update sync fields on the reused item
            _copy_fields(src_item, target[desired_idx], data_fields)

def update_dataclasses_to_match_collectionprop(
    actual_FWC: type[T], # The actual Feature Wrapper Class that contains 
    source,  # CollectionProperty
    target: list[T], # Python list of same-type @dataclass instances
    key_fields: list[str],
    data_fields: list[str],
) -> None:
    """
    Update a list of dataclasses to match a Blender CollectionProperty.
    
    Source (collection) is authoritative. Target list is mutated in place —
    items are reused and reordered, not recreated unnecessarily.
    """
    # Build index of target items by key tuple
    target_by_key: dict[tuple, list[int]] = {}
    for i, item in enumerate(target):
        key = _get_key_tuple(item, key_fields)
        target_by_key.setdefault(key, []).append(i)
    
    claimed_indices: set[int] = set()
    
    # Determine mapping: source_index -> target_index (or None if needs creation)
    source_to_target: list[int | None] = []
    
    for src_item in source:
        key = _get_key_tuple(src_item, key_fields)
        candidates = target_by_key.get(key, [])
        available = [i for i in candidates if i not in claimed_indices]
        
        if available:
            chosen = available[0]
            claimed_indices.add(chosen)
            source_to_target.append(chosen)
        else:
            source_to_target.append(None)
    
    # Build list of items to keep (in their current positions for now)
    kept_items: list[T | None] = [
        target[i] if i in claimed_indices else None 
        for i in range(len(target))
    ]
    
    # Clear and rebuild the target list in correct order
    target.clear()
    
    for src_item, existing_idx in zip(source, source_to_target):
        if existing_idx is not None:
            # Reuse existing dataclass instance
            reused = kept_items[existing_idx]
            _copy_fields(src_item, reused, data_fields)
            target.append(reused)
        else:
            # Create new dataclass instance with key + sync fields
            kwargs = {
                name: getattr(src_item, name) 
                for name in key_fields + data_fields
            }
            kwargs["skip_BL_sync"] = True # BL data is already correct. Prevent unneeded BL->RTC->BL sync
            new_instance = actual_FWC.create_instance(**kwargs)
            target.append(new_instance)


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

