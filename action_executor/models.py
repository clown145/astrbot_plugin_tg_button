"""Data models used by the ActionExecutor runtime."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class RuntimeContext:
    """Information describing the current execution context for an action."""

    chat_id: str
    chat_type: Optional[str] = None
    message_id: Optional[int] = None
    thread_id: Optional[int] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    callback_data: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ActionExecutionResult:
    """Aggregated result produced by executing a single action."""

    success: bool
    should_edit_message: bool = False
    new_text: Optional[str] = None
    parse_mode: Optional[str] = None
    next_menu_id: Optional[str] = None
    error: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    button_title: Optional[str] = None
    button_overrides: List[Dict[str, Any]] = field(default_factory=list)
    notification: Optional[Dict[str, Any]] = None
    web_app_launch: Optional[Dict[str, Any]] = None
    new_message_chain: Optional[List[Any]] = None
    temp_files_to_clean: List[str] = field(default_factory=list)
