
import dataclasses
from datetime import datetime
from typing import Any
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helper_funcs import create_simplified_list_from_csv_string, get_members_and_values_of_propertygroup_with_name_prefix, print_section_separator

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .._block_core.core_features.feature_hooks import Wrapper_Hooks
from .._block_core.core_features.feature_runtime_cache import Wrapper_Runtime_Cache
from .._block_core.core_helpers.helper_uilayouts import draw_wrapped_text_v2, ui_box_with_header, uilayout_section_separator
from .._block_core.core_helpers.constants import Core_Block_Hook_Sources, Core_Runtime_Cache_Members, debug_sort_hooks_choice_items, _BLOCK_ID as core_block_id

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ..block_debug_console_print.constants import Core_Debugging_Print_Options, Block_Hook_Sources

# --------------------------------------------------------------
# Helper funcs for formatting data
# --------------------------------------------------------------

def make_table_string_from_data(
        data: dict,
        indent_level: int = 0,
        indent_width: int = 2,
        row_key_header: str = "",
        path_separator: str = " > ",
        sort_key: str = "",
        sort_ascending: bool = False,
        max_cell_width: int = 40) -> str:
    """
    Format a nested dict as an ASCII table by discovering leaf dicts at any depth.
    
    Walks the dict recursively to find all "leaf dicts" (dicts whose values are 
    all non-containers). The first leaf dict found sets the reference columns.
    Leaf dicts with different keys are skipped with a warning.
    
    Intermediate dict levels become visual group headers in the table.
    
    Args:
        data:              Dict to format.
        indent_level:      Current indentation level for nesting.
        indent_width:      Spaces per indent level.
        row_key_header:    Header label for the row key column.
        path_separator:    Separator used when flattening group paths into labels.
        sort_key:          Column key to sort rows by. Empty string = no sorting.
        sort_ascending:    Sort direction. True = ascending (▲), False = descending (▼).
        max_cell_width:    Max character width for string cells. 0 = no truncation.
    
    Returns:
        Formatted table string, or empty string if no valid leaf dicts found.
    
    Raises:
        ValueError: If sort_key is provided but doesn't match any column in the leaf dicts.
    """
    if not isinstance(data, dict) or not data:
        print("[Table Warning] Input is not a non-empty dict.")
        return ""
    
    def is_leaf_value(val) -> bool:
        return not isinstance(val, (dict, list, tuple, set, frozenset))
    
    def is_leaf_dict(d: dict) -> bool:
        return all(is_leaf_value(v) for v in d.values())
    
    # --- Collect all leaf dicts with their paths ---
    leaf_entries = []
    
    def collect_leaves(node, path: list[str]):
        if not isinstance(node, dict):
            return
        if is_leaf_dict(node):
            if node:
                leaf_entries.append((list(path), node))
            return
        for key, value in node.items():
            collect_leaves(value, path + [str(key)])
    
    collect_leaves(data, [])
    
    if not leaf_entries:
        print("[Table Warning] No leaf dicts found in structure.")
        return ""
    
    # --- Determine reference columns from first leaf ---
    reference_keys = list(leaf_entries[0][1].keys())
    reference_set = set(reference_keys)
    
    # --- Validate sort_key ---
    if sort_key:
        if sort_key not in reference_set:
            raise ValueError(
                f"sort_key '{sort_key}' not found in leaf dict keys. "
                f"Available keys: {reference_keys}")
    
    # Filter to only matching leaf dicts
    valid_entries = []
    skipped_count = 0
    for path, leaf in leaf_entries:
        if set(leaf.keys()) == reference_set:
            valid_entries.append((path, leaf))
        else:
            skipped_count += 1
            path_str = path_separator.join(path) if path else "(root)"
            print(f"[Table Warning] Skipping '{path_str}': keys {set(leaf.keys())} don't match reference {reference_set}")
    
    if not valid_entries:
        print("[Table Warning] No leaf dicts match the reference keys.")
        return ""
    
    col_keys = reference_keys
    
    # --- Cell formatting helpers ---
    def to_cell(value) -> str:
        if value is None:
            return "None"
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, float):
            if value == int(value):
                return str(int(value))
            return f"{value:.6f}".rstrip('0').rstrip('.')
        text = str(value)
        if max_cell_width > 0 and len(text) > max_cell_width:
            return text[:max_cell_width - 3] + "..."
        return text
    
    def is_numeric(value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    
    def sort_value(value):
        """Return a sortable key. Numbers sort naturally, everything else sorts as lowercase string."""
        if is_numeric(value):
            return (0, value)
        return (1, str(value).lower())
    
    # Per-column numeric check
    col_is_numeric = {}
    for ck in col_keys:
        col_is_numeric[ck] = all(is_numeric(leaf[ck]) for _, leaf in valid_entries)
    
    # --- Determine grouping ---
    min_depth = min(len(path) for path, _ in valid_entries)
    max_depth = max(len(path) for path, _ in valid_entries)
    
    common_prefix_len = 0
    if len(valid_entries) > 1:
        first_path = valid_entries[0][0]
        for depth in range(min_depth):
            if all(path[depth] == first_path[depth] for path, _ in valid_entries):
                common_prefix_len = depth + 1
            else:
                break
    
    # --- Build grouped + sorted structure ---
    # Group entries by their group path (everything between common prefix and leaf key)
    from collections import OrderedDict
    
    groups = OrderedDict()
    for path, leaf in valid_entries:
        if len(path) == 0:
            group_key = ()
            row_label = "(root)"
        else:
            row_label = path[-1]
            group_key = tuple(path[common_prefix_len:-1])
        
        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append((row_label, leaf))
    
    # Sort within each group
    if sort_key:
        for group_key in groups:
            groups[group_key].sort(
                key=lambda entry: sort_value(entry[1][sort_key]),
                reverse=not sort_ascending)
    
    # --- Build row list with group headers ---
    class GroupHeader:
        def __init__(self, label: str, depth: int):
            self.label = label
            self.depth = depth
    
    class DataRow:
        def __init__(self, label: str, cells: dict):
            self.label = label
            self.cells = cells
    
    rows = []
    last_group_parts = []
    
    for group_key, entries in groups.items():
        group_parts = list(group_key)
        
        # Emit group headers for new group levels
        for depth_i, part in enumerate(group_parts):
            check_path = group_parts[:depth_i + 1]
            if check_path != last_group_parts[:depth_i + 1]:
                rows.append(GroupHeader(part, depth_i))
        
        last_group_parts = group_parts
        
        for row_label, leaf in entries:
            cell_strings = {}
            for ck in col_keys:
                cell_strings[ck] = to_cell(leaf[ck])
            rows.append(DataRow(row_label, cell_strings))
    
    # --- Calculate column widths ---
    row_labels = [r.label for r in rows if isinstance(r, DataRow)]
    
    row_col_width = max(len(s) for s in row_labels) if row_labels else 0
    if row_key_header:
        row_col_width = max(row_col_width, len(row_key_header))
    
    # Column header strings (with sort arrow if applicable)
    col_headers = {}
    for ck in col_keys:
        header = str(ck)
        if sort_key and ck == sort_key:
            arrow = "▲" if sort_ascending else "▼"
            header = f"{header} {arrow}"
        col_headers[ck] = header
    
    col_widths = {}
    for ck in col_keys:
        header_len = len(col_headers[ck])
        max_val_len = max(
            (len(r.cells[ck]) for r in rows if isinstance(r, DataRow)),
            default=0)
        col_widths[ck] = max(header_len, max_val_len)
    
    total_table_width = (row_col_width + 3)
    for ck in col_keys:
        total_table_width += col_widths[ck] + 3
    total_table_width += 1
    
    # --- Render ---
    prefix = ' ' * (indent_level * indent_width)
    
    def pad_cell(text: str, width: int, right_align: bool = False) -> str:
        if right_align:
            return text.rjust(width)
        return text.ljust(width)
    
    def make_separator(left: str, mid: str, right: str, fill: str = '-') -> str:
        parts = [fill * (row_col_width + 2)]
        for ck in col_keys:
            parts.append(fill * (col_widths[ck] + 2))
        return prefix + left + mid.join(parts) + right
    
    def make_data_row(label: str, cells: dict, is_header: bool = False) -> str:
        row_cell = pad_cell(label, row_col_width)
        parts = [f" {row_cell} "]
        for ck in col_keys:
            cell_text = cells[ck]
            right_align = col_is_numeric[ck] and not is_header
            parts.append(f" {pad_cell(cell_text, col_widths[ck], right_align)} ")
        return prefix + "|" + "|".join(parts) + "|"
    
    def make_group_row(label: str) -> str:
        inner_width = total_table_width - 2
        text = f" {label} "
        padded = text.ljust(inner_width)
        return prefix + "|" + padded + "|"
    
    lines = []
    
    # Top border
    lines.append(make_separator('+', '+', '+'))
    
    # Column header row
    header_cells = {ck: col_headers[ck] for ck in col_keys}
    lines.append(make_data_row(row_key_header, header_cells, is_header=True))
    lines.append(make_separator('+', '+', '+'))
    
    # Data rows with group headers
    for row in rows:
        if isinstance(row, GroupHeader):
            lines.append(make_separator('+', '-', '+'))
            lines.append(make_group_row(row.label))
            lines.append(make_separator('+', '+', '+'))
        else:
            lines.append(make_data_row(row.label, row.cells))
    
    # Bottom border
    lines.append(make_separator('+', '+', '+'))
    
    if skipped_count > 0:
        lines.append(f"{prefix}({skipped_count} leaf dict(s) skipped: keys didn't match reference)")
    
    return '\n'.join(lines)

def make_pretty_json_string_from_data(
        raw_data_to_print,
        filter_inclusion_dict_keys_raw_str: str = "",
        filter_exclusion_dict_keys_raw_str: str = "",
        filter_inclusion_dict_keys_level: str = "OFF",
        filter_exclusion_dict_keys_level: str = "OFF",
        filter_numerical_op: str = "OFF",
        filter_numerical_value: float = 0.0,
        filter_numerical_level: str = "OFF",
        min_verbosity: bool = False,
        show_type_labels: bool = False,
        show_memory_address: bool = False,
        show_memory_duplicates: bool = False,
        max_rows_of_each_container: int = 0,
        max_depth_of_container_search: int = 0,
        indent: int = 2,
        
        expand_dataclasses: bool = True):

    NUMERICAL_OPS = {
        ">":  lambda v, t: v > t,
        ">=": lambda v, t: v >= t,
        "=":  lambda v, t: v == t,
        "==": lambda v, t: v == t,
        "!=": lambda v, t: v != t,
        "<":  lambda v, t: v < t,
        "<=": lambda v, t: v <= t,
    }

    # Memory address tracker: addr -> (type_name, count)
    address_tracker: dict[int, tuple[str, int]] = {}

    def track_address(item: Any) -> None:
        """Record an object's address and type for duplicate detection."""
        if not show_memory_duplicates:
            return
        if is_native_type(item):
            return
        addr = id(item)
        type_name = type(item).__name__
        if addr in address_tracker:
            existing_type, count = address_tracker[addr]
            address_tracker[addr] = (existing_type, count + 1)
        else:
            address_tracker[addr] = (type_name, 1)

    def clean_json_string(input_str: str) -> str:

        if not input_str:
            return input_str

        syntax_chars = set('{}[],')
        lines = input_str.splitlines()

        def is_syntax_only(line: str) -> bool:
            stripped = line.strip()
            if not stripped:
                return True
            return all(char in syntax_chars for char in stripped)

        cleaned_lines = []
        for i, line in enumerate(lines):
            if not is_syntax_only(line):
                cleaned_lines.append(line)
            else:
                if i < len(lines) - 1 and not is_syntax_only(lines[i + 1]):
                    if any(char in line for char in ']}'):
                        cleaned_lines.append(line)
                if i > 0 and not is_syntax_only(lines[i - 1]):
                    if any(char in line for char in '[{'):
                        cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def is_native_type(item: Any) -> bool:
        return isinstance(item, (int, float, str, bool, type(None)))

    def is_container_type(item: Any) -> bool:
        return isinstance(item, (dict, list, tuple, set, frozenset))

    def is_dataclass_instance(item: Any) -> bool:
        return dataclasses.is_dataclass(item) and not isinstance(item, type)

    def _filter_applies(filter_level: str, is_leaf: bool) -> bool:
        """Whether a given filter level applies to this node type."""
        if filter_level == "OFF":
            return False
        if filter_level == "FULL":
            return True
        if filter_level == "LEAF" and is_leaf:
            return True
        if filter_level == "BRANCH" and not is_leaf:
            return True
        return False

    def passes_numerical_filter(value: Any) -> bool:
        """
        Returns True if this leaf value passes the numerical filter.
        Non-numeric values always pass (filter is ignored for them).
        """
        if filter_numerical_level == "OFF":
            return True
        if filter_numerical_op == "OFF":
            return True
        if not isinstance(value, (int, float)):
            return True
        if isinstance(value, bool):
            return True

        if filter_numerical_op not in NUMERICAL_OPS:
            return True

        v = float(value)
        op_func = NUMERICAL_OPS[filter_numerical_op]
        op_result = op_func(v, float(filter_numerical_value))
        if filter_numerical_level == "FILTER-EXCLUDE":
            return not op_result
        return op_result

    def passes_dict_key_filter(key: str, is_leaf: bool) -> bool:
        """
        Returns True if this key should be included in the output.

        Include and exclude filters each have their own level:
          - OFF:    Filter not applied.
          - LEAF:   Filter only applies to leaf nodes (non-container values).
          - BRANCH: Filter only applies to branch nodes (container values).
          - FULL:   Filter applies to all nodes at every level.
        """
        key_lower = str(key).lower()

        # Blacklist check
        if filter_exclusion_dict_keys_list and _filter_applies(filter_exclusion_dict_keys_level, is_leaf):
            for f in filter_exclusion_dict_keys_list:
                if f.lower() in key_lower:
                    return False

        # Whitelist check
        if filter_inclusion_dict_keys_list and _filter_applies(filter_inclusion_dict_keys_level, is_leaf):
            matched = False
            for f in filter_inclusion_dict_keys_list:
                if f.lower() in key_lower:
                    matched = True
                    break
            if not matched:
                return False

        return True

    def passes_member_count_filter(idx: int) -> bool:
        return max_rows_of_each_container == 0 or idx < max_rows_of_each_container

    def is_blender_collection(item: Any) -> bool:
        try:
            return isinstance(item, (bpy.types.bpy_prop_collection,))
        except (ImportError, AttributeError, NameError):
            return False

    def is_blender_id(item: Any) -> bool:
        try:
            return isinstance(item, bpy.types.ID)
        except (ImportError, AttributeError, NameError):
            return False

    def is_numpy_array(item: Any) -> bool:
        try:
            import numpy as np
            return isinstance(item, np.ndarray)
        except (ImportError, AttributeError):
            return False

    def is_blender_property_group(item: Any) -> bool:
        try:
            return isinstance(item, bpy.types.PropertyGroup)
        except (ImportError, AttributeError, NameError):
            return False

    def format_numpy_array(item: Any, level: int) -> str:
        spaces = ' ' * (level * indent)
        next_spaces = ' ' * ((level + 1) * indent)
        lines = [f"ndarray {{"]
        lines.append(f"{next_spaces}shape: {item.shape},")
        lines.append(f"{next_spaces}dtype: {item.dtype},")
        lines.append(f"{next_spaces}size: {item.size},")
        if item.ndim > 1:
            lines.append(f"{next_spaces}rows: {item.shape[0]},")
            lines.append(f"{next_spaces}cols: {item.shape[1] if item.ndim > 1 else 'N/A'},")
        lines.append(f"{next_spaces}min: {item.min()},")
        lines.append(f"{next_spaces}max: {item.max()},")
        lines.append(f"{next_spaces}mean: {item.mean():.4f},")
        lines.append(f"{spaces}}}")
        return '\n'.join(lines)

    def format_blender_collection(item: Any, level: int, depth: int) -> str:
        spaces = ' ' * (level * indent)
        next_spaces = ' ' * ((level + 1) * indent)
        count = len(item)

        if max_depth_of_container_search > 0 and depth >= max_depth_of_container_search:
            return f"bpy_prop_collection({count} items)"

        if count == 0:
            return "bpy_prop_collection(empty)"

        lines = [f"bpy_prop_collection({count} items) ["]
        for i, obj in enumerate(item):
            name = getattr(obj, 'name', None) or str(obj)
            type_name = type(obj).__name__
            lines.append(f"{next_spaces}{type_name}('{name}'),")
        lines.append(f"{spaces}]")
        return '\n'.join(lines)

    def format_blender_id(item: Any, level: int) -> str:
        type_name = type(item).__name__
        name = getattr(item, 'name', '?')
        return f"{type_name}('{name}')"

    def count_summary(item: Any) -> str:
        """Summary string when max_depth_of_container_search is reached."""
        type_name = type(item).__name__

        if isinstance(item, dict):
            return f"dict({len(item)} keys)"
        elif isinstance(item, (list, tuple)):
            return f"{type_name}({len(item)} items)"
        elif isinstance(item, set):
            return f"set({len(item)} items)"
        elif isinstance(item, frozenset):
            return f"frozenset({len(item)} items)"
        elif is_blender_collection(item):
            return f"bpy_prop_collection({len(item)} items)"
        else:
            return str(item)

    def addr_str(item: Any) -> str:
        """Return memory address string if show_memory_address is enabled.
        Skips native types (int, float, str, bool, None)."""
        if not show_memory_address:
            return ""
        if is_native_type(item):
            return ""
        return f" @{hex(id(item))}"

    def get_homogeneous_type_label(key: str, container: Any) -> str:
        """
        Returns a type label string like ' <str : list>' if show_type_labels is on
        and the container has homogeneous value types.
        Returns '' otherwise.
        """
        if not show_type_labels:
            return ""

        key_type = type(key).__name__

        if isinstance(container, dict):
            if not container:
                return f" <{key_type} : dict>"
            val_types = set(type(v).__name__ for v in container.values())
            if len(val_types) == 1:
                val_type = next(iter(val_types))
                return f" <{key_type} : dict[{val_type}]>"
            return ""
        elif isinstance(container, (list, tuple)):
            container_type = type(container).__name__
            if not container:
                return f" <{key_type} : {container_type}>"
            val_types = set(type(v).__name__ for v in container)
            if len(val_types) == 1:
                val_type = next(iter(val_types))
                return f" <{key_type} : {container_type}[{val_type}]>"
            return ""
        elif isinstance(container, (set, frozenset)):
            container_type = type(container).__name__
            if not container:
                return f" <{key_type} : {container_type}>"
            val_types = set(type(v).__name__ for v in container)
            if len(val_types) == 1:
                val_type = next(iter(val_types))
                return f" <{key_type} : {container_type}[{val_type}]>"
            return ""
        elif is_dataclass_instance(container):
            return f" <{key_type} : {type(container).__name__}>"
        else:
            val_type = type(container).__name__
            return f" <{key_type} : {val_type}>"

    def get_standalone_type_label(container: Any) -> str:
        """
        Returns a type label for containers at the top level or inside lists
        (where there's no dict key).
        """
        if not show_type_labels:
            return ""
        if isinstance(container, dict):
            if not container:
                return " <dict>"
            val_types = set(type(v).__name__ for v in container.values())
            key_types = set(type(k).__name__ for k in container.keys())
            if len(val_types) == 1 and len(key_types) == 1:
                return f" <dict[{next(iter(key_types))} : {next(iter(val_types))}]>"
            return ""
        elif isinstance(container, (list, tuple)):
            container_type = type(container).__name__
            if not container:
                return f" <{container_type}>"
            val_types = set(type(v).__name__ for v in container)
            if len(val_types) == 1:
                return f" <{container_type}[{next(iter(val_types))}]>"
            return ""
        elif isinstance(container, (set, frozenset)):
            container_type = type(container).__name__
            if not container:
                return f" <{container_type}>"
            val_types = set(type(v).__name__ for v in container)
            if len(val_types) == 1:
                return f" <{container_type}[{next(iter(val_types))}]>"
            return ""
        return ""

    # Track seen objects for circular reference detection
    seen = set()

    def format_item(item: Any, level: int = 0, depth: int = 0, dict_key: str = None, is_top_level: bool = False) -> str:
        item_id = id(item)
        spaces = ' ' * (level * indent)
        next_spaces = ' ' * ((level + 1) * indent)

        # Track address for duplicate detection
        track_address(item)

        # Compute address suffix (suppressed for top-level and native types)
        item_addr = "" if is_top_level else addr_str(item)

        # Circular reference check
        if item_id in seen and isinstance(item, (dict, list, set)):
            return "<circular reference>"

        # --- Dataclass expansion ---
        if expand_dataclasses and is_dataclass_instance(item):
            dc_type_name = type(item).__name__
            fields = dataclasses.fields(item)
            if not fields:
                return f"{dc_type_name}(){item_addr}"
            if min_verbosity:
                lines = [f"{dc_type_name}{item_addr}"]
            else:
                lines = [f"{dc_type_name}{item_addr} {{"]
            hidden_count = 0
            leaf_count = 0
            for field in fields:
                v = getattr(item, field.name)
                is_leaf = not is_container_type(v) and not is_dataclass_instance(v)

                if not passes_dict_key_filter(field.name, is_leaf):
                    hidden_count += 1
                    continue

                if is_leaf and not passes_numerical_filter(v):
                    hidden_count += 1
                    continue

                if is_leaf and not passes_member_count_filter(leaf_count):
                    hidden_count += 1
                    continue
                leaf_count += 1 if is_leaf else 0

                type_label = get_homogeneous_type_label(field.name, v) if is_container_type(v) or is_dataclass_instance(v) else ""
                if show_type_labels and is_leaf and not type_label:
                    type_label = f" <{type(v).__name__}>"

                lines.append(f"{next_spaces}{field.name}{type_label}: {format_item(v, level + 1, depth + 1, dict_key=field.name)},")

            if hidden_count > 0:
                if len(lines) == 1:
                    return f"{dc_type_name}({len(fields)} fields, all hidden by filter)"
                lines.append(f"{next_spaces}... {hidden_count} hidden by filter")
            if not min_verbosity:
                lines.append(f"{spaces}}}")
            return '\n'.join(lines)

        # --- Numpy types ---
        if is_numpy_array(item):
            return format_numpy_array(item, level)

        # --- Blender types ---
        if is_blender_id(item):
            return format_blender_id(item, level)

        if is_blender_property_group(item):
            type_name = type(item).__name__
            name = getattr(item, 'name', None)
            return f"{type_name}('{name}')" if name else type_name

        if is_blender_collection(item):
            return format_blender_collection(item, level, depth)

        # --- Trim depth check for container types ---
        if max_depth_of_container_search > 0 and depth >= max_depth_of_container_search:
            if isinstance(item, (dict, list, tuple, set, frozenset)):
                return count_summary(item)
            if expand_dataclasses and is_dataclass_instance(item):
                dc_type_name = type(item).__name__
                return f"{dc_type_name}({len(dataclasses.fields(item))} fields)"

        # --- Dict ---
        if isinstance(item, dict):
            if not item:
                return "{}" if not min_verbosity else ""
            seen.add(item_id)
            type_label = get_standalone_type_label(item) if dict_key is None else ""
            if min_verbosity:
                header = f"{type_label}{item_addr}".strip()
                lines = [header] if header else [""]
            else:
                lines = [f"{{{type_label}{item_addr}".rstrip()]
            hidden_count = 0
            leaf_count = 0
            for k, v in item.items():
                is_leaf = not is_container_type(v) and not (expand_dataclasses and is_dataclass_instance(v))

                if not passes_dict_key_filter(k, is_leaf):
                    hidden_count += 1
                    continue

                # Numerical leaf filter
                if is_leaf and not passes_numerical_filter(v):
                    hidden_count += 1
                    continue

                if is_leaf and not passes_member_count_filter(leaf_count):
                    hidden_count += 1
                    continue
                leaf_count += 1 if is_leaf else 0

                key_str = f"'{k}'" if isinstance(k, str) else str(k)

                type_label_kv = ""
                if show_type_labels:
                    if is_container_type(v) or (expand_dataclasses and is_dataclass_instance(v)):
                        type_label_kv = get_homogeneous_type_label(k, v)
                    elif is_leaf:
                        type_label_kv = f" <{type(k).__name__} : {type(v).__name__}>"

                lines.append(f"{next_spaces}{key_str}{type_label_kv}: {format_item(v, level + 1, depth + 1, dict_key=k)},")

            if hidden_count > 0:
                no_content = (len(lines) == 1 and not min_verbosity) or (len(lines) == 0 and min_verbosity)
                if no_content:
                    seen.discard(item_id)
                    return f"dict({len(item)} keys, all hidden by filter)"
                lines.append(f"{next_spaces}... {hidden_count} hidden by filter")
            if not min_verbosity:
                lines.append(f"{spaces}}}")
            seen.discard(item_id)
            return '\n'.join(lines)

        # --- List / Tuple ---
        if isinstance(item, (list, tuple)):
            if not item:
                if min_verbosity:
                    return ""
                return "[]" if isinstance(item, list) else "()"
            bracket_open = "[" if isinstance(item, list) else "("
            bracket_close = "]" if isinstance(item, list) else ")"
            # Short native-type lists inline
            if len(item) <= 3 and all(is_native_type(x) for x in item):
                items = ", ".join(format_item(x, 0, depth + 1) for x in item)
                if min_verbosity:
                    return f"{items}"
                return f"{bracket_open}{items}{bracket_close}"
            seen.add(item_id)
            type_label = get_standalone_type_label(item) if dict_key is None else ""
            if min_verbosity:
                header = f"{type_label}{item_addr}".strip()
                lines = [header] if header else [""]
            else:
                lines = [f"{bracket_open}{type_label}{item_addr}".rstrip()]
            hidden_count = 0
            for i, v in enumerate(item):
                if not passes_member_count_filter(i):
                    hidden_count += 1
                    continue
                # Numerical leaf filter for list items
                if not is_container_type(v) and not (expand_dataclasses and is_dataclass_instance(v)):
                    if not passes_numerical_filter(v):
                        hidden_count += 1
                        continue
                lines.append(f"{next_spaces}{format_item(v, level + 1, depth + 1)},")
            if hidden_count > 0:
                lines.append(f"{next_spaces}... {hidden_count} hidden by filter")
            if not min_verbosity:
                lines.append(f"{spaces}{bracket_close}")
            seen.discard(item_id)
            return '\n'.join(lines)

        # --- Set / Frozenset ---
        if isinstance(item, (set, frozenset)):
            type_name = type(item).__name__
            if not item:
                if min_verbosity:
                    return ""
                return f"{type_name}()"
            if len(item) <= 3 and all(is_native_type(x) for x in item):
                items = ", ".join(format_item(x, 0, depth + 1) for x in item)
                if min_verbosity:
                    return items
                return f"{type_name}({{{items}}})"
            seen.add(item_id)
            if min_verbosity:
                header = f"{item_addr}".strip()
                lines = [header] if header else [""]
            else:
                lines = [f"{type_name}({{"]
            hidden_count = 0
            for i, v in enumerate(item):
                if not passes_member_count_filter(i):
                    hidden_count += 1
                    continue
                if not is_container_type(v) and not passes_numerical_filter(v):
                    hidden_count += 1
                    continue
                lines.append(f"{next_spaces}{format_item(v, level + 1, depth + 1)},")
            if hidden_count > 0:
                lines.append(f"{next_spaces}... {hidden_count} hidden by filter")
            if not min_verbosity:
                lines.append(f"{spaces}}})")
            seen.discard(item_id)
            return '\n'.join(lines)

        # --- Mathutils Vector ---
        if str(type(item)) == "<class 'mathutils.Vector'>":
            return f"Vector({', '.join(f'{coord:.3f}' for coord in item)})"

        # --- Mathutils Matrix ---
        if str(type(item)) == "<class 'mathutils.Matrix'>":
            return f"Matrix({item.row_size}x{item.col_size})"

        # --- Primitives (no memory address for native types) ---
        if isinstance(item, (int, float)):
            return str(item)

        if isinstance(item, str):
            return f"'{item}'"

        # --- Fallback ---
        result = str(item)
        result += item_addr
        return result

    if isinstance(raw_data_to_print, str):
        return raw_data_to_print

    filter_exclusion_dict_keys_list = create_simplified_list_from_csv_string(filter_exclusion_dict_keys_raw_str)
    filter_inclusion_dict_keys_list = create_simplified_list_from_csv_string(filter_inclusion_dict_keys_raw_str)

    string_lines = format_item(raw_data_to_print, is_top_level=True)
    string_lines += "\n"

    if min_verbosity and string_lines:
        string_lines = clean_json_string(string_lines)

    if len(string_lines) == 0:
        string_lines += "\nnothing to print"

    # --- Print memory duplicates ---
    if show_memory_duplicates:
        duplicates = {addr: (type_name, count) for addr, (type_name, count) in address_tracker.items() if count > 1}
        if duplicates:
            string_lines += f"\n\n--- Memory Address Duplicates in Data. This does not imply a problem ---"
            for addr, (type_name, count) in sorted(duplicates.items(), key=lambda x: x[1][1], reverse=True):
                string_lines += f"\n@{hex(addr)}  {type_name}  x{count}"
        
    return string_lines

# --------------------------------------------------------------
# Returns formatted data to print
# --------------------------------------------------------------

def extract_core_block_data_to_print(context, other_input):
    
    # --------------------------------------------------------------
    # Internal helper funcs
    # --------------------------------------------------------------
    
    def get_data_for_subscriber_hook_table(column_rename_map):
        
        reformatted_hooks_data = {}
        all_subscriber_hooks = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SUBSCRIBERS)
        for hook_func_name in all_subscriber_hooks:
            reformatted_hooks_data[hook_func_name] = {}
            for bhm in all_subscriber_hooks[hook_func_name]:
                
                # Reformat (RTC_Hook_Subscriber_Instance -> dict) & rename columns of hook data for printing
                if bhm.total_nanos_running_time == 0:
                    avg_ms_runtime = 0
                else:
                    avg_ms_runtime = (bhm.count_hook_propagate_success + bhm.count_hook_propagate_failure) / (bhm.total_nanos_running_time * 1000)
                raw_data = {
                    debug_sort_hooks_choice_items[0][0] : datetime.fromtimestamp(bhm.timestamp_ms_last_attempt/1000).strftime(("%Y-%m-%d %H:%M:%S.%f")),
                    debug_sort_hooks_choice_items[1][0] : not bhm.is_hook_enabled,
                    debug_sort_hooks_choice_items[2][0] : bhm.count_hook_propagate_success,
                    debug_sort_hooks_choice_items[3][0] : bhm.count_hook_propagate_failure,
                    debug_sort_hooks_choice_items[4][0] : bhm.count_bypass_via_data_filter,
                    debug_sort_hooks_choice_items[5][0] : bhm.count_bypass_via_status,
                    debug_sort_hooks_choice_items[6][0] : bhm.count_bypass_via_frequency,
                    debug_sort_hooks_choice_items[7][0] : avg_ms_runtime,
                }
                renamed_data = {column_rename_map.get(k, k): v for k, v in raw_data.items()}
                block_id = bhm.subscriber_block_module._BLOCK_ID
                reformatted_hooks_data[hook_func_name][block_id] = renamed_data
        
        return reformatted_hooks_data
    
    def get_data_for_unused_hooks_list():
        
        all_hook_subscribers = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SUBSCRIBERS)
        unused_hooks = [h for h in all_hook_subscribers if len(all_hook_subscribers[h]) == 0]
        if len(unused_hooks) == 0:
            return "No Unused Hooks"
        str_unused_hooks = "\n\nUnused Hooks:\n- " + "\n- ".join(unused_hooks)
        return str_unused_hooks
    
    # --------------------------------------------------------------
    # Main Func Logic
    # --------------------------------------------------------------
    
    debug_settings = context.scene.dgblocks_debug_console_print_props
    data_to_return = {}
    
    # Return unfiltered table string, of hook subscriber metadata
    if other_input == Core_Debugging_Print_Options.HOOK_SUBSCRIBERS:
        print_section_separator("All Hooks in Addon")
        
        column_rename_map = {item[0]: item[1] for item in debug_sort_hooks_choice_items}
        sort_key = column_rename_map[debug_settings.debug_block_hooks_table_sort_by]
        formatted_data = get_data_for_subscriber_hook_table(column_rename_map)
        
        data_to_return = "\n"
        data_to_return += make_table_string_from_data(formatted_data, sort_key = sort_key)
        data_to_return += get_data_for_unused_hooks_list()
             
    # Return entire runtime cache
    elif other_input == Core_Debugging_Print_Options.ALL_BLOCKS_RTC_MEMBERS:
        print_section_separator(f"All Runtime Cache Data")
        data_to_return = Wrapper_Runtime_Cache._cache
    
    # Return JSON representation of all current-scene properties related to Blocks
    elif other_input == Core_Debugging_Print_Options.ALL_BLOCKS_BL_SCENE_PROPS:
        print_section_separator(f"All Scene-Owned Addon data")
        data_to_return = get_members_and_values_of_propertygroup_with_name_prefix(context.scene, "dgblock")
        
    # elif other_input == Core_Debugging_Print_Options.ALL_BLOCKS_BL_PREFERENCES_PROPS:
    #     print_section_separator(f"All Scene-Owned Addon data")
    #     prefs = get_addon_preferences(context)
    #     data_to_return = get_members_and_values_of_propertygroup_with_name_prefix(prefs, "dgblock")

    else:
        data_to_return = ""

    return data_to_return

# --------------------------------------------------------------
# UI-Draw funcs
# --------------------------------------------------------------

def uilayout_draw_core_block_console_print_panel(context:bpy.context, container:bpy.types.UILayout, block_id:str):
    
    debug_settings = context.scene.dgblocks_debug_console_print_props
    button_scale = 1.5
    
    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "All Hook Data (Table, Unfiltered)")
    op.source_block_id = block_id
    op.other_input = Core_Debugging_Print_Options.HOOK_SUBSCRIBERS
    split = box.split()
    row_l = split.row()
    row_r = split.row()
    # row_l.label(text = "Sort by")
    row_l.prop(debug_settings, "debug_block_hooks_table_sort_by") 
    # row_r.prop(debug_settings, "debug_block_hooks_table_include_unused") 

    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "All RTC Data (JSON, Filtered)")
    op.source_block_id = block_id
    op.other_input = Core_Debugging_Print_Options.ALL_BLOCKS_RTC_MEMBERS
    
    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "BL-Scene Data (JSON, Filtered)")
    op.source_block_id = block_id
    op.other_input = Core_Debugging_Print_Options.ALL_BLOCKS_BL_SCENE_PROPS
    
    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "BL-Preferences Data (JSONified, Filtered)")
    op.source_block_id = block_id
    op.other_input = Core_Debugging_Print_Options.ALL_BLOCKS_BL_PREFERENCES_PROPS

    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "UNIT TESTS")
    op.source_block_id = "TEST"

def uilayout_draw_debug_settings(context:bpy.context, container:bpy.types.UILayout):
    
    debug_props = context.scene.dgblocks_debug_console_print_props
    
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_print_console", default_closed=True)
    panel_header.label(text = f"Print {core_block_id.upper()} State")
    if panel_body is not None:  
        uilayout_draw_core_block_console_print_panel(context, panel_body, core_block_id)



    # Call drawing functions in downstrean blocks which are hooked for function hook_debug_uilayout_draw_console_print_settings
    # Each block can have it's own presentation logic, so block-core passes the UILayout (internal_panel_body) to each block hook to allow those blocks to contribute to this current draw call
    
    hook_func_name = Block_Hook_Sources.DEBUG_UI_DRAW_FOR_BLOCK_CONSOLE_PRINT
    all_blocks_metadata_for_hook = Wrapper_Hooks.get_instance(hook_func_name) # get_hooked_blocks_metadata_for_func(hook_func_name
    for idx, block_hook_metadata in enumerate(all_blocks_metadata_for_hook):
        # if idx > 0:
        uilayout_section_separator(container, extra_space = 0)
        block_id = block_hook_metadata.subscriber_block_module._BLOCK_ID
        internal_panel_header, internal_panel_body = container.panel(idname = f"_dummy_dgblocks_console_print_{block_id}", default_closed = True)
        internal_panel_header.alignment = "CENTER"
        internal_panel_header.label(text = f"Print {block_id.upper()} State")
        if internal_panel_body: 
            Wrapper_Hooks.run_hooked_funcs(
                hook_func_name = hook_func_name, 
                specific_subscriber_block_id = block_id, 
                context = context,
                container = internal_panel_body
            )







    # For console prints  
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_print_console_t2", default_closed=True)
    panel_header.label(text = "Filter settings")
    if panel_body is not None:  
        
        # General Settings
        internal_panel_header, internal_panel_body = panel_body.panel(idname = f"_dummy_dgblocks_general_console_print_settings", default_closed = True)
        internal_panel_header.alignment = "CENTER"
        internal_panel_header.label(text = f"General Settings")
        if internal_panel_body:
            grid = internal_panel_body.grid_flow(columns=2)
            box_l = grid.box()
            box_l.prop(debug_props, "debug_console_print_should_clear_previous_output")
            box_l.prop(debug_props, "debug_console_print_min_verbosity")
            box_l.prop(debug_props, "debug_console_print_json_indent_width")
            box_r = grid.box()
            box_r.prop(debug_props, "debug_console_print_include_memory_address")
            box_r.prop(debug_props, "debug_console_print_include_data_type")
            
        uilayout_section_separator(panel_body, extra_space = 0)
        
        # Key Filtering
        inclusion_filter_keys = create_simplified_list_from_csv_string(debug_props.debug_console_print_filter_key_to_include)
        inclusion_filter_on = len(inclusion_filter_keys) > 0 and debug_props.debug_console_print_filter_key_inclusion_level != "OFF"
        exclusion_filter_keys = create_simplified_list_from_csv_string(debug_props.debug_console_print_filter_key_to_exclude)
        exclusion_filter_on = len(exclusion_filter_keys) > 0 and debug_props.debug_console_print_filter_key_exclusion_level != "OFF"
        internal_panel_header, internal_panel_body = panel_body.panel(idname = f"_dummy_dgblocks_filter_console_print_keys", default_closed = True)
        internal_panel_header.alignment = "CENTER"
        internal_panel_header.label(text = f"Filter by Dict Keys")
        internal_panel_header.label(text = "", icon = "HIDE_OFF" if (inclusion_filter_on or exclusion_filter_on) else "HIDE_ON")
        if internal_panel_body:
            draw_wrapped_text_v2(context, internal_panel_body, "Use Comma-Separated Wildcards Strings. Whitespace & capitilization are ignored. Only dicts will be filtered, tables & lists are untouched")
            box = internal_panel_body.box()
            grid = box.grid_flow(columns=2)
            include_filter_icon = "HIDE_OFF" if inclusion_filter_on > 0 else "HIDE_ON"
            row = grid.row()
            row.alignment = "CENTER"
            row.label(text = "Keys to Include")
            row.label(text = "", icon = include_filter_icon)
            grid.prop(debug_props, "debug_console_print_filter_key_to_include", text = "")
            grid.prop(debug_props, "debug_console_print_filter_key_inclusion_level", text = "")
            exclude_filter_icon = "HIDE_OFF" if exclusion_filter_on > 0 else "HIDE_ON"
            row = grid.row()
            row.alignment = "CENTER"
            row.label(text = "Keys to Exclude")
            row.label(text = "", icon = exclude_filter_icon)
            grid.prop(debug_props, "debug_console_print_filter_key_to_exclude", text = "")
            grid.prop(debug_props, "debug_console_print_filter_key_exclusion_level", text = "")
               
        uilayout_section_separator(panel_body, extra_space = 0)    
            
        # Data Filtering
        has_container_filter = debug_props.debug_console_print_filter_data_max_rows_in_each_container > 0 or debug_props.debug_console_print_depth_to_truncate > 0
        has_numeric_filter = debug_props.debug_console_print_data_numeric_filter_level != "OFF"
        internal_panel_header, internal_panel_body = panel_body.panel(idname = f"_dummy_dgblocks_filter_console_print_values", default_closed = True)
        internal_panel_header.alignment = "CENTER"
        internal_panel_header.label(text = f"Filter by Data")
        internal_panel_header.label(text = "", icon = "HIDE_OFF" if (has_container_filter or has_numeric_filter) else "HIDE_ON")
        if internal_panel_body:
            box = ui_box_with_header(context, internal_panel_body, ["Structural (list / set / dict) Filters", "Disabled when = 0"], icon = "HIDE_OFF" if has_container_filter > 0 else "HIDE_ON")
            grid = box.grid_flow(columns=2)
            grid.prop(debug_props, "debug_console_print_filter_data_max_rows_in_each_container")
            grid.prop(debug_props, "debug_console_print_depth_to_truncate")
            box = ui_box_with_header(context, internal_panel_body, "Numerical Data Filter", icon = "HIDE_OFF" if has_numeric_filter > 0 else "HIDE_ON")
            grid = box.grid_flow(columns=3)
            grid.alignment = "EXPAND"
            include_filter_icon = "HIDE_OFF" if inclusion_filter_on > 0 else "HIDE_ON"
            grid.prop(debug_props, "debug_console_print_data_numeric_filter_level", text = "")
            grid.prop(debug_props, "debug_console_print_data_numeric_filter_operation", text = "")
            grid.prop(debug_props, "debug_console_print_data_numeric_filter_value", text = "")
            
        uilayout_section_separator(panel_body, extra_space = 0)

