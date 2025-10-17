"""Execution support for local (Python) actions."""
from __future__ import annotations

import asyncio
import functools
from typing import Any, Dict, TYPE_CHECKING

from .models import ActionExecutionResult, RuntimeContext
from .templating import TemplateEngine
from .utils import map_parse_mode

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from ..main import ActionRegistry, DynamicButtonFrameworkPlugin


class LocalActionExecutor:
    """Execute registered local Python actions."""

    def __init__(
        self,
        *,
        registry: "ActionRegistry",
        template_engine: TemplateEngine,
        logger,
    ) -> None:
        self._registry = registry
        self._template_engine = template_engine
        self._logger = logger

    async def execute(
        self,
        plugin: "DynamicButtonFrameworkPlugin",
        action: Dict[str, Any],
        *,
        button: Dict[str, Any],
        menu: Dict[str, Any],
        runtime: RuntimeContext,
        preview: bool = False,
    ) -> ActionExecutionResult:
        action_name = action.get("config", {}).get("name")
        if not action_name:
            return ActionExecutionResult(success=False, error="本地动作配置缺少 name 字段")

        registered_action = self._registry.get(action_name)
        if not registered_action:
            return ActionExecutionResult(
                success=False, error=f"未注册的本地动作: '{action_name}'"
            )

        if preview:
            return ActionExecutionResult(
                success=True, new_text=f"此为本地动作 '{action_name}' 的预览。"
            )

        base_context = self._template_engine.build_context(
            action=action,
            button=button,
            menu=menu,
            runtime=runtime,
            variables=runtime.variables,
        )

        params: Dict[str, Any] = {}
        param_config = action.get("config", {}).get("parameters", {})
        try:
            params = await self._template_engine.render_structure(
                param_config, base_context
            )
            if not isinstance(params, dict):
                return ActionExecutionResult(
                    success=False, error="渲染后的动作参数必须是一个字典"
                )
        except Exception as exc:
            return ActionExecutionResult(
                success=False, error=f"渲染本地动作参数失败: {exc}"
            )

        try:
            import inspect

            if inspect.iscoroutinefunction(registered_action.function):
                result = await registered_action.function(plugin, runtime=runtime, **params)
            else:
                func_to_run = functools.partial(
                    registered_action.function, plugin, runtime=runtime, **params
                )
                result = await asyncio.to_thread(func_to_run)

            if not isinstance(result, dict):
                self._logger.warning(
                    "本地动作 '%s' 的返回值不是一个字典，已忽略。", action_name
                )
                result = {}

            return ActionExecutionResult(
                success=True,
                should_edit_message=bool(result.get("new_text")),
                new_text=result.get("new_text"),
                parse_mode=map_parse_mode(result.get("parse_mode", "html")),
                next_menu_id=result.get("next_menu_id"),
                button_overrides=result.get("button_overrides", []),
                notification=result.get("notification"),
                new_message_chain=result.get("new_message_chain"),
                temp_files_to_clean=result.get("temp_files_to_clean", []),
                data={
                    "variables": result.get("variables", {})
                },
                button_title=result.get("button_title"),
            )
        except Exception as exc:
            self._logger.error(
                "执行本地动作 '%s' 失败: %s", action_name, exc, exc_info=True
            )
            return ActionExecutionResult(
                success=False, error=f"执行本地动作 '{action_name}' 时发生错误: {exc}"
            )
