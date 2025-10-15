"""等待用户输入的预设动作。"""

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from ..actions import RuntimeContext
    from ..main import DynamicButtonFrameworkPlugin


ACTION_METADATA = {
    "id": "await_user_input",
    "name": "等待用户输入",
    "description": (
        "向触发工作流的用户发送提示消息，并暂停执行直到收到下一条文本输入。"
        "输入内容会以输出端口提供，便于后续节点引用。"
    ),
    "inputs": [
        {
            "name": "prompt",
            "type": "string",
            "description": "等待前发送给用户的提示语。",
            "default": "请发送一段文本作为后续步骤的输入。",
        },
        {
            "name": "timeout",
            "type": "integer",
            "description": "最长等待时间（秒）。",
            "default": 60,
        },
        {
            "name": "allow_empty",
            "type": "boolean",
            "description": "是否允许用户发送空白内容。",
            "default": False,
        },
        {
            "name": "retry_prompt",
            "type": "string",
            "description": "当输入为空且不允许时，回复给用户的提示语。",
        },
        {
            "name": "timeout_message",
            "type": "string",
            "description": "等待超时时发送的提醒，留空则不额外提醒。",
        },
        {
            "name": "delete_prompt",
            "type": "boolean",
            "description": "收到有效输入后是否删除提示消息。",
            "default": False,
        },
        {
            "name": "acknowledge_template",
            "type": "string",
            "description": "收到输入后发送的确认消息，支持 {{ user_input }} 占位符。",
        },
        {
            "name": "store_variable",
            "type": "string",
            "description": "可选：将输入内容写入的全局变量名。",
        },
    ],
    "outputs": [
        {
            "name": "user_text",
            "type": "string",
            "description": "用户刚刚发送的文本。",
        },
        {
            "name": "timed_out",
            "type": "boolean",
            "description": "是否发生了超时。",
        },
        {
            "name": "prompt_message_id",
            "type": "integer",
            "description": "用于提示输入的消息 ID（若有）。",
        },
        {
            "name": "response_message_id",
            "type": "integer",
            "description": "用户回复消息的 ID（若可获取）。",
        },
    ],
}


async def execute(
    plugin: "DynamicButtonFrameworkPlugin",
    runtime: "RuntimeContext",
    prompt: str = "请发送一段文本作为后续步骤的输入。",
    timeout: int = 60,
    allow_empty: bool = False,
    retry_prompt: str = "",
    timeout_message: str = "",
    delete_prompt: bool = False,
    acknowledge_template: str = "",
    store_variable: str = "",
) -> Dict[str, Any]:
    wait_result = await plugin.wait_for_user_input(
        runtime,
        prompt=prompt or "请发送一段文本作为后续步骤的输入。",
        timeout=max(int(timeout or 0), 1),
        allow_empty=bool(allow_empty),
        retry_prompt=retry_prompt or None,
        timeout_message=timeout_message or None,
        delete_prompt=bool(delete_prompt),
        acknowledge_template=acknowledge_template or None,
        acknowledge_behavior="send_message",
        edit_original_message=False,
        clear_original_markup=False,
    )

    user_text = wait_result.get("user_text", "")
    timed_out = bool(wait_result.get("timed_out"))
    prompt_message_id = wait_result.get("prompt_message_id")
    response_message_id = wait_result.get("response_message_id")

    variables_payload: Dict[str, Any] = {
        "user_text": user_text,
        "timed_out": timed_out,
        "prompt_message_id": prompt_message_id,
        "response_message_id": response_message_id,
    }

    variable_key = (store_variable or "").strip()
    if variable_key and user_text and not timed_out:
        variables_payload[variable_key] = user_text

    return {
        "user_text": user_text,
        "timed_out": timed_out,
        "prompt_message_id": prompt_message_id,
        "response_message_id": response_message_id,
        "acknowledged": bool(wait_result.get("acknowledged")),
        "variables": variables_payload,
    }
