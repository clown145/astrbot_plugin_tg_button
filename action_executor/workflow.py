"""Workflow execution support for ActionExecutor."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from .models import ActionExecutionResult, RuntimeContext
from .templating import TemplateEngine
from .utils import coerce_to_bool, merge_workflow_node_result, topological_sort_nodes

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from ..storage import ButtonsModel, WorkflowEdge, WorkflowNode
    from ..main import DynamicButtonFrameworkPlugin, ModularActionRegistry
    from .http import HTTPActionExecutor
    from .local import LocalActionExecutor
    from .modular import ModularActionExecutor


class WorkflowRunner:
    """Coordinate the execution of workflow-based actions."""

    def __init__(
        self,
        *,
        logger,
        modular_registry: "ModularActionRegistry",
        template_engine: TemplateEngine,
        http_executor: "HTTPActionExecutor",
        local_executor: "LocalActionExecutor",
        modular_executor: "ModularActionExecutor",
    ) -> None:
        self._logger = logger
        self._modular_registry = modular_registry
        self._template_engine = template_engine
        self._http_executor = http_executor
        self._local_executor = local_executor
        self._modular_executor = modular_executor

    async def run(
        self,
        plugin: "DynamicButtonFrameworkPlugin",
        action: Dict[str, Any],
        *,
        button: Dict[str, Any],
        menu: Dict[str, Any],
        runtime: RuntimeContext,
        preview: bool = False,
    ) -> ActionExecutionResult:
        workflow_id = action.get("config", {}).get("workflow_id")
        if not workflow_id:
            return ActionExecutionResult(
                success=False, error="工作流动作配置缺少 workflow_id"
            )

        if preview:
            return ActionExecutionResult(
                success=True, new_text=f"此为工作流 ‘{workflow_id}’ 的预览。"
            )

        snapshot = await plugin.button_store.get_snapshot()
        workflow_data = snapshot.workflows.get(workflow_id)
        if not workflow_data:
            return ActionExecutionResult(
                success=False, error=f"未找到 ID 为 ‘{workflow_id}’ 的工作流"
            )

        nodes = workflow_data.nodes
        edges = workflow_data.edges
        if not nodes:
            return ActionExecutionResult(success=True, new_text="工作流为空，执行完成。")

        self._logger.info("开始执行工作流 ‘%s’", workflow_id)

        execution_order, error_msg = topological_sort_nodes(nodes, edges)
        if error_msg:
            full_error = f"工作流 ‘{workflow_id}’ 执行失败: {error_msg}"
            self._logger.error(full_error)
            return ActionExecutionResult(success=False, error=full_error)

        node_outputs: Dict[str, Dict[str, Any]] = {}
        final_result = ActionExecutionResult(success=True)
        final_text_parts: List[str] = []
        global_variables = dict(runtime.variables)
        files_to_clean: List[str] = []

        for node_id in execution_order:
            node_def = nodes[node_id]
            result, node_error = await self._execute_node(
                plugin,
                workflow_id,
                node_id,
                node_def,
                snapshot,
                button,
                menu,
                runtime,
                global_variables,
                node_outputs,
                edges,
                preview,
            )

            if node_error:
                return ActionExecutionResult(success=False, error=node_error)
            if not result:
                err_msg = f"工作流 ‘{workflow_id}’ 在节点 ‘{node_id}’ 执行后未收到有效结果。"
                self._logger.error(err_msg)
                return ActionExecutionResult(success=False, error=err_msg)

            if result.temp_files_to_clean:
                files_to_clean.extend(result.temp_files_to_clean)

            if result.data and isinstance(result.data.get("variables"), dict):
                node_outputs[node_id] = result.data["variables"]
                global_variables.update(result.data["variables"])
            else:
                node_outputs[node_id] = {}

            merge_workflow_node_result(result, final_result, final_text_parts)

        if final_text_parts and final_result.new_message_chain is None:
            final_result.new_text = "\n".join(final_text_parts)

        final_result.should_edit_message = (
            bool(
                final_result.new_text
                or final_result.next_menu_id
                or final_result.button_overrides
                or final_result.button_title
            )
            and not final_result.new_message_chain
        )
        final_result.data = {"variables": global_variables}
        final_result.success = True
        final_result.temp_files_to_clean = files_to_clean

        self._logger.info("工作流 ‘%s’ 执行完毕。", workflow_id)
        return final_result

    async def _execute_node(
        self,
        plugin: "DynamicButtonFrameworkPlugin",
        workflow_id: str,
        node_id: str,
        node_def: "WorkflowNode",
        snapshot: "ButtonsModel",
        button: Dict[str, Any],
        menu: Dict[str, Any],
        runtime: RuntimeContext,
        global_variables: Dict[str, Any],
        node_outputs: Dict[str, Dict[str, Any]],
        edges: List["WorkflowEdge"],
        preview: bool,
    ) -> Tuple[Optional[ActionExecutionResult], Optional[str]]:
        action_id = node_def.action_id
        if not action_id:
            self._logger.warning("  -> 跳过节点 '%s'，因为它没有设置 action_id。", node_id)
            return ActionExecutionResult(success=True, data={"variables": {}}), None

        found_action = self._find_action_definition(action_id, snapshot)
        if not found_action:
            error_msg = (
                f"在节点 ‘{node_id}’ 执行失败: 未找到 ID 为 '{action_id}' 的动作定义。"
            )
            return None, error_msg

        self._logger.info(
            "  -> 执行节点 ‘%s’ (动作: '%s', 类型: '%s')",
            node_id,
            action_id,
            found_action["kind"],
        )

        input_params: Dict[str, Any] = dict(node_def.data)
        condition_cfg = input_params.pop("__condition__", None)

        for edge in edges:
            if edge.target_node == node_id:
                source_node = edge.source_node
                source_output_name = edge.source_output
                target_input_name = edge.target_input

                if (
                    source_node in node_outputs
                    and source_output_name in node_outputs[source_node]
                ):
                    input_params[target_input_name] = node_outputs[source_node][
                        source_output_name
                    ]
                else:
                    self._logger.warning(
                        "      - 输入 '%s' 的值无法从上游节点 '%s' 的输出 '%s' 中找到。",
                        target_input_name,
                        source_node,
                        source_output_name,
                    )

        current_runtime_dict = runtime.__dict__.copy()
        current_runtime_dict["variables"] = global_variables
        current_runtime = RuntimeContext(**current_runtime_dict)

        try:
            render_context = self._template_engine.build_context(
                action=node_def.data,
                button=button,
                menu=menu,
                runtime=current_runtime,
                variables=global_variables,
            )

            rendered_params = await self._template_engine.render_structure(
                input_params, render_context
            )
            if not isinstance(rendered_params, dict):
                rendered_params = {}

            condition_context = dict(render_context)
            condition_context.setdefault("inputs", rendered_params)

            should_execute, condition_error = await self._evaluate_node_condition(
                condition_cfg,
                node_id=node_id,
                condition_context=condition_context,
            )
            if condition_error:
                return None, condition_error
            if not should_execute:
                self._logger.info("      - 节点 ‘%s’ 的执行条件未满足，跳过。", node_id)
                return ActionExecutionResult(success=True, data={"variables": {}}), None

            kind = found_action["kind"]
            definition = found_action["definition"]
            result: Optional[ActionExecutionResult]

            if kind == "modular":
                result = await self._modular_executor.execute(
                    plugin,
                    definition,
                    runtime=current_runtime,
                    preview=preview,
                    input_params=rendered_params,
                )
            elif kind == "local":
                current_runtime.variables.update(rendered_params)
                result = await self._local_executor.execute(
                    plugin,
                    definition,
                    button=button,
                    menu=menu,
                    runtime=current_runtime,
                    preview=preview,
                )
            elif kind == "http":
                current_runtime.variables.update(rendered_params)
                result = await self._http_executor.execute(
                    definition,
                    button=button,
                    menu=menu,
                    runtime=current_runtime,
                    preview=preview,
                )
            elif kind == "workflow":
                raise RuntimeError("不支持嵌套工作流。")
            else:
                raise RuntimeError(f"不支持的动作类型 '{kind}'。")

            if not result or not result.success:
                raise RuntimeError(result.error if result else "未知错误")

            return result, None
        except Exception as exc:
            error_msg = f"在节点 ‘{action_id}’ 遇到意外错误: {exc}"
            self._logger.error(
                "工作流 ‘%s’ %s", workflow_id, error_msg, exc_info=True
            )
            return None, error_msg

    def _find_action_definition(
        self, action_id: str, snapshot: "ButtonsModel"
    ) -> Optional[Dict[str, Any]]:
        modular_action = self._modular_registry.get(action_id)
        if modular_action:
            return {"kind": "modular", "definition": modular_action}

        legacy_action = snapshot.actions.get(action_id)
        if legacy_action:
            return {"kind": legacy_action.kind, "definition": legacy_action.to_dict()}

        return None

    async def _evaluate_node_condition(
        self,
        condition_cfg: Any,
        *,
        node_id: str,
        condition_context: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        if not isinstance(condition_cfg, dict):
            return True, None

        mode = str(condition_cfg.get("mode", "always") or "always").lower()
        if mode in ("", "always"):
            return True, None
        if mode == "never":
            return False, None

        if "inputs" not in condition_context:
            condition_context["inputs"] = {}

        try:
            if mode == "expression":
                expression = str(condition_cfg.get("expression", ""))
                if not expression.strip():
                    self._logger.warning(
                        "节点 ‘%s’ 配置了空的表达式条件，视为 False。",
                        node_id,
                    )
                    return False, None
                rendered = await self._template_engine.render_template(
                    expression, condition_context
                )
                return coerce_to_bool(rendered), None

            if mode == "linked":
                link_cfg = condition_cfg.get("link") or {}
                template = link_cfg.get("template")
                rendered_value: Any = None
                if template:
                    rendered_value = await self._template_engine.render_template(
                        str(template), condition_context
                    )
                else:
                    target_key = link_cfg.get("target_input") or link_cfg.get(
                        "target_input_port"
                    )
                    inputs = condition_context.get("inputs", {})
                    if isinstance(inputs, dict) and target_key in inputs:
                        rendered_value = inputs.get(target_key)
                return coerce_to_bool(rendered_value), None

            self._logger.warning(
                "节点 ‘%s’ 使用了未知的条件模式 '%s'，默认继续执行。",
                node_id,
                mode,
            )
            return True, None
        except Exception as exc:
            error_msg = f"节点 ‘{node_id}’ 的条件计算失败: {exc}"
            self._logger.error(error_msg, exc_info=True)
            return False, error_msg
