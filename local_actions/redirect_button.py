"""将当前按钮临时重定向到另一个既有按钮的预设动作。"""

from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ..main import DynamicButtonFrameworkPlugin
    from ..actions import RuntimeContext


ACTION_METADATA = {
    "id": "redirect_trigger_button",
    "name": "按钮重定向",
    "description": (
        "临时把当前按钮替换为另一个既有按钮的行为，可用于把一次点击引导到"
        "另一套菜单或工作流。"
    ),
    "inputs": [
        {
            "name": "target_button_id",
            "type": "button",
            "required": True,
            "description": "选择一个现有按钮，当前按钮会暂时继承它的行为。",
        },
        {
            "name": "reuse_target_text",
            "type": "boolean",
            "default": True,
            "description": "同步目标按钮的文案，保持用户体验一致。",
        },
        {
            "name": "custom_text",
            "type": "string",
            "description": "可选：填写后会覆盖上面的文案同步逻辑。",
            "placeholder": "例如：返回主菜单",
        },
        {
            "name": "locate_target_menu",
            "type": "boolean",
            "default": False,
            "description": "若启用，回调时会将上下文定位到目标按钮所在菜单。",
        },
    ],
    "outputs": [],
}


def _ensure_str(value: Any) -> str:
    return str(value) if value is not None else ""


def _build_raw_callback(prefix: str, suffix: str) -> str:
    return f"{prefix}{suffix}" if suffix else prefix


async def execute(
    plugin: "DynamicButtonFrameworkPlugin",
    target_button_id: str,
    reuse_target_text: bool = True,
    custom_text: Optional[str] = None,
    locate_target_menu: bool = False,
    runtime: Optional["RuntimeContext"] = None,
) -> Dict[str, Any]:
    target_id = (target_button_id or "").strip()
    if not target_id:
        raise ValueError("必须先选择要重定向到的目标按钮。")

    snapshot = await plugin.button_store.get_snapshot()
    target_button = snapshot.buttons.get(target_id)
    if not target_button:
        raise ValueError(f"未找到 ID 为 '{target_id}' 的按钮，可能已被删除。")

    origin_button_id = ""
    origin_menu_id = ""
    if runtime and runtime.variables:
        origin_button_id = str(
            runtime.variables.get("button_id")
            or runtime.variables.get("redirect_original_button_id")
            or ""
        )
        origin_menu_id = str(
            runtime.variables.get("menu_id")
            or runtime.variables.get("redirect_original_menu_id")
            or ""
        )

    payload = target_button.payload or {}
    override: Dict[str, Any] = {"target": "self", "temporary": True}

    desired_text = (custom_text or "").strip()
    if desired_text:
        override["text"] = desired_text
    elif reuse_target_text and target_button.text:
        override["text"] = target_button.text

    btn_type = (target_button.type or "command").lower()

    if btn_type == "url":
        url = payload.get("url")
        if not url:
            raise ValueError("目标按钮缺少 URL，无法进行重定向。")
        override["type"] = "url"
        override["url"] = url
    elif btn_type == "web_app":
        override["type"] = "web_app"
        web_app_id = payload.get("web_app_id")
        if web_app_id:
            override["web_app_id"] = web_app_id
        web_app_url = payload.get("url")
        if web_app_url:
            override["web_app_url"] = web_app_url
        if not web_app_id and not web_app_url:
            raise ValueError("目标 WebApp 按钮缺少可用的 URL 或 WebApp ID。")
    elif btn_type == "submenu":
        menu_id = payload.get("menu_id")
        if not menu_id:
            raise ValueError("目标子菜单按钮缺少 menu_id。")
        override["type"] = "submenu"
        override["menu_id"] = menu_id
    elif btn_type == "inline_query":
        override["type"] = "inline_query"
        override["query"] = _ensure_str(payload.get("query"))
    elif btn_type == "switch_inline_query":
        override["type"] = "switch_inline_query"
        override["query"] = _ensure_str(payload.get("query"))
    elif btn_type == "raw":
        callback_data = payload.get("callback_data")
        if not callback_data:
            raise ValueError("目标原始回调按钮缺少 callback_data。")
        override["raw_callback_data"] = _ensure_str(callback_data)
    elif btn_type == "back":
        target_menu = payload.get("menu_id") or payload.get("target_menu")
        if not target_menu:
            raise ValueError("目标返回按钮缺少要回退的菜单 ID。")
        override["raw_callback_data"] = _build_raw_callback(
            plugin.CALLBACK_PREFIX_BACK, _ensure_str(target_menu)
        )
    elif btn_type == "command":
        override["raw_callback_data"] = _build_raw_callback(
            plugin.CALLBACK_PREFIX_COMMAND, target_button.id
        )
    elif btn_type == "action":
        override["raw_callback_data"] = _build_raw_callback(
            plugin.CALLBACK_PREFIX_ACTION, target_button.id
        )
    elif btn_type == "workflow":
        override["raw_callback_data"] = _build_raw_callback(
            plugin.CALLBACK_PREFIX_WORKFLOW, target_button.id
        )
    else:
        # 兜底：直接复用原按钮的回调数据，如果存在的话；否则仍按照命令处理。
        callback_data = payload.get("callback_data")
        if callback_data:
            override["raw_callback_data"] = _ensure_str(callback_data)
        else:
            override["raw_callback_data"] = _build_raw_callback(
                plugin.CALLBACK_PREFIX_COMMAND, target_button.id
            )

    if override.get("raw_callback_data"):
        wrapped_button_id = origin_button_id or target_button.id
        wrapped_menu_id = origin_menu_id or ""
        flag = "1" if locate_target_menu else "0"
        override["raw_callback_data"] = (
            f"{plugin.CALLBACK_PREFIX_REDIRECT}"
            f"{wrapped_button_id}:{wrapped_menu_id}:{flag}:"
            f"{override['raw_callback_data']}"
        )

    return {"button_overrides": [override]}
