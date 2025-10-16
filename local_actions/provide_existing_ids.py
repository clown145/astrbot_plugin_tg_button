"""提供当前配置中菜单、按钮、WebApp、本地动作和工作流的 ID 选项。"""

from typing import Any, Dict


ACTION_METADATA = {
    "id": "provide_existing_ids",
    "name": "获取现有 ID",
    "description": "通过下拉菜单选择现有的菜单、按钮、WebApp、本地动作和工作流，并输出它们的 ID。",
    "inputs": [
        {
            "name": "menu_id",
            "type": "string",
            "description": "选择一个已经存在的菜单。",
            "options": [],
            "options_source": "menus",
        },
        {
            "name": "button_id",
            "type": "string",
            "description": "选择一个已经存在的按钮（显示为 菜单名称-按钮标题）。",
            "options": [],
            "options_source": "buttons",
        },
        {
            "name": "web_app_id",
            "type": "string",
            "description": "选择一个已经存在的 WebApp。",
            "options": [],
            "options_source": "web_apps",
        },
        {
            "name": "local_action_id",
            "type": "string",
            "description": "选择一个已经存在的旧版/本地动作。",
            "options": [],
            "options_source": "local_actions",
        },
        {
            "name": "workflow_id",
            "type": "string",
            "description": "选择一个已经存在的工作流。",
            "options": [],
            "options_source": "workflows",
        },
    ],
    "outputs": [
        {
            "name": "menu_id",
            "type": "string",
            "description": "所选菜单的 ID。",
        },
        {
            "name": "button_id",
            "type": "string",
            "description": "所选按钮的 ID。",
        },
        {
            "name": "web_app_id",
            "type": "string",
            "description": "所选 WebApp 的 ID。",
        },
        {
            "name": "local_action_id",
            "type": "string",
            "description": "所选本地动作的 ID。",
        },
        {
            "name": "workflow_id",
            "type": "string",
            "description": "所选工作流的 ID。",
        },
    ],
}


async def execute(
    menu_id: Any = "",
    button_id: Any = "",
    web_app_id: Any = "",
    local_action_id: Any = "",
    workflow_id: Any = "",
) -> Dict[str, str]:
    """简单地返回被选中的 ID，没有额外处理。"""

    def _normalize(value: Any) -> str:
        return "" if value is None else str(value)

    return {
        "menu_id": _normalize(menu_id),
        "button_id": _normalize(button_id),
        "web_app_id": _normalize(web_app_id),
        "local_action_id": _normalize(local_action_id),
        "workflow_id": _normalize(workflow_id),
    }
