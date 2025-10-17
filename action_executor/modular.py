"""Execution helpers for modular (web-defined) actions."""
from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from .models import ActionExecutionResult, RuntimeContext
from .utils import map_parse_mode

if TYPE_CHECKING:  # pragma: no cover - optional type imports
    from ..main import DynamicButtonFrameworkPlugin
    from ..modular_actions import ModularAction


class ModularActionExecutor:
    """Execute modular actions registered through the WebUI."""

    def __init__(self, *, logger) -> None:
        self._logger = logger

    async def execute(
        self,
        plugin: "DynamicButtonFrameworkPlugin",
        action: "ModularAction",
        *,
        runtime: RuntimeContext,
        preview: bool,
        input_params: Dict[str, Any],
    ) -> ActionExecutionResult:
        action_name = action.name
        if preview:
            return ActionExecutionResult(
                success=True, new_text=f"此为模块化动作 '{action_name}' 的预览。"
            )

        params_to_pass: Dict[str, Any] = {}
        missing_params = []
        for input_def in action.inputs:
            input_name = input_def["name"]
            if input_name in input_params:
                params_to_pass[input_name] = input_params[input_name]
            elif "default" in input_def:
                params_to_pass[input_name] = input_def["default"]
            elif input_def.get("required", False):
                missing_params.append(input_name)

        if missing_params:
            error_msg = (
                f"执行模块化动作 '{action_name}' 失败: 缺少输入参数: "
                + ", ".join(missing_params)
            )
            self._logger.error(error_msg)
            return ActionExecutionResult(success=False, error=error_msg)

        try:
            import inspect

            signature = inspect.signature(action.execute)
            if "plugin" in signature.parameters:
                params_to_pass["plugin"] = plugin
            if "runtime" in signature.parameters:
                params_to_pass["runtime"] = runtime

            result_dict = await action.execute(**params_to_pass)
            if not isinstance(result_dict, dict):
                self._logger.warning(
                    "模块化动作 '%s' 的返回值不是一个字典，已忽略。", action_name
                )
                result_dict = {}

            output_variables = {
                key: value
                for key, value in result_dict.items()
                if key
                not in {
                    "new_text",
                    "parse_mode",
                    "next_menu_id",
                    "button_overrides",
                    "notification",
                    "new_message_chain",
                    "temp_files_to_clean",
                    "button_title",
                }
            }

            return ActionExecutionResult(
                success=True,
                should_edit_message=bool(
                    result_dict.get("new_text")
                    or result_dict.get("next_menu_id")
                    or result_dict.get("button_overrides")
                    or result_dict.get("button_title")
                ),
                new_text=result_dict.get("new_text"),
                parse_mode=map_parse_mode(result_dict.get("parse_mode", "html")),
                next_menu_id=result_dict.get("next_menu_id"),
                button_overrides=result_dict.get("button_overrides", []),
                button_title=result_dict.get("button_title"),
                notification=result_dict.get("notification"),
                new_message_chain=result_dict.get("new_message_chain"),
                temp_files_to_clean=result_dict.get("temp_files_to_clean", []),
                data={"variables": output_variables},
            )
        except Exception as exc:  # pragma: no cover - narrow scope
            self._logger.error(
                "执行模块化动作 '%s' 失败: %s", action_name, exc, exc_info=True
            )
            return ActionExecutionResult(
                success=False, error=f"执行模块化动作 '{action_name}' 时发生错误: {exc}"
            )
