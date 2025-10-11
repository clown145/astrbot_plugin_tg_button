import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx
from jinja2 import Environment, StrictUndefined

try:
    import jmespath
except ImportError:  # pragma: no cover - optional dependency
    jmespath = None

try:
    from jsonpath_ng import parse as jsonpath_parse  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    jsonpath_parse = None


@dataclass
class RuntimeContext:
    chat_id: str
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
    web_app_launch: Optional[Dict[str, Any]] = None


class ActionExecutor:
    def __init__(self, *, logger):
        self._logger = logger
        self._template_env = Environment(
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )
        self._template_env.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)
        self._template_env.filters["urlencode"] = lambda value: quote_plus(str(value))
        self._template_env.filters["zip"] = zip
        self._http_client: Optional[httpx.AsyncClient] = None

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def execute(
        self,
        action: Dict[str, Any],
        *,
        button: Dict[str, Any],
        menu: Dict[str, Any],
        runtime: RuntimeContext,
        preview: bool = False,
    ) -> ActionExecutionResult:
        kind = action.get("kind", "http")
        if kind == "http":
            return await self._execute_http(action, button=button, menu=menu, runtime=runtime, preview=preview)
        return ActionExecutionResult(success=False, error=f"未知的动作类型: {kind}")

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

    def _render_template(self, template_str: str, context: Dict[str, Any]) -> str:
        if not template_str:
            return ""
        template = self._template_env.from_string(template_str)
        return template.render(**context)

    def _render_structure(self, value: Any, context: Dict[str, Any]) -> Any:
        if isinstance(value, str):
            return self._render_template(value, context)
        if isinstance(value, list):
            return [self._render_structure(item, context) for item in value]
        if isinstance(value, dict):
            return {key: self._render_structure(val, context) for key, val in value.items()}
        return value

    def _render_button_overrides(
        self, overrides_cfg: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        rendered: List[Dict[str, Any]] = []
        for entry in overrides_cfg or []:
            if not isinstance(entry, dict):
                continue
            target = entry.get("target", "self")
            try:
                result: Dict[str, Any] = {
                    "target": target,
                    "temporary": bool(entry.get("temporary", True)),
                }
                # template-based fields
                template_fields = {
                    "text": entry.get("text_template"),
                    "callback_data": entry.get("callback_template"),
                    "url": entry.get("url_template"),
                    "switch_inline_query": entry.get("switch_inline_query_template"),
                    "switch_inline_query_current_chat": entry.get("switch_inline_query_current_chat_template"),
                }
                for field, template_value in template_fields.items():
                    if template_value:
                        result[field] = self._render_template(str(template_value), context)
                if entry.get("web_app_url_template"):
                    result["web_app_url"] = self._render_template(str(entry["web_app_url_template"]), context)
                # direct passthrough fields
                for field in ("type", "action_id", "menu_id", "web_app_id"):
                    if field in entry and entry[field]:
                        result[field] = entry[field]
                # allow static overrides if template not provided
                for field in ("text", "callback_data", "url"):
                    if field not in result and entry.get(field):
                        result[field] = entry[field]
                layout_cfg = entry.get("layout")
                if isinstance(layout_cfg, dict):
                    rendered_layout: Dict[str, Any] = {}
                    if "row" in layout_cfg:
                        try:
                            rendered_layout["row"] = int(self._render_template(str(layout_cfg["row"]), context))
                        except Exception:
                            pass
                    if "col" in layout_cfg:
                        try:
                            rendered_layout["col"] = int(self._render_template(str(layout_cfg["col"]), context))
                        except Exception:
                            pass
                    if rendered_layout:
                        result["layout"] = rendered_layout
                rendered.append({key: value for key, value in result.items() if value not in (None, "")})
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.error(f"渲染按钮覆盖配置失败: {exc}", exc_info=True)
        return rendered

    async def _get_http_client(self) -> httpx.AsyncClient:
        if not self._http_client:
            self._http_client = httpx.AsyncClient(http2=False)
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
                return ActionExecutionResult(success=False, error="HTTP 动作缺少 URL 配置")
            url = self._render_template(str(url_template), base_context)
            headers_cfg = request_cfg.get("headers") or {}
            headers: Dict[str, str] = {}
            if isinstance(headers_cfg, dict):
                for key, value in headers_cfg.items():
                    if key:
                        headers[str(key)] = self._render_template(str(value), base_context)
            elif isinstance(headers_cfg, list):
                for item in headers_cfg:
                    if isinstance(item, dict):
                        key = item.get("key") or item.get("name")
                        value = item.get("value", "")
                        if key:
                            headers[str(key)] = self._render_template(str(value), base_context)
            timeout = float(request_cfg.get("timeout", config.get("timeout", 10)) or 10)
            json_payload: Optional[Any] = None
            data_payload: Optional[Any] = None
            content_payload: Optional[Any] = None
            body_cfg = request_cfg.get("body")
            if body_cfg is not None:
                if isinstance(body_cfg, dict) and body_cfg.get("mode"):
                    mode = str(body_cfg.get("mode") or "raw").lower()
                    if mode == "json":
                        rendered_body = self._render_structure(body_cfg.get("json", {}), base_context)
                        json_payload = rendered_body
                    elif mode in {"form", "urlencoded"}:
                        rendered_body = self._render_structure(body_cfg.get("form", {}), base_context)
                        if isinstance(rendered_body, dict):
                            data_payload = {str(k): "" if v is None else str(v) for k, v in rendered_body.items()}
                    elif mode == "multipart":
                        rendered_body = self._render_structure(body_cfg.get("form", {}), base_context)
                        data_payload = rendered_body
                    else:  # raw
                        template_value = body_cfg.get("text") or body_cfg.get("raw") or ""
                        content_payload = self._render_template(str(template_value), base_context)
                        encoding = body_cfg.get("encoding", "utf-8")
                        if isinstance(content_payload, str):
                            content_payload = content_payload.encode(encoding)
                else:
                    if isinstance(body_cfg, str):
                        content_payload = self._render_template(body_cfg, base_context).encode(
                            request_cfg.get("encoding", "utf-8")
                        )
                    else:
                        rendered = self._render_structure(body_cfg, base_context)
                        if isinstance(rendered, (dict, list)):
                            json_payload = rendered
                        else:
                            content_payload = str(rendered).encode(request_cfg.get("encoding", "utf-8"))
        except Exception as exc:
            return ActionExecutionResult(success=False, error=f"渲染请求模板失败: {exc}")

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
                return ActionExecutionResult(success=False, error=f"HTTP 请求失败: {exc}")
        else:
            response = None

        extracted = None
        parse_cfg = config.get("parse", {}) or {}
        extractor_cfg = parse_cfg.get("extractor") or config.get("extractor", {}) or {}
        extractor_type = extractor_cfg.get("type", "none").lower()
        expr = extractor_cfg.get("expression")
        if extractor_type != "none" and expr:
            try:
                extracted = self._apply_extractor(extractor_type, expr, response)
            except Exception as exc:
                return ActionExecutionResult(success=False, error=f"解析返回体失败: {exc}")

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
            for var_entry in variables_cfg:
                if not isinstance(var_entry, dict):
                    continue
                name = var_entry.get("name")
                if not name:
                    continue
                vtype = str(var_entry.get("type", "template")).lower()
                try:
                    if vtype == "template":
                        template_str = var_entry.get("template", "")
                        combined_variables[name] = self._render_template(str(template_str), render_context)
                    elif vtype in {"jmespath", "jsonpath"}:
                        expr = var_entry.get("expression", "")
                        if expr:
                            combined_variables[name] = self._apply_extractor(vtype, expr, response)
                    elif vtype == "static":
                        combined_variables[name] = var_entry.get("value")
                    elif vtype == "runtime":
                        combined_variables[name] = runtime.variables.get(var_entry.get("key"))
                except Exception as exc:  # pragma: no cover - defensive logging
                    self._logger.error(f"解析变量 {name} 失败: {exc}", exc_info=True)
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
            next_menu_id = message_cfg.get("next_menu_id", render_cfg.get("next_menu_id"))
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
                result_text = self._render_template(template_str, render_context)
            except Exception as exc:
                return ActionExecutionResult(success=False, error=f"渲染返回模板失败: {exc}")

        overrides = self._render_button_overrides(overrides_cfg, render_context)
        overrides_self_text = next(
            (item.get("text") for item in overrides if item.get("target") in {"self", button.get("id")}),
            None,
        )
        if button_title_template:
            try:
                rendered_title = self._render_template(button_title_template, render_context)
                overrides.append({"target": "self", "text": rendered_title, "temporary": True})
                overrides_self_text = rendered_title
            except Exception as exc:
                return ActionExecutionResult(success=False, error=f"渲染按钮标题失败: {exc}")

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

    def _apply_extractor(self, extractor_type: str, expression: str, response: Optional[httpx.Response]) -> Any:
        if extractor_type == "template":
            render_context = {"response": None}
            if response is not None:
                try:
                    render_context["response"] = {
                        "json": response.json(),
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
            return template.render(**render_context)

        if response is None:
            raise RuntimeError("预览模式下无法执行该解析器，需要实际响应数据")

        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(f"响应非 JSON，无法解析: {exc}") from exc

        if extractor_type == "jmespath":
            if not jmespath:
                raise RuntimeError("未安装 jmespath 库，无法使用 jmespath 解析器")
            return jmespath.search(expression, payload)
        if extractor_type == "jsonpath":
            if not jsonpath_parse:
                raise RuntimeError("未安装 jsonpath-ng 库，无法使用 jsonpath 解析器")
            jsonpath_expr = jsonpath_parse(expression)
            matches = [match.value for match in jsonpath_expr.find(payload)]
            return matches[0] if matches else None
        raise RuntimeError(f"不支持的解析器类型: {extractor_type}")
