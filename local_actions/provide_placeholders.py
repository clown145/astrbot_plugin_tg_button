from typing import Dict

# --- 动作元数据 ---
ACTION_METADATA = {
    "id": "provide_placeholders",
    "name": "提供占位符 (Provide Placeholders)",
    "description": "提供常用的运行时变量占位符模板，方便连接到其他动作的输入，无需手动记忆和输入。",
    "inputs": [],
    "outputs": [
        {
            "name": "chat_id_placeholder",
            "type": "string",
            "description": "【占位符】当前聊天的唯一ID。用于需要指定聊天窗口的操作（如发送消息）。",
        },
        {
            "name": "user_id_placeholder",
            "type": "string",
            "description": "【占位符】触发此工作流的用户的唯一ID。",
        },
        {
            "name": "message_id_placeholder",
            "type": "string",
            "description": "【占位符】触发此工作流的原始消息的唯一ID。可用于回复或编辑该消息。",
        },
        {
            "name": "username_placeholder",
            "type": "string",
            "description": "【占位符】触发用户的用户名（例如 @username），如果用户未设置则可能为空。",
        },
        {
            "name": "full_name_placeholder",
            "type": "string",
            "description": "【占位符】触发用户的全名。",
        },
        {
            "name": "callback_data_placeholder",
            "type": "string",
            "description": "【占位符】触发此工作流的按钮所包含的回调数据。",
        },
        {
            "name": "menu_id_placeholder",
            "type": "string",
            "description": "【占位符】当前菜单的ID。",
        },
        {
            "name": "menu_name_placeholder",
            "type": "string",
            "description": "【占位符】当前菜单的名称。",
        },
    ],
}


# --- 动作执行逻辑 ---
async def execute() -> Dict[str, str]:
    """
    此动作不执行复杂逻辑，仅返回一个包含所有预定义占位符模板字符串的字典。
    工作流引擎会在后续步骤中渲染这些模板。
    """
    return {
        "chat_id_placeholder": "{{ runtime.chat_id }}",
        "user_id_placeholder": "{{ runtime.user_id }}",
        "message_id_placeholder": "{{ runtime.message_id }}",
        "username_placeholder": "{{ runtime.username }}",
        "full_name_placeholder": "{{ runtime.full_name }}",
        "callback_data_placeholder": "{{ runtime.callback_data }}",
        "menu_id_placeholder": "{{ runtime.variables.menu_id }}",
        "menu_name_placeholder": "{{ runtime.variables.menu_name }}",
    }
