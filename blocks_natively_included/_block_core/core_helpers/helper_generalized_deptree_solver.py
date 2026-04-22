from dataclasses import dataclass
from enum import Enum, auto
from graphlib import TopologicalSorter


class DisableReason(Enum):
    NONE = auto()
    MANUALLY_DISABLED = auto()
    SELF_INVALID = auto()
    DEPENDENCY_INVALID = auto()


@dataclass
class NodeStatus:
    is_enabled: bool
    disable_reason: DisableReason
    failed_dependencies: list[str]


def solve_hierarchy(nodes: dict[str, dict]) -> dict[str, NodeStatus]:
    """
    Resolve enable/disable status for a hierarchy of nodes.
    
    Args:
        nodes: Dict mapping node_id -> node_dict, where each node_dict has:
            - is_self_disabled: bool
            - is_block_valid: bool
            - dependencies: list[str] (node IDs this depends on)
    
    Returns:
        Dict mapping node_id -> NodeStatus
    """
    # Build dependency graph and get processing order
    graph = {node_id: set(node.get("dependencies", [])) for node_id, node in nodes.items()}
    order = list(TopologicalSorter(graph).static_order())
    
    results: dict[str, NodeStatus] = {}
    
    for node_id in order:
        node = nodes[node_id]
        
        # Check manual disable
        if node["is_self_disabled"]:
            results[node_id] = NodeStatus(
                is_enabled=False,
                disable_reason=DisableReason.MANUALLY_DISABLED,
                failed_dependencies=[],
            )
            continue
        
        # Check self validity
        if not node["is_block_valid"]:
            results[node_id] = NodeStatus(
                is_enabled=False,
                disable_reason=DisableReason.SELF_INVALID,
                failed_dependencies=[],
            )
            continue
        
        # Check dependencies (already processed due to topo order)
        failed_deps = [
            dep_id
            for dep_id in node.get("dependencies", [])
            if not results[dep_id].is_enabled
        ]
        
        if failed_deps:
            results[node_id] = NodeStatus(
                is_enabled=False,
                disable_reason=DisableReason.DEPENDENCY_INVALID,
                failed_dependencies=failed_deps,
            )
            continue
        
        # All checks passed
        results[node_id] = NodeStatus(
            is_enabled=True,
            disable_reason=DisableReason.NONE,
            failed_dependencies=[],
        )
    
    return results


def determine_activation_updates(nodes: dict[str, dict]):
    """
    Find nodes whose resolved state differs from their current is_dependency_chain_valid.
    
    - to_disable: nodes currently marked valid but should be disabled
    - to_enable: nodes currently marked invalid but should be enabled
    """
    resolved = solve_hierarchy(nodes)
    
    to_enable = [
        node_id
        for node_id, status in resolved.items()
        if status.is_enabled and not nodes[node_id]["is_dependency_chain_valid"]
    ]
    
    to_disable = [
        node_id
        for node_id, status in resolved.items()
        if not status.is_enabled and nodes[node_id]["is_dependency_chain_valid"]
    ]
    
    return to_enable, to_disable