"""Facade class for executing actions within the plugin."""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

import httpx

from .http import HTTPActionExecutor
from .local import LocalActionExecutor
from .models import ActionExecutionResult, RuntimeContext
from .modular import ModularActionExecutor
from .templating import TemplateEngine
from .utils import map_parse_mode
from .workflow import WorkflowRunner

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from ..main import ActionRegistry, DynamicButtonFrameworkPlugin, ModularActionRegistry


class ActionExecutor:
    """Coordinate the different execution strategies for actions."""

    def __init__(
        self,
        *,
        logger,
        registry: "ActionRegistry",
        modular_registry: "ModularActionRegistry",
    ) -> None:
        self._logger = logger
        self._registry = registry
        self._modular_registry = modular_registry

        self._template_engine = TemplateEngine(logger=logger)
        self._http_client: Optional[httpx.AsyncClient] = None

        self._http_executor = HTTPActionExecutor(
            template_engine=self._template_engine,
            logger=logger,
            http_client_factory=self._get_http_client,
        )
        self._local_executor = LocalActionExecutor(
            registry=registry,
            template_engine=self._template_engine,
            logger=logger,
        )
        self._modular_executor = ModularActionExecutor(logger=logger)
        self._workflow_runner = WorkflowRunner(
            logger=logger,
            modular_registry=modular_registry,
            template_engine=self._template_engine,
            http_executor=self._http_executor,
            local_executor=self._local_executor,
            modular_executor=self._modular_executor,
        )

    async def close(self) -> None:
        """Release any shared resources (e.g., HTTP clients)."""

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
            return await self._http_executor.execute(
                action,
                button=button,
                menu=menu,
                runtime=runtime,
                preview=preview,
            )

        if kind == "local":
            return await self._local_executor.execute(
                plugin,
                action,
                button=button,
                menu=menu,
                runtime=runtime,
                preview=preview,
            )

        if kind == "workflow":
            return await self._workflow_runner.run(
                plugin,
                action,
                button=button,
                menu=menu,
                runtime=runtime,
                preview=preview,
            )

        if kind == "modular":
            config = action.get("config", {}) or {}
            action_id = config.get("action_id") or action.get("id")
            modular_action = self._modular_registry.get(action_id) if action_id else None
            if not modular_action:
                return ActionExecutionResult(
                    success=False, error=f"未知的模块化动作 ID: {action_id}"
                )

            base_context = self._template_engine.build_context(
                action=action,
                button=button,
                menu=menu,
                runtime=runtime,
                variables=runtime.variables,
            )
            try:
                rendered_inputs = await self._template_engine.render_structure(
                    config.get("inputs", {}) or {},
                    base_context,
                )
                if not isinstance(rendered_inputs, dict):
                    rendered_inputs = {}
            except Exception as exc:
                return ActionExecutionResult(
                    success=False, error=f"渲染模块化动作输入失败: {exc}"
                )

            return await self._modular_executor.execute(
                plugin,
                modular_action,
                runtime=runtime,
                preview=preview,
                input_params=rendered_inputs,
            )

        return ActionExecutionResult(success=False, error=f"未知的动作类型: {kind}")

    async def _get_http_client(self) -> httpx.AsyncClient:
        if not self._http_client:
            self._http_client = httpx.AsyncClient(http2=False, follow_redirects=True)
        return self._http_client

    # Convenience accessors for compatibility ---------------------------------
    @staticmethod
    def map_parse_mode(alias: Any) -> Optional[str]:
        """Delegate to the shared parse mode mapper (primarily for tests)."""

        return map_parse_mode(alias)
