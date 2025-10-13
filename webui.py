import asyncio
import json
from typing import Any, Dict, Optional
from pathlib import Path

try:
    from aiohttp import web
except ImportError:  # 可选依赖
    web = None

try:  # 尝试包内导入，兼容直接运行
    from .actions import RuntimeContext  # type: ignore
except ImportError:
    from actions import RuntimeContext  # type: ignore


class WebUIServer:
    """基于 aiohttp 的 WebUI 与 API 服务器。"""

    def __init__(
        self,
        *,
        plugin,
        logger,
        data_store,
        action_executor,
        action_registry,
        modular_action_registry, # 新增
        host: str,
        port: int,
        auth_token: str = "",
    ):
        self._logger = logger
        self._plugin = plugin
        self._store = data_store
        self._executor = action_executor
        self._registry = action_registry
        self._modular_registry = modular_action_registry
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
            path = request.path

            # OPTIONS 请求用于 CORS 预检，应始终允许。
            if request.method == "OPTIONS":
                return self._json_response({"status": "ok"})

            # 任何非 /api/ 开头的路径都被视为页面或静态文件，是公开的。
            # 保护逻辑将由前端 JavaScript 处理。
            if not path.startswith('/api/'):
                return await handler(request)

            # 从这里开始，处理的是 API 请求。
            token = request.headers.get("X-Auth-Token")

            # /api/health 是一个特殊端点，用于登录页面检查令牌有效性。
            if path == '/api/health':
                if token == self._auth_token:
                    return await handler(request) # 令牌正确，返回 {'status': 'ok'} 和 200 状态码
                # 如果令牌错误或缺失，返回 401。登录页面会处理此情况。
                return self._json_response({"error": "unauthorized"}, status=401)

            # 对于所有其他 API 路径，令牌必须有效。
            if token != self._auth_token:
                return self._json_response({"error": "unauthorized"}, status=401)

            # 令牌有效，继续处理 API 请求。
            return await handler(request)
        return middleware_handler

    def _setup_routes(self, app: "web.Application") -> None:
        app.router.add_get("/login", self._handle_login_page)
        app.router.add_get("/api/health", self._handle_health)
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/api/state", self._handle_get_state)
        app.router.add_put("/api/state", self._handle_put_state)
        app.router.add_get("/api/actions/local/available", self._handle_get_local_actions)
        app.router.add_get("/api/actions/modular/available", self._handle_get_modular_actions)
        app.router.add_post("/api/actions/modular/upload", self._handle_upload_modular_action) # 新增上传路由
        app.router.add_get("/api/actions/modular/download/{action_id}", self._handle_download_modular_action) # 新增下载路由
        app.router.add_post("/api/actions/test", self._handle_test_action)
        app.router.add_post("/api/util/ids", self._handle_generate_id)
        app.router.add_get("/api/workflows", self._handle_get_all_workflows)
        app.router.add_get("/api/workflows/{workflow_id}", self._handle_get_workflow)
        app.router.add_put("/api/workflows/{workflow_id}", self._handle_put_workflow)
        app.router.add_delete("/api/workflows/{workflow_id}", self._handle_delete_workflow)
        app.router.add_static("/static/", path=self._webui_dir, name="static")

    async def _handle_health(self, _request: "web.Request") -> "web.Response":
        return self._json_response({"status": "ok"})

    async def _handle_index(self, _request: "web.Request") -> "web.Response":
        index_path = self._webui_dir / "index.html"
        if not index_path.is_file():
            return self._json_response({"error": "WebUI not found"}, status=404)
        return web.Response(text=index_path.read_text("utf-8"), content_type="text/html")

    async def _handle_login_page(self, _request: "web.Request") -> "web.Response":
        login_path = self._webui_dir / "login.html"
        if not login_path.is_file():
            return self._json_response({"error": "Login page not found"}, status=404)
        return web.Response(text=login_path.read_text("utf-8"), content_type="text/html")

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

    async def _handle_get_all_workflows(self, _request: "web.Request") -> "web.Response":
        snapshot = await self._store.get_snapshot()
        workflows_dict = {
            workflow_id: workflow.to_dict()
            for workflow_id, workflow in (snapshot.workflows or {}).items()
        }
        return self._json_response(workflows_dict)

    async def _handle_get_workflow(self, request: "web.Request") -> "web.Response":
        workflow_id = request.match_info.get("workflow_id")
        if not workflow_id:
            return self._json_response({"error": "缺少 workflow_id"}, status=400)

        snapshot = await self._store.get_snapshot()
        workflow = snapshot.workflows.get(workflow_id)

        if not workflow:
            return self._json_response({"error": f"未找到工作流 '{workflow_id}'"}, status=404)

        return self._json_response(workflow.to_dict())

    async def _handle_put_workflow(self, request: "web.Request") -> "web.Response":
        workflow_id = request.match_info.get("workflow_id")
        if not workflow_id:
            return self._json_response({"error": "缺少 workflow_id"}, status=400)

        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("请求体格式错误，应为 JSON 对象。")
        except Exception as exc:
            return self._json_response({"error": f"解析请求失败: {exc}"}, status=400)

        try:
            snapshot = await self._store.get_snapshot()
            new_model_dict = snapshot.to_dict()

            if "workflows" not in new_model_dict or not isinstance(new_model_dict["workflows"], dict):
                new_model_dict["workflows"] = {}

            new_model_dict["workflows"][workflow_id] = payload
            await self._store.replace_with(new_model_dict)
        except Exception as exc:
            self._logger.error(f"写入工作流 '{workflow_id}' 失败: {exc}", exc_info=True)
            return self._json_response({"error": f"写入失败: {exc}"}, status=500)

        return self._json_response({"status": "ok", "id": workflow_id})

    async def _handle_delete_workflow(self, request: "web.Request") -> "web.Response":
        workflow_id = request.match_info.get("workflow_id")
        if not workflow_id:
            return self._json_response({"error": "缺少 workflow_id"}, status=400)

        try:
            snapshot = await self._store.get_snapshot()
            new_model_dict = snapshot.to_dict()

            if "workflows" in new_model_dict and workflow_id in new_model_dict["workflows"]:
                del new_model_dict["workflows"][workflow_id]
                await self._store.replace_with(new_model_dict)
        except Exception as exc:
            self._logger.error(f"删除工作流 '{workflow_id}' 失败: {exc}", exc_info=True)
            return self._json_response({"error": f"删除失败: {exc}"}, status=500)

        return web.Response(status=204, headers=self._cors_headers)


    async def _handle_generate_id(self, request: "web.Request") -> "web.Response":
        try:
            payload = await request.json()
            entity_type = payload.get("type", "button")
        except Exception:
            entity_type = "button"
        new_id = self._store.generate_id(entity_type)
        return self._json_response({"id": new_id})

    async def _handle_get_local_actions(self, _request: "web.Request") -> "web.Response":
        actions = self._registry.get_all()
        formatted_actions = [
            {
                "name": action.name,
                "description": action.description,
                "parameters": action.parameters,
            }
            for action in actions
        ]
        return self._json_response({"actions": formatted_actions})

    async def _handle_get_modular_actions(self, _request: "web.Request") -> "web.Response":
        actions = self._modular_registry.get_all()
        formatted_actions = [
            {
                "id": action.id,
                "name": action.name,
                "description": action.description,
                "inputs": action.inputs,
                "outputs": action.outputs,
                "filename": action.source_file.name,
            }
            for action in actions
        ]
        return self._json_response({"actions": formatted_actions})

    async def _handle_download_modular_action(self, request: "web.Request") -> "web.Response":
        """处理模块化动作 .py 文件的下载请求。"""
        action_id = request.match_info.get("action_id")
        if not action_id:
            return self._json_response({"error": "缺少 action_id"}, status=400)

        action = self._modular_registry.get(action_id)
        if not action or not action.source_file.is_file():
            return self._json_response({"error": f"未找到 ID 为 '{action_id}' 的动作文件"}, status=404)

        try:
            return web.Response(
                body=action.source_file.read_bytes(),
                content_type="text/plain",
                headers={
                    "Content-Disposition": f'attachment; filename="{action.source_file.name}"',
                    **self._cors_headers,
                },
            )
        except Exception as exc:
            self._logger.error(f"读取动作文件 {action.source_file} 失败: {exc}", exc_info=True)
            return self._json_response({"error": f"读取文件失败: {exc}"}, status=500)

    async def _handle_upload_modular_action(self, request: "web.Request") -> "web.Response":
        """处理上传新的模块化动作 .py 文件。"""
        try:
            payload = await request.json()
            filename = payload.get("filename")
            content = payload.get("content")

            if not filename or not isinstance(filename, str) or not content or not isinstance(content, str):
                return self._json_response({"error": "请求体缺少 filename 或 content 字段"}, status=400)

            # 安全性：清理文件名以防止路径遍历
            safe_filename = Path(filename).name
            if not safe_filename.endswith(".py"):
                 return self._json_response({"error": "无效的文件类型，只允许上传 .py 文件"}, status=400)

            actions_dir = self._modular_registry._actions_dir
            target_path = actions_dir / safe_filename

            # 写入文件
            target_path.write_text(content, encoding="utf-8")
            self._logger.info(f"新模块化动作文件已保存: {target_path}")

            # 重新加载动作
            await self._modular_registry.scan_and_load_actions()
            self._logger.info("模块化动作已重新加载。")

            return self._json_response({"status": "ok", "filename": safe_filename})

        except Exception as exc:
            self._logger.error(f"上传模块化动作失败: {exc}", exc_info=True)
            return self._json_response({"error": f"上传失败: {exc}"}, status=500)

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
        variables = runtime_payload.get("variables") or {}
        if menu_id and "menu_id" not in variables:
            variables["menu_id"] = menu_id

        runtime = RuntimeContext(
            chat_id=str(runtime_payload.get("chat_id", "0")),
            message_id=runtime_payload.get("message_id"),
            thread_id=runtime_payload.get("thread_id"),
            user_id=runtime_payload.get("user_id"),
            username=runtime_payload.get("username"),
            full_name=runtime_payload.get("full_name"),
            callback_data=runtime_payload.get("callback_data"),
            variables=variables,
        )

        result = await self._executor.execute(
            self._plugin,
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
