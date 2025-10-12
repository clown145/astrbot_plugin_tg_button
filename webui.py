import asyncio
import json
from typing import Any, Dict, Optional
from pathlib import Path

try:
    from aiohttp import web
except ImportError:  # pragma: no cover - optional dependency
    web = None

try:  # 尝试包内导入，兼容直接运行
    from .actions import RuntimeContext  # type: ignore
except ImportError:  # pragma: no cover
    from actions import RuntimeContext  # type: ignore


class WebUIServer:
    """aiohttp based WebUI and API server."""

    def __init__(
        self,
        *,
        logger,
        data_store,
        action_executor,
        host: str,
        port: int,
        auth_token: str = "",
    ):
        self._logger = logger
        self._store = data_store
        self._executor = action_executor
        self._host = host
        self._port = port
        self._auth_token = auth_token.strip()
        self._runner: Optional["web.AppRunner"] = None
        self._site: Optional["web.TCPSite"] = None
        self._app: Optional["web.Application"] = None
        self._lock = asyncio.Lock()
        self._webui_dir = Path(__file__).parent / "webui_assets"
        self._cors_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type, X-Auth-Token",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        }

    @property
    def is_supported(self) -> bool:
        return web is not None

    async def start(self) -> None:
        if not self.is_supported:
            raise RuntimeError("未安装 aiohttp，无法启用 WebUI。")
        async with self._lock:
            if self._runner:
                return
            middlewares = [self._auth_middleware] if self._auth_token else []
            self._app = web.Application(middlewares=middlewares)
            self._setup_routes(self._app)
            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self._host, self._port)
            await self._site.start()
            self._logger.info(f"WebUI 已启动: http://{self._host}:{self._port}")

    async def stop(self) -> None:
        async with self._lock:
            if self._site:
                await self._site.stop()
                self._site = None
            if self._runner:
                await self._runner.cleanup()
                self._runner = None
            self._app = None

    async def _auth_middleware(self, app, handler):
        async def middleware_handler(request):
            if request.method == "OPTIONS":
                # For OPTIONS requests, return CORS headers and stop processing.
                return self._json_response({"status": "ok"})

            # The root path and static files are always public
            if request.path == '/' or request.path.startswith('/static/'):
                return await handler(request)

            # For other API paths, check the token
            token = request.headers.get("X-Auth-Token") or request.query.get("token")
            if token != self._auth_token:
                return self._json_response({"error": "unauthorized"}, status=401)

            return await handler(request)
        return middleware_handler

    def _setup_routes(self, app: "web.Application") -> None:
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/api/state", self._handle_get_state)
        app.router.add_put("/api/state", self._handle_put_state)
        app.router.add_post("/api/actions/test", self._handle_test_action)
        app.router.add_post("/api/util/ids", self._handle_generate_id)
        app.router.add_static("/static/", path=self._webui_dir, name="static")

    async def _handle_health(self, _request: "web.Request") -> "web.Response":
        return self._json_response({"status": "ok"})

    async def _handle_index(self, _request: "web.Request") -> "web.Response":
        index_path = self._webui_dir / "index.html"
        if not index_path.is_file():
            return self._json_response({"error": "WebUI not found"}, status=404)
        return web.Response(text=index_path.read_text("utf-8"), content_type="text/html")

    async def _handle_get_state(self, _request: "web.Request") -> "web.Response":
        snapshot = await self._store.get_snapshot()
        return self._json_response(snapshot.to_dict())

    async def _handle_put_state(self, request: "web.Request") -> "web.Response":
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("请求体格式错误，应为 JSON 对象。")
        except Exception as exc:
            return self._json_response({"error": f"解析请求失败: {exc}"}, status=400)
        try:
            snapshot = await self._store.replace_with(payload)
        except Exception as exc:
            self._logger.error(f"写入配置失败: {exc}", exc_info=True)
            return self._json_response({"error": f"写入失败: {exc}"}, status=400)
        return self._json_response(snapshot.to_dict())

    async def _handle_generate_id(self, request: "web.Request") -> "web.Response":
        try:
            payload = await request.json()
            entity_type = payload.get("type", "button")
        except Exception:
            entity_type = "button"
        new_id = self._store.generate_id(entity_type)
        return self._json_response({"id": new_id})

    async def _handle_test_action(self, request: "web.Request") -> "web.Response":
        try:
            payload = await request.json()
        except Exception as exc:
            return self._json_response({"error": f"解析请求失败: {exc}"}, status=400)
        preview = bool(payload.get("preview"))
        snapshot = await self._store.get_snapshot()

        action_payload = payload.get("action")
        action_id = payload.get("action_id")
        action_dict: Optional[Dict[str, Any]] = None
        if action_payload and isinstance(action_payload, dict):
            action_dict = action_payload
        elif action_id:
            action_obj = snapshot.actions.get(action_id)
            if not action_obj:
                return self._json_response({"error": f"未找到动作 {action_id}"}, status=404)
            action_dict = action_obj.to_dict()
        else:
            return self._json_response({"error": "缺少动作定义。"}, status=400)

        button_payload = payload.get("button")
        button_id = payload.get("button_id")
        button_dict: Optional[Dict[str, Any]] = None
        if button_payload and isinstance(button_payload, dict):
            button_dict = button_payload
        elif button_id:
            button_obj = snapshot.buttons.get(button_id)
            if not button_obj:
                return self._json_response({"error": f"未找到按钮 {button_id}"}, status=404)
            button_dict = button_obj.to_dict()
        else:
            button_dict = {"id": "test_button", "text": "测试按钮", "type": "action", "payload": {}}

        menu_payload = payload.get("menu")
        menu_id = payload.get("menu_id")
        menu_dict: Optional[Dict[str, Any]] = None
        if menu_payload and isinstance(menu_payload, dict):
            menu_dict = menu_payload
        elif menu_id:
            menu_obj = snapshot.menus.get(menu_id)
            if not menu_obj:
                return self._json_response({"error": f"未找到菜单 {menu_id}"}, status=404)
            menu_dict = menu_obj.to_dict()
        else:
            menu_dict = {"id": "test_menu", "name": "测试菜单", "items": [button_dict["id"]], "header": "测试"}

        runtime_payload = payload.get("runtime") or {}
        runtime = RuntimeContext(
            chat_id=str(runtime_payload.get("chat_id", "0")),
            message_id=runtime_payload.get("message_id"),
            thread_id=runtime_payload.get("thread_id"),
            user_id=runtime_payload.get("user_id"),
            username=runtime_payload.get("username"),
            full_name=runtime_payload.get("full_name"),
            callback_data=runtime_payload.get("callback_data"),
            variables=runtime_payload.get("variables") or {},
        )

        result = await self._executor.execute(
            action_dict,
            button=button_dict,
            menu=menu_dict,
            runtime=runtime,
            preview=preview,
        )
        return self._json_response(
            {
                "success": result.success,
                "should_edit_message": result.should_edit_message,
                "new_text": result.new_text,
                "parse_mode": result.parse_mode,
                "next_menu_id": result.next_menu_id,
                "error": result.error,
                "data": result.data,
            }
        )

    def _json_response(self, data: Dict[str, Any], status: int = 200) -> "web.Response":
        return web.json_response(data, status=status, headers=self._cors_headers)