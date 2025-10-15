import json
import functools
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .main import (
        ActionRegistry,
        DynamicButtonFrameworkPlugin,
        ModularActionRegistry,
    )

from urllib.parse import quote_plus

import httpx
from jinja2 import Environment, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

try:
    import jmespath
except ImportError:  # 可选依赖
    jmespath = None

try:
    from jsonpath_ng import parse as jsonpath_parse  # type: ignore
except ImportError:  # 可选依赖
    jsonpath_parse = None


@dataclass
class RuntimeContext:
    chat_id: str
    chat_type: Optional[str] = None
    message_id: Optional[int] = None
    thread_id: Optional[int] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    callback_data: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionExecutionResult:
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
    new_message_chain: Optional[list] = None
    temp_files_to_clean: List[str] = field(default_factory=list)


class ActionExecutor:
    def __init__(
        self,
        *,
        logger,
        registry: "ActionRegistry",
        modular_registry: "ModularActionRegistry",
    ):
        self._logger = logger
        self._registry = registry
        self._modular_registry = modular_registry
        self._template_env = SandboxedEnvironment(
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )
        self._template_env.filters["tojson"] = lambda value: json.dumps(
            value, ensure_ascii=False
        )
        self._template_env.filters["urlencode"] = lambda value: quote_plus(str(value))
        self._template_env.filters["zip"] = zip
        self._http_client: Optional[httpx.AsyncClient] = None

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

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
        kind = action.get("kind", "http")
        if kind == "http":
            return await self._execute_http(
                action, button=button, menu=menu, runtime=runtime, preview=preview
            )
        if kind == "local":
            return await self._execute_local(
                plugin,
                action,
                button=button,
                menu=menu,
                runtime=runtime,
                preview=preview,
            )
        if kind == "workflow":
            return await self._execute_workflow(
                plugin,
                action,
                button=button,
                menu=menu,
                runtime=runtime,
                preview=preview,
            )
        return ActionExecutionResult(success=False, error=f"未知的动作类型: {kind}")

    def _find_action_definition(
        self, action_id: str, snapshot: "ButtonsModel"
    ) -> Optional[Dict[str, Any]]:
        """从模块化动作或旧版动作中查找动作定义。"""
        # 优先匹配模块化动作
        modular_action = self._modular_registry.get(action_id)
        if modular_action:
            # 对于模块化动作，其“定义”就是 ModularAction 对象本身
            return {"kind": "modular", "definition": modular_action}

        # 回退到存储在状态文件中的旧版动作
        legacy_action = snapshot.actions.get(action_id)
        if legacy_action:
            # 对于旧版动作，其“定义”是字典表示形式
            return {"kind": legacy_action.kind, "definition": legacy_action.to_dict()}

        return None

    async def _execute_modular(
        self,
        plugin: "DynamicButtonFrameworkPlugin",
        action: "ModularAction",
        *,
        runtime: RuntimeContext,
        preview: bool = False,
        input_params: Dict[str, Any],
    ) -> ActionExecutionResult:
        """执行一个新的模块化动作。"""
        action_name = action.name
        if preview:
            return ActionExecutionResult(
                success=True, new_text=f"此为模块化动作 '{action_name}' 的预览。"
            )

        # 收集最终参数，并应用默认值
        params_to_pass = {}
        missing_params = []
        for input_def in action.inputs:
            input_name = input_def["name"]
            if input_name in input_params:
                params_to_pass[input_name] = input_params[input_name]
            elif "default" in input_def:
                params_to_pass[input_name] = input_def["default"]
            # Only consider a parameter missing if it's explicitly marked as required and not provided.
            elif input_def.get("required", False):
                missing_params.append(input_name)

        if missing_params:
            error_msg = f"执行模块化动作 '{action_name}' 失败: 缺少输入参数: {', '.join(missing_params)}"
            self._logger.error(error_msg)
            return ActionExecutionResult(success=False, error=error_msg)

        try:
            import inspect

            sig = inspect.signature(action.execute)
            if "plugin" in sig.parameters:
                params_to_pass["plugin"] = plugin
            if "runtime" in sig.parameters:
                params_to_pass["runtime"] = runtime

            # 执行动作的异步函数
            result_dict = await action.execute(**params_to_pass)

            if not isinstance(result_dict, dict):
                self._logger.warning(
                    f"模块化动作 '{action_name}' 的返回值不是一个字典，已忽略。"
                )
                result_dict = {}

            # 动作的返回字典可以包含用于 UI 效果的特殊键，
            # 任何其他键都被视为输出变量。
            output_variables = {
                key: value
                for key, value in result_dict.items()
                if key
                not in [
                    "new_text",
                    "parse_mode",
                    "next_menu_id",
                    "button_overrides",
                    "notification",
                    "new_message_chain",
                    "temp_files_to_clean",
                ]
            }

            return ActionExecutionResult(
                success=True,
                should_edit_message=bool(result_dict.get("new_text")),
                new_text=result_dict.get("new_text"),
                parse_mode=self._map_parse_mode(result_dict.get("parse_mode", "html")),
                next_menu_id=result_dict.get("next_menu_id"),
                button_overrides=result_dict.get("button_overrides", []),
                notification=result_dict.get("notification"),
                new_message_chain=result_dict.get("new_message_chain"),
                temp_files_to_clean=result_dict.get("temp_files_to_clean", []),
                data={"variables": output_variables},
            )
        except Exception as exc:
            self._logger.error(
                f"执行模块化动作 '{action_name}' 失败: {exc}", exc_info=True
            )
            return ActionExecutionResult(
                success=False, error=f"执行模块化动作 '{action_name}' 时发生错误: {exc}"
            )

    def _topological_sort_nodes(
        self, nodes: Dict[str, Any], edges: List[Any]
    ) -> Tuple[List[str], Optional[str]]:
        """
        对工作流节点进行拓扑排序（卡恩算法）。
        :return: 一个元组 (execution_order, error_message)。如果成功，error_message 为 None。
        """
        adj: Dict[str, List[str]] = {node_id: [] for node_id in nodes}
        in_degree: Dict[str, int] = {node_id: 0 for node_id in nodes}

        for edge in edges:
            source_node = edge.source_node
            target_node = edge.target_node
            if source_node in adj and target_node in in_degree:
                adj[source_node].append(target_node)
                in_degree[target_node] += 1

        queue = [node_id for node_id in nodes if in_degree[node_id] == 0]
        exec_order = []
        while queue:
            u = queue.pop(0)
            exec_order.append(u)
            for v in adj.get(u, []):
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(exec_order) != len(nodes):
            processed_nodes = set(exec_order)
            cycle_nodes = [
                node_id for node_id in nodes if node_id not in processed_nodes
            ]
            error_msg = f"执行失败: 检测到循环依赖。涉及节点: {', '.join(cycle_nodes)}"
            return [], error_msg

        return exec_order, None

    def _merge_workflow_node_result(
        self,
        result: "ActionExecutionResult",
        final_result: "ActionExecutionResult",
        final_text_parts: List[str],
    ) -> None:
        """将单个工作流节点的执行结果合并到最终结果中。"""
        # 1. 处理互斥的“终结”操作 (如发送新消息)，它们会重置其他UI更新
        if result.new_message_chain is not None:
            final_result.new_message_chain = result.new_message_chain
            final_result.new_text = None
            final_result.should_edit_message = False
            final_text_parts.clear()  # 清空旧文本

        if result.web_app_launch is not None:
            final_result.web_app_launch = result.web_app_launch

        # 2. 聚合可组合的UI效果 (当没有终结操作时)
        if final_result.new_message_chain is None:
            if result.new_text is not None:
                final_text_parts.append(result.new_text)
            if result.next_menu_id is not None:
                final_result.next_menu_id = result.next_menu_id
            # 使用最后一个提供文本的节点的解析模式
            if result.parse_mode and result.new_text:
                final_result.parse_mode = result.parse_mode

        # 3. 累加所有可累加/覆盖的项
        if result.notification is not None:
            final_result.notification = result.notification  # 弹窗，最后一个有效

        if result.button_overrides:
            final_result.button_overrides.extend(
                result.button_overrides
            )  # 按钮覆盖，全部累加

    async def _execute_workflow_node(
        self,
        plugin: "DynamicButtonFrameworkPlugin",
        workflow_id: str,
        node_id: str,
        node_def: Any,  # WorkflowNode
        snapshot: "ButtonsModel",
        button: Dict[str, Any],
        menu: Dict[str, Any],
        runtime: "RuntimeContext",
        global_variables: Dict[str, Any],
        node_outputs: Dict[str, Dict[str, Any]],
        edges: List[Any],  # List[WorkflowEdge]
        preview: bool,
    ) -> Tuple[Optional["ActionExecutionResult"], Optional[str]]:
        """执行单个工作流节点并返回结果。"""
        action_id = node_def.action_id
        if not action_id:
            self._logger.warning(
                f"  -> 跳过节点 '{node_id}'，因为它没有设置 action_id。"
            )
            return ActionExecutionResult(success=True, data={"variables": {}}), None

        found_action = self._find_action_definition(action_id, snapshot)
        if not found_action:
            error_msg = (
                f"在节点 ‘{node_id}’ 执行失败: 未找到 ID 为 '{action_id}' 的动作定义。"
            )
            return None, error_msg

        self._logger.info(
            f"  -> 执行节点 ‘{node_id}’ (动作: '{action_id}', 类型: '{found_action['kind']}')"
        )

        # 为当前节点收集输入参数
        input_params: Dict[str, Any] = {}
        input_params.update(node_def.data)

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
                        f"      - 输入 '{target_input_name}' 的值无法从上游节点 '{source_node}' 的输出 '{source_output_name}' 中找到。"
                    )

        current_runtime_dict = runtime.__dict__.copy()
        current_runtime_dict["variables"] = global_variables
        current_runtime = RuntimeContext(**current_runtime_dict)

        try:
            kind = found_action["kind"]
            definition = found_action["definition"]
            result: Optional[ActionExecutionResult] = None

            if kind == "modular":
                render_context = self._build_template_context(
                    action=node_def.data,
                    button=button,
                    menu=menu,
                    runtime=current_runtime,
                    variables=global_variables,
                )
                rendered_params = await self._arender_structure(
                    input_params, render_context
                )
                result = await self._execute_modular(
                    plugin,
                    definition,
                    runtime=current_runtime,
                    preview=preview,
                    input_params=rendered_params,
                )
            elif kind == "local":
                current_runtime.variables.update(input_params)
                result = await self._execute_local(
                    plugin,
                    definition,
                    button=button,
                    menu=menu,
                    runtime=current_runtime,
                    preview=preview,
                )
            elif kind == "http":
                current_runtime.variables.update(input_params)
                result = await self._execute_http(
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
            self._logger.error(f"工作流 ‘{workflow_id}’ {error_msg}", exc_info=True)
            return None, error_msg

    async def _execute_workflow(
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

        # 1. 从数据快照加载工作流定义
        snapshot = await plugin.button_store.get_snapshot()
        workflow_data = snapshot.workflows.get(workflow_id)
        if not workflow_data:
            return ActionExecutionResult(
                success=False, error=f"未找到 ID 为 ‘{workflow_id}’ 的工作流"
            )

        # 直接访问 WorkflowDefinition 对象的属性
        nodes = workflow_data.nodes
        edges = workflow_data.edges

        if not nodes:
            return ActionExecutionResult(
                success=True, new_text="工作流为空，执行完成。"
            )

        self._logger.info(f"开始执行工作流 ‘{workflow_id}’")

        # 2. 对节点进行拓扑排序
        exec_order, error_msg = self._topological_sort_nodes(nodes, edges)
        if error_msg:
            full_error_msg = f"工作流 ‘{workflow_id}’ 执行失败: {error_msg}"
            self._logger.error(full_error_msg)
            return ActionExecutionResult(success=False, error=full_error_msg)

        # 3. 按顺序执行节点
        node_outputs: Dict[str, Dict[str, Any]] = {}  # 格式: {节点ID: {输出名称: 值}}
        final_result = ActionExecutionResult(success=True)
        final_text_parts = []
        global_variables = dict(runtime.variables)
        files_to_clean_in_workflow: List[str] = []

        for node_id in exec_order:
            node_def = nodes[node_id]
            result, error_msg = await self._execute_workflow_node(
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

            # 如果节点执行失败，则立即终止整个工作流
            if error_msg:
                return ActionExecutionResult(success=False, error=error_msg)

            # 如果节点执行成功，但没有返回有效结果，这是一个意外情况，也应终止
            if not result:
                err_msg = (
                    f"工作流 ‘{workflow_id}’ 在节点 ‘{node_id}’ 执行后未收到有效结果。"
                )
                self._logger.error(err_msg)
                return ActionExecutionResult(success=False, error=err_msg)

            # 更新工作流级别的状态
            if result.temp_files_to_clean:
                files_to_clean_in_workflow.extend(result.temp_files_to_clean)

            if result.data and isinstance(result.data.get("variables"), dict):
                node_outputs[node_id] = result.data["variables"]
                global_variables.update(result.data["variables"])
            else:
                node_outputs[node_id] = {}

            # 将节点结果合并到最终的工作流结果中
            self._merge_workflow_node_result(result, final_result, final_text_parts)

        # --- MODIFICATION START ---
        # 组装最终文本 (仅当没有新消息链时)
        if final_text_parts and final_result.new_message_chain is None:
            final_result.new_text = "\n".join(final_text_parts)

        # 确定是否需要编辑消息 (有新文本、新菜单或按钮覆盖，且不是发送新消息时)
        final_result.should_edit_message = (
            bool(
                final_result.new_text
                or final_result.next_menu_id
                or final_result.button_overrides
            )
            and not final_result.new_message_chain
        )
        # --- MODIFICATION END ---
        final_result.data = {"variables": global_variables}
        final_result.success = True  # 如果执行到这里，代表工作流成功
        final_result.temp_files_to_clean = files_to_clean_in_workflow

        self._logger.info(f"工作流 ‘{workflow_id}’ 执行完毕。")
        return final_result

    async def _execute_local(
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
            return ActionExecutionResult(
                success=False, error="本地动作配置缺少 name 字段"
            )

        registered_action = self._registry.get(action_name)
        if not registered_action:
            return ActionExecutionResult(
                success=False, error=f"未注册的本地动作: '{action_name}'"
            )

        if preview:
            return ActionExecutionResult(
                success=True, new_text=f"此为本地动作 '{action_name}' 的预览。"
            )

        base_context = self._build_template_context(
            action=action,
            button=button,
            menu=menu,
            runtime=runtime,
            variables=runtime.variables,
        )

        params = {}
        param_config = action.get("config", {}).get("parameters", {})
        try:
            params = await self._arender_structure(param_config, base_context)
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
                result = await registered_action.function(
                    plugin, runtime=runtime, **params
                )
            else:
                import asyncio

                # Create a partial function with all arguments pre-filled
                func_to_run = functools.partial(
                    registered_action.function, plugin, runtime=runtime, **params
                )
                # Run the synchronous function in a separate thread to avoid blocking the event loop.
                result = await asyncio.to_thread(func_to_run)

            if not isinstance(result, dict):
                self._logger.warning(
                    f"本地动作 '{action_name}' 的返回值不是一个字典，已忽略。"
                )
                result = {}

            return ActionExecutionResult(
                success=True,
                should_edit_message=bool(result.get("new_text")),
                new_text=result.get("new_text"),
                parse_mode=self._map_parse_mode(result.get("parse_mode", "html")),
                next_menu_id=result.get("next_menu_id"),
                button_overrides=result.get("button_overrides", []),
                notification=result.get("notification"),
                new_message_chain=result.get("new_message_chain"),
                temp_files_to_clean=result.get("temp_files_to_clean", []),
                data={
                    "variables": result.get("variables", {})
                },  # 这是用于状态传递的关键字段
            )
        except Exception as exc:
            self._logger.error(
                f"执行本地动作 '{action_name}' 失败: {exc}", exc_info=True
            )
            return ActionExecutionResult(
                success=False, error=f"执行本地动作 '{action_name}' 时发生错误: {exc}"
            )

    def _build_template_context(
        self,
        *,
        action: Dict[str, Any],
        button: Dict[str, Any],
        menu: Dict[str, Any],
        runtime: RuntimeContext,
        response: Optional[httpx.Response] = None,
        extracted: Any = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        resp_payload: Dict[str, Any] = {}
        if response is not None:
            resp_payload = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "text": response.text,
            }
            try:
                resp_payload["json"] = response.json()
            except Exception:
                resp_payload["json"] = None

        return {
            "action": action,
            "button": button,
            "menu": menu,
            "runtime": runtime.__dict__,
            "response": resp_payload,
            "extracted": extracted,
            "variables": variables or {},
        }

    async def _arender_template(
        self, template_str: str, context: Dict[str, Any]
    ) -> str:
        if not template_str:
            return ""

        # Jinja2's render is synchronous and can be CPU-bound.
        # We run it in an executor to avoid blocking the event loop.
        template = self._template_env.from_string(template_str)
        func_to_run = functools.partial(template.render, **context)
        import asyncio

        return await asyncio.to_thread(func_to_run)

    async def _arender_structure(self, value: Any, context: Dict[str, Any]) -> Any:
        import asyncio

        if isinstance(value, str):
            return await self._arender_template(value, context)
        if isinstance(value, list):
            # Concurrently render all items in the list
            tasks = [self._arender_structure(item, context) for item in value]
            return await asyncio.gather(*tasks)
        if isinstance(value, dict):
            # Concurrently render all values in the dict
            keys = list(value.keys())
            tasks = [self._arender_structure(value[key], context) for key in keys]
            rendered_values = await asyncio.gather(*tasks)
            return dict(zip(keys, rendered_values))
        return value

    async def _arender_button_overrides(
        self, overrides_cfg: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        import asyncio

        rendered: List[Dict[str, Any]] = []
        for entry in overrides_cfg or []:
            if not isinstance(entry, dict):
                continue

            try:
                # 1. Collect all templates
                templates_to_render: Dict[str, str] = {}

                # Field templates
                template_fields = {
                    "text": entry.get("text_template"),
                    "callback_data": entry.get("callback_template"),
                    "url": entry.get("url_template"),
                    "switch_inline_query": entry.get("switch_inline_query_template"),
                    "switch_inline_query_current_chat": entry.get(
                        "switch_inline_query_current_chat_template"
                    ),
                }
                if entry.get("web_app_url_template"):
                    templates_to_render["web_app_url"] = str(
                        entry["web_app_url_template"]
                    )
                for field, template_value in template_fields.items():
                    if template_value:
                        templates_to_render[field] = str(template_value)

                # Layout templates
                layout_cfg = entry.get("layout")
                if isinstance(layout_cfg, dict):
                    if "row" in layout_cfg:
                        templates_to_render["layout_row"] = str(layout_cfg["row"])
                    if "col" in layout_cfg:
                        templates_to_render["layout_col"] = str(layout_cfg["col"])

                # 2. Render all concurrently
                rendered_parts: Dict[str, Any] = {}
                if templates_to_render:
                    keys = list(templates_to_render.keys())
                    tasks = [
                        self._arender_template(templates_to_render[key], context)
                        for key in keys
                    ]
                    values = await asyncio.gather(*tasks, return_exceptions=True)
                    for key, value in zip(keys, values):
                        if not isinstance(value, Exception):
                            rendered_parts[key] = value
                        else:
                            self._logger.warning(
                                f"Failed to render template for override key '{key}': {value}"
                            )

                # 3. Assemble result
                result: Dict[str, Any] = {
                    "target": entry.get("target", "self"),
                    "temporary": bool(entry.get("temporary", True)),
                }
                result.update(rendered_parts)

                # Direct pass fields
                for field in ("type", "action_id", "menu_id", "web_app_id"):
                    if field in entry and entry[field]:
                        result[field] = entry[field]
                # Static values
                for field in ("text", "callback_data", "url"):
                    if field not in result and entry.get(field):
                        result[field] = entry[field]

                # Assemble layout
                rendered_layout: Dict[str, Any] = {}
                if "layout_row" in result:
                    try:
                        rendered_layout["row"] = int(result.pop("layout_row"))
                    except (ValueError, TypeError):
                        pass
                if "layout_col" in result:
                    try:
                        rendered_layout["col"] = int(result.pop("layout_col"))
                    except (ValueError, TypeError):
                        pass
                if rendered_layout:
                    result["layout"] = rendered_layout

                rendered.append(
                    {
                        key: value
                        for key, value in result.items()
                        if value not in (None, "")
                    }
                )

            except Exception as exc:  # Defensive logging
                self._logger.error(f"渲染按钮覆盖配置失败: {exc}", exc_info=True)
        return rendered

    async def _get_http_client(self) -> httpx.AsyncClient:
        if not self._http_client:
            self._http_client = httpx.AsyncClient(http2=False, follow_redirects=True)
        return self._http_client

    async def _execute_http(
        self,
        action: Dict[str, Any],
        *,
        button: Dict[str, Any],
        menu: Dict[str, Any],
        runtime: RuntimeContext,
        preview: bool = False,
    ) -> ActionExecutionResult:
        config = action.get("config", {}) or {}
        request_cfg = config.get("request")
        if not isinstance(request_cfg, dict):
            request_cfg = {
                "method": config.get("method", "GET"),
                "url": config.get("url"),
                "headers": config.get("headers"),
                "body": config.get("body"),
                "timeout": config.get("timeout", 10),
            }
        base_context = self._build_template_context(
            action=action,
            button=button,
            menu=menu,
            runtime=runtime,
            variables=runtime.variables,
        )
        try:
            method = str(request_cfg.get("method", "GET") or "GET").upper()
            url_template = request_cfg.get("url") or ""
            if not url_template:
                return ActionExecutionResult(
                    success=False, error="HTTP 动作缺少 URL 配置"
                )
            url = await self._arender_template(str(url_template), base_context)
            headers_cfg = request_cfg.get("headers") or {}
            headers: Dict[str, str] = {}
            header_templates: Dict[str, str] = {}

            if isinstance(headers_cfg, dict):
                for key, value in headers_cfg.items():
                    if key:
                        header_templates[str(key)] = str(value)
            elif isinstance(headers_cfg, list):
                for item in headers_cfg:
                    if isinstance(item, dict):
                        key = item.get("key") or item.get("name")
                        value = item.get("value", "")
                        if key:
                            header_templates[str(key)] = str(value)

            if header_templates:
                import asyncio

                header_keys = list(header_templates.keys())
                tasks = [
                    self._arender_template(header_templates[key], base_context)
                    for key in header_keys
                ]
                rendered_values = await asyncio.gather(*tasks)
                headers = dict(zip(header_keys, rendered_values))
            timeout = float(request_cfg.get("timeout", config.get("timeout", 10)) or 10)
            json_payload: Optional[Any] = None
            data_payload: Optional[Any] = None
            content_payload: Optional[Any] = None
            body_cfg = request_cfg.get("body")
            if body_cfg is not None:
                if isinstance(body_cfg, dict) and body_cfg.get("mode"):
                    mode = str(body_cfg.get("mode") or "raw").lower()
                    if mode == "json":
                        rendered_body = await self._arender_structure(
                            body_cfg.get("json", {}), base_context
                        )
                        json_payload = rendered_body
                    elif mode in {"form", "urlencoded"}:
                        rendered_body = await self._arender_structure(
                            body_cfg.get("form", {}), base_context
                        )
                        if isinstance(rendered_body, dict):
                            data_payload = {
                                str(k): "" if v is None else str(v)
                                for k, v in rendered_body.items()
                            }
                    elif mode == "multipart":
                        rendered_body = await self._arender_structure(
                            body_cfg.get("form", {}), base_context
                        )
                        data_payload = rendered_body
                    else:  # 原始文本
                        template_value = (
                            body_cfg.get("text") or body_cfg.get("raw") or ""
                        )
                        content_payload = await self._arender_template(
                            str(template_value), base_context
                        )
                        encoding = body_cfg.get("encoding", "utf-8")
                        if isinstance(content_payload, str):
                            content_payload = content_payload.encode(encoding)
                else:
                    if isinstance(body_cfg, str):
                        rendered_str = await self._arender_template(
                            body_cfg, base_context
                        )
                        content_payload = rendered_str.encode(
                            request_cfg.get("encoding", "utf-8")
                        )
                    else:
                        rendered = await self._arender_structure(body_cfg, base_context)
                        if isinstance(rendered, (dict, list)):
                            json_payload = rendered
                        else:
                            content_payload = str(rendered).encode(
                                request_cfg.get("encoding", "utf-8")
                            )
        except Exception as exc:
            return ActionExecutionResult(
                success=False, error=f"渲染请求模板失败: {exc}"
            )

        response: Optional[httpx.Response] = None
        if not preview:
            try:
                client = await self._get_http_client()
                request_kwargs: Dict[str, Any] = {
                    "method": method,
                    "url": url,
                    "headers": headers or None,
                    "timeout": timeout,
                }
                if json_payload is not None:
                    request_kwargs["json"] = json_payload
                elif data_payload is not None:
                    request_kwargs["data"] = data_payload
                if content_payload is not None:
                    request_kwargs["content"] = content_payload
                response = await client.request(**request_kwargs)
            except Exception as exc:
                return ActionExecutionResult(
                    success=False, error=f"HTTP 请求失败: {exc}"
                )
        else:
            response = None

        extracted = None
        parse_cfg = config.get("parse", {}) or {}
        extractor_cfg = parse_cfg.get("extractor") or config.get("extractor", {}) or {}
        extractor_type = extractor_cfg.get("type", "none").lower()
        expr = extractor_cfg.get("expression")
        if extractor_type != "none" and expr:
            try:
                extracted = await self._aapply_extractor(extractor_type, expr, response)
            except Exception as exc:
                return ActionExecutionResult(
                    success=False, error=f"解析返回体失败: {exc}"
                )

        combined_variables: Dict[str, Any] = dict(runtime.variables)
        render_context = self._build_template_context(
            action=action,
            button=button,
            menu=menu,
            runtime=runtime,
            response=response,
            extracted=extracted,
            variables=combined_variables,
        )
        variables_cfg = parse_cfg.get("variables", [])
        if isinstance(variables_cfg, list):
            import asyncio
            from typing import Coroutine

            tasks: Dict[str, Coroutine[Any, Any, Any]] = {}
            # First pass: handle static/runtime vars and collect async tasks
            for var_entry in variables_cfg:
                if not isinstance(var_entry, dict):
                    continue
                name = var_entry.get("name")
                if not name:
                    continue
                vtype = str(var_entry.get("type", "template")).lower()
                try:
                    if vtype == "template":
                        tasks[name] = self._arender_template(
                            str(var_entry.get("template", "")), render_context
                        )
                    elif vtype in {"jmespath", "jsonpath"}:
                        expr = var_entry.get("expression", "")
                        if expr:
                            tasks[name] = self._aapply_extractor(vtype, expr, response)
                    elif vtype == "static":
                        combined_variables[name] = var_entry.get("value")
                    elif vtype == "runtime":
                        combined_variables[name] = runtime.variables.get(
                            var_entry.get("key")
                        )
                except Exception as exc:
                    self._logger.error(
                        f"准备解析变量 {name} 失败: {exc}", exc_info=True
                    )

            # Second pass: run all async tasks concurrently
            if tasks:
                var_names = list(tasks.keys())
                task_list = list(tasks.values())
                # Use return_exceptions=True to prevent one failure from stopping all
                results = await asyncio.gather(*task_list, return_exceptions=True)
                for name, result in zip(var_names, results):
                    if not isinstance(result, Exception):
                        combined_variables[name] = result
                    else:
                        # Log the type of the failed task for better debugging
                        failed_vtype = "unknown"
                        for var_entry in variables_cfg:
                            if var_entry.get("name") == name:
                                failed_vtype = var_entry.get("type", "unknown")
                                break
                        self._logger.error(
                            f"解析变量 '{name}' (类型: {failed_vtype}) 失败: {result}",
                            exc_info=False,
                        )
        render_context = self._build_template_context(
            action=action,
            button=button,
            menu=menu,
            runtime=runtime,
            response=response,
            extracted=extracted,
            variables=combined_variables,
        )

        render_cfg = config.get("render", {}) or {}
        message_cfg = render_cfg.get("message")
        if isinstance(message_cfg, dict):
            template_str = message_cfg.get("template", "")
            parse_mode_alias = str(message_cfg.get("format", "html")).lower()
            should_edit = bool(message_cfg.get("update_message", True))
            next_menu_id = message_cfg.get(
                "next_menu_id", render_cfg.get("next_menu_id")
            )
        else:
            template_str = render_cfg.get("template", "")
            parse_mode_alias = str(render_cfg.get("format", "html")).lower()
            should_edit = bool(render_cfg.get("update_message", True))
            next_menu_id = render_cfg.get("next_menu_id")
        parse_mode = self._map_parse_mode(parse_mode_alias)
        button_title_template = render_cfg.get("button_title_template")
        overrides_cfg: List[Dict[str, Any]] = []
        if isinstance(message_cfg, dict) and message_cfg.get("button_overrides"):
            overrides_cfg.extend(message_cfg.get("button_overrides") or [])
        if render_cfg.get("button_overrides"):
            overrides_cfg.extend(render_cfg.get("button_overrides") or [])

        result_text = ""
        if template_str:
            try:
                result_text = await self._arender_template(template_str, render_context)
            except Exception as exc:
                return ActionExecutionResult(
                    success=False, error=f"渲染返回模板失败: {exc}"
                )

        overrides = await self._arender_button_overrides(overrides_cfg, render_context)

        if button_title_template:
            try:
                rendered_title = await self._arender_template(
                    button_title_template, render_context
                )
                overrides.append(
                    {"target": "self", "text": rendered_title, "temporary": True}
                )
            except Exception as exc:
                return ActionExecutionResult(
                    success=False, error=f"渲染按钮标题失败: {exc}"
                )

        overrides_self_text = next(
            (
                item.get("text")
                for item in overrides
                if item.get("target") in {"self", button.get("id")}
            ),
            None,
        )

        return ActionExecutionResult(
            success=True,
            should_edit_message=should_edit and bool(result_text),
            new_text=result_text or None,
            parse_mode=parse_mode,
            next_menu_id=next_menu_id,
            data={
                "extracted": extracted,
                "response_status": response.status_code if response else None,
                "variables": combined_variables,
            },
            button_title=overrides_self_text,
            button_overrides=overrides,
        )

    def _map_parse_mode(self, alias: str) -> Optional[str]:
        if alias in {"markdown", "md"}:
            return "Markdown"
        if alias in {"markdownv2", "mdv2"}:
            return "MarkdownV2"
        if alias == "html":
            return "HTML"
        return None

    async def _aapply_extractor(
        self, extractor_type: str, expression: str, response: Optional[httpx.Response]
    ) -> Any:
        import asyncio
        import functools

        if extractor_type == "template":
            render_context = {"response": None}
            if response is not None:
                try:
                    # response.json() is sync, run in thread
                    json_data = await asyncio.to_thread(response.json)
                    render_context["response"] = {
                        "json": json_data,
                        "text": response.text,
                        "headers": dict(response.headers),
                        "status_code": response.status_code,
                    }
                except Exception:
                    render_context["response"] = {
                        "json": None,
                        "text": response.text,
                        "headers": dict(response.headers),
                        "status_code": response.status_code,
                    }
            template = self._template_env.from_string(expression)
            # template.render() is sync, run in thread
            func_to_run = functools.partial(template.render, **render_context)
            return await asyncio.to_thread(func_to_run)

        if response is None:
            raise RuntimeError("预览模式下无法执行该解析器，需要实际响应数据")

        try:
            # response.json() is sync, run in thread
            payload = await asyncio.to_thread(response.json)
        except Exception as exc:
            raise RuntimeError(f"响应非 JSON，无法解析: {exc}") from exc

        if extractor_type == "jmespath":
            if not jmespath:
                raise RuntimeError("未安装 jmespath 库，无法使用 jmespath 解析器")
            # jmespath.search is sync, run in thread
            return await asyncio.to_thread(jmespath.search, expression, payload)

        if extractor_type == "jsonpath":
            if not jsonpath_parse:
                raise RuntimeError("未安装 jsonpath-ng 库，无法使用 jsonpath 解析器")

            # jsonpath logic is sync, run in thread
            def run_jsonpath():
                jsonpath_expr = jsonpath_parse(expression)
                matches = [match.value for match in jsonpath_expr.find(payload)]
                return matches[0] if matches else None

            return await asyncio.to_thread(run_jsonpath)

        raise RuntimeError(f"不支持的解析器类型: {extractor_type}")
