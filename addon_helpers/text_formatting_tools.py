
import sys
import dataclasses
import time
from typing import Any, Optional
import bpy # type: ignore


# Addon-level imports
from .data_tools import create_simplified_list_from_csv_string


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
                f"sort_key '{sort_key}' not found in leaf Dict Keys Filter. "
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

# ==============================================================================================================================
# PRETTY-PRINT — two-pass architecture
#
# Pass 1 (prune): walk the raw data into an intermediate `_Node` tree, applying every filter
#                 (dict-key include/exclude with ancestor retention, numeric/string leaf data
#                 filters, depth truncation, max-row limits). All "how many were filtered"
#                 counting lives here.
# Pass 2 (render): walk the `_Node` tree into a string. Pure formatting, no filter logic.
# ==============================================================================================================================

class _Node:
    """Intermediate pruned-tree node consumed by the render pass."""
    __slots__ = (
        "kind",                 # "dict" | "dataclass" | "list" | "tuple" | "set" | "leaf" | "summary"
        "obj",                  # original python object (for type labels, addr, size, len)
        "children",             # list[ (orig_index:int, key:Any|None, child:_Node) ]
        "total_count",          # original member count (pre-filter)
        "filtered_count",       # how many direct members were removed
        "show_indices",         # render original member indices (container was filtered)
        "subtree_has_include",  # this node's key matched include, or a descendant did
        "summary",              # precomputed one-line string (summary nodes only)
        "is_truncated",         # summary node produced by depth truncation
    )

    def __init__(self, kind, obj):
        self.kind = kind
        self.obj = obj
        self.children = []
        self.total_count = 0
        self.filtered_count = 0
        self.show_indices = False
        self.subtree_has_include = True
        self.summary = ""
        self.is_truncated = False


def make_pretty_json_string_from_data(
        raw_data_to_print,
        filter_keys_enabled: bool = False,
        filter_inclusion_dict_keys_raw_str: str = "",
        filter_exclusion_dict_keys_raw_str: str = "",
        numeric_filter_enabled: bool = False,
        numeric_filter_mode: str = "INCLUDE",   # "INCLUDE" | "EXCLUDE"
        numeric_filters: Optional[list] = None,  # list[(op:str, value:float)] — AND-combined
        string_filter_enabled: bool = False,
        string_filter_mode: str = "INCLUDE",    # "INCLUDE" | "EXCLUDE"
        string_filters: Optional[list] = None,   # list[(op:str, text:str)] — OR-combined
        min_verbosity: bool = False,
        show_type_labels: bool = False,
        show_memory_address: bool = False,
        show_memory_duplicates: bool = False,
        show_memory_size: bool = False,
        show_filter_indices: bool = True,
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

    STRING_OPS = {
        "contains":   lambda v, t: t in v,
        "equals":     lambda v, t: v == t,
        "startswith": lambda v, t: v.startswith(t),
        "endswith":   lambda v, t: v.endswith(t),
    }

    numeric_filters = numeric_filters or []
    string_filters = string_filters or []

    exclude_list = create_simplified_list_from_csv_string(filter_exclusion_dict_keys_raw_str)
    include_list = create_simplified_list_from_csv_string(filter_inclusion_dict_keys_raw_str)
    exclude_list = [f.lower() for f in exclude_list]
    include_list = [f.lower() for f in include_list]

    # Active-state flags computed once.
    key_exclude_active = filter_keys_enabled and bool(exclude_list)
    key_include_active = filter_keys_enabled and bool(include_list)
    numeric_on = bool(numeric_filter_enabled)
    string_on = bool(string_filter_enabled)
    data_filter_active = numeric_on or string_on

    # Memory address tracker: addr -> (type_name, count)
    address_tracker: dict[int, tuple[str, int]] = {}

    def is_primitive_type(item: Any) -> bool:
        """True for simple value types that should never carry memory annotations.

        Covers native Python scalars, mathutils.Vector, and numpy arrays.
        """
        if isinstance(item, str):# and item == "block_core":
            pass
        if is_native_type(item):
            return True
        if is_mathutils_vector(item):
            return True
        if is_numpy_array(item):
            return True
        return False

    def track_address(item: Any) -> None:
        """Record an object's address and type for duplicate detection."""
        if not show_memory_duplicates:
            return
        if is_primitive_type(item):
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

    def is_mathutils_vector(item: Any) -> bool:
        t = type(item)
        return t.__module__ == "mathutils" and t.__name__ == "Vector"

    def is_mathutils_matrix(item: Any) -> bool:
        t = type(item)
        return t.__module__ == "mathutils" and t.__name__ == "Matrix"

    def numeric_magnitude(value: Any) -> Optional[float]:
        """Numeric scalar for a leaf, or None if the value is not a 1-D number.

        Plain ints/floats pass through; mathutils.Vector and 1-D numpy arrays
        collapse to their magnitude; bools, None, matrices and >1-D arrays => None.
        """
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if is_mathutils_vector(value):
            try:
                return float(value.magnitude)
            except Exception:
                try:
                    return float(sum(c * c for c in value)) ** 0.5
                except Exception:
                    return None
        if is_numpy_array(value):
            try:
                import numpy as np
                if value.ndim == 1:
                    return float(np.linalg.norm(value))
            except Exception:
                return None
            return None
        return None

    def classify_leaf(value: Any):
        """Returns ('numeric', float) | ('string', str) | ('other', None)."""
        if isinstance(value, str):
            return ("string", value)
        mag = numeric_magnitude(value)
        if mag is not None:
            return ("numeric", mag)
        return ("other", None)

    def numeric_set_pass(fval: float) -> bool:
        applicable = [(op, val) for op, val in numeric_filters if op in NUMERICAL_OPS]
        base = all(NUMERICAL_OPS[op](fval, float(val)) for op, val in applicable)  # AND-combined
        return (not base) if numeric_filter_mode == "EXCLUDE" else base

    def string_set_pass(sval: str) -> bool:
        applicable = [(op, t) for op, t in string_filters if op in STRING_OPS]
        if not applicable:
            base = True
        else:
            low = sval.lower()
            base = any(STRING_OPS[op](low, str(t).lower()) for op, t in applicable)  # OR-combined
        return (not base) if string_filter_mode == "EXCLUDE" else base

    def leaf_passes_data_filter(value: Any) -> bool:
        """Leaf-only number/string data filter with the agreed join semantics.

        - No active data filter => everything passes.
        - Each leaf is judged by its own type: numeric leaves by the numeric set,
          string leaves by the string set.
        - A leaf whose type has no active filter is dropped (e.g. strings when only
          the numeric filter is on); 'other' leaves (objects that can't be printed)
          are always dropped while any data filter is active.
        """
        if not data_filter_active:
            return True
        kind, val = classify_leaf(value)
        if kind == "numeric" and numeric_on:
            return numeric_set_pass(val)
        if kind == "string" and string_on:
            return string_set_pass(val)
        return False

    def key_excluded(key: Any) -> bool:
        if not key_exclude_active or key is None:
            return False
        kl = str(key).lower()
        return any(f in kl for f in exclude_list)

    def key_matches_include(key: Any) -> bool:
        if not key_include_active or key is None:
            return False
        kl = str(key).lower()
        return any(f in kl for f in include_list)

    def node_kind(value: Any) -> Optional[str]:
        """Kind for recursing containers, else None (leaf-like / summary object)."""
        if isinstance(value, dict):
            return "dict"
        if expand_dataclasses and is_dataclass_instance(value):
            return "dataclass"
        if isinstance(value, list):
            return "list"
        if isinstance(value, tuple):
            return "tuple"
        if isinstance(value, (set, frozenset)):
            return "set"
        return None

    def is_keyed_kind(kind: str) -> bool:
        return kind in ("dict", "dataclass")

    def container_len(item: Any, kind: str) -> int:
        if kind == "dataclass":
            return len(dataclasses.fields(item))
        return len(item)

    def iter_items(item: Any, kind: str):
        """Yields (key, value); key is None for unkeyed containers (list/tuple/set)."""
        if kind == "dict":
            return list(item.items())
        if kind == "dataclass":
            return [(f.name, getattr(item, f.name)) for f in dataclasses.fields(item)]
        return [(None, x) for x in item]

    def deep_sizeof(obj: Any, _seen: set = None) -> int:
        if _seen is None:
            _seen = set()
        oid = id(obj)
        if oid in _seen:
            return 0
        _seen.add(oid)
        try:
            size = sys.getsizeof(obj)
        except Exception:
            size = 0
        try:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    size += deep_sizeof(k, _seen) + deep_sizeof(v, _seen)
            elif isinstance(obj, (list, tuple, set, frozenset)):
                for x in obj:
                    size += deep_sizeof(x, _seen)
            elif expand_dataclasses and is_dataclass_instance(obj):
                for f in dataclasses.fields(obj):
                    size += deep_sizeof(getattr(obj, f.name), _seen)
        except Exception:
            pass
        return size

    def size_str(obj: Any) -> str:
        """KB summary suffix. Shown on leaves (own size) and containers (deep size)."""
        if not show_memory_size:
            return ""
        try:
            kb = deep_sizeof(obj) / 1024.0
        except Exception:
            return ""
        return f" ~{kb:.2f}KB"


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
        Skips primitive types (native scalars, mathutils.Vector, numpy arrays)."""
        if not show_memory_address:
            return ""
        if is_primitive_type(item):
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

    # ------------------------------------------------------------------
    # PASS 1 — prune raw data into a filtered _Node tree
    # ------------------------------------------------------------------
    prune_seen = set()

    def shallow_filtered_count(item, kind) -> int:
        """Count direct members a one-level filter pass would drop. Used to annotate
        depth-truncated containers; never recurses below the truncation point."""
        cnt = 0
        keyed = is_keyed_kind(kind)
        for k, v in iter_items(item, kind):
            if key_excluded(k):
                cnt += 1
                continue
            if node_kind(v) is None:  # leaf-like only — no recursion
                if data_filter_active and not leaf_passes_data_filter(v):
                    cnt += 1
                    continue
                if key_include_active and keyed and not key_matches_include(k):
                    cnt += 1
                    continue
        return cnt

    def prune(item, depth, key):
        # Key-level blacklist drops the whole entry (and its subtree).
        if key_excluded(key):
            return None

        self_inc = key_matches_include(key)
        track_address(item)
        kind = node_kind(item)

        # --- leaf-like value / unprintable object ---
        if kind is None:
            if data_filter_active and not leaf_passes_data_filter(item):
                return None
            if is_native_type(item) or is_mathutils_vector(item) or is_numpy_array(item):
                node = _Node("leaf", item)
            else:
                node = _Node("summary", item)  # blender id / collection / matrix / etc.
            node.subtree_has_include = self_inc
            return node

        # --- container ---
        oid = id(item)
        if oid in prune_seen:
            node = _Node("summary", item)
            node.summary = "<circular reference>"
            node.subtree_has_include = self_inc
            return node

        # Depth truncation: summarise, count one shallow level, do not recurse.
        if max_depth_of_container_search > 0 and depth >= max_depth_of_container_search:
            node = _Node("summary", item)
            node.is_truncated = True
            node.total_count = container_len(item, kind)
            node.filtered_count = shallow_filtered_count(item, kind)
            node.subtree_has_include = self_inc
            return node

        prune_seen.add(oid)
        node = _Node(kind, item)
        keyed = is_keyed_kind(kind)
        total = container_len(item, kind)
        kept = []
        filtered = 0
        any_child_inc = False
        for orig_index, (k, v) in enumerate(iter_items(item, kind)):
            child = prune(v, depth + 1, k if keyed else None)
            if child is None:
                filtered += 1
                continue
            if child.subtree_has_include:
                any_child_inc = True
            kept.append((orig_index, k, child))

        node_inc = self_inc or any_child_inc

        # Include whitelist drops keyed children that have no match anywhere in their
        # subtree (ancestor retention: a branch survives if any descendant key matched).
        if key_include_active and keyed:
            retained = []
            for entry in kept:
                if entry[2].subtree_has_include:
                    retained.append(entry)
                else:
                    filtered += 1
            kept = retained

        # Max-rows cap (general setting).
        if max_rows_of_each_container > 0 and len(kept) > max_rows_of_each_container:
            filtered += len(kept) - max_rows_of_each_container
            kept = kept[:max_rows_of_each_container]

        prune_seen.discard(oid)

        node.children = kept
        node.total_count = total
        node.filtered_count = filtered
        node.show_indices = (filtered > 0) and show_filter_indices
        node.subtree_has_include = node_inc
        return node

    # ------------------------------------------------------------------
    # PASS 2 — render the pruned _Node tree to a string
    # ------------------------------------------------------------------
    def collapsed_summary(obj, total, filtered, kind) -> str:
        if kind == "dict":
            name, unit = "dict", "keys"
        elif kind == "dataclass":
            name, unit = type(obj).__name__, "fields"
        elif kind == "set":
            name, unit = type(obj).__name__, "items"
        else:  # list / tuple
            name, unit = kind, "items"
        if filtered > 0:
            return f"{name}({total} {unit}, {filtered} filtered)"
        return f"{name}({total} {unit})"

    def other_summary_str(obj, level) -> str:
        if is_numpy_array(obj):
            return format_numpy_array(obj, level)
        if is_blender_id(obj):
            return format_blender_id(obj, level)
        if is_blender_property_group(obj):
            name = getattr(obj, 'name', None)
            return f"{type(obj).__name__}('{name}')" if name else type(obj).__name__
        if is_blender_collection(obj):
            return format_blender_collection(obj, level, 0)
        if is_mathutils_matrix(obj):
            return f"Matrix({obj.row_size}x{obj.col_size})"
        return str(obj)

    def leaf_repr(obj, level) -> str:
        if is_primitive_type(obj):
            mem = ""
        else:
            mem = f"{addr_str(obj)}{size_str(obj)}"
        if isinstance(obj, str):
            return f"'{obj}'{mem}"
        if isinstance(obj, bool):
            return f"{obj}{mem}"
        if obj is None:
            return f"None{mem}"
        if isinstance(obj, (int, float)):
            return f"{obj}{mem}"
        if is_mathutils_vector(obj):
            return f"Vector({', '.join(f'{c:.3f}' for c in obj)}){mem}"
        if is_numpy_array(obj):
            return f"{format_numpy_array(obj, level)}{mem}"
        return f"{str(obj)}{mem}"

    def child_type_label(key, child) -> str:
        if not show_type_labels:
            return ""
        v = child.obj
        if child.kind in ("dict", "dataclass", "list", "tuple", "set"):
            return get_homogeneous_type_label(key, v)
        return f" <{type(key).__name__} : {type(v).__name__}>"

    def emit_children(node, level) -> list:
        next_spaces = ' ' * ((level + 1) * indent)
        out = []
        keyed = is_keyed_kind(node.kind)
        for orig_index, k, child in node.children:
            idx_prefix = f"[{orig_index}] " if node.show_indices else ""
            if keyed:
                key_str = f"'{k}'" if isinstance(k, str) else str(k)
                out.append(f"{next_spaces}{idx_prefix}{key_str}{child_type_label(k, child)}: {render(child, level + 1)},")
            else:
                out.append(f"{next_spaces}{idx_prefix}{render(child, level + 1)},")
        if node.filtered_count > 0:
            out.append(f"{next_spaces}... {node.filtered_count} filtered")
        return out

    def render(node, level) -> str:
        spaces = ' ' * (level * indent)
        obj = node.obj

        if node.kind == "leaf":
            return leaf_repr(obj, level)

        if node.kind == "summary":
            if node.is_truncated:
                return collapsed_summary(obj, node.total_count, node.filtered_count, node_kind(obj)) + size_str(obj)
            if node.summary:
                return node.summary
            return f"{other_summary_str(obj, level)}{addr_str(obj)}{size_str(obj)}"

        header_suffix = f"{addr_str(obj)}{size_str(obj)}"

        # Empty / fully-filtered containers collapse to a single line.
        if not node.children:
            if node.total_count == 0:
                if node.kind == "dict":
                    return "{}"
                if node.kind in ("dataclass", "set"):
                    return f"{type(obj).__name__}()"
                return "[]" if node.kind == "list" else "()"
            return collapsed_summary(obj, node.total_count, node.filtered_count, node.kind)

        if node.kind == "dict":
            lines = [f"{{{get_standalone_type_label(obj)}{header_suffix}".rstrip()]
            lines += emit_children(node, level)
            lines.append(spaces + "}")
            return '\n'.join(lines)

        if node.kind == "dataclass":
            lines = [f"{type(obj).__name__}{header_suffix} {{".rstrip()]
            lines += emit_children(node, level)
            lines.append(spaces + "}")
            return '\n'.join(lines)

        if node.kind in ("list", "tuple"):
            open_b = "[" if node.kind == "list" else "("
            close_b = "]" if node.kind == "list" else ")"
            # Inline short native lists when nothing was filtered.
            if (not node.show_indices and node.filtered_count == 0 and len(node.children) <= 3
                    and all(c.kind == "leaf" and is_native_type(c.obj) for _, _, c in node.children)):
                inline = ", ".join(render(c, 0) for _, _, c in node.children)
                return f"{open_b}{inline}{close_b}"
            lines = [f"{open_b}{get_standalone_type_label(obj)}{header_suffix}".rstrip()]
            lines += emit_children(node, level)
            lines.append(spaces + close_b)
            return '\n'.join(lines)

        # set / frozenset
        lines = [f"{type(obj).__name__}({{{header_suffix}".rstrip()]
        lines += emit_children(node, level)
        lines.append(spaces + "})")
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Driver
    # ------------------------------------------------------------------
    if isinstance(raw_data_to_print, str):
        return raw_data_to_print

    root = prune(raw_data_to_print, depth=0, key=None)
    if root is None:
        string_lines = "\nnothing to print"
    else:
        string_lines = render(root, 0) + "\n"

    if min_verbosity and string_lines:
        string_lines = clean_json_string(string_lines)

    if len(string_lines.strip()) == 0:
        string_lines = "\nnothing to print"

    # --- Print memory duplicates ---
    if show_memory_duplicates:
        duplicates = {addr: (type_name, count) for addr, (type_name, count) in address_tracker.items() if count > 1}
        if duplicates:
            string_lines += f"\n\n--- Memory Address Duplicates in Data. This does not imply a problem ---"
            for addr, (type_name, count) in sorted(duplicates.items(), key=lambda x: x[1][1], reverse=True):
                string_lines += f"\n@{hex(addr)}  {type_name}  x{count}"

    return string_lines


