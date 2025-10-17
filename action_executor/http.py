"""HTTP action execution logic."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx

from .models import ActionExecutionResult, RuntimeContext
from .templating import TemplateEngine
from .utils import map_parse_mode

try:  # Optional dependencies
    import jmespath
except ImportError:  # pragma: no cover - optional dependency
    jmespath = None

try:  # Optional dependencies
    from jsonpath_ng import parse as jsonpath_parse  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    jsonpath_parse = None


class HTTPActionExecutor:
    """Execute HTTP-based actions using templates and extractors."""

    def __init__(
        self,
        *,
        template_engine: TemplateEngine,
        logger,
        http_client_factory: Callable[[], Awaitable[httpx.AsyncClient]],
    ) -> None:
        self._logger = logger
        self._template_engine = template_engine
        self._http_client_factory = http_client_factory

    async def execute(
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

        base_context = self._template_engine.build_context(
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

            url = await self._template_engine.render_template(
                str(url_template), base_context
            )

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
                header_keys = list(header_templates.keys())
                tasks = [
                    self._template_engine.render_template(
                        header_templates[key], base_context
                    )
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
                        rendered_body = await self._template_engine.render_structure(
                            body_cfg.get("json", {}), base_context
                        )
                        json_payload = rendered_body
                    elif mode in {"form", "urlencoded"}:
                        rendered_body = await self._template_engine.render_structure(
                            body_cfg.get("form", {}), base_context
                        )
                        if isinstance(rendered_body, dict):
                            data_payload = {
                                str(k): "" if v is None else str(v)
                                for k, v in rendered_body.items()
                            }
                    elif mode == "multipart":
                        rendered_body = await self._template_engine.render_structure(
                            body_cfg.get("form", {}), base_context
                        )
                        data_payload = rendered_body
                    else:
                        template_value = body_cfg.get("text") or body_cfg.get("raw") or ""
                        content_payload = await self._template_engine.render_template(
                            str(template_value), base_context
                        )
                        encoding = body_cfg.get("encoding", "utf-8")
                        if isinstance(content_payload, str):
                            content_payload = content_payload.encode(encoding)
                else:
                    if isinstance(body_cfg, str):
                        rendered_str = await self._template_engine.render_template(
                            body_cfg, base_context
                        )
                        content_payload = rendered_str.encode(
                            request_cfg.get("encoding", "utf-8")
                        )
                    else:
                        rendered = await self._template_engine.render_structure(
                            body_cfg, base_context
                        )
                        if isinstance(rendered, (dict, list)):
                            json_payload = rendered
                        else:
                            content_payload = str(rendered).encode(
                                request_cfg.get("encoding", "utf-8")
                            )
        except Exception as exc:
            return ActionExecutionResult(success=False, error=f"渲染请求模板失败: {exc}")

        response: Optional[httpx.Response] = None
        if not preview:
            try:
                client = await self._http_client_factory()
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
                return ActionExecutionResult(success=False, error=f"HTTP 请求失败: {exc}")

        extracted = None
        parse_cfg = config.get("parse", {}) or {}
        extractor_cfg = parse_cfg.get("extractor") or config.get("extractor", {}) or {}
        extractor_type = str(extractor_cfg.get("type", "none")).lower()
        expr = extractor_cfg.get("expression")
        if extractor_type != "none" and expr:
            try:
                extracted = await self._apply_extractor(
                    extractor_type, str(expr), response, preview
                )
            except Exception as exc:
                return ActionExecutionResult(success=False, error=f"解析返回体失败: {exc}")

        combined_variables: Dict[str, Any] = dict(runtime.variables)
        render_context = self._template_engine.build_context(
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
            tasks: Dict[str, asyncio.Task[Any]] = {}
            for var_entry in variables_cfg:
                if not isinstance(var_entry, dict):
                    continue
                name = var_entry.get("name")
                if not name:
                    continue
                vtype = str(var_entry.get("type", "template")).lower()
                try:
                    if vtype == "template":
                        tasks[name] = asyncio.create_task(
                            self._template_engine.render_template(
                                str(var_entry.get("template", "")), render_context
                            )
                        )
                    elif vtype in {"jmespath", "jsonpath"}:
                        expr = var_entry.get("expression", "")
                        if expr:
                            tasks[name] = asyncio.create_task(
                                self._apply_extractor(
                                    vtype,
                                    str(expr),
                                    response,
                                    preview,
                                )
                            )
                    elif vtype == "static":
                        combined_variables[name] = var_entry.get("value")
                    elif vtype == "runtime":
                        combined_variables[name] = runtime.variables.get(
                            var_entry.get("key")
                        )
                except Exception as exc:
                    self._logger.error("准备解析变量 %s 失败: %s", name, exc, exc_info=True)

            if tasks:
                var_names = list(tasks.keys())
                task_list = list(tasks.values())
                results = await asyncio.gather(*task_list, return_exceptions=True)
                for name, result in zip(var_names, results):
                    if isinstance(result, Exception):
                        failed_vtype = "unknown"
                        for var_entry in variables_cfg:
                            if var_entry.get("name") == name:
                                failed_vtype = var_entry.get("type", "unknown")
                                break
                        self._logger.error(
                            "解析变量 '%s' (类型: %s) 失败: %s",
                            name,
                            failed_vtype,
                            result,
                            exc_info=False,
                        )
                    else:
                        combined_variables[name] = result

        render_context = self._template_engine.build_context(
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

        parse_mode = map_parse_mode(parse_mode_alias)
        button_title_template = render_cfg.get("button_title_template")
        overrides_cfg: List[Dict[str, Any]] = []
        if isinstance(message_cfg, dict) and message_cfg.get("button_overrides"):
            overrides_cfg.extend(message_cfg.get("button_overrides") or [])
        if render_cfg.get("button_overrides"):
            overrides_cfg.extend(render_cfg.get("button_overrides") or [])

        result_text = ""
        if template_str:
            try:
                result_text = await self._template_engine.render_template(
                    template_str, render_context
                )
            except Exception as exc:
                return ActionExecutionResult(
                    success=False, error=f"渲染返回模板失败: {exc}"
                )

        overrides = await self._template_engine.render_button_overrides(
            overrides_cfg, render_context
        )

        if button_title_template:
            try:
                rendered_title = await self._template_engine.render_template(
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

    async def _apply_extractor(
        self,
        extractor_type: str,
        expression: str,
        response: Optional[httpx.Response],
        preview: bool,
    ) -> Any:
        if extractor_type == "template":
            render_context = {"response": None}
            if response is not None:
                try:
                    json_payload = await asyncio.to_thread(response.json)
                    render_context["response"] = {
                        "json": json_payload,
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
            template = self._template_engine.environment.from_string(expression)
            func_to_run = lambda: template.render(**render_context)
            return await asyncio.to_thread(func_to_run)

        if response is None:
            if preview:
                raise RuntimeError("预览模式下无法执行该解析器，需要实际响应数据")
            raise RuntimeError("解析器需要实际响应数据")

        try:
            payload = await asyncio.to_thread(response.json)
        except Exception as exc:
            raise RuntimeError(f"响应非 JSON，无法解析: {exc}") from exc

        if extractor_type == "jmespath":
            if not jmespath:
                raise RuntimeError("未安装 jmespath 库，无法使用 jmespath 解析器")
            return await asyncio.to_thread(jmespath.search, expression, payload)

        if extractor_type == "jsonpath":
            if not jsonpath_parse:
                raise RuntimeError("未安装 jsonpath-ng 库，无法使用 jsonpath 解析器")

            def run_jsonpath() -> Any:
                jsonpath_expr = jsonpath_parse(expression)
                matches = [match.value for match in jsonpath_expr.find(payload)]
                return matches[0] if matches else None

            return await asyncio.to_thread(run_jsonpath)

        raise RuntimeError(f"不支持的解析器类型: {extractor_type}")
