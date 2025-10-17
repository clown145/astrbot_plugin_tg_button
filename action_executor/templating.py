"""Asynchronous templating support for action execution."""
from __future__ import annotations

import asyncio
import functools
import json
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from urllib.parse import quote_plus

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

if TYPE_CHECKING:  # pragma: no cover - optional dependency hints
    import httpx


class TemplateEngine:
    """Utility wrapper around a sandboxed Jinja2 environment."""

    def __init__(self, *, logger) -> None:
        self._logger = logger
        self._environment = SandboxedEnvironment(
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )
        self._environment.filters["tojson"] = lambda value: json.dumps(
            value, ensure_ascii=False
        )
        self._environment.filters["urlencode"] = lambda value: quote_plus(str(value))
        self._environment.filters["zip"] = zip

    @property
    def environment(self) -> SandboxedEnvironment:
        """Expose the underlying Jinja2 environment."""

        return self._environment

    def build_context(
        self,
        *,
        action: Dict[str, Any],
        button: Dict[str, Any],
        menu: Dict[str, Any],
        runtime: Any,
        variables: Optional[Dict[str, Any]] = None,
        response: Optional["httpx.Response"] = None,
        extracted: Any = None,
    ) -> Dict[str, Any]:
        """Create the standard templating context shared across executors."""

        response_payload: Dict[str, Any] = {}
        if response is not None:
            response_payload = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "text": response.text,
            }
            try:
                response_payload["json"] = response.json()
            except Exception:
                response_payload["json"] = None

        runtime_dict = runtime if isinstance(runtime, dict) else dict(runtime.__dict__)
        context = {
            "action": action,
            "button": button,
            "menu": menu,
            "runtime": runtime_dict,
            "response": response_payload,
            "extracted": extracted,
            "variables": variables or {},
        }
        return context

    async def render_template(self, template_str: str, context: Dict[str, Any]) -> str:
        """Render a template string asynchronously."""

        if not template_str:
            return ""
        template = self._environment.from_string(template_str)
        func_to_run = functools.partial(template.render, **context)
        return await asyncio.to_thread(func_to_run)

    async def render_structure(self, value: Any, context: Dict[str, Any]) -> Any:
        """Recursively render a templated structure (dict/list/str)."""

        if isinstance(value, str):
            return await self.render_template(value, context)
        if isinstance(value, list):
            tasks = [self.render_structure(item, context) for item in value]
            return await asyncio.gather(*tasks)
        if isinstance(value, dict):
            keys = list(value.keys())
            tasks = [self.render_structure(value[key], context) for key in keys]
            rendered = await asyncio.gather(*tasks)
            return dict(zip(keys, rendered))
        return value

    async def render_button_overrides(
        self, overrides_cfg: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Render button override definitions using the provided context."""

        rendered_overrides: List[Dict[str, Any]] = []
        for entry in overrides_cfg or []:
            if not isinstance(entry, dict):
                continue

            try:
                templates: Dict[str, str] = {}
                field_templates = {
                    "text": entry.get("text_template"),
                    "callback_data": entry.get("callback_template"),
                    "url": entry.get("url_template"),
                    "switch_inline_query": entry.get(
                        "switch_inline_query_template"
                    ),
                    "switch_inline_query_current_chat": entry.get(
                        "switch_inline_query_current_chat_template"
                    ),
                }
                if entry.get("web_app_url_template"):
                    templates["web_app_url"] = str(entry["web_app_url_template"])

                for field, template_value in field_templates.items():
                    if template_value:
                        templates[field] = str(template_value)

                layout_cfg = entry.get("layout")
                if isinstance(layout_cfg, dict):
                    if "row" in layout_cfg:
                        templates["layout_row"] = str(layout_cfg["row"])
                    if "col" in layout_cfg:
                        templates["layout_col"] = str(layout_cfg["col"])

                rendered_parts: Dict[str, Any] = {}
                if templates:
                    keys = list(templates.keys())
                    tasks = [
                        self.render_template(templates[key], context) for key in keys
                    ]
                    values = await asyncio.gather(*tasks, return_exceptions=True)
                    for key, value in zip(keys, values):
                        if isinstance(value, Exception):
                            self._logger.warning(
                                "Failed to render template for override key '%s': %s",
                                key,
                                value,
                            )
                            continue
                        rendered_parts[key] = value

                result: Dict[str, Any] = {
                    "target": entry.get("target", "self"),
                    "temporary": bool(entry.get("temporary", True)),
                }
                result.update(rendered_parts)

                for field in ("type", "action_id", "menu_id", "web_app_id"):
                    if field in entry and entry[field]:
                        result[field] = entry[field]

                for field in ("text", "callback_data", "url"):
                    if field not in result and entry.get(field):
                        result[field] = entry[field]

                layout_result: Dict[str, Any] = {}
                if "layout_row" in result:
                    try:
                        layout_result["row"] = int(result.pop("layout_row"))
                    except (TypeError, ValueError):
                        pass
                if "layout_col" in result:
                    try:
                        layout_result["col"] = int(result.pop("layout_col"))
                    except (TypeError, ValueError):
                        pass
                if layout_result:
                    result["layout"] = layout_result

                rendered_overrides.append(
                    {
                        key: value
                        for key, value in result.items()
                        if value not in (None, "")
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.error("渲染按钮覆盖配置失败: %s", exc, exc_info=True)
        return rendered_overrides
