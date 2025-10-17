"""Utility helpers shared across ActionExecutor modules."""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import ActionExecutionResult


def map_parse_mode(alias: Optional[str]) -> Optional[str]:
    """Normalize user-provided parse mode aliases to Telegram parse modes."""

    if alias is None:
        return None
    normalized = str(alias).strip().lower()
    if normalized in {"markdown", "md"}:
        return "Markdown"
    if normalized in {"markdownv2", "mdv2"}:
        return "MarkdownV2"
    if normalized == "html":
        return "HTML"
    return None


def coerce_to_bool(value: Any) -> bool:
    """Convert a templated return value into a boolean flag."""

    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "0", "false", "none", "null", "no", "off"}:
            return False
        return True
    return bool(value)


def topological_sort_nodes(
    nodes: Dict[str, Any],
    edges: Iterable[Any],
) -> Tuple[List[str], Optional[str]]:
    """Perform a Kahn topological sort over workflow nodes."""

    adjacency: Dict[str, List[str]] = {node_id: [] for node_id in nodes}
    in_degree: Dict[str, int] = {node_id: 0 for node_id in nodes}

    for edge in edges:
        source_node = getattr(edge, "source_node", None)
        target_node = getattr(edge, "target_node", None)
        if source_node in adjacency and target_node in in_degree:
            adjacency[source_node].append(target_node)
            in_degree[target_node] += 1

    queue: deque[str] = deque(node_id for node_id, count in in_degree.items() if count == 0)
    execution_order: List[str] = []

    while queue:
        current = queue.popleft()
        execution_order.append(current)
        for neighbor in adjacency.get(current, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(execution_order) != len(nodes):
        processed = set(execution_order)
        cycle_nodes = [node_id for node_id in nodes if node_id not in processed]
        error_msg = "执行失败: 检测到循环依赖。涉及节点: {}".format(
            ", ".join(cycle_nodes)
        )
        return [], error_msg

    return execution_order, None


def merge_workflow_node_result(
    result: ActionExecutionResult,
    final_result: ActionExecutionResult,
    final_text_parts: List[str],
) -> None:
    """Merge the effect of a node execution into the aggregated workflow result."""

    if result.new_message_chain is not None:
        final_result.new_message_chain = result.new_message_chain
        final_result.new_text = None
        final_result.should_edit_message = False
        final_text_parts.clear()

    if result.web_app_launch is not None:
        final_result.web_app_launch = result.web_app_launch

    if final_result.new_message_chain is None:
        if result.new_text is not None:
            final_text_parts.append(result.new_text)
        if result.next_menu_id is not None:
            final_result.next_menu_id = result.next_menu_id
        if result.parse_mode and result.new_text:
            final_result.parse_mode = result.parse_mode

    if result.notification is not None:
        final_result.notification = result.notification

    if result.button_overrides:
        final_result.button_overrides.extend(result.button_overrides)

    if result.button_title:
        final_result.button_title = result.button_title
